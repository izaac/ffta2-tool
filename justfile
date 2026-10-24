# Final Fantasy Tactics A2 (FFTA2) Tool - Justfile

default:
    @just --list

# Install ffta2-tool in editable mode (supports uv or standard pip)
install:
    @if command -v uv >/dev/null 2>&1; then \
        uv pip install -e . ; \
    else \
        python3 -m pip install -e . ; \
    fi

# Run test suite (extra args go to pytest, e.g. `just test -k crypto -v`)
test *args:
    #!/usr/bin/env bash
    set -euo pipefail
    if uv run --quiet pytest --version >/dev/null 2>&1; then
        exec uv run pytest {{args}}
    elif command -v pytest >/dev/null 2>&1; then
        exec pytest {{args}}
    elif python3 -m pytest --version >/dev/null 2>&1; then
        exec python3 -m pytest {{args}}
    else
        echo "[INFO] pytest unavailable, running the standalone script suites"
        PYTHONPATH=. python3 tests/test_crypto.py
        PYTHONPATH=. python3 tests/test_patcher.py
        PYTHONPATH=. python3 tests/test_battle_bot.py
        PYTHONPATH=. python3 tests/test_arm_tools.py
    fi

md_targets := "docs/*.md README.md"

# Lint, format-check and test the codebase
check: test pycheck pyfmt-check (mdlint "scan")

# Format codebase
fmt: pyfmt (mdlint "fix")

[private]
mdlint action:
    @if uv run --quiet pymarkdown version >/dev/null 2>&1; then \
        uv run pymarkdown --config .pymarkdown.json {{action}} {{md_targets}} ; \
    elif command -v pymarkdown >/dev/null 2>&1; then \
        pymarkdown --config .pymarkdown.json {{action}} {{md_targets}} ; \
    elif python3 -m pymarkdownlnt version >/dev/null 2>&1; then \
        python3 -m pymarkdownlnt --config .pymarkdown.json {{action}} {{md_targets}} ; \
    else \
        uvx pymarkdownlnt --config .pymarkdown.json {{action}} {{md_targets}} ; \
    fi

[private]
pycheck:
    @if uv run --quiet ruff --version >/dev/null 2>&1; then \
        uv run ruff check . ; \
    elif command -v ruff >/dev/null 2>&1; then \
        ruff check . ; \
    elif python3 -m ruff --version >/dev/null 2>&1; then \
        python3 -m ruff check . ; \
    else \
        uvx ruff check . ; \
    fi

[private]
pyfmt-check:
    @if uv run --quiet ruff --version >/dev/null 2>&1; then \
        uv run ruff format --check . ; \
    elif command -v ruff >/dev/null 2>&1; then \
        ruff format --check . ; \
    elif python3 -m ruff --version >/dev/null 2>&1; then \
        python3 -m ruff format --check . ; \
    else \
        uvx ruff format --check . ; \
    fi

[private]
pyfmt:
    @if uv run --quiet ruff --version >/dev/null 2>&1; then \
        uv run ruff format . && uv run ruff check --fix . ; \
    elif command -v ruff >/dev/null 2>&1; then \
        ruff format . && ruff check --fix . ; \
    elif python3 -m ruff --version >/dev/null 2>&1; then \
        python3 -m ruff format . && python3 -m ruff check --fix . ; \
    else \
        uvx ruff format . && uvx ruff check --fix . ; \
    fi

# Validate a save file (checks custom target, backup dir, or example save)
validate save="":
    #!/usr/bin/env bash
    target="{{save}}"
    if [ -z "$target" ]; then
        if [ -f "$HOME/Documents/FFTA2_Backups/071 Final Fantasy Tactics A2 - after first pub - stable.sav" ]; then
            target="$HOME/Documents/FFTA2_Backups/071 Final Fantasy Tactics A2 - after first pub - stable.sav"
        elif [ -f "examples/FFTA2_Meta_Squad_Hard.sav" ]; then
            target="examples/FFTA2_Meta_Squad_Hard.sav"
        fi
    fi
    if [ -n "$target" ] && [ -f "$target" ]; then
        PYTHONPATH=. python3 -m ffta2_tool.cli validate "$target"
    else
        echo "No save file found. Specify one via: just validate <path>"
        exit 1
    fi

# Run headless melonDS automated test runner
melonds-test rom save="examples/FFTA2_Meta_Squad_Hard.sav" out="examples/melonds/output":
    ./examples/melonds/run_headless_test.sh "{{rom}}" "{{save}}" "{{out}}"

# Win the E5 quicksave battle in melonDS, save on the world map, reload and verify (needs run_e5_full.sh first)
melonds-e6 out="/tmp":
    OUT_DIR="{{out}}" python3 examples/melonds/e2e/scenarios/run_e6_battle.py
