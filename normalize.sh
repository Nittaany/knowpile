#!/usr/bin/env bash
# KEPKB Evidence Normalization Pipeline
# Source of truth: manifest.json per project. This script never modifies
# original evidence files — only reads them and writes normalized copies
# into the staging directory.

STAGING_ROOT="$HOME/.kepkb/staging"   # fallback only if user doesn't specify one

# ---------------------------------------------------------------------------
# helper: detect backend exactly the way graphify itself does.
# Priority per graphify's own docs: Gemini → Kimi → Claude → OpenAI →
# DeepSeek → Azure → Bedrock → Ollama → claude-cli (subscription, no key).
# Checking live env vars (not parsing .zshrc/.env files) is correct here —
# however a key got into the shell (export, direnv, keychain, Windows env
# panel), it shows up as $VAR by the time this script runs, on any OS.
# ---------------------------------------------------------------------------
_detect_backend() {
    if [ -n "$GEMINI_API_KEY" ] || [ -n "$GOOGLE_API_KEY" ]; then
        echo "gemini"
    elif [ -n "$MOONSHOT_API_KEY" ]; then
        echo "kimi"
    elif [ -n "$ANTHROPIC_API_KEY" ]; then
        echo "claude"
    elif [ -n "$OPENAI_API_KEY" ]; then
        echo "openai"
    elif [ -n "$DEEPSEEK_API_KEY" ]; then
        echo "deepseek"
    elif [ -n "$AZURE_OPENAI_API_KEY" ] && [ -n "$AZURE_OPENAI_ENDPOINT" ]; then
        echo "azure"
    elif [ -n "$AWS_ACCESS_KEY_ID" ] || [ -f "$HOME/.aws/credentials" ]; then
        echo "bedrock"
    elif [ -n "$OLLAMA_BASE_URL" ] || curl -s -o /dev/null -m 1 "http://localhost:11434" 2>/dev/null; then
        echo "ollama"
    elif command -v claude >/dev/null 2>&1; then
        echo "claude-cli"
    else
        echo ""
    fi
}

