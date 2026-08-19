from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from .models import AuthorityRecord, FileEvidence, ProjectEvidence


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
AUTHORITY_EXCERPT_CHARS = 1200
AUTHORITY_RECORD_LIMIT = 20


def collect_project_evidence(project_root: Path, max_files: int = 500) -> ProjectEvidence:
    root = project_root.resolve()
    if not root.exists():
        raise FileNotFoundError(f"Project path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Project path is not a directory: {root}")

    files: list[FileEvidence] = []
    authority_records: list[AuthorityRecord] = []
    detected: dict[str, list[str]] = {
        "manifest": [],
        "pps": [],
        "readme": [],
        "release_documentation": [],
        "governance": [],
    }

    for path in _iter_files(root):
        rel = path.relative_to(root).as_posix()
        role = _classify_path(root, path)
        files.append(FileEvidence(path=rel, size_bytes=path.stat().st_size, role=role))

        record_types = _record_types(path, root)
        for record_type in record_types:
            detected[record_type].append(rel)
        if record_types and len(authority_records) < AUTHORITY_RECORD_LIMIT:
            authority_records.append(_authority_record(root, path, record_types[0]))

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
        authority_records=authority_records,
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


def _classify_path(root: Path, path: Path) -> str:
    if _is_release_artifact_path(root, path):
        return "release_artifact"
    return _classify_file(path.name)


def _record_types(path: Path, root: Path | None = None) -> list[str]:
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
    if root is not None and lower_name in {"readme.md", "readme.txt", "readme.rst"} and _is_release_artifact_path(root, path):
        record_types.append("release_documentation")
    elif lower_name in {"readme.md", "readme.txt", "readme.rst"}:
        record_types.append("readme")
    if extension in AUTHORITY_EXTENSIONS and (
        "governance" in stem or stem.endswith("standard") or " standard" in stem
    ):
        record_types.append("governance")

    return record_types


def _path_priority(root: Path, path: Path) -> tuple[int, int, str]:
    rel = path.relative_to(root)
    role = _classify_path(root, path)
    if _record_types(path, root):
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


def _is_release_artifact_path(root: Path, path: Path) -> bool:
    rel_parts = tuple(part.lower() for part in path.relative_to(root).parts)
    return "artifacts" in rel_parts or "publish" in rel_parts or "release" in rel_parts


def _authority_record(root: Path, path: Path, record_type: str) -> AuthorityRecord:
    content = path.read_bytes()
    return AuthorityRecord(
        path=path.relative_to(root).as_posix(),
        record_type=record_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        excerpt=_text_excerpt(content),
    )


def _text_excerpt(content: bytes) -> str:
    text = content.decode("utf-8", errors="replace")
    text = "\n".join(line.rstrip() for line in text.splitlines())
    if len(text) <= AUTHORITY_EXCERPT_CHARS:
        return text
    return text[:AUTHORITY_EXCERPT_CHARS].rstrip() + "\n[excerpt truncated]"


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
