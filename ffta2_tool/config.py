"""Configuration and builds database loading for ffta2_tool."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = None  # type: ignore[assignment]

# Fields every meta squad build entry must provide to the patcher
REQUIRED_BUILD_KEYS = (
    "name",
    "slot",
    "job_id",
    "primary_set",
    "secondary_set",
    "weapon_id",
    "shield_id",
    "helm_id",
    "armor_id",
    "accessory_id",
)


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
    """Minimal fallback parser for the table/key subset of TOML used by builds.toml."""
    data: dict[str, Any] = {}
    section: dict[str, Any] = data
    for raw_line in content.splitlines():
        line = _strip_comment(raw_line)
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
        section[key.strip()] = _parse_scalar(val.strip())
    return data


def _read_toml(path: Path) -> dict[str, Any]:
    """Reads a TOML file, falling back to the minimal parser when tomllib is absent."""
    content = path.read_text(encoding="utf-8")
    if tomllib is not None:
        try:
            return tomllib.loads(content)
        except tomllib.TOMLDecodeError:
            return _parse_simple_toml(content)
    return _parse_simple_toml(content)


def load_builds(builds_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Loads the meta squad builds database from builds.toml.

    Search priority:
    1. Explicit builds_path argument
    2. Repository-root builds.toml (next to the package)
    3. ./builds.toml (working directory)

    Returns a list of build dicts sorted by slot. Invalid or missing entries are
    skipped; an empty list is returned when no usable builds file is found.
    """
    if builds_path:
        target = Path(os.path.expanduser(str(builds_path)))
        if not target.is_file():
            return []
    else:
        target = Path(__file__).resolve().parent.parent / "builds.toml"
        if not target.is_file():
            local = Path("builds.toml")
            target = local if local.is_file() else target
        if not target.is_file():
            return []

    try:
        raw_data = _read_toml(target)
        raw_builds = raw_data.get("builds", {})
    except OSError:
        return []

    builds: list[dict[str, Any]] = []
    entries = (
        raw_builds if isinstance(raw_builds, list) else (raw_builds.values() if isinstance(raw_builds, dict) else [])
    )
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if not all(key in entry for key in REQUIRED_BUILD_KEYS):
            continue
        builds.append(entry)

    builds.sort(key=lambda b: int(b["slot"]))
    return builds
