"""
`knowpiler doctor` -- fail fast, never auto-install.

Every check here maps to a real Level-0 failure:
- markitdown is a library import, so a broken install surfaces as a normal
  ImportError here, instead of a silent 0-byte report file mid-run.
- graphify/cloc/git remain external binaries knowpiler depends on but
  doesn't own -- checked here, never auto-installed.
- The Apple Silicon / Rosetta arch-mismatch check is ported directly: it's
  the exact root cause of the original 0-byte-report bug.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass
from typing import List

from rich.console import Console

console = Console()


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


def _check_markitdown() -> CheckResult:
    try:
        from markitdown import MarkItDown  # noqa: F401
        return CheckResult("markitdown (library)", True)
    except ImportError as e:
        return CheckResult(
            "markitdown (library)", False,
            f"Not importable ({e}). Fix: pip install 'markitdown[pdf,docx,pptx]'",
        )


def _install_hint(tool: str) -> str:
    system = platform.system()
    if system == "Darwin":
        return f"brew install {tool}"
    if system == "Linux":
        if shutil.which("apt"):
            return f"sudo apt install {tool}"
        if shutil.which("dnf"):
            return f"sudo dnf install {tool}"
        if shutil.which("pacman"):
            return f"sudo pacman -S {tool}"
        return f"install '{tool}' via your distro's package manager"
    if system == "Windows":
        return f"choco install {tool}  (or: scoop install {tool})"
    return f"install '{tool}' -- see its own docs"


def _check_binary(name: str, hint: str, version_flag: str = "--version") -> CheckResult:
    path = shutil.which(name)
    if not path:
        return CheckResult(name, False, f"Not on PATH. {hint}")
    try:
        subprocess.run([name, version_flag], capture_output=True, timeout=5, check=False)
        return CheckResult(name, True, path)
    except Exception as e:
        return CheckResult(name, False, f"On PATH but failed to run: {e}")


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
        _check_binary("graphify", "See https://github.com/Graphify-Labs/graphify (pip install graphifyy)"),
        _check_binary("cloc", _install_hint("cloc")),
        _check_binary("git", _install_hint("git")),
    ]


def print_report(results: List[CheckResult]) -> bool:
    all_ok = True
    for r in results:
        if r.ok:
            console.print(f"[green]OK[/green]   {r.name}  [dim]{r.detail}[/dim]")
        else:
            all_ok = False
            console.print(f"[red]FAIL[/red] {r.name}  -- {r.detail}")
    return all_ok
