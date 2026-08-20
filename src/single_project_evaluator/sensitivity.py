from __future__ import annotations

import re
from dataclasses import dataclass

from .models import PreparedContext, ProjectEvidence


@dataclass(frozen=True)
class SensitiveMatch:
    source: str
    path: str
    kind: str


SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----", re.IGNORECASE),
    ),
    (
        "bearer_token",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE),
    ),
    (
        "openai_api_key",
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "credential_assignment",
        re.compile(
            r"\b(?:api[_-]?key|secret|token|password|passwd|pwd)\b\s*[:=]\s*[\"']?[A-Za-z0-9._~+/=-]{12,}",
            re.IGNORECASE,
        ),
    ),
)


def find_sensitive_material(evidence: ProjectEvidence, prepared_context: PreparedContext) -> list[SensitiveMatch]:
    matches: list[SensitiveMatch] = []

    for record in evidence.authority_records:
        matches.extend(_scan_text(source=f"authority_record:{record.record_type}", path=record.path, text=record.excerpt))

    for material in prepared_context.governance_materials:
        matches.extend(_scan_text(source=f"governance_material:{material.standard}", path=material.path, text=material.excerpt))

    for snippet in prepared_context.text_snippets:
        matches.extend(_scan_text(source=f"text_snippet:{snippet.role}", path=snippet.path, text=snippet.excerpt))

    return _deduplicate(matches)


def find_sensitive_text(*, source: str, path: str, text: str) -> list[SensitiveMatch]:
    return _deduplicate(_scan_text(source=source, path=path, text=text))


def describe_sensitive_matches(matches: list[SensitiveMatch], limit: int = 8) -> str:
    shown = matches[:limit]
    rendered = ", ".join(f"{match.kind} in {match.path} ({match.source})" for match in shown)
    if len(matches) > limit:
        rendered += f", +{len(matches) - limit} more"
    return rendered


def _scan_text(*, source: str, path: str, text: str) -> list[SensitiveMatch]:
    matches: list[SensitiveMatch] = []
    for kind, pattern in SENSITIVE_PATTERNS:
        if pattern.search(text):
            matches.append(SensitiveMatch(source=source, path=path, kind=kind))
    return matches


def _deduplicate(matches: list[SensitiveMatch]) -> list[SensitiveMatch]:
    deduped: list[SensitiveMatch] = []
    seen: set[tuple[str, str, str]] = set()
    for match in matches:
        key = (match.source, match.path, match.kind)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(match)
    return deduped