# ---------------------------------------------------------------------------
# helper: ask the configured backend for extra ignore patterns based on the
# tree. Low-stakes/mechanical (a filter list, not a knowledge decision) —
# safe to automate. REST-callable backends get a real call; bedrock/claude-cli
# need extra auth plumbing this script doesn't do, so they fall back to the
# static gitignore-seeded list only (graphify itself still uses them fine —
# this only affects the ignore-suggestion convenience step).
# ---------------------------------------------------------------------------
_suggest_ignore_patterns_via_llm() {
    local tree_file="$1"
    local backend="$2"
    local prompt tree_content response

    tree_content=$(cat "$tree_file")
    prompt="You are generating a .gitignore-style ignore list for a tool that \
sends non-code files (docs, PDFs, images, video) to an LLM for semantic \
extraction. Large/heavy binary or media files cause it to hang. Given this \
project file tree, output ONLY ignore patterns (one per line, gitignore \
syntax) for files/dirs that are binary, media, generated, or otherwise \
should NOT be sent to an LLM. No explanations, no markdown, patterns only.

TREE:
$tree_content"

    case "$backend" in
        gemini)
            local key="${GEMINI_API_KEY:-$GOOGLE_API_KEY}"
            # Header auth instead of ?key=... in the URL — a key in the URL
            # is visible to any other local user via `ps aux` while curl runs.
            response=$(curl -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent" \
                -H "x-goog-api-key: ${key}" \
                -H 'Content-Type: application/json' \
                -d "$(jq -n --arg p "$prompt" '{contents:[{parts:[{text:$p}]}]}')")
            echo "$response" | jq -r '.candidates[0].content.parts[0].text // empty' 2>/dev/null
            ;;
        claude)
            response=$(curl -s "${ANTHROPIC_BASE_URL:-https://api.anthropic.com}/v1/messages" \
                -H "x-api-key: ${ANTHROPIC_API_KEY}" \
                -H "anthropic-version: 2023-06-01" \
                -H 'Content-Type: application/json' \
                -d "$(jq -n --arg p "$prompt" --arg m "${ANTHROPIC_MODEL:-claude-sonnet-4-6}" '{model:$m,max_tokens:1000,messages:[{role:"user",content:$p}]}')")
            echo "$response" | jq -r '.content[0].text // empty' 2>/dev/null
            ;;
        openai|deepseek|kimi)
            local url key model
            case "$backend" in
                openai)   url="${OPENAI_BASE_URL:-https://api.openai.com/v1}/chat/completions"; key="$OPENAI_API_KEY"; model="${OPENAI_MODEL:-gpt-4.1-mini}" ;;
                deepseek) url="https://api.deepseek.com/chat/completions"; key="$DEEPSEEK_API_KEY"; model="deepseek-chat" ;;
                kimi)     url="https://api.moonshot.ai/v1/chat/completions"; key="$MOONSHOT_API_KEY"; model="moonshot-v1-8k" ;;
            esac
            response=$(curl -s "$url" \
                -H "Authorization: Bearer ${key}" \
                -H 'Content-Type: application/json' \
                -d "$(jq -n --arg p "$prompt" --arg m "$model" '{model:$m,messages:[{role:"user",content:$p}]}')")
            echo "$response" | jq -r '.choices[0].message.content // empty' 2>/dev/null
            ;;
        azure)
            response=$(curl -s "${AZURE_OPENAI_ENDPOINT}/openai/deployments/\${AZURE_DEPLOYMENT:-gpt-4}/chat/completions?api-version=2024-02-15-preview" \
                -H "api-key: ${AZURE_OPENAI_API_KEY}" \
                -H 'Content-Type: application/json' \
                -d "$(jq -n --arg p "$prompt" '{messages:[{role:"user",content:$p}]}')")
            echo "$response" | jq -r '.choices[0].message.content // empty' 2>/dev/null
            ;;
        ollama)
            response=$(curl -s "${OLLAMA_BASE_URL:-http://localhost:11434}/api/generate" \
                -d "$(jq -n --arg p "$prompt" --arg m "${OLLAMA_MODEL:-llama3}" '{model:$m,prompt:$p,stream:false}')")
            echo "$response" | jq -r '.response // empty' 2>/dev/null
            ;;
        bedrock|claude-cli)
            echo ""   # skip suggestion call; static gitignore-seeded list used as-is
            ;;
        *)
            echo ""
            ;;
    esac
}

# ---------------------------------------------------------------------------
# helper: OS-appropriate install command, since "brew install X" only
# applies to macOS/Linuxbrew — giving the same command to every user causes
# exactly the confusion being flagged here.
# ---------------------------------------------------------------------------
_install_hint() {
    local tool="$1"
    case "$(uname -s 2>/dev/null)" in
        Darwin) echo "brew install $tool" ;;
        Linux)
            if command -v apt >/dev/null 2>&1; then echo "sudo apt install $tool"
            elif command -v dnf >/dev/null 2>&1; then echo "sudo dnf install $tool"
            elif command -v pacman >/dev/null 2>&1; then echo "sudo pacman -S $tool"
            else echo "install '$tool' via your distro's package manager"
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*) echo "choco install $tool  (or: scoop install $tool)" ;;
        *) echo "install '$tool' — see https://github.com/AlDanial/cloc#install or the tool's own docs" ;;
    esac
}

