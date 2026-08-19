from __future__ import annotations

import hashlib
from pathlib import Path
from pathlib import PurePosixPath

from .models import (
    ApplicabilityState,
    DeterministicEvidence,
    GovernanceMaterial,
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
GOVERNANCE_MATERIAL_CHARS = 2000
GOVERNANCE_MATERIAL_LIMIT = 8
DETERMINISTIC_EVIDENCE_LIMIT = 40
DETERMINISTIC_EVIDENCE_CATEGORY_LIMITS = {
    "verification_record": 12,
    "release_artifact": 10,
    "test_source": 10,
    "build_configuration": 8,
}


def prepare_evaluation_context(evidence: ProjectEvidence, context: ProjectContext) -> PreparedContext:
    inventory_summary = summarize_inventory(evidence)
    surfaces = infer_surfaces(evidence)
    governance_applicability = infer_governance_applicability(context, surfaces)
    governance_materials = collect_governance_materials(evidence, context)
    deterministic_evidence = infer_deterministic_evidence(evidence)
    representative_files = select_representative_files(evidence)
    text_snippets = collect_text_snippets(evidence, representative_files)
    notes = [
        "Surface and governance applicability are heuristic in Phase 1; conformance checks are not implemented yet."
    ]
    return PreparedContext(
        inventory_summary=inventory_summary,
        surfaces=surfaces,
        governance_applicability=governance_applicability,
        governance_materials=governance_materials,
        deterministic_evidence=deterministic_evidence,
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


def collect_governance_materials(
    evidence: ProjectEvidence,
    context: ProjectContext,
    limit: int = GOVERNANCE_MATERIAL_LIMIT,
) -> list[GovernanceMaterial]:
    materials: list[GovernanceMaterial] = []
    seen_paths: set[str] = set()

    for standard, path in _context_governance_paths(context).items():
        if len(materials) >= limit:
            break
        _append_governance_material(
            materials,
            seen_paths,
            standard=standard,
            path=Path(path),
            display_path=path,
            source=context.governance_standard_paths.source or "context",
        )

    root = Path(evidence.root)
    for relative_path in evidence.detected_records.get("governance", []):
        if len(materials) >= limit:
            break
        _append_governance_material(
            materials,
            seen_paths,
            standard=_standard_from_path(relative_path),
            path=root / relative_path,
            display_path=relative_path,
            source="project_governance_record",
        )

    return materials


def infer_deterministic_evidence(
    evidence: ProjectEvidence,
    limit: int = DETERMINISTIC_EVIDENCE_LIMIT,
) -> list[DeterministicEvidence]:
    candidates: dict[str, list[DeterministicEvidence]] = {
        category: [] for category in DETERMINISTIC_EVIDENCE_CATEGORY_LIMITS
    }
    seen: set[tuple[str, str]] = set()

    def add(category: str, file_path: str, size_bytes: int, summary: str) -> None:
        key = (category, file_path)
        if key in seen:
            return
        seen.add(key)
        candidates.setdefault(category, []).append(
            DeterministicEvidence(
                category=category,
                path=file_path,
                size_bytes=size_bytes,
                summary=summary,
            )
        )

    for file in evidence.files:
        path = PurePosixPath(file.path)
        lower_path = file.path.lower()
        lower_name = path.name.lower()
        suffix = path.suffix.lower()

        if _is_test_evidence(path, lower_path):
            add("test_source", file.path, file.size_bytes, "Test source or fixture present in project inventory.")
        if _is_build_configuration(lower_name):
            add("build_configuration", file.path, file.size_bytes, "Build or package configuration present.")
        if file.role == "release_artifact":
            add("release_artifact", file.path, file.size_bytes, "Release or packaged artifact present.")
        if _is_verification_record(lower_path, lower_name, suffix):
            add("verification_record", file.path, file.size_bytes, "Verification, hash, checklist, or log record present.")

    signals: list[DeterministicEvidence] = []
    for category, category_limit in DETERMINISTIC_EVIDENCE_CATEGORY_LIMITS.items():
        for signal in candidates.get(category, [])[:category_limit]:
            if len(signals) >= limit:
                return signals
            signals.append(signal)
    return signals


def _append_governance_material(
    materials: list[GovernanceMaterial],
    seen_paths: set[str],
    *,
    standard: str,
    path: Path,
    display_path: str,
    source: str,
) -> None:
    path_key = str(path.resolve()) if path.exists() else str(path)
    if path_key in seen_paths:
        return
    seen_paths.add(path_key)

    try:
        content = path.read_bytes()
    except OSError as exc:
        materials.append(
            GovernanceMaterial(
                standard=standard,
                path=display_path,
                source=source,
                size_bytes=0,
                sha256="",
                chars=0,
                truncated=False,
                excerpt="",
                read_error=str(exc),
            )
        )
        return

    excerpt = "\n".join(content.decode("utf-8", errors="replace").splitlines())
    truncated = len(excerpt) > GOVERNANCE_MATERIAL_CHARS
    if truncated:
        excerpt = excerpt[:GOVERNANCE_MATERIAL_CHARS].rstrip() + "\n[governance material truncated]"
    materials.append(
        GovernanceMaterial(
            standard=standard,
            path=display_path,
            source=source,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            chars=len(excerpt),
            truncated=truncated,
            excerpt=excerpt,
        )
    )


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


def _context_governance_paths(context: ProjectContext) -> dict[str, str]:
    value = context.governance_standard_paths.value
    if not isinstance(value, dict):
        return {}
    paths = {}
    for standard, path in value.items():
        if isinstance(standard, str) and isinstance(path, str) and standard.strip() and path.strip():
            paths[standard] = path
    return paths


def _standard_from_path(path: str) -> str:
    name = PurePosixPath(path).stem
    upper_name = name.upper()
    for standard in ["AAMHS", "ARHS", "CTS", "DDS", "DRS", "LDS", "PPS", "SIS", "WDS", "WGS"]:
        if standard in upper_name:
            return standard
    return name


def _is_test_evidence(path: PurePosixPath, lower_path: str) -> bool:
    parts = [part.lower() for part in path.parts]
    name = path.name.lower()
    return (
        "tests" in parts
        or "test" in parts
        or any(part.endswith(".tests") for part in parts)
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith("tests.vb")
        or name.endswith("tests.cs")
        or "/tests/" in lower_path
    )


def _is_build_configuration(lower_name: str) -> bool:
    return lower_name in {
        "cargo.toml",
        "directory.build.props",
        "global.json",
        "package.json",
        "project.json",
        "pyproject.toml",
        "setup.py",
        "vite.config.js",
        "vite.config.ts",
    } or lower_name.endswith((".csproj", ".fsproj", ".sln", ".slnx", ".vbproj"))


def _is_verification_record(lower_path: str, lower_name: str, suffix: str) -> bool:
    verification_terms = ["verification", "verify", "checklist", "hash", "sha256", "release"]
    return (
        any(term in lower_path for term in verification_terms)
        and suffix in {".json", ".log", ".md", ".txt", ".toml", ".yaml", ".yml"}
    ) or lower_name.endswith((".sha256", ".sha256sum"))


def _confidence(paths: list[str]) -> str:
    if len(paths) >= 3:
        return "strong"
    if len(paths) >= 2:
        return "moderate"
    return "weak"
