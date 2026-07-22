"""
Small filesystem-safety helpers shared by every interface (CLI today, web
later). Nothing here knows about terminals or browsers -- pure functions.
"""
from __future__ import annotations

import re

_QUOTE_CHARS = ("'", '"')

# Matches a Windows drive-letter path ("C:\Users\...") or a UNC path
# ("\\server\share\..."). Backslash is a genuine path separator in both --
# it must never be treated as a shell escape character.
_WINDOWS_PATH_RE = re.compile(r"^[a-zA-Z]:\\")


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


def clean_path(path: str) -> str:
    """Normalize a path as it actually arrives from real-world input.

    Two distinct corruption patterns were confirmed via live testing
    (Level 2.2), not assumed:

    1. Quote-wrapped: copying a path via a terminal's "Copy as Pathname"
       (or manually quoting one) bakes the quote characters into the
       string itself -- e.g. "'/Users/x/Report (1).pdf'". Confirmed via
       a real `knowpiler init` run producing exactly this, rejected by
       `PathValidator` because the literal quoted string doesn't exist
       on disk.
    2. Backslash-escaped: dragging a file from Finder (or many Linux file
       managers) into a terminal auto-escapes shell metacharacters --
       spaces, parens, etc. -- e.g. "/Users/x/Major\\ Project\\ -\\ DOCS/...".
       Same failure mode: the literal escaped string isn't a real path.

    Windows-style paths (`C:\\...` or `\\\\server\\share\\...`) are left
    untouched -- backslash there is a path separator, not a shell escape,
    and must never be stripped.

    This function does the cleaning; callers decide when to invoke it.
    It is used in exactly two places: the CLI's path validators (so a
    dragged/pasted path is accepted on the first try, not rejected and
    reprompted forever) and `core.manifest`'s Pydantic field validators
    (so whatever ends up persisted is always clean, even if a caller
    constructs a Manifest directly, bypassing the CLI entirely).
    """
    if not path:
        return path

    cleaned = path.strip()

    # Strip one matching pair of wrapping quote characters, if present.
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in _QUOTE_CHARS:
        cleaned = cleaned[1:-1].strip()

    # Un-escape shell-style backslash escapes ("\ " -> " ", "\(" -> "(")
    # -- but never touch genuine Windows path separators.
    if "\\" in cleaned and not _WINDOWS_PATH_RE.match(cleaned) and not cleaned.startswith("\\\\"):
        cleaned = re.sub(r"\\(.)", r"\1", cleaned)

    return cleaned.strip()