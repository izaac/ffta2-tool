"""Minimal, dependency-free TOML reading helpers.

Lives below both ``ffta2_tool.config`` (user config) and ``ffta2_tool.builds``
(builds database) so each layer can parse TOML without importing the other.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = None  # type: ignore[assignment]


def _strip_comment(line: str) -> str:
    """Strips trailing comments not contained inside quotes."""
    in_quote = False
    quote_char = ""
    for i, ch in enumerate(line):
        if ch in ('"', "'"):
            if not in_quote:
                in_quote = True
                quote_char = ch
            elif ch == quote_char:
                in_quote = False
        elif ch == "#" and not in_quote:
            return line[:i].strip()
    return line.strip()


def _parse_scalar(val: str) -> Any:
    """Parses a single TOML scalar or single-line array value."""
    if val.lower() in ("true", "false"):
        return val.lower() == "true"
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        items = []
        for item in inner.split(","):
            item = item.strip()
            if len(item) >= 2 and item[0] == item[-1] and item[0] in "\"'":
                items.append(item[1:-1])
            else:
                try:
                    items.append(int(item, 0))
                except ValueError:
                    items.append(item)
        return items
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        return val[1:-1]
    try:
        return int(val, 0)
    except ValueError:
        return val


def _parse_simple_toml(content: str) -> dict[str, Any]:
    """Minimal fallback parser for the table/key subset of TOML used by builds.toml and config.toml."""
    data: dict[str, Any] = {}
    section: dict[str, Any] = data
    lines = content.splitlines()
    idx = 0
    while idx < len(lines):
        line = _strip_comment(lines[idx])
        idx += 1
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            header = line[1:-1].strip()
            parts = [p.strip() for p in header.split(".") if p.strip()]
            curr = data
            for part in parts:
                curr = curr.setdefault(part, {})
            section = curr
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.strip()
        while val.startswith("[") and not val.endswith("]") and idx < len(lines):
            next_line = _strip_comment(lines[idx])
            idx += 1
            if next_line:
                val = f"{val} {next_line}"
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if inner.endswith(","):
                val = f"[{inner[:-1].strip()}]"
        section[key.strip()] = _parse_scalar(val)
    return data


def read_toml(path: Path) -> dict[str, Any]:
    """Reads a TOML file, falling back to the minimal parser when tomllib is absent."""
    content = path.read_text(encoding="utf-8")
    if tomllib is not None:
        try:
            return tomllib.loads(content)
        except tomllib.TOMLDecodeError:
            return _parse_simple_toml(content)
    return _parse_simple_toml(content)
