from __future__ import annotations

import subprocess
from pathlib import Path

from .models import FileEvidence, ProjectEvidence


SKIPPED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    ".idea",
    ".vs",
    "node_modules",
    "__pycache__",
    "target",
    "dist",
    "build",
    "bin",
    "obj",
}

AUTHORITY_EXTENSIONS = {".md", ".txt", ".toml", ".json", ".yaml", ".yml"}


def collect_project_evidence(project_root: Path, max_files: int = 500) -> ProjectEvidence:
    root = project_root.resolve()
    if not root.exists():
        raise FileNotFoundError(f"Project path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Project path is not a directory: {root}")

    files: list[FileEvidence] = []
    detected: dict[str, list[str]] = {
        "manifest": [],
        "pps": [],
        "readme": [],
        "governance": [],
    }

    for path in _iter_files(root):
        rel = path.relative_to(root).as_posix()
        role = _classify_file(path.name)
        files.append(FileEvidence(path=rel, size_bytes=path.stat().st_size, role=role))

        for record_type in _record_types(path):
            detected[record_type].append(rel)

        if len(files) >= max_files:
            break

    notes = []
    if len(files) >= max_files:
        notes.append(f"File inventory was capped at {max_files} files.")
    notes.append(
        "Common generated/tooling directories were omitted from passive inventory: "
        + ", ".join(sorted(SKIPPED_DIRS))
        + "."
    )

    return ProjectEvidence(
        root=str(root),
        project_name=root.name,
        files_examined=len(files),
        files=files,
        detected_records={key: value for key, value in detected.items() if value},
        git_commit=_git_commit(root),
        notes=notes,
    )


def _iter_files(root: Path):
    paths = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIPPED_DIRS for part in path.relative_to(root).parts):
            continue
        paths.append(path)

    for path in sorted(paths, key=lambda candidate: _path_priority(root, candidate)):
        yield path


def _classify_file(name: str) -> str:
    lower = name.lower()
    if lower.endswith((".md", ".txt", ".rst")):
        return "documentation"
    if lower.endswith((".toml", ".json", ".yaml", ".yml")):
        return "configuration"
    if lower.endswith((".py", ".rs", ".ts", ".tsx", ".js", ".jsx", ".cs")):
        return "source"
    return "artifact"


def _record_types(path: Path) -> list[str]:
    lower_name = path.name.lower()
    stem = path.stem.lower()
    extension = path.suffix.lower()
    record_types = []

    if lower_name in {"project.manifest.toml", "development.manifest.toml", "manifest.toml"}:
        record_types.append("manifest")
    if extension in {".md", ".txt"} and (
        "project proposal" in stem or stem == "pps" or stem.endswith(" pps")
    ):
        record_types.append("pps")
    if lower_name in {"readme.md", "readme.txt", "readme.rst"}:
        record_types.append("readme")
    if extension in AUTHORITY_EXTENSIONS and (
        "governance" in stem or stem.endswith("standard") or " standard" in stem
    ):
        record_types.append("governance")

    return record_types


def _path_priority(root: Path, path: Path) -> tuple[int, int, str]:
    rel = path.relative_to(root)
    role = _classify_file(path.name)
    if _record_types(path):
        group = 0
    elif role == "documentation":
        group = 1
    elif role == "configuration":
        group = 2
    elif role == "source":
        group = 3
    else:
        group = 4
    return (group, len(rel.parts), rel.as_posix().lower())


def _git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={root.as_posix()}", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return result.stdout.strip() or None
