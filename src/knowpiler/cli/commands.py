"""
knowpiler CLI -- the interface layer.

This file's only job is: collect input from a terminal (via InquirerPy),
and hand plain values to knowpiler.core. It must never construct a
Manifest or Config directly, never touch Pydantic, and never contain
business rules. A future web interface will collect the exact same plain
values from an HTTP request body and call the exact same core functions.
"""
from __future__ import annotations

import typer
from InquirerPy import inquirer
from InquirerPy.validator import PathValidator
from rich.console import Console

from knowpiler.core import config as cfg
from knowpiler.core.doctor import print_report, run_all
from knowpiler.core.manifest import create_manifest

app = typer.Typer(help="knowpiler -- knowledge compiler for engineers.")
console = Console()

REPORT_TYPES = ["final_report", "architecture_report", "functional_report", "research_report", "synopsis", "other"]

DIR_VALIDATOR = PathValidator(is_dir=True, message="Path does not exist or is not a directory")
FILE_VALIDATOR = PathValidator(is_file=True, message="Path does not exist or is not a file")


@app.command()
def doctor() -> None:
    """Check environment: markitdown, graphify, cloc, git, architecture."""
    console.print("[bold]knowpiler doctor[/bold]")
    ok = print_report(run_all())
    if not ok:
        console.print("\n[red]Fix the above, then re-run `knowpiler doctor`.[/red]")
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
    
    # Billing Transparency Warning for Cloud Providers
    if backend != "ollama":
        console.print(
            f"\n[cyan]◆ BILLING NOTICE[/cyan] [dim]Setting your backend to '{backend}' means you will be billed by the provider for API usage.\n"
            "                 This includes semantic extraction, knowledge file rewriting, and final artifact generation.\n"
            "                 Please ensure you have a valid API key and understand the costs.\n"
        )
        
    # Local Model Hint for OpenAI compatible endpoints
    if backend == "openai":
        console.print(
            "[cyan]◇ LOCAL MODEL[/cyan] [dim]If using a local OpenAI-compatible server (LM Studio, vLLM, etc.),\n"
            "                 just paste your base URL (e.g., http://localhost:8080/v1) below.\n"
            "                 We will auto-configure the rest.[/dim]\n"
        )
    
    # The interceptor: if they don't have the key set, securely ask for it now
    if not cfg.backend_ready(backend) and backend != "ollama":
        env_var = cfg.ENV_VAR_BY_BACKEND[backend]
        
        # Dynamically change the prompt text based on backend
        prompt_msg = f"Enter your {backend} API key (input is hidden):"
        if backend == "openai":
            prompt_msg = f"Enter your {backend} API key OR Local Base URL (input is hidden):"
            
        # Masked password prompt using InquirerPy
        user_input = inquirer.secret(message=prompt_msg).execute()
        
        if user_input:
            # SMART ROUTING: Did they paste a URL?
            if backend == "openai" and user_input.startswith("http"):
                cfg.save_credential("OPENAI_BASE_URL", user_input.strip())
                cfg.save_credential("OPENAI_API_KEY", "sk-local-dummy-key")
                console.print("[green]Local base URL saved securely! Dummy API key auto-generated.[/green]\n")
            else:
                cfg.save_credential(env_var, user_input.strip())
                console.print("[green]API key saved securely to ~/.knowpiler/.env[/green]\n")
        else:
            console.print("[red]Backend setup skipped.[/red]\n")
            raise typer.Exit(code=1)

    c = cfg.load_config()
    c.backend = backend
    cfg.save_config(c)
    console.print(f"[green]Backend successfully set to {backend}.[/green]")


@app.command()
def init(project: str = typer.Argument(..., help="Project name, e.g. 'Semantic Web - guide allocation'")) -> None:
    """Step 1 -- interactive evidence inventory. Builds and saves manifest.json."""
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
    console.print(f"[dim]Next: knowpiler normalize {project}[/dim]")


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
        "(`knowpiler config set-backend <name>`) and real staged output from `normalize` first."
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
