"""
knowpiler CLI -- the interface layer.

This file's only job is: collect input from a terminal (via InquirerPy),
and hand plain values to knowpiler.core. It must never construct a
Manifest or Config directly, never touch Pydantic, and never contain
business rules. A future web interface will collect the exact same plain
values from an HTTP request body and call the exact same core functions.
"""
from __future__ import annotations

from pathlib import Path

import typer
from InquirerPy import inquirer
from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError, Validator
from rich.console import Console

from knowpiler.core import config as cfg
from knowpiler.core.doctor import print_report, run_all
from knowpiler.core.manifest import create_manifest
from knowpiler.core.utils import clean_path

app = typer.Typer(help="knowpiler -- knowledge compiler for engineers.")
console = Console()

REPORT_TYPES = ["final_report", "architecture_report", "functional_report", "research_report", "synopsis", "other"]


class CleanPathValidator(Validator):
    """Validates a path after normalizing it via clean_path() first.

    InquirerPy's own PathValidator checks the raw buffer text -- so a path
    dragged from Finder/Explorer (backslash-escaped) or copied via "Copy
    as Pathname" (quote-wrapped) gets rejected and reprompted forever,
    since the literal escaped/quoted string never exists on disk. This
    cleans first, then checks -- confirmed fix against both real-world
    patterns hit during Level 2.2 testing.
    """

    def __init__(self, is_file: bool = False, is_dir: bool = False, message: str = "Path does not exist") -> None:
        self._is_file = is_file
        self._is_dir = is_dir
        self._message = message

    def validate(self, document: Document) -> None:
        raw = document.text
        if not raw:
            raise ValidationError(message=self._message, cursor_position=len(raw))
        candidate = Path(clean_path(raw)).expanduser()

        if self._is_dir and not candidate.is_dir():
            raise ValidationError(message=self._message, cursor_position=len(raw))
        if self._is_file and not candidate.is_file():
            raise ValidationError(message=self._message, cursor_position=len(raw))


DIR_VALIDATOR = CleanPathValidator(is_dir=True, message="Path does not exist or is not a directory")
FILE_VALIDATOR = CleanPathValidator(is_file=True, message="Path does not exist or is not a file")

@app.callback()
def main_callback() -> None:
    """knowpiler - Knowledge compilation engine"""
    cfg.hydrate_env()

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


