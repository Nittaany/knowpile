"""
Defensive wrapper around markitdown's native Python API.

Two deliberate constraints:
  - `convert_local()` only, never `convert()`. The generic `convert()`
    accepts remote URIs; `convert_local()` cannot, closing off that class
    of attack entirely.
  - every call is isolated in its own try/except. A single bad file
    becomes one recorded failure, not a dead pipeline.
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
        return ConversionResult(path=path, ok=False, error=f"{type(e).__name__}: {e}")
