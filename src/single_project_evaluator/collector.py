from __future__ import annotations

import subprocess
from pathlib import Path

from .models import FileEvidence, ProjectEvidence


SKIPPED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "node_modules",
    "__pycache__",
    "target",
    "dist",
    "build",
}

RECORD_NAMES = {
    "manifest": ("project.manifest.toml", "Development.manifest.toml", "manifest.toml"),
    "pps": ("Project Proposal", "PPS"),
    "readme": ("README.md", "README.txt"),
    "governance": ("Governance", "Standard"),
}


def collect_project_evidence(project_root: Path, max_files: int = 500) -> ProjectEvidence:
    root = project_root.resolve()
    if not root.exists():
        raise FileNotFoundError(f"Project path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Project path is not a directory: {root}")

    files: list[FileEvidence] = []
    detected: dict[str, list[str]] = {key: [] for key in RECORD_NAMES}

    for path in _iter_files(root):
        rel = path.relative_to(root).as_posix()
        role = _classify_file(path.name)
        files.append(FileEvidence(path=rel, size_bytes=path.stat().st_size, role=role))

        for record_type, markers in RECORD_NAMES.items():
            if any(marker.lower() in path.name.lower() for marker in markers):
                detected[record_type].append(rel)

        if len(files) >= max_files:
            break

    notes = []
    if len(files) >= max_files:
        notes.append(f"File inventory was capped at {max_files} files.")

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
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIPPED_DIRS for part in path.relative_to(root).parts):
            continue
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


def _git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return result.stdout.strip() or None
