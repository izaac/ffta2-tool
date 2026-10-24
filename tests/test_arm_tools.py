"""Test suite for NDS ROM inspection, ARM9 extraction, and overlay extraction.

Builds a synthetic in-memory NDS ROM whose overlay entries use deliberately
non-sequential ``file_id`` values, so a linear "overlay i reads FAT[i]" bug is
detected instead of silently hidden by matching indices.
"""

import atexit
import os
import shutil
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ffta2_tool.arm_tools import (
    FAT_ENTRY_SIZE,
    HEADER_SIZE,
    OVERLAY_ENTRY_SIZE,
    extract_arm9,
    extract_overlays,
    inspect_nds_rom,
    inspect_overlays,
)

# Synthetic ROM layout.
ARM9_OFFSET = 0x200
ARM9_SIZE = 0x100
OVERLAY_TABLE_OFFSET = 0x300
FAT_OFFSET = 0x400
ROM_SIZE = 0x900

# file_id -> (rom start, rom end). Non-sequential by design: overlay 0 -> 5,
# overlay 1 -> 2, overlay 2 -> 7.
OVERLAY_FAT = {
    5: (0x800, 0x850),
    2: (0x850, 0x8B0),
    7: (0x8B0, 0x900),
}
OVERLAY_FILL = {5: 0x11, 2: 0x22, 7: 0x33}

# Decoy FAT slots: if the code read FAT[i] instead of FAT[file_id], overlay 0
# would be 16 bytes, overlay 1 8 bytes, overlay 2 32 bytes.
DECOY_FAT = [(0x800, 0x810), (0x850, 0x858), (0x8B0, 0x8C0)]

DEFAULT_OVERLAYS = [
    # (overlay_id, ram_address, ram_size, bss_size, static_init_start, static_init_end, file_id, flags)
    (0, 0x02100000, 0x50, 0x00, 0x02100000, 0x02100004, 5, 0x00000000),
    (1, 0x02110000, 0x60, 0x20, 0x02110000, 0x02110004, 2, 0x01000000),
    (2, 0x02120000, 0x50, 0x00, 0x02120000, 0x02120004, 7, 0x00000001),
]


def default_fat() -> list[tuple[int, int]]:
    entries = [(0x800, 0x810)] * 8
    entries[0] = DECOY_FAT[0]
    entries[1] = DECOY_FAT[1]
    entries[3] = DECOY_FAT[2]
    for file_id, (start, end) in OVERLAY_FAT.items():
        entries[file_id] = (start, end)
    return entries


def build_rom(
    fat: list[tuple[int, int]] | None = None,
    overlays: list[tuple[int, ...]] | None = None,
    arm9_size: int = ARM9_SIZE,
    rom_size: int = ROM_SIZE,
) -> bytes:
    """Build a synthetic NDS ROM image with a valid header, ARM9, overlay table and FAT."""
    fat_entries = list(default_fat() if fat is None else fat)
    overlay_entries = list(DEFAULT_OVERLAYS if overlays is None else overlays)

    buf = bytearray(rom_size)
    header = bytearray(HEADER_SIZE)
    header[0:12] = b"FFTA2TEST\x00\x00\x00"
    header[12:16] = b"ATST"
    struct.pack_into("<IIII", header, 0x20, ARM9_OFFSET, 0x02000000, 0x02000000, arm9_size)
    struct.pack_into("<II", header, 0x48, FAT_OFFSET, len(fat_entries) * FAT_ENTRY_SIZE)
    struct.pack_into("<II", header, 0x50, OVERLAY_TABLE_OFFSET, len(overlay_entries) * OVERLAY_ENTRY_SIZE)
    buf[0:HEADER_SIZE] = header

    writable_arm9 = max(0, min(arm9_size, rom_size - ARM9_OFFSET))
    buf[ARM9_OFFSET : ARM9_OFFSET + writable_arm9] = bytes((i % 251) + 1 for i in range(writable_arm9))

    for index, entry in enumerate(overlay_entries):
        struct.pack_into("<IIIIIIII", buf, OVERLAY_TABLE_OFFSET + index * OVERLAY_ENTRY_SIZE, *entry)

    for index, (start, end) in enumerate(fat_entries):
        struct.pack_into("<II", buf, FAT_OFFSET + index * FAT_ENTRY_SIZE, start, end)

    for file_id, fill in OVERLAY_FILL.items():
        if file_id >= len(fat_entries):
            continue
        start, end = fat_entries[file_id]
        if end <= rom_size and start < end:
            buf[start:end] = bytes([fill]) * (end - start)

    return bytes(buf)


