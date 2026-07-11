# KEPKB — Evidence Normalization Pipeline

**Checkpoint 0** of a personal knowledge base project: turning fragmented project evidence into a single, LLM-ready staging folder.

## The problem

Most engineers — students and professionals alike — end up with their project evidence scattered: code in one folder, the final report in Downloads, research docs somewhere else, the repo on GitHub. When it's time to actually explain or document the project (interviews, a portfolio, a resume), that evidence has to be hunted down and re-read from scratch every time.

**KEPKB** (Knowledge Extraction Personal Knowledge Base) is an attempt to fix that — not by archiving prose, but by building a pipeline that turns scattered evidence into structured, semantic project knowledge that can be regenerated into resumes, interviews, or documentation on demand.

## What this is

`normalize.sh` is Stage 1: **evidence normalization**, not knowledge extraction. It doesn't understand your project — it collects everything relevant (README, reports, research, presentations, notes, architecture diagrams, codebase structure, commit history, and a graphify-generated semantic code graph) and converts it all into clean, staged Markdown/JSON/text, ready to hand to an LLM for the actual extraction step.

It's a zsh/bash script, interactive via [`gum`](https://github.com/charmbracelet/gum), and runs a fixed tool kit identically across every project so output stays comparable project to project:

- [`markitdown`](https://github.com/microsoft/markitdown) — PDF/DOCX/PPTX → Markdown
- [`graphify`](https://pypi.org/project/graphifyy/) — local AST parsing + LLM-backed semantic code graph
- `cloc` — language/size metrics
- `git log` — bounded commit history (first 50 + last 450 commits)
- native `tree` — project structure

## Setup

```bash
brew install gum jq cloc tree
pip install markitdown[all] --break-system-packages   # or via pipx
# graphify: see https://pypi.org/project/graphifyy/
export GEMINI_API_KEY="..."   # or ANTHROPIC_API_KEY / OPENAI_API_KEY / etc.

mv normalize.sh ~/.kepkb/normalize.sh
echo '[ -f ~/.kepkb/normalize.sh ] && source ~/.kepkb/normalize.sh' >> ~/.zshrc
source ~/.zshrc
```

## Usage

```bash
check_dependencies      # verify everything's installed and a backend key is set
kepkb-inventory          # interactive: locate evidence, builds manifest.json
kepkb-normalize <staging_dir>   # runs the full pipeline, stages normalized output
```

Every path is picked via a fuzzy `gum filter` search scoped to Documents/Downloads/Desktop — no hunting through folders by hand.

## Why "Checkpoint 0"

This script works, but building it surfaced a pattern worth being honest about: bash sourced into an interactive shell has real, silent failure modes — commands that mean one thing in bash and something entirely different in zsh (`export -f`, `read -e`), and third-party CLI tools (`gum`) with confirmed upstream rendering bugs that took several rounds to work around properly. None of that is a reason to distrust the *output* — every bug below was found, root-caused, and fixed — but it's why this is being treated as a foundation, not the final tool.

Real bugs found and fixed during development:
- A pipx-installed `markitdown` silently crashing on an arch mismatch, producing empty output with no error surfaced
- `zsh` not supporting `export -f` the way `bash` does — a function call that failed silently across a subshell boundary
- `gum spin` silently discarding a wrapped command's output when redirected to a file (confirmed upstream bug)
- Command-injection risk from building shell commands as interpolated strings instead of using native quoting
- An API key exposed via the process list (`ps aux`) from being passed as a URL parameter instead of a header
- Two separate confirmed upstream `gum file` bugs (invisible headers, directory selection hanging)

Full write-up of each, with root causes, is in the project's internal engineering log (not published here — this file is the short version).

**What's next:** a Python CLI (`kepkb.py`) rebuilding the same pipeline without the shell-dialect fragility, scoped deliberately to feature-parity with this script first — no scope creep — before any of it becomes an actual product.

## Status

- ✅ Evidence collection, normalization, and semantic-graph generation: working
- ⬜ Knowledge extraction, validation, and Layer 2 file generation: not yet started — the actual point of this whole pipeline
- ⬜ Python rewrite: in progress

## License

MIT (or whatever you want to license this repo as — update before publishing)
