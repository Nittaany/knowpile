"""
Defensive wrapper around markitdown's native Python API.

Two deliberate constraints, both stability/security decisions rather than
style preferences:

  - `convert_local()` only, never `convert()`. The generic `convert()`
    accepts remote URIs; a malicious or malformed file could embed one and
    trigger an unintended outbound request. `convert_local()` cannot do
    that by construction, closing off that class of attack entirely.

  - every call is isolated in its own try/except. Level 0's version of
    this had exactly the opposite failure mode: a single bad file produced
    a silent 0-byte output with no indication of which file caused it, and
    a subprocess call that gave no structured exception to catch. Here a
    bad file becomes one recorded failure, not a dead pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from markitdown import MarkItDown


@dataclass
class ConversionResult:
    path: Path
    ok: bool
    text: Optional[str] = None
    error: Optional[str] = None


def convert_file(path: Path, converter: Optional[MarkItDown] = None) -> ConversionResult:
    md = converter or MarkItDown()
    try:
        result = md.convert_local(str(path))
        return ConversionResult(path=path, ok=True, text=result.text_content)
    except Exception as e:
        # Broad catch is deliberate here: markitdown raises different
        # exception types per format, and the contract of this function is
        # "never propagate -- always return a result the caller can log
        # and skip past."
        return ConversionResult(path=path, ok=False, error=f"{type(e).__name__}: {e}")
