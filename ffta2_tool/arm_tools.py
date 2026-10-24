"""NDS ROM Inspection and ARM9 Extraction Utilities."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

HEADER_SIZE = 0x200
FAT_ENTRY_SIZE = 8
OVERLAY_ENTRY_SIZE = 32

# Compression is signalled by the undocumented high bit in the overlay flags,
# or (as a legacy fallback) by the low bit used by some toolchains.
OVERLAY_COMPRESSED_FLAG = 0x01000000


def _read_exact(f, count: int, what: str, path: Path) -> bytes:
    """Read exactly ``count`` bytes or raise a descriptive error."""
    data = f.read(count)
    if len(data) != count:
        raise ValueError(f"Truncated NDS ROM: expected {count} bytes of {what} in {path.name}, got {len(data)}")
    return data


def inspect_nds_rom(rom_path: str | Path) -> dict[str, Any]:
    """Inspect NDS header parameters and binary offsets.

    Raises:
        ValueError: If the file is too small to hold an NDS header, or the header
            declares tables that fall outside the file bounds.
    """
    path = Path(rom_path)
    rom_size = path.stat().st_size
    if rom_size < HEADER_SIZE:
        raise ValueError(f"Not an NDS ROM: {path.name} is {rom_size} bytes, minimum is {HEADER_SIZE} (0x200)")

    with path.open("rb") as f:
        header = _read_exact(f, HEADER_SIZE, "NDS header", path)

    title = header[:12].decode("ascii", errors="ignore").strip("\x00 ")
    gamecode = header[12:16].decode("ascii", errors="ignore").strip("\x00 ")
    arm9_off, arm9_entry, arm9_ram, arm9_size = struct.unpack("<IIII", header[0x20:0x30])
    fat_off, fat_size = struct.unpack("<II", header[0x48:0x50])
    ov_off, ov_size = struct.unpack("<II", header[0x50:0x58])

    # Header sanity: declared tables must be addressable inside the file.
    if fat_off + fat_size > rom_size:
        raise ValueError(
            f"Invalid NDS header in {path.name}: FAT table "
            f"(0x{fat_off:X}+0x{fat_size:X}) exceeds ROM size 0x{rom_size:X}"
        )
    if ov_off + ov_size > rom_size:
        raise ValueError(
            f"Invalid NDS header in {path.name}: overlay table "
            f"(0x{ov_off:X}+0x{ov_size:X}) exceeds ROM size 0x{rom_size:X}"
        )
    if arm9_size and arm9_off + arm9_size > rom_size:
        raise ValueError(
            f"Invalid NDS header in {path.name}: ARM9 binary "
            f"(0x{arm9_off:X}+0x{arm9_size:X}) exceeds ROM size 0x{rom_size:X}"
        )

    return {
        "title": title,
        "gamecode": gamecode,
        "rom_size": rom_size,
        "arm9_offset": arm9_off,
        "arm9_entry": arm9_entry,
        "arm9_ram": arm9_ram,
        "arm9_size": arm9_size,
        "fat_offset": fat_off,
        "fat_size": fat_size,
        "overlay_offset": ov_off,
        "overlay_size": ov_size,
        "overlay_count": ov_size // OVERLAY_ENTRY_SIZE,
    }


def inspect_overlays(rom_path: str | Path) -> list[dict[str, Any]]:
    """Read the NDS overlay table and resolve each overlay's physical file range.

    Each overlay table entry is 32 bytes and describes where the overlay is mapped
    in RAM, not where it lives in the ROM. The physical byte range comes from the
    FAT entry indexed by the overlay's ``file_id``.

    Raises:
        ValueError: If the overlay table, the FAT, or a resolved overlay range is
            out of bounds for the ROM file.
    """
    info = inspect_nds_rom(rom_path)
    path = Path(rom_path)
    rom_size: int = info["rom_size"]
    fat_offset: int = info["fat_offset"]
    fat_size: int = info["fat_size"]
    count: int = info["overlay_count"]

    if count == 0:
        return []

    with path.open("rb") as f:
        f.seek(info["overlay_offset"])
        table = _read_exact(f, count * OVERLAY_ENTRY_SIZE, "overlay table", path)
        f.seek(fat_offset)
        fat = _read_exact(f, fat_size, "FAT", path)

    overlays: list[dict[str, Any]] = []
    for index in range(count):
        chunk = table[index * OVERLAY_ENTRY_SIZE : (index + 1) * OVERLAY_ENTRY_SIZE]
        (
            overlay_id,
            ram_address,
            ram_size,
            bss_size,
            static_init_start,
            static_init_end,
            file_id,
            flags,
        ) = struct.unpack("<IIIIIIII", chunk)

        fat_entry_offset = file_id * FAT_ENTRY_SIZE
        if fat_entry_offset + FAT_ENTRY_SIZE > len(fat):
            raise ValueError(
                f"Overlay {overlay_id} references file_id {file_id}, which is outside the FAT "
                f"({len(fat) // FAT_ENTRY_SIZE} entries)"
            )

        start, end = struct.unpack("<II", fat[fat_entry_offset : fat_entry_offset + FAT_ENTRY_SIZE])
        if start > end:
            raise ValueError(f"Overlay {overlay_id} has an inverted FAT range: start 0x{start:X} > end 0x{end:X}")
        if end > rom_size:
            raise ValueError(f"Overlay {overlay_id} FAT range 0x{start:X}-0x{end:X} exceeds ROM size 0x{rom_size:X}")

        overlays.append(
            {
                "overlay_id": overlay_id,
                "ram_address": ram_address,
                "ram_size": ram_size,
                "bss_size": bss_size,
                "static_init_start": static_init_start,
                "static_init_end": static_init_end,
                "file_id": file_id,
                "flags": flags,
                "compressed": bool(flags & OVERLAY_COMPRESSED_FLAG) or bool(flags & 1),
                "start": start,
                "end": end,
                "size": end - start,
            }
        )

    return overlays


def extract_arm9(rom_path: str | Path, output_path: str | Path) -> Path:
    """Extract ARM9 executable binary from an NDS ROM.

    Raises:
        ValueError: If the declared ARM9 range falls outside the ROM file.
    """
    info = inspect_nds_rom(rom_path)
    out = Path(output_path)

    arm9_offset: int = info["arm9_offset"]
    arm9_size: int = info["arm9_size"]
    rom_size: int = info["rom_size"]
    if arm9_offset + arm9_size > rom_size:
        raise ValueError(
            f"ARM9 range 0x{arm9_offset:X}+0x{arm9_size:X} exceeds ROM size 0x{rom_size:X}: {Path(rom_path).name}"
        )

    with Path(rom_path).open("rb") as f:
        f.seek(arm9_offset)
        arm9_data = _read_exact(f, arm9_size, "ARM9 binary", Path(rom_path))

    out.write_bytes(arm9_data)
    return out


def extract_overlays(rom_path: str | Path, output_dir: str | Path) -> list[Path]:
    """Extract all overlays from the NDS ROM.

    Each overlay's physical range is resolved through ``FAT[file_id]``, so the
    files are written as ``overlay_<overlay_id>.bin`` in overlay-id order.

    Raises:
        ValueError: If an overlay range is out of bounds or the ROM is truncated.
    """
    overlays = inspect_overlays(rom_path)
    path = Path(rom_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    extracted: list[Path] = []
    with path.open("rb") as f:
        for overlay in overlays:
            start: int = overlay["start"]
            size: int = overlay["size"]
            f.seek(start)
            data = _read_exact(f, size, f"overlay {overlay['overlay_id']}", path)

            ov_path = out_dir / f"overlay_{overlay['overlay_id']:04d}.bin"
            ov_path.write_bytes(data)
            extracted.append(ov_path)

    return extracted
