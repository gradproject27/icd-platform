"""Model clients for the LLM opinion: chat messages in, n short answers out.

    stub          deterministic, no model (CI, dry runs): a fixed share of "yes" answers
    openai_http   any OpenAI-compatible chat endpoint, the same server the report uses: the
                  faculty cluster's vLLM service (site "hpc") or Ollama on a laptop ("local")

Chosen by ICD_OPINION_BACKEND (default stub). The openai_http client reads the report backend's
variables (app/analysis/backends.py): ICD_LLM_ENDPOINT, ICD_LLM_MODEL, ICD_LLM_REVISION,
ICD_LLM_SITE, ICD_LLM_API_KEY, ICD_LLM_TIMEOUT_SECONDS, ICD_LLM_NO_THINKING. The key is never
stored or logged.

n samples: vLLM answers `n` choices in one request; a server that ignores `n` (Ollama) returns
one, so the client asks again until it has n. Token probability: with `logprobs`, the client
finds the answer token ("yes" or "no", the first one, since "answer" comes first in the JSON)
and returns P(yes) / (P(yes) + P(no)) over that position's top tokens.
"""

import json
import math
import os
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.analysis.backends import BackendError

Site = Literal["mock", "hpc", "local"]
TOP_LOGPROBS = 10
DEFAULT_MAX_TOKENS = 120
_WORD = re.compile(r"[a-z]+")


@dataclass(frozen=True)
class Sample:
    text: str
    yes_probability: float | None = None  # from token probabilities, when asked and available


class OpinionClient(Protocol):
    generated_by: Site
    model_id: str

    def ask(
        self, messages: list[dict[str, str]], *, n: int, temperature: float, logprobs: bool
    ) -> list[Sample]: ...


def _answer_word(token: str) -> str | None:
    words = _WORD.findall(token.lower())
    return words[0] if len(words) == 1 and words[0] in ("yes", "no") else None


def yes_probability(content: list[dict[str, Any]] | None) -> float | None:
    """P(yes) at the first answer token of one choice's logprobs; None if there is none."""
    for position in content or []:
        if _answer_word(str(position.get("token", ""))) is None:
            continue
        mass = {"yes": 0.0, "no": 0.0}
        candidates = position.get("top_logprobs") or [position]
        for candidate in candidates:
            word = _answer_word(str(candidate.get("token", "")))
            logprob = candidate.get("logprob")
            if word is not None and isinstance(logprob, int | float):
                mass[word] += math.exp(logprob)
        total = mass["yes"] + mass["no"]
        return mass["yes"] / total if total > 0 else None
    return None


class StubOpinionClient:
    """Deterministic: the first round(n * p_yes) answers say yes. Reasons are marked [STUB]."""

    generated_by: Site = "mock"

    def __init__(self, p_yes: float = 0.8, model_id: str = "stub-opinion") -> None:
        if not 0 <= p_yes <= 1:
            raise ValueError("p_yes must be 0 to 1")
        self.p_yes, self.model_id = p_yes, model_id

    def ask(
        self, messages: list[dict[str, str]], *, n: int, temperature: float, logprobs: bool
    ) -> list[Sample]:
        yes = round(n * self.p_yes)
        return [
            Sample(
                json.dumps(
                    {"answer": "yes" if i < yes else "no", "reason": "[STUB] no model was called"}
                ),
                self.p_yes if logprobs else None,
            )
            for i in range(n)
        ]


class OpenAIOpinionClient:
    def __init__(
        self,
        endpoint: str,
        model: str,
        *,
        site: Literal["hpc", "local"] = "local",
        revision: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 120,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        no_thinking: bool = False,
    ) -> None:
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("the endpoint must be an http or https URL")
        self.endpoint, self.model = endpoint, model
        self.generated_by: Site = site
        self.model_id = f"{model}@{revision}" if revision else model
        self._api_key = api_key
        self.timeout_seconds, self.max_tokens, self.no_thinking = (
            timeout_seconds,
            max_tokens,
            no_thinking,
        )

    def body(
        self, messages: list[dict[str, str]], *, n: int, temperature: float, logprobs: bool
    ) -> dict:
        body: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": temperature,
            "n": n,
        }
        if logprobs:
            body["logprobs"] = True
            body["top_logprobs"] = TOP_LOGPROBS
        if self.no_thinking:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        return body

    def _post(self, body: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = urllib.request.Request(self.endpoint, json.dumps(body).encode("utf-8"), headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise BackendError(f"HTTP {exc.code} from the model server") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise BackendError(f"model server not reachable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise BackendError("the model server did not answer with JSON") from exc

    def ask(
        self, messages: list[dict[str, str]], *, n: int, temperature: float, logprobs: bool
    ) -> list[Sample]:
        samples: list[Sample] = []
        for _ in range(n):  # at most n requests, even if the server answers one choice each
            data = self._post(
                self.body(messages, n=n - len(samples), temperature=temperature, logprobs=logprobs)
            )
            choices = data.get("choices")
            if not isinstance(choices, list) or not choices:
                raise BackendError("no choices in the server answer")
            for choice in choices:
                message = choice.get("message") or {}
                text = message.get("content")
                if not isinstance(text, str):
                    text = ""
                content = (choice.get("logprobs") or {}).get("content") if logprobs else None
                samples.append(Sample(text, yes_probability(content) if logprobs else None))
            if len(samples) >= n:
                break
        return samples[:n]


def _flag(env: Mapping[str, str], name: str) -> bool:
    return env.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def client_from_env(env: Mapping[str, str] | None = None) -> OpinionClient:
    env = os.environ if env is None else env
    backend = env.get("ICD_OPINION_BACKEND", "stub").strip() or "stub"
    if backend == "stub":
        return StubOpinionClient()
    if backend == "openai_http":
        endpoint, model = env.get("ICD_LLM_ENDPOINT"), env.get("ICD_LLM_MODEL")
        if not endpoint or not model:
            raise ValueError("openai_http needs ICD_LLM_ENDPOINT and ICD_LLM_MODEL")
        site = env.get("ICD_LLM_SITE", "local")
        if site not in ("hpc", "local"):
            raise ValueError("ICD_LLM_SITE must be hpc or local")
        return OpenAIOpinionClient(
            endpoint,
            model,
            site=site,  # type: ignore[arg-type]
            revision=env.get("ICD_LLM_REVISION") or None,
            api_key=env.get("ICD_LLM_API_KEY") or None,
            timeout_seconds=float(env.get("ICD_LLM_TIMEOUT_SECONDS", "120")),
            no_thinking=_flag(env, "ICD_LLM_NO_THINKING"),
        )
    raise ValueError(f"unknown ICD_OPINION_BACKEND {backend!r}; use stub or openai_http")
