"""
knowpile CLI -- the interface layer.

This file's only job is: collect input from a terminal (via InquirerPy),
and hand plain values to knowpile.core. It must never construct a Manifest
or Config directly, never touch Pydantic, and never contain business rules
-- that's the whole point of the core/interface split. A future web
interface (knowpile.web) will collect the exact same plain values from an
HTTP request body and call the exact same core functions.

Prompt library: InquirerPy, not questionary. Reason: InquirerPy's
`filepath(only_directories=True, validate=PathValidator(is_dir=True))` is a
genuine, built-in match for replacing the old bash `_pick_directory` loop
-- questionary has no equivalent flag, so matching that behavior there
would mean writing a manual validator by hand. Since InquirerPy also
covers confirm/select/text just as well, this is a full migration, not a
two-library hybrid.
"""
from __future__ import annotations

import typer
from InquirerPy import inquirer
from InquirerPy.validator import PathValidator
from rich.console import Console

from knowpile.core import config as cfg
from knowpile.core.doctor import print_report, run_all
from knowpile.core.manifest import create_manifest

app = typer.Typer(help="knowpile -- personal knowledge compiler for engineers.")
console = Console()

REPORT_TYPES = ["final_report", "architecture_report", "functional_report", "research_report", "synopsis", "other"]

DIR_VALIDATOR = PathValidator(is_dir=True, message="Path does not exist or is not a directory")
FILE_VALIDATOR = PathValidator(is_file=True, message="Path does not exist or is not a file")


@app.command()
def doctor() -> None:
    """Check environment: markitdown, graphify, cloc, git, architecture."""
    console.print("[bold]knowpile doctor[/bold]")
    ok = print_report(run_all())
    if not ok:
        console.print("\n[red]Fix the above, then re-run `knowpile doctor`.[/red]")
        raise typer.Exit(code=1)
    console.print("\n[green]All dependencies present.[/green]")


config_app = typer.Typer(help="View or set persisted defaults.")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show() -> None:
    c = cfg.load_config()
    console.print(c.model_dump())


@config_app.command("set-backend")
def config_set_backend(backend: str = typer.Argument(..., help=f"one of {cfg.SUPPORTED_BACKENDS}")) -> None:
    if backend not in cfg.SUPPORTED_BACKENDS:
        console.print(f"[red]Unknown backend '{backend}'.[/red] Choose from: {cfg.SUPPORTED_BACKENDS}")
        raise typer.Exit(code=1)
    if not cfg.backend_ready(backend):
        env_var = cfg.ENV_VAR_BY_BACKEND[backend]
        console.print(f"[yellow]Warning:[/yellow] {env_var} isn't set yet -- set it before running `rewrite`.")
    c = cfg.load_config()
    c.backend = backend
    cfg.save_config(c)
    console.print(f"[green]Backend set to {backend}.[/green]")


@app.command()
def init(project: str = typer.Argument(..., help="Project name, e.g. 'Semantic Web - guide allocation'")) -> None:
    """Step 1 -- interactive evidence inventory. Builds and saves manifest.json.

    This function ONLY prompts and collects plain strings/lists. All the
    actual Manifest construction, path cleaning, and saving happens inside
    knowpile.core.manifest.create_manifest -- the same function a web
    interface would call with the same arguments.
    """
    c = cfg.load_config()
    console.print(f"[bold]Inventory for:[/bold] {project}")

    root_dir = inquirer.filepath(
        message="Codebase root folder:", only_directories=True, validate=DIR_VALIDATOR
    ).execute()
    src_dir = inquirer.filepath(
        message="Source folder graphify should scan:",
        default=f"{root_dir.rstrip('/')}/src",
        only_directories=True,
        validate=DIR_VALIDATOR,
    ).execute()

    readme_path = None
    if inquirer.confirm(message="Do you have a README?", default=False).execute():
        readme_path = inquirer.filepath(message="README path:", validate=FILE_VALIDATOR).execute()

    reports = []
    while inquirer.confirm(message="Add a report?", default=False).execute():
        rtype = inquirer.select(message="Report type:", choices=REPORT_TYPES).execute()
        rpath = inquirer.filepath(
            message=f"Path to {rtype} (pdf/docx only):", validate=FILE_VALIDATOR
        ).execute()
        reports.append({"type": rtype, "path": rpath})

    research = []
    while inquirer.confirm(message="Add a research doc?", default=False).execute():
        research.append(
            inquirer.filepath(message="Path (pdf/docx only):", validate=FILE_VALIDATOR).execute()
        )

    presentations = []
    while inquirer.confirm(message="Add a presentation?", default=False).execute():
        presentations.append(
            inquirer.filepath(message="Path (pdf/pptx only):", validate=FILE_VALIDATOR).execute()
        )

    notes = []
    while inquirer.confirm(message="Add a notes/checkpoint file?", default=False).execute():
        notes.append(
            inquirer.filepath(
                message="Path (md/txt/rst/adoc/org only):", validate=FILE_VALIDATOR
            ).execute()
        )

    arch_diagram_path = None
    if inquirer.confirm(message="Do you have an architecture diagram?", default=False).execute():
        arch_diagram_path = inquirer.filepath(
            message="Path (pdf/svg/png/jpg/jpeg/webp):", validate=FILE_VALIDATOR
        ).execute()

    manifest = create_manifest(
        project=project,
        root_dir=root_dir,
        src_dir=src_dir,
        storage_root=c.storage_root,
        readme_path=readme_path,
        reports=reports,
        research=research,
        presentations=presentations,
        notes=notes,
        arch_diagram_path=arch_diagram_path,
    )

    console.print(f"[green]Manifest saved:[/green] {manifest.staging_dir}/manifest.json")
    console.print(f"[dim]Next: knowpile normalize {project}[/dim]")


@app.command()
def normalize(project: str) -> None:
    """Step 2-3 -- markitdown (library), native tree, cloc/git, graphify subprocess."""
    console.print(
        "[yellow]Not yet built.[/yellow] Next: wire core.convert + core.ignore + "
        "core.treewalk together against a real manifest, plus cloc/git subprocess calls."
    )


@app.command()
def rewrite(project: str) -> None:
    """Step 4 -- semantic rewrite into Layer-2 voice, using Master_PKB as style reference."""
    console.print(
        "[yellow]Not yet built.[/yellow] Needs a confirmed backend "
        "(`knowpile config set-backend <name>`) and real staged output from `normalize` first."
    )


@app.command()
def assemble(project: str) -> None:
    """Step 5 -- assemble the final Project Knowledge File."""
    console.print("[yellow]Not yet built.[/yellow]")


@app.command()
def review(project: str) -> None:
    """Step 6 -- human review gate."""
    console.print("[yellow]Not yet built.[/yellow]")


@app.command()
def store(project: str) -> None:
    """Step 7 -- store as Layer 2, merge into the unified Layer 1+2 knowledge corpus."""
    console.print("[yellow]Not yet built.[/yellow]")


@app.command()
def run(project: str) -> None:
    """One-shot pipeline: init -> normalize -> rewrite -> assemble -> review -> store."""
    console.print(
        "[yellow]Not yet built.[/yellow] Will chain the commands above once each is real."
    )


if __name__ == "__main__":
    app()
