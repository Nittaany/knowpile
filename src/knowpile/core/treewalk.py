"""
Native replacement for the `tree` binary.

`tree` isn't preinstalled on Windows and is inconsistently available across
Linux distros -- exactly the kind of per-OS install friction the Level-0
rebuild is meant to eliminate, not just document install-hints for.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Iterable, List

DEFAULT_IGNORES = (".git", "node_modules", "__pycache__", "venv", ".venv", "graphify-out")


def _ignored(name: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def render_tree(root: Path, ignore_patterns: Iterable[str] = DEFAULT_IGNORES, max_depth: int = 8) -> str:
    root = Path(root)
    lines: List[str] = [str(root)]

    def walk(dir_path: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(
                (e for e in dir_path.iterdir() if not _ignored(e.name, ignore_patterns)),
                key=lambda e: (e.is_file(), e.name.lower()),
            )
        except PermissionError:
            return
        for i, entry in enumerate(entries):
            connector = "└── " if i == len(entries) - 1 else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                extension = "    " if i == len(entries) - 1 else "│   "
                walk(entry, prefix + extension, depth + 1)

    walk(root, "", 0)
    return "\n".join(lines)
