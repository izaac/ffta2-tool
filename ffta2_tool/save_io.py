"""Filesystem I/O helpers for FFTA2 save files.

Kept separate from ``ffta2_tool.save`` so the save domain model holds no filesystem
concerns. ``ffta2_tool.save`` re-exports these names for backward compatibility.
"""

from __future__ import annotations

import contextlib
import glob
import os
import shutil
import string
from datetime import datetime
from pathlib import Path

from ffta2_tool.config import get_default_backup_dir

# Minimum plausible FFTA2 save size (NDS saves are 512 KiB; floor filters junk matches)
MIN_SAVE_SIZE = 0x10000

# Common save-file name fragment used across emulators and handheld SD cards
SAVE_NAME_GLOB = "*Final Fantasy Tactics A2*.sav"


def atomic_write(filepath: str | Path, data: bytes) -> None:
    """Safely writes data to a temporary sibling file then replaces target atomically with fsync."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp_{os.getpid()}")
    try:
        with open(tmp_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        if hasattr(os, "sync"):
            with contextlib.suppress(AttributeError, OSError):
                os.sync()
    finally:
        if tmp_path.exists():
            with contextlib.suppress(OSError):
                tmp_path.unlink()


def auto_detect_save(search_paths: list[str] | None = None) -> str | None:
    """Attempts to find the most relevant FFTA2 save file automatically.

    Checks mounted handheld/media SD cards, ~/Documents/FFTA2_Backups/, and the
    current directory (in that priority order) unless custom glob patterns are
    supplied via search_paths. Returns the most recently modified valid
    candidate, or None when nothing is found.
    """
    candidates: list[str] = []

    if search_paths is not None:
        for pattern in search_paths:
            candidates.extend(glob.glob(os.path.expanduser(pattern)))
    else:
        # Removable media mounts (retro handheld SD cards, flashcards, volumes)
        # Note: /mnt is intentionally excluded to avoid slow/hanging network or FUSE cloud mounts (e.g. rclone/CIFS).
        for mount_root in ("/run/media", "/media", "/Volumes"):
            for layout in (
                "*/*/*/Saves/nds/common",
                "*/*/*/Saves/NDS/common",
                "*/*/*/Saves/nds",
                "*/*/*/Saves/NDS",
                "*/Saves/nds/common",
                "*/Saves/NDS/common",
                "*/Saves/nds",
                "*/Saves/NDS",
                "*/*/*/*",
                "*/*/*",
                "*/*",
                "*",
            ):
                candidates.extend(glob.glob(f"{mount_root}/{layout}/{SAVE_NAME_GLOB}"))

        if os.name == "nt":
            for letter in string.ascii_uppercase[2:]:
                candidates.extend(glob.glob(f"{letter}:\\Saves\\nds\\common\\{SAVE_NAME_GLOB}"))
                candidates.extend(glob.glob(f"{letter}:\\Saves\\NDS\\common\\{SAVE_NAME_GLOB}"))
                candidates.extend(glob.glob(f"{letter}:\\Saves\\nds\\{SAVE_NAME_GLOB}"))
                candidates.extend(glob.glob(f"{letter}:\\Saves\\NDS\\{SAVE_NAME_GLOB}"))

        # Local backup directory, repo examples directory, and current directory fallbacks
        backup_dir = get_default_backup_dir()
        try:
            if backup_dir.is_dir():
                candidates.extend(glob.glob(str(backup_dir / "*.sav")))
        except OSError:
            pass

        repo_examples = Path(__file__).resolve().parent.parent / "examples"
        try:
            if repo_examples.is_dir():
                candidates.extend(glob.glob(str(repo_examples / "*.sav")))
        except OSError:
            pass

        candidates.extend(glob.glob("*.sav"))

    valid = [p for p in candidates if os.path.isfile(p) and os.path.getsize(p) >= MIN_SAVE_SIZE]
    if not valid:
        return None

    def _save_priority(path_str: str) -> tuple[int, float]:
        name_lower = Path(path_str).name.lower()
        is_scratch = any(k in name_lower for k in ("test", "sample", "copy", "bak"))
        return (0 if not is_scratch else -1, os.path.getmtime(path_str))

    valid.sort(key=_save_priority, reverse=True)
    return valid[0]


def create_backup_snapshot(filepath: str | Path, backup_dir: str | Path | None = None) -> Path:
    """Creates a timestamped snapshot '<name>.bak_YYYYMMDD_HHMMSS' in the centralized backup folder."""
    path = Path(filepath)
    dest_dir = get_default_backup_dir(backup_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = dest_dir / f"{path.name}.bak_{timestamp}"
    shutil.copy2(path, backup_path)
    return backup_path
