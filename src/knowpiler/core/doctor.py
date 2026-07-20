"""
`knowpiler doctor` -- environment-aware diagnostic tool.

Every check here maps to a real Level-0 failure:
- markitdown: library import check.
- graphify: now venv-managed.
- cloc: removed (replaced by python-native pygount).
- git: downgraded to a warning (non-technical users won't be blocked).
- The Apple Silicon / Rosetta arch-mismatch check is ported directly: it's
  the exact root cause of the original 0-byte-report bug.
"""
from __future__ import annotations

import platform
import shutil
import sys
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import List

from rich.console import Console

console = Console()


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    warning: bool = False


def _check_markitdown() -> CheckResult:
    try:
        import markitdown
        # __file__ gives the exact path to the loaded library
        path = getattr(markitdown, "__file__", "Imported, but path unknown")
        return CheckResult("markitdown (library)", True, str(path))
    except ImportError as e:
        return CheckResult(
            "markitdown (library)", False,
            f"Not importable ({e}). Fix: run `uv pip install -e .`",
        )

def _check_pygount() -> CheckResult:
    """Explicitly verifies our pure-Python line counter is importable."""
    try:
        import pygount
        path = getattr(pygount, "__file__", "Imported, but path unknown")
        return CheckResult("pygount (library)", True, str(path))
    except ImportError as e:
        return CheckResult(
            "pygount (library)", False,
            f"Not importable ({e}). Fix: run `uv pip install -e .`",
        )
    
def _check_graphify_venv() -> CheckResult:
    """this is a venv-local check, not a system PATH check. 

    Bypasses standard global PATH searching entirely. It looks directly
    inside the active virtual environment execution directory to guarantee
    we are running our local pinned version, not a leaking global binary.
    """
    venv_bin_dir = Path(sys.executable).parent
    graphify_bin = venv_bin_dir / "graphify"

    if not graphify_bin.exists():
        return CheckResult(
            "graphify (venv CLI)", False,
            f"Executable missing from venv at {graphify_bin}. Fix: run `uv pip install -e .`"
        )
    try:
        subprocess.run([str(graphify_bin), "--version"], capture_output=True, timeout=5, check=False)
        return CheckResult("graphify (venv CLI)", True, str(graphify_bin))
    except Exception as e:
        return CheckResult(
            "graphify (venv CLI)", False,
            f"Found in venv but failed to execute: {e}"
        )


def _check_system_git() -> CheckResult:
    """Checks for system Git. Softened to a warning for absolute plug-and-play stability."""
    path = shutil.which("git")
    if not path:
        return CheckResult("git (system UI)", False, "Not found on PATH. (Optional: Commit history parsing will be skipped)", warning=True)
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=5, check=False)
        return CheckResult("git (system UI)", True, path)
    except Exception as e:
        return CheckResult("git (system UI)", False, f"Failed to run: {e}", warning=True)    


def _check_arch_mismatch() -> CheckResult:
    if platform.system() != "Darwin":
        return CheckResult("architecture", True)
    machine = platform.machine()
    proc = platform.processor()
    if machine == "arm64" and proc == "i386":
        return CheckResult(
            "architecture", False,
            "Running under Rosetta (x86_64 emulation) on Apple Silicon -- pip "
            "may pull arm64-only wheels that crash at runtime. Terminal.app -> "
            "Get Info -> uncheck 'Open using Rosetta', then reinstall.",
        )
    return CheckResult("architecture", True, machine)


def run_all() -> List[CheckResult]:
    return [
        _check_arch_mismatch(),
        _check_markitdown(),
        _check_pygount(),       
        _check_graphify_venv(), 
        _check_system_git(),
    ]


def print_report(results: List[CheckResult]) -> bool:
    all_ok = True
    for r in results:
        if r.ok:
            console.print(f"[green]OK[/green]   {r.name}  [dim]{r.detail}[/dim]")
        elif r.warning:
            console.print(f"[yellow]WARN[/yellow] {r.name}  [dim]{r.detail}[/dim]")
        else:
            all_ok = False
            console.print(f"[red]FAIL[/red] {r.name}  -- {r.detail}")
    return all_ok