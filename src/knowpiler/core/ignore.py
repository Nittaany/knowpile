"""
Parsing and applying .graphifyignore with real Git-ignore semantics via
`pathspec` -- replaces both the old shell grep/awk chains and this
project's own earlier `fnmatch`-based ignore tuple, neither of which
understood negation patterns or directory-anchored rules correctly.

Load order (validated against the real Level-0 bash implementation, kept
unchanged here because it's proven, not guessed):
  1. .graphifyignore exists at the project root -> use it as-is.
  2. Otherwise -> seed from .gitignore, then append a static binary/media
     safety net. The safety net matters even when an LLM-suggestion step
     is added later: the pipeline must never depend on a network call
     succeeding just to filter files.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import pathspec

STATIC_SAFETY_NET = [
    ".git/", "node_modules/", "__pycache__/", ".venv/", "venv/",
    "graphify-out/", "*.lock",
    "*.png", "*.jpg", "*.jpeg", "*.webp", "*.ico", "*.svg",
    "*.pdf", "*.zip", "*.tar.gz",
]


def load_ignore_patterns(project_root: Path) -> List[str]:
    project_root = Path(project_root)
    graphifyignore = project_root / ".graphifyignore"
    if graphifyignore.exists():
        return [line for line in graphifyignore.read_text().splitlines() if line.strip()]

    patterns: List[str] = []
    gitignore = project_root / ".gitignore"
    if gitignore.exists():
        patterns.extend(line for line in gitignore.read_text().splitlines() if line.strip())
    patterns.extend(STATIC_SAFETY_NET)

    # De-dupe while preserving order (a plain set() would scramble it).
    seen = set()
    deduped = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            deduped.append(p)
    return deduped


def compile_spec(patterns: List[str]) -> pathspec.PathSpec:
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def filtered_files(project_root: Path, patterns: List[str]) -> List[Path]:
    """Walk project_root, returning only files NOT matched by the ignore spec."""
    spec = compile_spec(patterns)
    root = Path(project_root)
    kept: List[Path] = []
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(root).as_posix()
        if not spec.match_file(rel):
            kept.append(path)
    return kept