_TEMP_DIRS: list[Path] = []


def _cleanup_temp_dirs() -> None:
    for d in _TEMP_DIRS:
        shutil.rmtree(d, ignore_errors=True)


atexit.register(_cleanup_temp_dirs)


def make_temp_dir(prefix: str) -> Path:
    d = Path(tempfile.mkdtemp(prefix=prefix))
    _TEMP_DIRS.append(d)
    return d


def write_rom(data: bytes) -> Path:
    tmpdir = make_temp_dir(prefix="ffta2-arm-tools-")
    rom_path = tmpdir / "synthetic.nds"
    rom_path.write_bytes(data)
    return rom_path


def expect_value_error(fn, label: str) -> None:
    try:
        fn()
    except ValueError as exc:
        print(f"[PASS] {label} -> ValueError: {exc}")
        return
    raise AssertionError(f"{label}: expected ValueError, none raised")


def test_inspect_nds_rom() -> None:
    rom = write_rom(build_rom())
    info = inspect_nds_rom(rom)

    assert info["title"] == "FFTA2TEST", info["title"]
    assert info["gamecode"] == "ATST", info["gamecode"]
    assert info["rom_size"] == ROM_SIZE, info["rom_size"]
    assert info["arm9_offset"] == ARM9_OFFSET
    assert info["arm9_size"] == ARM9_SIZE
    assert info["fat_offset"] == FAT_OFFSET
    assert info["fat_size"] == 8 * FAT_ENTRY_SIZE
    assert info["overlay_offset"] == OVERLAY_TABLE_OFFSET
    assert info["overlay_size"] == 3 * OVERLAY_ENTRY_SIZE
    assert info["overlay_count"] == 3, info["overlay_count"]
    print("[PASS] inspect_nds_rom returns header fields for the synthetic ROM")


def test_inspect_overlays_resolves_fat() -> None:
    rom = write_rom(build_rom())
    overlays = inspect_overlays(rom)

    assert len(overlays) == 3, len(overlays)
    assert [ov["file_id"] for ov in overlays] == [5, 2, 7]
    assert [ov["overlay_id"] for ov in overlays] == [0, 1, 2]

    for overlay in overlays:
        expected_start, expected_end = OVERLAY_FAT[overlay["file_id"]]
        assert overlay["start"] == expected_start, (overlay["overlay_id"], overlay["start"], expected_start)
        assert overlay["end"] == expected_end, (overlay["overlay_id"], overlay["end"], expected_end)
        assert overlay["size"] == expected_end - expected_start

    sizes = [ov["size"] for ov in overlays]
    assert sizes == [0x50, 0x60, 0x50], sizes
    # Decoy ranges would give 0x10 / 0x08 / 0x10 sized overlays if FAT lookup were linear.
    resolved = [(ov["start"], ov["end"]) for ov in overlays]
    linear = [DECOY_FAT[0], DECOY_FAT[1], DECOY_FAT[2]]
    assert resolved != linear, f"overlay ranges match decoy FAT entries: {resolved}"

    assert [ov["compressed"] for ov in overlays] == [False, True, True], [ov["compressed"] for ov in overlays]
    assert [ov["ram_size"] for ov in overlays] == [0x50, 0x60, 0x50]
    assert overlays[1]["bss_size"] == 0x20
    assert overlays[0]["ram_address"] == 0x02100000
    assert overlays[1]["flags"] == 0x01000000
    assert overlays[2]["flags"] == 0x1
    print("[PASS] inspect_overlays resolves ranges via FAT[file_id] (non-sequential file_ids)")


def test_extract_arm9() -> None:
    rom = write_rom(build_rom())
    out = make_temp_dir(prefix="ffta2-arm9-") / "arm9.bin"
    result = extract_arm9(rom, out)

    assert result == out
    data = out.read_bytes()
    assert len(data) == ARM9_SIZE, len(data)
    assert data == bytes((i % 251) + 1 for i in range(ARM9_SIZE))
    print(f"[PASS] extract_arm9 wrote {len(data)} bytes")


