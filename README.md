# knowpile

**knowpile** is a personal knowledge compiler for engineers.

Its goal is simple: take scattered project evidence, convert it into semantically faithful Markdown knowledge files, and use that canonical context with LLMs (Gemini, Claude, GPT, etc.) to generate better career artifacts (resume, LinkedIn, GitHub profile refinement, interview prep, and job-facing content).

## Why knowpile exists

Engineering evidence is usually fragmented across:

- READMEs
- reports/research PDFs
- architecture diagrams
- slides/notes
- source code and git history

When this context is fed to LLMs in an ad-hoc way, outputs become generic, inconsistent, or drift away from real implementation details.

knowpile is built to preserve semantic meaning first, so downstream outputs stay grounded.

## What this repo currently is (Checkpoint 0)

Current implementation is the first operational checkpoint: **evidence normalization + staging**.

`normalize.sh` collects project evidence and produces structured staged outputs (Markdown/JSON/text), including semantic graph support, so the project context is ready for higher-quality LLM reasoning.

It is the foundation layer, not the full product yet.

## High-level flow

1. Collect project evidence
2. Normalize and semantically structure it (loss-aware, fidelity-first)
3. Produce canonical `.md`-centric context files
4. Feed those files to LLMs for downstream artifact generation

## Tooling used in checkpoint implementation

- [`markitdown`](https://github.com/microsoft/markitdown) for document-to-Markdown conversion
- [`graphify`](https://pypi.org/project/graphifyy/) for semantic code graph generation
- `cloc`, `tree`, and `git log` for project metrics and structure evidence
- [`gum`](https://github.com/charmbracelet/gum) for interactive CLI workflow

## Setup

```bash
brew install gum jq cloc tree
pipx install "markitdown[all]"   # or equivalent pip install
# graphify: see https://pypi.org/project/graphifyy/
export GEMINI_API_KEY="..."      # or ANTHROPIC_API_KEY / OPENAI_API_KEY / etc.

source normalize.sh
```

## Usage

```bash
check_dependencies
kepkb-inventory
kepkb-normalize <staging_dir>
```

> Note: command names still use legacy prefixes in this checkpoint script. Branding and product identity are now **knowpile**.

## Status

- ✅ Evidence ingestion and normalization pipeline is working
- ⏸️ Project was paused mid-way before full knowledge extraction/validation automation
- 🔜 Next milestone: robust canonical knowledge compilation and downstream artifact generation workflow

## License

MIT
