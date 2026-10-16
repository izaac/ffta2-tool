"""NDS ROM Inspection and ARM9 Extraction Utilities."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Dict, Any, List


def inspect_nds_rom(rom_path: str | Path) -> Dict[str, Any]:
    """Inspect NDS header parameters and binary offsets."""
    path = Path(rom_path)
    with path.open("rb") as f:
        header = f.read(0x200)

    title = header[:12].decode("ascii", errors="ignore").strip()
    gamecode = header[12:16].decode("ascii", errors="ignore")
    arm9_off, arm9_entry, arm9_ram, arm9_size = struct.unpack("<IIII", header[0x20:0x30])
    fat_off, fat_size = struct.unpack("<II", header[0x48:0x50])
    ov_off, ov_size = struct.unpack("<II", header[0x50:0x58])

    return {
        "title": title,
        "gamecode": gamecode,
        "arm9_offset": arm9_off,
        "arm9_entry": arm9_entry,
        "arm9_ram": arm9_ram,
        "arm9_size": arm9_size,
        "fat_offset": fat_off,
        "fat_size": fat_size,
        "overlay_offset": ov_off,
        "overlay_size": ov_size,
        "overlay_count": ov_size // 32,
    }


def extract_arm9(rom_path: str | Path, output_path: str | Path) -> Path:
    """Extract ARM9 executable binary from an NDS ROM."""
    info = inspect_nds_rom(rom_path)
    out = Path(output_path)

    with Path(rom_path).open("rb") as f:
        f.seek(info["arm9_offset"])
        arm9_data = f.read(info["arm9_size"])

    out.write_bytes(arm9_data)
    return out


def extract_overlays(rom_path: str | Path, output_dir: str | Path) -> List[Path]:
    """Extract all overlays from the NDS ROM."""
    info = inspect_nds_rom(rom_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    extracted = []
    with Path(rom_path).open("rb") as f:
        f.seek(info["fat_offset"])
        for i in range(info["overlay_count"]):
            start, end = struct.unpack("<II", f.read(8))
            cur = f.tell()
            f.seek(start)
            data = f.read(end - start)
            f.seek(cur)

            ov_path = out_dir / f"overlay_{i:04d}.bin"
            ov_path.write_bytes(data)
            extracted.append(ov_path)

    return extracted
