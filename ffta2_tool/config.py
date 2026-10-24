"""Configuration and builds database loading for ffta2_tool.

The TOML readers live in ``ffta2_tool.toml_lite`` and the builds database lives in
``ffta2_tool.builds``; both are re-exported here for backward compatibility.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ffta2_tool.builds import (
    DEFAULT_META_SQUAD_BUILDS,
    REQUIRED_BUILD_KEYS,
    load_builds,
    load_builds_by_key,
    resolve_build,
)
from ffta2_tool.toml_lite import _parse_simple_toml, read_toml

__all__ = [
    "DEFAULT_CONFIG_EXAMPLE_PATH",
    "DEFAULT_META_SQUAD_BUILDS",
    "REQUIRED_BUILD_KEYS",
    "_parse_simple_toml",
    "get_default_backup_dir",
    "load_builds",
    "load_builds_by_key",
    "load_config",
    "read_toml",
    "resolve_build",
]

_PACKAGE_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_ROOT.parent


def _resolve_data_file(name: str) -> Path:
    """Resolves a bundled TOML data file across repo and package-data layouts.

    Search order: repository root, then ``ffta2_tool/data/`` next to this module.
    """
    for candidate in (_REPO_ROOT / name, _PACKAGE_ROOT / "data" / name):
        if candidate.is_file():
            return candidate
    return _PACKAGE_ROOT / "data" / name


DEFAULT_CONFIG_EXAMPLE_PATH = _resolve_data_file("config.example.toml")


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
                raw = read_toml(path)
                return {
                    "paths": raw.get("paths", {}) if isinstance(raw.get("paths"), dict) else {},
                    "defaults": raw.get("defaults", {}) if isinstance(raw.get("defaults"), dict) else {},
                }
            except OSError:
                break

    return {"paths": {}, "defaults": {}}
