from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from .models import ContextValue, ProjectContext, ProjectEvidence


PPS_FIELD_PATTERNS = {
    "lifecycle_state": re.compile(r"^\*\*WGS Lifecycle State:\*\*\s*(.+?)\s*$", re.IGNORECASE),
    "project_classes": re.compile(r"^\*\*Project Class:\*\*\s*(.+?)\s*$", re.IGNORECASE),
    "primary_standard": re.compile(r"^\*\*Primary Governing Standard:\*\*\s*(.+?)\s*$", re.IGNORECASE),
    "expected_delivery_standard": re.compile(r"^\*\*Expected Delivery Standard:\*\*\s*(.+?)\s*$", re.IGNORECASE),
    "project_name": re.compile(r"^\*\*Final Project Name:\*\*\s*(.+?)\s*$", re.IGNORECASE),
}


def extract_project_context(project_root: Path, evidence: ProjectEvidence) -> ProjectContext:
    root = project_root.resolve()
    notes: list[str] = []
    context = _empty_context(notes)

    manifest_path = _first_existing(root, evidence.detected_records.get("manifest", []))
    if manifest_path is not None:
        context = _merge_context(context, _context_from_manifest(root, manifest_path, notes))

    pps_path = _first_existing(root, evidence.detected_records.get("pps", []))
    if pps_path is not None:
        context = _merge_context(context, _context_from_pps(root, pps_path, notes))

    readme_path = _first_existing(root, evidence.detected_records.get("readme", []))
    if readme_path is not None and context.readme_path.value is None:
        readme_source = _relative(root, readme_path)
        context = _replace(context, readme_path=ContextValue(readme_source, readme_source))

    if context.project_name.value is None:
        context = _replace(
            context,
            project_name=ContextValue(evidence.project_name, "directory_name"),
        )
        notes.append("Project name fell back to the evaluated directory name.")

    return context


def _empty_context(notes: list[str]) -> ProjectContext:
    return ProjectContext(notes=notes)


def _context_from_manifest(root: Path, manifest_path: Path, notes: list[str]) -> ProjectContext:
    source = _relative(root, manifest_path)
    try:
        data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        notes.append(f"Could not parse manifest `{source}`: {exc}")
        return ProjectContext(notes=notes)

    project = _table(data, "project")
    entity = _table(data, "entity")
    governance = _table(data, "governance")
    intent = _table(data, "intent")
    primary_standard = _string(governance.get("primary_standard"))
    additional_standards = _string_list(governance.get("additional_standards"))

    return ProjectContext(
        project_name=_context_value(
            _string(project.get("name") or project.get("working_name") or project.get("title") or entity.get("title")),
            source,
        ),
        project_classes=_context_value(_manifest_project_classes(project, entity), source),
        lifecycle_state=_context_value(_string(project.get("lifecycle_state") or project.get("stage")), source),
        manifest_adoption_posture=_context_value(_string(project.get("adoption_posture")), source),
        primary_standard=_context_value(primary_standard, source),
        expected_delivery_standard=_context_value(_string(governance.get("expected_delivery_standard")), source),
        applicable_governance=_context_value(
            _unique(
                _string_list(governance.get("applicable"))
                + ([primary_standard] if primary_standard else [])
                + additional_standards
            ),
            source,
        ),
        pps_path=_context_value(_string(intent.get("pps")), source),
        notes=notes,
    )


def _context_from_pps(root: Path, pps_path: Path, notes: list[str]) -> ProjectContext:
    source = _relative(root, pps_path)
    values: dict[str, ContextValue] = {
        "pps_path": ContextValue(source, source),
    }

    try:
        lines = pps_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        notes.append(f"Could not read PPS `{source}`: {exc}")
        return ProjectContext(notes=notes, **values)

    for line in lines[:80]:
        for field_name, pattern in PPS_FIELD_PATTERNS.items():
            match = pattern.match(line.strip())
            if not match:
                continue
            value = match.group(1).strip()
            if value and value.upper() not in {"TBD", "N/A"}:
                if field_name == "project_classes":
                    values[field_name] = ContextValue(_split_classes(value), source)
                else:
                    values[field_name] = ContextValue(value, source)

    return ProjectContext(notes=notes, **values)


def _merge_context(base: ProjectContext, incoming: ProjectContext) -> ProjectContext:
    values = {
        "project_name": _prefer(base.project_name, incoming.project_name),
        "project_classes": _prefer(base.project_classes, incoming.project_classes),
        "lifecycle_state": _prefer(base.lifecycle_state, incoming.lifecycle_state),
        "manifest_adoption_posture": _prefer(
            base.manifest_adoption_posture,
            incoming.manifest_adoption_posture,
        ),
        "primary_standard": _prefer(base.primary_standard, incoming.primary_standard),
        "expected_delivery_standard": _prefer(
            base.expected_delivery_standard,
            incoming.expected_delivery_standard,
        ),
        "applicable_governance": _prefer(base.applicable_governance, incoming.applicable_governance),
        "pps_path": _prefer(base.pps_path, incoming.pps_path),
        "readme_path": _prefer(base.readme_path, incoming.readme_path),
    }
    return ProjectContext(notes=base.notes, **values)


def _replace(context: ProjectContext, **changes: ContextValue) -> ProjectContext:
    values = {
        "project_name": context.project_name,
        "project_classes": context.project_classes,
        "lifecycle_state": context.lifecycle_state,
        "manifest_adoption_posture": context.manifest_adoption_posture,
        "primary_standard": context.primary_standard,
        "expected_delivery_standard": context.expected_delivery_standard,
        "applicable_governance": context.applicable_governance,
        "pps_path": context.pps_path,
        "readme_path": context.readme_path,
    }
    values.update(changes)
    return ProjectContext(notes=context.notes, **values)


def _prefer(current: ContextValue, incoming: ContextValue) -> ContextValue:
    if current.value not in (None, [], ""):
        return current
    return incoming


def _context_value(value: Any, source: str) -> ContextValue:
    if value in (None, [], ""):
        return ContextValue(value)
    return ContextValue(value, source)


def _first_existing(root: Path, relative_paths: list[str]) -> Path | None:
    for relative_path in relative_paths:
        path = root / relative_path
        if path.exists() and path.is_file():
            return path
    return None


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item.strip()]
    return []


def _manifest_project_classes(project: dict[str, Any], entity: dict[str, Any]) -> list[str]:
    explicit = _string_list(project.get("class"))
    if explicit:
        return explicit

    values = []
    for candidate in (project.get("type"), project.get("portfolio_class"), entity.get("kind")):
        if isinstance(candidate, str) and candidate.strip() and candidate not in values:
            values.append(candidate)
    return values


def _split_classes(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"/|,", value) if item.strip()]


def _unique(values: list[str]) -> list[str]:
    unique_values = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)
    return unique_values