def test_extract_overlays() -> None:
    rom = write_rom(build_rom())
    out_dir = make_temp_dir(prefix="ffta2-overlays-")
    paths = extract_overlays(rom, out_dir)

    assert [p.name for p in paths] == ["overlay_0000.bin", "overlay_0001.bin", "overlay_0002.bin"]
    overlays = inspect_overlays(rom)
    expected_fill = {0: 0x11, 1: 0x22, 2: 0x33}
    for path, overlay in zip(paths, overlays, strict=True):
        data = path.read_bytes()
        assert len(data) == overlay["end"] - overlay["start"], (path.name, len(data))
        assert data == bytes([expected_fill[overlay["overlay_id"]]]) * len(data), path.name
    print("[PASS] extract_overlays writes each overlay from its FAT[file_id] range")


def test_bounds_and_errors() -> None:
    # ROM smaller than an NDS header.
    tiny = write_rom(bytes(0x100))
    expect_value_error(lambda: inspect_nds_rom(tiny), "header too small")

    # Header intact, tables truncated: FAT falls outside the file.
    truncated = write_rom(build_rom())
    truncated.write_bytes(truncated.read_bytes()[:0x410])
    expect_value_error(lambda: inspect_nds_rom(truncated), "truncated FAT")
    expect_value_error(
        lambda: extract_overlays(truncated, truncated.parent / "out"), "extract_overlays on truncated ROM"
    )

    # ARM9 declared past the end of the file.
    short_arm9 = write_rom(build_rom(arm9_size=0x1000))
    expect_value_error(lambda: extract_arm9(short_arm9, short_arm9.parent / "arm9.bin"), "ARM9 out of bounds")

    # file_id outside the FAT (only 4 entries available).
    small_fat = [(0x800, 0x810)] * 4
    bad_file_id = write_rom(build_rom(fat=small_fat))
    expect_value_error(lambda: inspect_overlays(bad_file_id), "file_id exceeding FAT")
    expect_value_error(lambda: extract_overlays(bad_file_id, bad_file_id.parent / "out"), "extract with bad file_id")

    # Inverted FAT range: start > end.
    inverted = list(default_fat())
    inverted[5] = (0x850, 0x800)
    inverted_rom = write_rom(build_rom(fat=inverted))
    expect_value_error(lambda: inspect_overlays(inverted_rom), "start > end")

    # FAT range beyond the ROM file.
    oversize = list(default_fat())
    oversize[5] = (0x800, ROM_SIZE + 0x100)
    oversize_rom = write_rom(build_rom(fat=oversize))
    expect_value_error(lambda: inspect_overlays(oversize_rom), "FAT range beyond ROM")
    print("[PASS] bounds and error handling")


def test_live_rom_overlays() -> None:
    candidates = [
        Path("/run/media/izaac/8088-DEB9/208G01/071 Final Fantasy Tactics A2.nds"),
        Path("/tmp/opencode/ffta2.nds"),
    ]
    rom_path = next((p for p in candidates if p.exists()), None)
    if rom_path is None:
        print("[SKIP] live ROM integration test (no FFTA2 ROM found)")
        return

    overlays = inspect_overlays(rom_path)
    assert len(overlays) == 18, f"expected 18 overlays, got {len(overlays)}"
    print(f"[PASS] live ROM {rom_path.name}: {len(overlays)} overlays")

    with tempfile.TemporaryDirectory(prefix="ffta2-live-overlays-") as tmp:
        paths = extract_overlays(rom_path, tmp)
        assert len(paths) == 18, len(paths)

        rom_size = os.path.getsize(rom_path)
        for path, overlay in zip(paths, overlays, strict=True):
            expected = overlay["end"] - overlay["start"]
            actual = path.stat().st_size
            assert actual == expected, f"{path.name}: {actual} bytes, expected {expected}"
            assert overlay["end"] <= rom_size

        itcm = Path(tmp) / "overlay_0000.bin"
        assert itcm.stat().st_size == 20608, f"ITCM overlay is {itcm.stat().st_size} bytes, expected 20608"
        first_words = struct.unpack("<4I", itcm.read_bytes()[:16])
        print(f"[PASS] overlay_0000.bin (ITCM) = 20608 bytes, first words {[hex(w) for w in first_words]}")
        print(f"[PASS] all 18 overlays extracted with exact FAT-derived sizes to {tmp}")


if __name__ == "__main__":
    test_inspect_nds_rom()
    test_inspect_overlays_resolves_fat()
    test_extract_arm9()
    test_extract_overlays()
    test_bounds_and_errors()
    test_live_rom_overlays()
    print("[OK] arm_tools test suite complete")
