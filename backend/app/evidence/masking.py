"""Masking of host, user and IP values before the evidence leaves the app host (T3-07, NFR-S-07).

Tokens are numbered per incident in first-seen order (decision C2-D5): the first IP met is
ip-01, the next new one ip-02, and so on; host-NN and user-NN the same way. The style is the
one the EvidencePackage contract, AI1's prompt and AI1's grounding check already use
(`host-01`, `ip-01`, `user-01`; grounding.MASKED_TOKEN). One value always gets
the same token inside one incident, so the AI can still see that two events share a machine.
Source and destination IPs share the IP numbering.

The map (token -> real value) never leaves the app host. The report is stored masked, as the
model wrote it, and only the API un-masks it for the analyst (C2-D7).
"""

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum

from app.contracts import EvidenceEvent


class TokenKind(StrEnum):
    HOST = "host"
    IP = "ip"
    USER = "user"


# Field of EvidenceEvent -> kind of token that replaces its value.
MASKED_FIELDS: dict[str, TokenKind] = {
    "host": TokenKind.HOST,
    "src_ip": TokenKind.IP,
    "dst_ip": TokenKind.IP,
    "user": TokenKind.USER,
}

TOKEN_PATTERN = re.compile(r"\b(?:host|ip|user)-\d{2,}\b")


class MaskingLeak(Exception):
    """A real host, user or IP value is still in the masked package."""


@dataclass
class MaskingMap:
    """Token -> real value for one incident. Kept on the app host only."""

    incident_id: str
    tokens: dict[str, tuple[TokenKind, str]] = field(default_factory=dict)
    _by_value: dict[tuple[TokenKind, str], str] = field(default_factory=dict, repr=False)

    def token_for(self, kind: TokenKind, value: str) -> str:
        key = (kind, value)
        if key not in self._by_value:
            count = sum(1 for k, _ in self._by_value if k == kind) + 1
            token = f"{kind.value}-{count:02d}"
            self._by_value[key] = token
            self.tokens[token] = key
        return self._by_value[key]

    @classmethod
    def from_tokens(
        cls, incident_id: str, tokens: dict[str, tuple[TokenKind, str]]
    ) -> "MaskingMap":
        """Rebuild a stored map (app/evidence/store.py)."""
        masking_map = cls(incident_id)
        for token, (kind, value) in tokens.items():
            masking_map.tokens[token] = (TokenKind(kind), value)
            masking_map._by_value[(TokenKind(kind), value)] = token
        return masking_map

    def real_values(self) -> set[str]:
        return {value for _, value in self.tokens.values()}

    def unmask(self, text: str) -> str:
        """Put the real values back into a text written with this incident's tokens."""
        return TOKEN_PATTERN.sub(
            lambda m: self.tokens[m.group(0)][1] if m.group(0) in self.tokens else m.group(0),
            text,
        )


@dataclass(frozen=True)
class MaskedPackage:
    """Masked evidence events plus the map that turns them back."""

    events: tuple[EvidenceEvent, ...]
    masking_map: MaskingMap


def mask_events(incident_id: str, events: list[EvidenceEvent]) -> MaskedPackage:
    """Replace host, user and IP values with tokens, in package order."""
    masking_map = MaskingMap(incident_id)
    masked = []
    for event in events:
        changes = {
            name: masking_map.token_for(kind, value)
            for name, kind in MASKED_FIELDS.items()
            if (value := getattr(event, name)) is not None
        }
        masked.append(event.model_copy(update=changes))
    # A summary or source is never meant to hold an entity (docs/ingestion.md, section 6);
    # replace any that slipped in rather than send it.
    by_value = {value: token for token, (_, value) in masking_map.tokens.items()}
    cleaned = []
    for event in masked:
        summary = _replace_values(event.summary, by_value)
        source = _replace_values(event.source, by_value)
        cleaned.append(event.model_copy(update={"summary": summary, "source": source}))
    return MaskedPackage(tuple(cleaned), masking_map)


def _value_pattern(values: list[str]) -> re.Pattern[str]:
    """Whole values only: 10.0.0.1 must not match inside 10.0.0.12 or web-01 inside web-010."""
    alternatives = "|".join(re.escape(v) for v in sorted(values, key=len, reverse=True))
    return re.compile(rf"(?<![\w.:-])(?:{alternatives})(?![\w.:-]*[\w])")


def _replace_values(text: str, by_value: dict[str, str]) -> str:
    if not by_value:
        return text
    return _value_pattern(list(by_value)).sub(lambda m: by_value[m.group(0)], text)


def find_leaks(payload: object, masking_map: MaskingMap) -> list[str]:
    """Kinds of real values found in the serialized payload; empty when it is clean."""
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    return sorted(
        {
            kind.value
            for kind, value in masking_map.tokens.values()
            if _value_pattern([value]).search(text)
        }
    )
