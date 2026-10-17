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

# Run test suite
test:
    PYTHONPATH=. python3 tests/test_crypto.py
    PYTHONPATH=. python3 tests/test_patcher.py

md_targets := "docs/*.md README.md"
md_ignores := "MD013,MD024,MD026,MD033,MD036,MD041"

# Lint and check codebase
check: test pycheck (mdlint "scan")

# Format codebase
fmt: pyfmt (mdlint "fix")

[private]
mdlint action:
    @if command -v uvx >/dev/null 2>&1; then \
        uvx pymarkdownlnt -d {{md_ignores}} {{action}} {{md_targets}} ; \
    elif command -v pymarkdownlnt >/dev/null 2>&1; then \
        pymarkdownlnt -d {{md_ignores}} {{action}} {{md_targets}} ; \
    elif python3 -m pymarkdownlnt version >/dev/null 2>&1; then \
        python3 -m pymarkdownlnt -d {{md_ignores}} {{action}} {{md_targets}} ; \
    fi

[private]
pycheck:
    @if command -v uvx >/dev/null 2>&1; then \
        uvx ruff check . ; \
    elif command -v ruff >/dev/null 2>&1; then \
        ruff check . ; \
    else \
        python3 -m ruff check . ; \
    fi

[private]
pyfmt:
    @if command -v uvx >/dev/null 2>&1; then \
        uvx ruff format . && uvx ruff check --fix . ; \
    elif command -v ruff >/dev/null 2>&1; then \
        ruff format . && ruff check --fix . ; \
    else \
        python3 -m ruff format . && python3 -m ruff check --fix . ; \
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
