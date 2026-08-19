from __future__ import annotations

import hashlib
from pathlib import Path
from pathlib import PurePosixPath

from .models import (
    ApplicabilityState,
    GovernanceApplicability,
    InventorySummary,
    PreparedContext,
    ProjectContext,
    ProjectEvidence,
    RepresentativeFile,
    SurfaceEvidence,
    SurfaceKind,
    TextSnippet,
)


SOURCE_EXTENSIONS = {
    ".cs": SurfaceKind.DESKTOP_APP,
    ".vb": SurfaceKind.DESKTOP_APP,
    ".xaml": SurfaceKind.DESKTOP_APP,
    ".py": SurfaceKind.COMMAND_TOOL,
    ".rs": SurfaceKind.COMMAND_TOOL,
    ".ts": SurfaceKind.WEBSITE,
    ".tsx": SurfaceKind.WEBSITE,
    ".js": SurfaceKind.WEBSITE,
    ".jsx": SurfaceKind.WEBSITE,
}

SURFACE_STANDARD_HINTS = {
    SurfaceKind.COMMAND_TOOL: "CTS",
    SurfaceKind.DESKTOP_APP: "DRS",
    SurfaceKind.WEBSITE: "WDS",
    SurfaceKind.LIBRARY: "LDS",
    SurfaceKind.SERVICE: "SIS",
    SurfaceKind.DATASET: "DDS",
}

TEXT_SNIPPET_EXTENSIONS = {
    ".cs",
    ".json",
    ".md",
    ".props",
    ".ps1",
    ".py",
    ".rs",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vb",
    ".vbproj",
    ".wxs",
    ".xaml",
    ".yaml",
    ".yml",
}
TEXT_SNIPPET_CHARS = 1200
TEXT_SNIPPET_LIMIT = 18


def prepare_evaluation_context(evidence: ProjectEvidence, context: ProjectContext) -> PreparedContext:
    inventory_summary = summarize_inventory(evidence)
    surfaces = infer_surfaces(evidence)
    governance_applicability = infer_governance_applicability(context, surfaces)
    representative_files = select_representative_files(evidence)
    text_snippets = collect_text_snippets(evidence, representative_files)
    notes = [
        "Surface and governance applicability are heuristic in Phase 1; conformance checks are not implemented yet."
    ]
    return PreparedContext(
        inventory_summary=inventory_summary,
        surfaces=surfaces,
        governance_applicability=governance_applicability,
        representative_files=representative_files,
        text_snippets=text_snippets,
        notes=notes,
    )


def summarize_inventory(evidence: ProjectEvidence) -> InventorySummary:
    role_counts: dict[str, int] = {}
    extension_counts: dict[str, int] = {}
    total_size = 0

    for file in evidence.files:
        role_counts[file.role] = role_counts.get(file.role, 0) + 1
        suffix = PurePosixPath(file.path).suffix.lower() or "[none]"
        extension_counts[suffix] = extension_counts.get(suffix, 0) + 1
        total_size += file.size_bytes

    return InventorySummary(
        role_counts=dict(sorted(role_counts.items())),
        extension_counts=dict(sorted(extension_counts.items(), key=lambda item: (-item[1], item[0]))),
        total_size_bytes=total_size,
    )


def infer_surfaces(evidence: ProjectEvidence) -> list[SurfaceEvidence]:
    evidence_by_surface: dict[SurfaceKind, list[str]] = {}

    for file in evidence.files:
        path = PurePosixPath(file.path)
        suffix = path.suffix.lower()
        if path.name in {"pyproject.toml", "setup.py"}:
            evidence_by_surface.setdefault(SurfaceKind.COMMAND_TOOL, []).append(file.path)
        if path.name in {"package.json", "vite.config.ts", "vite.config.js"}:
            evidence_by_surface.setdefault(SurfaceKind.WEBSITE, []).append(file.path)
        if path.name.endswith((".csproj", ".vbproj")):
            evidence_by_surface.setdefault(SurfaceKind.DESKTOP_APP, []).append(file.path)
        if suffix in SOURCE_EXTENSIONS:
            evidence_by_surface.setdefault(SOURCE_EXTENSIONS[suffix], []).append(file.path)

    surfaces = [
        SurfaceEvidence(
            kind=kind,
            confidence=_confidence(paths),
            evidence=paths[:12],
        )
        for kind, paths in sorted(evidence_by_surface.items(), key=lambda item: item[0].value)
    ]
    return surfaces or [SurfaceEvidence(kind=SurfaceKind.UNKNOWN, confidence="weak", evidence=[])]