@config_app.command("set-backend")
def config_set_backend(
    backend: str = typer.Argument(..., help=f"one of {cfg.SUPPORTED_BACKENDS}"),
    force: bool = typer.Option(False, "--force", "-f", help="Force update existing credentials and model")
) -> None:
    if backend not in cfg.SUPPORTED_BACKENDS:
        console.print(f"[red]Unknown backend '{backend}'.[/red] Choose from: {cfg.SUPPORTED_BACKENDS}")
        raise typer.Exit(code=1)
    
    # Smart UX Routing for Notices
    if backend == "openai":
        console.print(
            "\n[cyan]◇ LOCAL SERVER (FREE)[/cyan] [dim]If using LM Studio/vLLM, paste your base URL (http://...) below.[/dim]\n"
            "[cyan]◆ CLOUD API (PAID)[/cyan]    [dim]If using OpenAI's cloud API, pasting a key means you will be billed.[/dim]\n"
        )
    elif backend != "ollama":
        console.print(
            f"\n[cyan]◆ BILLING NOTICE[/cyan]      [dim]Setting your backend to '{backend}' means you will be billed\n"
            "                      by the provider for API usage. This includes semantic extraction,\n"
            "                      knowledge file rewriting, and final artifact generation.[/dim]\n"
        )

    # 1. Load config early to manage state transitions
    c = cfg.load_config()
    
    # 2. STATE PURGE: If switching backends, wipe out any old model configurations
    if c.backend != backend:
        c.model = None
        
    c.backend = backend
    
    # The interceptor: triggers if missing, OR if the user explicitly passes --force
    if (not cfg.backend_ready(backend) or force) and backend != "ollama":
        env_var = cfg.ENV_VAR_BY_BACKEND[backend]
        
        prompt_msg = f"Enter your {backend} API key (input is hidden):"
        if backend == "openai":
            prompt_msg = f"Enter your {backend} API key OR Local Base URL (input is hidden):"
            
        user_input = inquirer.secret(message=prompt_msg).execute()
        
        if user_input:
            # SMART ROUTING: Did they paste a URL?
            if backend == "openai" and user_input.startswith("http"):
                cfg.save_credential("OPENAI_BASE_URL", user_input.strip())
                cfg.save_credential("OPENAI_API_KEY", "sk-local-dummy-key")
                console.print("[green]Local base URL saved securely! Dummy API key auto-generated.[/green]")
                
                # Close the UX gap: Ask for the explicit local model name
                local_model = inquirer.text(
                    message="Enter the exact model name running on your server (e.g., 'llama-3-8b'):"
                ).execute()
                
                c.model = local_model.strip() if local_model else "local-model"
                cfg.save_config(c)
                console.print(f"\n[green]Backend successfully set to {backend} (routing to: {c.model}).[/green]")
                return  # Exit early to prevent standard saving below
            else:
                # TRANSITION CLEANUP: If they pasted a real API key for OpenAI, we must destroy 
                # any old Base URL and model data so it doesn't hijack the cloud request.
                if backend == "openai":
                    cfg.unset_credential("OPENAI_BASE_URL")
                    c.model = None 

                cfg.save_credential(env_var, user_input.strip())
                console.print("[green]API key saved securely to ~/.knowpiler/.env[/green]\n")
        else:
            console.print("[red]Backend setup aborted.[/red]\n")
            raise typer.Exit(code=1)

    # 3. Final save for standard paths
    cfg.save_config(c)
    console.print(f"[green]Backend successfully set to {backend}.[/green]")

    
@config_app.command("show")
def config_show() -> None:
    """Display current configuration and credential status (vault + system env)."""
    c = cfg.load_config()
    console.print("\n[bold]⚙️  Current Configuration (config.toml)[/bold]")
    console.print(f"  Active Backend : [cyan]{c.backend or 'Not set'}[/cyan]")
    console.print(f"  Active Model   : [cyan]{c.model or 'Default'}[/cyan]")

    console.print("\n[bold]🔒 Credential Status[/bold]")

    status = cfg.get_credential_status()
    for backend, info in status.items():
        source = info["source"]
        if source == "vault":
            color, label = "green", "✓ Ready (vault)"
        elif source == "system":
            color, label = "blue", "✓ Ready (system)"
        else:
            color, label = "dim", "✗ Missing"
        # Pad the plain label first, then wrap in markup -- padding a
        # string that already contains [color]...[/color] tags misaligns
        # columns, since the tag characters count toward the padded width
        # even though Rich strips them at render time.
        console.print(f"  [{color}]{label:<18}[/{color}] : {backend} ({info['env_var']})")

    # Special check for the OpenAI local-server base URL interceptor --
    # same vault-vs-system distinction applies here too, not hardcoded.
    local = cfg.get_local_base_url_status()
    if local:
        url, source = local
        console.print(f"  [green]{'✓ Ready (' + source + ')':<18}[/green] : openai local URL -> [cyan]{url}[/cyan]")

    console.print()


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
        # Default is root_dir itself, not a hardcoded "/src" guess --
        # confirmed wrong against real project trees (Laravel's app/,
        # the LMS backend's controllers/) that have no src/ folder at all.
        default=root_dir,
        only_directories=True,
        validate=DIR_VALIDATOR,
    ).execute()
    # Single prompt for now -- wrapped into the list the schema now
    # expects. The full multi-root collection loop (add another source
    # root? -> yes/no, repeat) is a separate, larger UX piece, not built
    # in this pass.
    src_dirs = [src_dir]

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
        src_dirs=src_dirs,
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