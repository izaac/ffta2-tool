"""Configuration and builds database loading for ffta2_tool."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = None  # type: ignore[assignment]

_PACKAGE_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_ROOT.parent

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


def _resolve_data_file(name: str) -> Path:
    """Resolves a bundled TOML data file across repo and package-data layouts.

    Search order: repository root, then ``ffta2_tool/data/`` next to this module.
    """
    for candidate in (_REPO_ROOT / name, _PACKAGE_ROOT / "data" / name):
        if candidate.is_file():
            return candidate
    return _PACKAGE_ROOT / "data" / name


DEFAULT_CONFIG_EXAMPLE_PATH = _resolve_data_file("config.example.toml")


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


def _read_toml(path: Path) -> dict[str, Any]:
    """Reads a TOML file, falling back to the minimal parser when tomllib is absent."""
    content = path.read_text(encoding="utf-8")
    if tomllib is not None:
        try:
            return tomllib.loads(content)
        except tomllib.TOMLDecodeError:
            return _parse_simple_toml(content)
    return _parse_simple_toml(content)


def get_default_backup_dir(custom_dir: str | Path | None = None) -> Path:
    """Returns the centralized directory for timestamped save backups."""
    if custom_dir:
        return Path(os.path.expanduser(str(custom_dir)))
    env_dir = os.environ.get("FFTA2_BACKUP_DIR")
    if env_dir:
        return Path(os.path.expanduser(env_dir))
    return Path.home() / "Documents" / "FFTA2_Backups"


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Loads user configuration from config.toml if available.

    Search priority:
    1. Explicit config_path argument (or FFTA2_CONFIG environment variable)
    2. ./config.toml (current working directory)
    3. ~/.config/ffta2-tool/config.toml
    """
    candidates: list[Path] = []
    if config_path:
        candidates.append(Path(os.path.expanduser(str(config_path))))
    elif os.environ.get("FFTA2_CONFIG"):
        candidates.append(Path(os.path.expanduser(os.environ["FFTA2_CONFIG"])))
    else:
        candidates.append(Path("config.toml"))
        candidates.append(Path.home() / ".config" / "ffta2-tool" / "config.toml")

    for path in candidates:
        if path.is_file():
            try:
                raw = _read_toml(path)
                return {
                    "paths": raw.get("paths", {}) if isinstance(raw.get("paths"), dict) else {},
                    "defaults": raw.get("defaults", {}) if isinstance(raw.get("defaults"), dict) else {},
                }
            except OSError:
                break

    return {"paths": {}, "defaults": {}}


def _resolve_builds_file(builds_path: str | Path | None = None) -> Path | None:
    """Resolves the builds database file.

    Search priority:
    1. Explicit builds_path argument
    2. Repository-root builds.toml
    3. ./builds.toml (current working directory)
    4. Bundled ffta2_tool/data/builds.toml (installed wheels)
    """
    if builds_path:
        target = Path(os.path.expanduser(str(builds_path)))
        return target if target.is_file() else None
    repo_root = _REPO_ROOT / "builds.toml"
    if repo_root.is_file():
        return repo_root
    local = Path("builds.toml")
    if local.is_file():
        return local
    pkg_data = _PACKAGE_ROOT / "data" / "builds.toml"
    return pkg_data if pkg_data.is_file() else None


def load_builds_by_key(builds_path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Loads builds from builds.toml keyed by their TOML table key (e.g. 'luso', 'nu_mou')."""
    target = _resolve_builds_file(builds_path)
    if target is None:
        return {}
    try:
        raw_data = _read_toml(target)
        raw_builds = raw_data.get("builds", {})
    except OSError:
        return {}

    keyed: dict[str, dict[str, Any]] = {}
    if isinstance(raw_builds, dict):
        for k, entry in raw_builds.items():
            if isinstance(entry, dict) and all(req in entry for req in REQUIRED_BUILD_KEYS):
                entry_copy = dict(entry)
                entry_copy.setdefault("key", str(k).lower())
                keyed[str(k).lower()] = entry_copy
    elif isinstance(raw_builds, list):
        for entry in raw_builds:
            if isinstance(entry, dict) and all(req in entry for req in REQUIRED_BUILD_KEYS):
                k = str(entry["name"]).lower().replace(" ", "_")
                entry_copy = dict(entry)
                entry_copy.setdefault("key", k)
                keyed[k] = entry_copy
    return keyed


def load_builds(builds_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Loads the meta squad builds database from builds.toml.

    Search priority:
    1. Explicit builds_path argument
    2. ./builds.toml (working directory)
    3. Repository-root builds.toml
    4. Bundled ffta2_tool/data/builds.toml from an installed wheel

    Returns a list of build dicts sorted by slot. Invalid or missing entries are
    skipped; an empty list is returned when no usable builds file is found.
    """
    keyed = load_builds_by_key(builds_path)
    builds = list(keyed.values())
    builds.sort(key=lambda b: int(b["slot"]))
    return builds