def infer_governance_applicability(
    context: ProjectContext,
    surfaces: list[SurfaceEvidence],
) -> list[GovernanceApplicability]:
    records: list[GovernanceApplicability] = []
    standards = _context_governance(context)

    for standard in standards:
        records.append(
            GovernanceApplicability(
                standard=standard,
                state=ApplicabilityState.DEFERRED,
                source=context.applicable_governance.source or context.primary_standard.source or "context",
                rationale="Named by extracted project context; Phase 1 does not yet evaluate conformance.",
            )
        )

    named = {record.standard for record in records}
    for surface in surfaces:
        hinted_standard = SURFACE_STANDARD_HINTS.get(surface.kind)
        if hinted_standard and hinted_standard not in named:
            records.append(
                GovernanceApplicability(
                    standard=hinted_standard,
                    state=ApplicabilityState.DEFERRED,
                    source="surface_heuristic",
                    rationale=f"Inferred from detected {surface.kind.value} surface evidence.",
                )
            )
            named.add(hinted_standard)

    return records


def select_representative_files(evidence: ProjectEvidence, limit: int = 30) -> list[RepresentativeFile]:
    selected: list[RepresentativeFile] = []
    seen: set[str] = set()

    def add(path: str, role: str, size_bytes: int, reason: str) -> None:
        if path in seen or len(selected) >= limit:
            return
        seen.add(path)
        selected.append(
            RepresentativeFile(
                path=path,
                role=role,
                size_bytes=size_bytes,
                reason=reason,
            )
        )

    files_by_path = {file.path: file for file in evidence.files}
    for record in evidence.authority_records:
        file = files_by_path.get(record.path)
        add(
            record.path,
            file.role if file else record.record_type,
            record.size_bytes,
            f"authority record: {record.record_type}",
        )

    for file in evidence.files:
        if file.role == "configuration":
            add(file.path, file.role, file.size_bytes, "configuration evidence")

    for file in evidence.files:
        if file.role == "source":
            add(file.path, file.role, file.size_bytes, "source surface sample")

    for file in evidence.files:
        if file.role == "release_artifact":
            add(file.path, file.role, file.size_bytes, "release artifact sample")

    return selected


def collect_text_snippets(
    evidence: ProjectEvidence,
    representative_files: list[RepresentativeFile],
    limit: int = TEXT_SNIPPET_LIMIT,
) -> list[TextSnippet]:
    snippets: list[TextSnippet] = []
    root = Path(evidence.root)

    for representative in representative_files:
        if len(snippets) >= limit:
            break
        if not _is_text_snippet_candidate(representative.path):
            continue
        path = root / representative.path
        try:
            content = path.read_bytes()
        except OSError:
            continue
        text = content.decode("utf-8", errors="replace")
        excerpt = "\n".join(line.rstrip() for line in text.splitlines())
        truncated = len(excerpt) > TEXT_SNIPPET_CHARS
        if truncated:
            excerpt = excerpt[:TEXT_SNIPPET_CHARS].rstrip() + "\n[snippet truncated]"
        snippets.append(
            TextSnippet(
                path=representative.path,
                role=representative.role,
                sha256=hashlib.sha256(content).hexdigest(),
                chars=len(excerpt),
                truncated=truncated,
                excerpt=excerpt,
            )
        )

    return snippets


def _is_text_snippet_candidate(path: str) -> bool:
    suffix = PurePosixPath(path).suffix.lower()
    return suffix in TEXT_SNIPPET_EXTENSIONS


def _context_governance(context: ProjectContext) -> list[str]:
    values = []
    for value in context.applicable_governance.value or []:
        if isinstance(value, str) and value not in values:
            values.append(value)
    primary = context.primary_standard.value
    if isinstance(primary, str) and primary not in values:
        values.insert(0, primary)
    expected = context.expected_delivery_standard.value
    if isinstance(expected, str) and expected not in values:
        values.append(expected)
    return values


def _confidence(paths: list[str]) -> str:
    if len(paths) >= 3:
        return "strong"
    if len(paths) >= 2:
        return "moderate"
    return "weak"