# ---------------------------------------------------------------------------
# 1. DEPENDENCY CHECK — fail fast, never auto-install
# ---------------------------------------------------------------------------
check_dependencies() {
    local missing=0

    # Actually RUN markitdown, don't just check it's on PATH — a broken
    # arch-mismatched pipx venv (arm64/x86_64 mixed numpy, as happened here)
    # still passes `command -v` but crashes the first time it's invoked,
    # which last run silently produced a 0-byte report file mid-normalize
    # instead of failing here where it's actionable.
    if command -v markitdown >/dev/null 2>&1; then
        if ! markitdown --version >/dev/null 2>&1; then
            echo "✗ markitdown is on PATH but crashes when run."
            # The most common real cause on Apple Silicon: Terminal.app itself
            # is running under Rosetta (x86_64 emulation), so pip installs
            # pull an arm64-only wheel (e.g. numpy) that the x86_64 process
            # can't load — an arch mismatch that has nothing to do with which
            # Python install method was used, and confuses everyone the same way.
            if [ "$(uname -s)" = "Darwin" ] && [ "$(sysctl -n sysctl.proc_translated 2>/dev/null)" = "1" ]; then
                echo "  → Detected: this terminal is running under Rosetta (x86_64 emulation) on Apple Silicon."
                echo "    Fix: Finder → Applications → Utilities → Terminal → Get Info → uncheck 'Open using Rosetta',"
                echo "    then restart Terminal and reinstall: pipx uninstall markitdown && pipx install 'markitdown[all]'"
            else
                echo "  Fix: pipx uninstall markitdown && pipx install 'markitdown[all]'   (the [all] extra is required for PDF/docx/xlsx parsing)"
            fi
            missing=1
        fi
    else
        echo "✗ markitdown missing. Run: pipx install 'markitdown[all]'   (the [all] extra is required for PDF/docx/xlsx parsing)"
        # pipx puts binaries in a user-specific bin dir that isn't always on
        # PATH by default — check the common locations and say so explicitly
        # instead of leaving the user to guess, same pattern as backend detection.
        for candidate in "$HOME/.local/bin" "$HOME/Library/Python/3.10/bin" "$HOME/Library/Python/3.11/bin"; do
            if [ -d "$candidate" ] && [ -f "$candidate/markitdown" ]; then
                echo "  Found markitdown in $candidate — add to PATH: export PATH=\"\$PATH:$candidate\""
            fi
        done
        missing=1
    fi

    command -v cloc     >/dev/null 2>&1 || { echo "✗ cloc missing. Run: $(_install_hint cloc)"; missing=1; }
    command -v tree     >/dev/null 2>&1 || { echo "✗ tree missing. Run: $(_install_hint tree)"; missing=1; }
    command -v gum      >/dev/null 2>&1 || { echo "✗ gum missing. Run: $(_install_hint gum)"; missing=1; }
    command -v jq       >/dev/null 2>&1 || { echo "✗ jq missing. Run: $(_install_hint jq)"; missing=1; }
    command -v graphify >/dev/null 2>&1 || { echo "✗ graphify missing. Check its install docs."; missing=1; }
    command -v git      >/dev/null 2>&1 || { echo "✗ git missing. Run: $(_install_hint git)"; missing=1; }

    local backend
    backend=$(_detect_backend)
    if [ -z "$backend" ]; then
        echo "✗ No LLM backend detected. Set one of: GEMINI_API_KEY, MOONSHOT_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY, AZURE_OPENAI_API_KEY(+ENDPOINT), AWS creds, OLLAMA_BASE_URL, or have the 'claude' CLI installed."
        missing=1
    else
        echo "ℹ Detected backend: $backend"
    fi

    if [ "$missing" -eq 1 ]; then
        echo "Fix the above, then re-run."
        return 1
    fi
    echo "✔ All dependencies present."
}

# ---------------------------------------------------------------------------
# helper: pick a DIRECTORY (not a file). Deliberately NOT using `gum file
# --directory` — it has two confirmed open upstream bugs: header/top-item
# get clipped off-screen without a --padding workaround (gum issue #977),
# and directory selection itself can get stuck/non-responsive in some
# environments (gum issue #887). Typing a known folder path and validating
# it exists is more reliable for directory picks, where the path is usually
# already known (unlike hunting for one file among hundreds).
# ---------------------------------------------------------------------------
_pick_directory() {
    local label="$1" default="$2"
    local p
    while true; do
        p=$(gum input --placeholder "Path to: $label" --value "$default")
        p="${p/#\~/$HOME}"   # expand a leading ~
        if [ -n "$p" ] && [ -d "$p" ]; then
            echo "$p"
            return
        fi
        echo "✗ '$p' is not a valid directory."
        if ! gum confirm "Try again?"; then
            echo ""
            return
        fi
    done
}

