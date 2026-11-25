"""Model backends for the analysis service (AI1): something that turns chat messages into text.

    stub          the deterministic stub (app.analysis.stub), no model; CI and runbook step 1
    openai_http   any OpenAI-compatible chat endpoint: Ollama on a laptop (site "local") or the
                  faculty cluster's model service through its SSH tunnel (site "hpc")
    hpc_batch     C1's Slurm batch handoff (app/hpc/batch.py, ICD_HPC_* variables there)
    replay        recorded real-model answers for the demo (app/analysis/replay.py, task 31)

The platform picks one from environment variables (`generator_from_env`, runbook section 2):

    ICD_ANALYSIS_BACKEND   stub (default) | openai_http | hpc_batch | replay
    ICD_REPLAY_FILES       replay only: comma-separated recordings (default: replay_data/)
    ICD_LLM_ENDPOINT       for example http://127.0.0.1:11434/v1/chat/completions
    ICD_LLM_MODEL          the served model name, for example qwen3.8-27b-awq-int4
    ICD_LLM_REVISION       optional weights commit; the model pin becomes <model>@<revision>
    ICD_LLM_SITE           local (default) | hpc   -> AnalysisReport.generated_by
    ICD_LLM_API_KEY        optional bearer key (the cluster's); read here, never stored or logged
    ICD_LLM_TIMEOUT_SECONDS  default 600
    ICD_LLM_MAX_TOKENS     default 4900
    ICD_LLM_NO_THINKING    1 = ask Qwen3-style servers to answer without thinking
    ICD_LLM_JSON_SCHEMA    1 = send the output schema as response_format (not on the cluster)

No new dependency: the HTTP call uses the standard library.
"""

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from app.analysis.output import LlmOutput
from app.contracts import EvidencePackage

Site = Literal["mock", "hpc", "local"]


class BackendError(Exception):
    """The backend gave no answer (network, timeout, server error, malformed response)."""


@dataclass(frozen=True)
class Generation:
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class Generator(Protocol):
    generated_by: Site
    model_id: str

    def generate(self, messages: list[dict[str, str]], evidence: EvidencePackage) -> Generation: ...


class OpenAIHttpGenerator:
    """POST /v1/chat/completions. Temperature 0 by default, so a run can be repeated."""

    def __init__(
        self,
        endpoint: str,
        model: str,
        *,
        site: Literal["hpc", "local"] = "local",
        revision: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 600,
        max_tokens: int = 4900,
        temperature: float = 0.0,
        no_thinking: bool = False,
        json_schema: bool = False,
    ) -> None:
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("the endpoint must be an http or https URL")
        self.endpoint, self.model = endpoint, model
        self.generated_by: Site = site
        self.model_id = f"{model}@{revision}" if revision else model
        self._api_key = api_key
        self.timeout_seconds, self.max_tokens = timeout_seconds, max_tokens
        self.temperature, self.no_thinking, self.json_schema = temperature, no_thinking, json_schema

    def settings(self) -> dict[str, object]:
        """What the run used, for the record (never the key)."""
        return {
            "endpoint": self.endpoint,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "no_thinking": self.no_thinking,
            "json_schema": self.json_schema,
        }

    def body(self, messages: list[dict[str, str]]) -> dict:
        body: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if self.no_thinking:  # Qwen3-style chat templates (vLLM, SGLang): answer without thinking
            body["chat_template_kwargs"] = {"enable_thinking": False}
        if self.json_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "llm_output_v0", "schema": LlmOutput.model_json_schema()},
            }
        return body

    def generate(self, messages: list[dict[str, str]], evidence: EvidencePackage) -> Generation:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = urllib.request.Request(
            self.endpoint, json.dumps(self.body(messages)).encode("utf-8"), headers
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            raise BackendError(f"HTTP {exc.code} from the model server") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise BackendError(f"model server not reachable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise BackendError("the model server did not answer with JSON") from exc
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendError("no choices[0].message.content in the server answer") from exc
        if not isinstance(text, str) or not text.strip():
            raise BackendError("the model returned an empty answer")
        usage = data.get("usage") or {}
        return Generation(text, usage.get("prompt_tokens"), usage.get("completion_tokens"))


def _flag(env: Mapping[str, str], name: str) -> bool:
    return env.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def generator_from_env(env: Mapping[str, str] | None = None) -> Generator:
    """The backend the environment names (module docstring). Unknown values are an error."""
    env = os.environ if env is None else env
    backend = env.get("ICD_ANALYSIS_BACKEND", "stub").strip() or "stub"
    if backend == "stub":
        from app.analysis.stub import StubGenerator

        return StubGenerator()
    if backend == "openai_http":
        endpoint, model = env.get("ICD_LLM_ENDPOINT"), env.get("ICD_LLM_MODEL")
        if not endpoint or not model:
            raise ValueError("openai_http needs ICD_LLM_ENDPOINT and ICD_LLM_MODEL")
        site = env.get("ICD_LLM_SITE", "local")
        if site not in ("hpc", "local"):
            raise ValueError("ICD_LLM_SITE must be hpc or local")
        return OpenAIHttpGenerator(
            endpoint,
            model,
            site=site,  # type: ignore[arg-type]
            revision=env.get("ICD_LLM_REVISION") or None,
            api_key=env.get("ICD_LLM_API_KEY") or None,
            timeout_seconds=float(env.get("ICD_LLM_TIMEOUT_SECONDS", "600")),
            max_tokens=int(env.get("ICD_LLM_MAX_TOKENS", "4900")),
            no_thinking=_flag(env, "ICD_LLM_NO_THINKING"),
            json_schema=_flag(env, "ICD_LLM_JSON_SCHEMA"),
        )
    if backend == "replay":  # task 31: recorded real-model answers, app/analysis/replay.py
        from app.analysis.replay import generator_from_env as replay_from_env

        return replay_from_env(env)  # type: ignore[return-value]
    if backend == "hpc_batch":  # C1 decision F4: Slurm batch handoff, app/hpc/batch.py
        from app.hpc.batch import HpcBatchConfig, HpcBatchGenerator

        return HpcBatchGenerator(HpcBatchConfig.from_env(env))  # type: ignore[return-value]
    raise ValueError(
        f"unknown ICD_ANALYSIS_BACKEND {backend!r}; use stub, openai_http, hpc_batch or replay"
    )
