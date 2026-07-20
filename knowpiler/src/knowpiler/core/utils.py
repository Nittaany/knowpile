"""
Small filesystem-safety helpers shared by every interface (CLI today, web
later). Nothing here knows about terminals or browsers -- pure functions.
"""
from __future__ import annotations

import re


def slugify(name: str) -> str:
    """Turn a free-form project name into a filesystem-safe folder name.

    `project` is allowed to be a human string with spaces and punctuation
    -- that's fine as a display name. It is NOT fine to use that string
    directly as a directory name; spaces and shell-special characters
    caused real path-handling failures in Level 0. Display name and
    on-disk name are kept deliberately separate.
    """
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "project"


def strip_shell_quotes(path: str) -> str:
    """Defensively strip one matching pair of quote characters.

    Paths copied from a terminal sometimes arrive still wrapped in the
    shell's own quoting -- the quote characters end up baked into the
    string value itself. Strip one matching pair rather than silently
    trying to open a file literally named "'/Users/...'".
    """
    path = path.strip()
    if len(path) >= 2 and path[0] == path[-1] and path[0] in ("'", '"'):
        return path[1:-1]
    return path