# ---------------------------------------------------------------------------
# helper: repeatedly collect {type, path} or {path} entries into a JSON array
# ---------------------------------------------------------------------------
_pick_path() {
    # $1 = label for what we're collecting.
    # $2 = space-separated extensions, no dots, e.g. "pdf doc docx pages"
    #      (empty = no filtering, show all files)
    local label="$1" exts="$2"
    local scope search_root rel ext_regex

    if [ -n "$exts" ]; then
        ext_regex="\.($(echo "$exts" | tr ' ' '|'))$"
    fi

    while true; do
        scope=$(gum choose --header "Where should I look for: $label?" "Documents" "Downloads" "Desktop" "Browse a folder")
        case "$scope" in
            Documents) search_root="$HOME/Documents" ;;
            Downloads) search_root="$HOME/Downloads" ;;
            Desktop)   search_root="$HOME/Desktop" ;;
            *)         search_root=$(_pick_directory "folder to search within" "$HOME") ;;
        esac

        if [ -n "$ext_regex" ]; then
            rel=$(cd "$search_root" 2>/dev/null && find . -type f \
                -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/graphify-out/*' \
                2>/dev/null | sed 's|^\./||' | grep -iE "$ext_regex" \
                | gum filter --height 20 --placeholder "Type to search: $label   (Esc to pick a different folder)")
        else
            rel=$(cd "$search_root" 2>/dev/null && find . -type f \
                -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/graphify-out/*' \
                2>/dev/null | sed 's|^\./||' \
                | gum filter --height 20 --placeholder "Type to search: $label   (Esc to pick a different folder)")
        fi

        if [ -n "$rel" ]; then
            echo "$search_root/$rel"
            return
        fi

        if ! gum confirm "Nothing selected in $scope. Try a different folder for: $label?"; then
            echo ""
            return
        fi
    done
}

_collect_typed_array() {
    # $1 = prompt label, $2 = "typed" (asks for a type field) or "plain"
    # $3 = extensions to filter by (space-separated, no dots; empty = all)
    local label="$1" mode="$2" exts="$3"
    local arr="[]"
    while gum confirm "Add a $label?"; do
        if [ "$mode" = "typed" ]; then
            local t p
            t=$(gum choose --header "What type of $label is this?" \
                "final_report" "architecture_report" "functional_report" "research_report" "synopsis" "other")
            if [ "$t" = "other" ]; then
                t=$(gum input --placeholder "Custom type name (no spaces)")
                t=$(echo "$t" | tr ' ' '_')
            fi
            p=$(_pick_path "$label ($t)" "$exts")
            if [ -z "$p" ]; then
                echo "ℹ No file selected — skipping this $label."
                continue
            fi
            echo "✔ $label ($t): $p"
            arr=$(echo "$arr" | jq --arg t "$t" --arg p "$p" '. + [{"type":$t,"path":$p}]')
        else
            local p
            p=$(_pick_path "$label" "$exts")
            if [ -z "$p" ]; then
                echo "ℹ No file selected — skipping this $label."
                continue
            fi
            echo "✔ $label: $p"
            arr=$(echo "$arr" | jq --arg p "$p" '. + [{"path":$p}]')
        fi
    done
    # Guard: a Ctrl+C mid-loop can occasionally still short-circuit this
    # function's output. Never let an empty string reach --argjson downstream.
    [ -z "$arr" ] && arr="[]"
    echo "$arr"
}

# ---------------------------------------------------------------------------
# 2. INVENTORY — interactive manifest builder (Step 1: evidence inventory)
# ---------------------------------------------------------------------------
kepkb-inventory() {
    check_dependencies || return 1

    local project_name staging_dir code_root code_src
    local readme_status readme_path
    local reports research presentations notes
    local arch_status arch_path

    project_name=$(gum input --placeholder "Project name (e.g. major-project-1)")

    local output_base
    output_base=$(_pick_directory "where evidence should be SAVED (staging folder)" "$HOME/Documents")
    staging_dir="$output_base/staging/$project_name"
    mkdir -p "$staging_dir"
    echo "✔ Staging dir: $staging_dir"

    code_root=$(_pick_directory "CODEBASE ROOT folder (top of the project)" "$HOME/Documents")
    echo "✔ Codebase root: $code_root"
    code_src=$(_pick_directory "SOURCE folder graphify should scan" "$code_root/src")
    echo "✔ Source dir for graphify: $code_src"

    if gum confirm "Do you have a README?"; then
        readme_status="collected"
        readme_path=$(find "$code_root" -maxdepth 2 -iname "readme*" 2>/dev/null | gum filter --placeholder "Select the README" --height 10)
        echo "ℹ README is copied as-is — plain-text formats only: md, txt, rst, adoc, org."
        [ -z "$readme_path" ] && readme_path=$(_pick_path "README file" "md txt rst adoc org")
        echo "✔ README: $readme_path"
    else
        readme_status="missing"
        readme_path="null"
    fi

    echo "-- Reports --"
    echo "ℹ Reports must be a format markitdown can actually convert: PDF or DOCX (Word docx only, not legacy .doc, .odt, .rtf, .pages — those produce garbled or empty output)."
    reports=$(_collect_typed_array "report" "typed" "pdf docx")
    echo "-- Research papers/docs --"
    echo "ℹ Same constraint: PDF or DOCX only."
    research=$(_collect_typed_array "research doc" "plain" "pdf docx")
    echo "-- Presentations --"
    echo "ℹ Presentations: PDF or PPTX only (not legacy .ppt, .key, .odp — unsupported by markitdown)."
    presentations=$(_collect_typed_array "presentation" "plain" "pdf pptx")
    echo "-- Notes / engineering checkpoints --"
    echo "ℹ Notes are copied as-is (not converted), so only genuinely plain-text formats work: md, txt, rst, adoc, org."
    notes=$(_collect_typed_array "notes file" "plain" "md txt rst adoc org")

    if gum confirm "Do you have an architecture diagram?"; then
        arch_status="collected"
        echo "ℹ Architecture diagram is copied as-is, not converted — use a directly viewable format: PDF, SVG, PNG, JPG/JPEG, or WEBP. (.drawio/.vsdx files aren't viewable without exporting them first — export to PNG/PDF before selecting.)"
        arch_path=$(_pick_path "architecture diagram" "pdf svg png jpg jpeg webp")
        echo "✔ Architecture diagram: $arch_path"
    else
        arch_status="missing"
        arch_path="null"
    fi

    jq -n \
      --arg project "$project_name" \
      --arg staging "$staging_dir" \
      --arg root "$code_root" \
      --arg src "$code_src" \
      --arg readme_status "$readme_status" \
      --arg readme_path "$readme_path" \
      --argjson reports "$reports" \
      --argjson research "$research" \
      --argjson presentations "$presentations" \
      --argjson notes "$notes" \
      --arg arch_status "$arch_status" \
      --arg arch_path "$arch_path" \
      '{
        project: $project,
        staging_dir: $staging,
        created_at: (now | todate),
        code: { root_dir: $root, src_dir: $src },
        readme: { status: $readme_status, path: $readme_path },
        reports: $reports,
        research: $research,
        presentations: $presentations,
        notes: $notes,
        arch_diagram: { status: $arch_status, path: $arch_path }
      }' > "$staging_dir/manifest.json"

    echo "✔ Manifest saved to $staging_dir/manifest.json"
    echo "ℹ To normalize, run: kepkb-normalize \"$staging_dir\""
}

# ---------------------------------------------------------------------------
# 3. NORMALIZE — run the 5-tool kit, write only normalized output to staging
# ---------------------------------------------------------------------------
kepkb-normalize() {
    local staging_dir="$1"
    if [ -z "$staging_dir" ] || [ ! -d "$staging_dir" ]; then
        echo "Usage: kepkb-normalize <staging-dir>   (the path printed by kepkb-inventory)"
        return 1
    fi

    local manifest="$staging_dir/manifest.json"
    if [ ! -f "$manifest" ]; then
        echo "✗ No manifest found. Run kepkb-inventory first."
        return 1
    fi

    local code_root code_src readme_path arch_path
    code_root=$(jq -r '.code.root_dir' "$manifest")
    code_src=$(jq -r '.code.src_dir' "$manifest")
    readme_path=$(jq -r '.readme.path' "$manifest")
    arch_path=$(jq -r '.arch_diagram.path' "$manifest")

    # README — plain copy, already markdown/text, no conversion needed.
    # Note: this is a genuine small duplication (README/notes are copied, not
    # just normalized), but they're typically a few KB — negligible. The real
    # space risk (whole codebases, PDFs, videos) is avoided because we NEVER
    # copy those raw; only their markitdown/tree/cloc/graphify OUTPUT lands
    # in staging. A symlink would save even that little, but breaks if you
    # later upload/zip the staging folder to hand off — so cp stays.
    if [ "$readme_path" != "null" ] && [ -f "$readme_path" ]; then
        cp "$readme_path" "$staging_dir/00_readme.md"
    fi

    # Architecture diagram — copied as-is (image/PDF, not converted).
    # This step was missing until now: the diagram was collected into the
    # manifest during inventory but never actually landed in staging.
    if [ "$arch_path" != "null" ] && [ -f "$arch_path" ]; then
        local arch_ext="${arch_path##*.}"
        cp "$arch_path" "$staging_dir/10_arch_diagram.$arch_ext"
        echo "✔ Staged architecture diagram"
    fi

    # Reports — markitdown each one, named by its type
    jq -c '.reports[]' "$manifest" | while read -r row; do
        local rtype rpath outname
        rtype=$(echo "$row" | jq -r '.type')
        rpath=$(echo "$row" | jq -r '.path')
        outname="01_report_${rtype}.md"
        echo "⏳ Normalizing report: $rtype"
        markitdown "$rpath" > "$staging_dir/$outname"
        echo "✔ Done."
    done

    # Research docs — markitdown each
    local i=1
    jq -c '.research[]' "$manifest" | while read -r row; do
        local rpath
        rpath=$(echo "$row" | jq -r '.path')
        echo "⏳ Normalizing research doc $i"
        markitdown "$rpath" > "$staging_dir/02_research_${i}.md"
        echo "✔ Done."
        i=$((i+1))
    done

    # Presentations — markitdown each (keynote unsupported, ppt/pptx only)
    i=1
    jq -c '.presentations[]' "$manifest" | while read -r row; do
        local ppath
        ppath=$(echo "$row" | jq -r '.path')
        echo "⏳ Normalizing presentation $i"
        markitdown "$ppath" > "$staging_dir/03_presentation_${i}.md"
        echo "✔ Done."
        i=$((i+1))
    done

    # Notes — plain copy (already text/markdown)
    i=1
    jq -c '.notes[]' "$manifest" | while read -r row; do
        local npath
        npath=$(echo "$row" | jq -r '.path')
        cp "$npath" "$staging_dir/04_notes_${i}.md"
        i=$((i+1))
    done

    # cloc + git log (tree already ran earlier, before graphify)
    # NOTE: deliberately not using `gum spin -- bash -c "cmd '$var' ..."` here.
    # Building a shell command as a string and re-parsing it via bash -c means
    # a folder name containing a single quote or backtick can break out of
    # quoting — a real command-injection risk, not hypothetical. Calling the
    # binary directly with native "$var" quoting is injection-safe because
    # the shell only parses it once, correctly, with no re-parsing step.
    echo "⏳ Generating cloc metrics..."
    cloc "$code_root" --exclude-dir=.git,node_modules,venv --md > "$staging_dir/06_cloc.md" 2>/dev/null
    echo "✔ Done."

    if [ -d "$code_root/.git" ]; then
        echo "⏳ Exporting git log..."
        ( cd "$code_root" && git log --stat > "$staging_dir/07_git_log.txt" )
        echo "✔ Done."
    else
        echo "ℹ No .git found in $code_root — skipping git log."
    fi

    # Graphify target — ask now, since the ignore file and tree review below
    # both depend on knowing which dir graphify will actually scan.
    local graph_target
    graph_target=$(_pick_directory "folder graphify should scan (confirm/override)" "$code_src")
    echo "✔ Graphify will scan: $graph_target"

    # .graphifyignore — build from .gitignore if one exists (root or src),
    # falling back to a generic list only if neither is found. Never
    # overwrite a .graphifyignore the user already wrote by hand.
    if [ ! -f "$code_root/.graphifyignore" ]; then
        local base_ignore=""
        if [ -f "$graph_target/.gitignore" ]; then
            base_ignore="$graph_target/.gitignore"
        elif [ -f "$code_root/.gitignore" ]; then
            base_ignore="$code_root/.gitignore"
        fi

        if [ -n "$base_ignore" ]; then
            cp "$base_ignore" "$code_root/.graphifyignore"
            echo "ℹ Seeded .graphifyignore from $base_ignore"
        else
            touch "$code_root/.graphifyignore"
            echo "ℹ No .gitignore found — starting .graphifyignore from scratch"
        fi

        # Always append graphify-specific noise (binaries/media Gemini chokes on),
        # regardless of whether we seeded from .gitignore, deduped.
        cat <<'EOF' >> "$code_root/.graphifyignore"
graphify-out/
*.png
*.jpg
*.jpeg
*.svg
*.ico
*.webp
*.npy
*.tflite
*.pyc
*.pdf
EOF
        sort -u "$code_root/.graphifyignore" -o "$code_root/.graphifyignore"
    else
        echo "ℹ Existing .graphifyignore found — leaving it untouched."
    fi

    # Tree runs BEFORE graphify now, so you can review project shape and
    # optionally hand it to an LLM (this chat, or graphify's own gemini call)
    # to sanity-check .graphifyignore before the semantic extraction step —
    # this is what actually prevents the "stuck on semantic extraction" hang.
    echo "⏳ Extracting file tree..."
    tree -a -I '.git|node_modules|venv|__pycache__' "$code_root" > "$staging_dir/05_tree.txt"
    echo "✔ Tree extracted."

    echo "ℹ Tree saved to $staging_dir/05_tree.txt"

    local backend
    backend=$(_detect_backend)
    if [ -z "$backend" ]; then
        echo "✗ No LLM backend detected — graphify's semantic pass needs one. Set one of the vars listed in check_dependencies."
        return 1
    fi

    # NOTE: deliberately NOT using `gum spin -- bash -c "func ..."` here. This
    # script gets sourced into zsh (via .zshrc), and zsh does not support
    # `export -f` the way bash does — an exported function never survives the
    # handoff into a spawned bash subshell, so it fails silently with
    # "command not found". Calling the function directly in the current shell
    # avoids the whole cross-shell export problem.
    echo "⏳ Asking $backend for extra ignore patterns from tree..."
    local suggested
    suggested=$(_suggest_ignore_patterns_via_llm "$staging_dir/05_tree.txt" "$backend")
    echo "✔ Done."

    if [ -n "$suggested" ]; then
        echo "$suggested" >> "$code_root/.graphifyignore"
        sort -u "$code_root/.graphifyignore" -o "$code_root/.graphifyignore"
        echo "ℹ Auto-appended LLM-suggested patterns based on your project tree."
    else
        echo "ℹ LLM suggestion call failed or returned nothing — falling back to static list only."
    fi

    echo "ℹ Final .graphifyignore:"
    cat "$code_root/.graphifyignore"
    if ! gum confirm "Look complete? (this list is now AI-suggested + gitignore-seeded, just confirm or edit manually)"; then
        echo "→ Edit $code_root/.graphifyignore manually, then re-run kepkb-normalize on this staging dir."
        return 1
    fi

    echo "Running graphify with backend=$backend (may take a while)..."
    ( cd "$code_root" && graphify extract "$graph_target" --backend "$backend" )
    ( cd "$code_root" && graphify cluster-only "$graph_target" --no-label --backend "$backend" )

    # Resolve where graphify's output actually landed. graph_target may be
    # absolute (as it was here — the default came from an absolute code_src)
    # or relative to code_root; blindly prepending code_root broke on the
    # absolute case last run, doubling the path.
    local resolved_target
    case "$graph_target" in
        /*) resolved_target="$graph_target" ;;
        *)  resolved_target="$code_root/$graph_target" ;;
    esac

    if [ -f "$resolved_target/graphify-out/GRAPH_REPORT.md" ]; then
        cp "$resolved_target/graphify-out/GRAPH_REPORT.md" "$staging_dir/08_graph_report.md"
        echo "✔ Staged GRAPH_REPORT.md"
    else
        echo "✗ GRAPH_REPORT.md not found at $resolved_target/graphify-out/ — check manually."
    fi

    # graph.json is the full structured graph (nodes/edges/communities) —
    # worth staging alongside the narrative report. GRAPH_REPORT.md is the
    # human-readable summary for extraction; graph.json is the queryable
    # structure, useful later for cross-checking claims during validation.
    if [ -f "$resolved_target/graphify-out/graph.json" ]; then
        cp "$resolved_target/graphify-out/graph.json" "$staging_dir/09_graph.json"
        echo "✔ Staged graph.json"
    fi

    echo ""
    echo "✔ Normalization complete. Evidence staged in: $staging_dir"
    ls -la "$staging_dir"
}
