"""Test suite for FFTA2 Meta Squad Patcher, Validator, Mappings, and Save Utilities."""

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ffta2_tool.config import _parse_simple_toml, load_builds
from ffta2_tool.crypto import verify_save_checksum
from ffta2_tool.mappings import (
    get_item_name,
    get_job_name,
    get_race_name,
    is_shield_capable,
    is_valid_item_id,
)
from ffta2_tool.patcher import (
    DEFAULT_META_SQUAD_BUILDS,
    META_INVENTORY_ITEMS,
    META_SQUAD_BUILDS,
    apply_meta_squad,
)
from ffta2_tool.save import (
    MIN_SAVE_SIZE,
    OFF_UNIT_ABILITIES_END,
    OFF_UNIT_ABILITIES_START,
    FFTA2Save,
    atomic_write,
    auto_detect_save,
    create_backup_snapshot,
)
from ffta2_tool.validator import SUPPORT_ABILITY_RACES, validate_save, validate_unit


def get_sample_save_path() -> Path | None:
    candidates = [
        Path.home() / "Documents" / "FFTA2_Backups" / "071 Final Fantasy Tactics A2.sav.orig",
        Path.home() / "Documents" / "FFTA2_Backups" / "071 Final Fantasy Tactics A2.sav",
        Path(__file__).resolve().parent.parent / "examples" / "FFTA2_Meta_Squad_Hard.sav",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def test_mappings():
    """Verify data mappings lookups and bounds."""
    assert get_job_name(0x08) == "Parivir"
    assert get_job_name(0x1F) == "Sage"
    assert get_race_name(1) == "Hume"
    assert get_race_name(3) == "Nu Mou"
    assert get_item_name(0x0018) == "Chirijiraden"
    assert get_item_name(0x0180) == "Ninja Tabi"
    assert is_shield_capable(0x1F) is True  # Nu Mou Sage can equip shield
    assert is_shield_capable(0x08) is False  # Parivir cannot equip shield
    assert is_valid_item_id(0x0050) is True
    assert is_valid_item_id(0x0500) is False
    assert SUPPORT_ABILITY_RACES[0x035C] == {1}, "Dual Wield must be Hume-only"


def test_load_builds():
    """Verify builds.toml loads the 6 verified meta squad builds and falls back safely."""
    builds = load_builds()
    assert len(builds) == 6, f"Expected 6 builds in builds.toml, got {len(builds)}"

    # Slots must be contiguous 0..5 in order
    assert [b["slot"] for b in builds] == [0, 1, 2, 3, 4, 5]

    # Loaded builds must match the built-in defaults field-for-field
    keys = (
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
        "r_ability",
        "p_ability",
    )
    for loaded, default in zip(builds, DEFAULT_META_SQUAD_BUILDS, strict=True):
        for key in keys:
            assert loaded[key] == default[key], f"Build slot {loaded['slot']} field {key} mismatch"

    # Active builds constant must be the loaded set
    assert builds == META_SQUAD_BUILDS

    # Missing file yields an empty list (patcher then falls back to defaults)
    assert load_builds("/nonexistent/path/builds.toml") == []
    print("[PASS] builds.toml loaded and matches built-in meta squad defaults.")


def test_parse_simple_toml():
    """Verify fallback parser handles dotted tables, inline comments, quotes, and scalars."""
    toml_text = """
    # Top-level comment
    [builds.slot0]
    name = "Luso #1" # inline comment
    slot = 0
    job_id = 0x08
    enabled = true
    empty_list = []
    items = ["Ninja Tabi", 0x180, 50]
    """
    parsed = _parse_simple_toml(toml_text)
    assert "builds" in parsed, "Expected 'builds' table in parsed output"
    assert "slot0" in parsed["builds"], "Expected 'slot0' nested under 'builds'"
    slot0 = parsed["builds"]["slot0"]
    assert slot0["name"] == "Luso #1", f"Comment stripping broke quoted string: {slot0['name']}"
    assert slot0["slot"] == 0
    assert slot0["job_id"] == 8
    assert slot0["enabled"] is True
    assert slot0["empty_list"] == []
    assert slot0["items"] == ["Ninja Tabi", 384, 50]
    print("[PASS] _parse_simple_toml correctly parsed dotted tables, comments, and values.")


def test_backup_snapshot():
    """Verify create_backup_snapshot writes a timestamped sibling copy."""
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "Test Save.sav"
        payload = b"FFTA2-SAVE-DATA" * 8
        save_path.write_bytes(payload)

        backup_path = create_backup_snapshot(save_path)

        assert backup_path.exists(), "Backup snapshot was not created"
        assert backup_path.name.startswith("Test Save.sav.bak_"), backup_path.name
        stamp = backup_path.name.split(".bak_", 1)[1]
        assert len(stamp) == len("YYYYMMDD_HHMMSS") and stamp[8] == "_", f"Bad timestamp: {stamp}"
        assert backup_path.read_bytes() == payload, "Backup content mismatch"
    print("[PASS] Timestamped backup snapshot created with expected name and content.")


def test_atomic_write():
    """Verify atomic_write safely and completely replaces target file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "atomic_test.bin"
        data1 = b"INITIAL_DATA"
        data2 = b"REPLACED_ATOMIC_DATA"

        atomic_write(target, data1)
        assert target.read_bytes() == data1

        atomic_write(target, data2)
        assert target.read_bytes() == data2
    print("[PASS] atomic_write wrote and replaced file cleanly.")


def test_auto_detect_save():
    """Verify auto_detect_save picks the newest valid .sav and ignores undersized files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        old_save = root / "old.sav"
        new_save = root / "new.sav"
        tiny_save = root / "tiny.sav"

        old_save.write_bytes(b"\x00" * MIN_SAVE_SIZE)
        new_save.write_bytes(b"\x00" * MIN_SAVE_SIZE)
        tiny_save.write_bytes(b"\x00" * 16)

        now = time.time()
        os.utime(old_save, (now - 100, now - 100))
        os.utime(new_save, (now, now))

        detected = auto_detect_save(search_paths=[str(root / "*.sav")])
        assert detected is not None, "auto_detect_save returned None for valid candidates"
        assert Path(detected).name == "new.sav", f"Expected newest save, got {detected}"

        # Only an undersized file present -> no detection
        new_save.unlink()
        old_save.unlink()
        assert auto_detect_save(search_paths=[str(root / "*.sav")]) is None
    print("[PASS] auto_detect_save selects newest valid save and rejects undersized files.")


def test_meta_squad_patcher():
    sample_path = get_sample_save_path()
    if not sample_path:
        print("[SKIP] No sample save found to test patcher.")
        return

    import struct

    from ffta2_tool.slots import SlotManager, calculate_metadata_checksum

    save = FFTA2Save(sample_path)
    u0 = save.get_unit(0)
    assert u0 is not None
    original_abilities = bytes(u0._data[OFF_UNIT_ABILITIES_START:OFF_UNIT_ABILITIES_END])
    original_preview = SlotManager(sample_path.read_bytes()).get_slot_preview(0)

    apply_meta_squad(save, inject_inventory=True)

    # Verify no validation errors
    issues = [i for i in validate_save(save) if i.severity == "ERROR"]
    assert len(issues) == 0, f"Validation errors found after patching: {issues}"

    # Verify memory representation matches builds
    for build in META_SQUAD_BUILDS:
        unit = save.get_unit(build["slot"])
        assert unit is not None
        assert unit.job_id == build["job_id"], f"Slot {build['slot']} job mismatch"
        assert unit.primary_ability_set == build["primary_set"]
        assert unit.secondary_ability_set == build["secondary_set"]
        assert unit.weapon_id == build["weapon_id"]
        assert unit.shield_id == build["shield_id"]
        assert unit.helm_id == build["helm_id"]
        assert unit.armor_id == build["armor_id"]
        assert unit.accessory_id == build["accessory_id"]
        assert unit.r_ability == build["r_ability"]
        assert unit.p_ability == build["p_ability"]

    # Verify inventory was populated
    inv = save.get_inventory()
    for item_id in META_INVENTORY_ITEMS:
        assert item_id in inv, f"Item 0x{item_id:04X} not found in clan inventory"
        total, _ = inv[item_id]
        assert total == 50

    # Verify clan job unlock flags
    assert save.plaintext[0x2814:0x2817] == b"\xff\xff\xff"
    assert save.plaintext[0x28AF:0x28B1] == b"\xff\xff"

    # Verify ability mastery is NOT blanket-filled by default (legal learning only)
    u0 = save.get_unit(0)
    assert u0 is not None
    assert u0.r_ability == 0x033C
    assert u0.p_ability == 0x035C
    assert bytes(u0._data[OFF_UNIT_ABILITIES_START:OFF_UNIT_ABILITIES_END]) == original_abilities, (
        "Default patch must leave the per-ability AP array untouched"
    )

    # Verify write and cryptographic resigning
    with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        save.save(tmp_path, backup=False)
        patched_raw = tmp_path.read_bytes()
        is_valid, stored, calculated = verify_save_checksum(patched_raw)
        assert is_valid, f"Patched save checksum invalid: stored 0x{stored:X} != calc 0x{calculated:X}"

        # Reload patched save
        reloaded = FFTA2Save(tmp_path)
        u0 = reloaded.get_unit(0)
        assert u0.job_id == 0x08  # Parivir
        assert u0.weapon_id == 0x0074  # Hyakushiki-masamune
        assert u0.shield_id == 0x0000  # Single-wield (off-hand katana black-screened Unit Info)
        assert u0.r_ability == 0x033C  # Strike Back
        assert u0.p_ability == 0x035C  # Dual Wield (Hume only)

        # Verify the load-screen preview follows the patched payload
        sm = SlotManager(bytearray(patched_raw))
        assert sm.verify_slot(0)[0], "Slot 0 checksum invalid after save"
        preview = sm.get_slot_preview(0)
        assert preview["leader_name"] == "Luso"
        assert preview["member_count"] == 6
        assert preview["cleared_quests"] == original_preview["cleared_quests"]
        assert preview["clan_title_rank"] == original_preview["clan_title_rank"]
        assert preview["leader_level"] == original_preview["leader_level"]
        assert preview["play_time_formatted"] == original_preview["play_time_formatted"]
        for copy_base in (0x0000, 0x00DC):
            stored = struct.unpack_from("<I", sm.raw, copy_base)[0]
            calculated = calculate_metadata_checksum(sm.raw[copy_base : copy_base + 0xDC])
            assert stored == calculated, f"Metadata checksum invalid at 0x{copy_base:04X}"

        print(f"[PASS] Successfully patched, signed, and re-verified meta squad on {tmp_path}!")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_validator_guards():
    """Verify validator flags black-screen conditions and illegal R/P learn sources."""
    sample_path = get_sample_save_path()
    if not sample_path:
        print("[SKIP] No sample save found to test validator guards.")
        return

    save = FFTA2Save(sample_path)
    u0 = save.get_unit(0)
    assert u0 is not None

    # Off-hand weapon without Dual Wield -> ERROR (known Unit Info black screen)
    u0.shield_id = 0x0074
    u0.p_ability = 0x0000
    errors = [i for i in validate_unit(u0) if i.field == "shield_id" and i.severity == "ERROR"]
    assert errors, "Off-hand weapon without Dual Wield was not flagged as ERROR"

    # Blanket 0xFF ability array -> WARNING (renders fine in melonDS, but not a legal state)
    u0.shield_id = 0x0000
    u0.p_ability = 0x035C
    u0._data[OFF_UNIT_ABILITIES_START:OFF_UNIT_ABILITIES_END] = b"\xff" * (
        OFF_UNIT_ABILITIES_END - OFF_UNIT_ABILITIES_START
    )
    abil = [i for i in validate_unit(u0) if i.field == "abilities"]
    assert abil and all(i.severity == "WARNING" for i in abil), "All-0xFF ability array must be a WARNING"

    # Dual Wield on a non-Hume -> WARNING
    non_hume = save.get_unit(1)
    assert non_hume is not None
    assert non_hume._data[0x0F] != 1, "Expected slot 1 to be a non-Hume for this check"
    non_hume.p_ability = 0x035C
    warnings = [i for i in validate_unit(non_hume) if i.field == "p_ability" and "not learnable" in i.message]
    assert warnings, "Dual Wield on a non-Hume was not flagged"

    # Elusion has no player learn source -> WARNING
    u0.p_ability = 0x0371
    warnings = [i for i in validate_unit(u0) if i.field == "p_ability" and "NPC-only" in i.message]
    assert warnings, "Elusion was not flagged as NPC-only"

    print("[PASS] Validator flags black-screen conditions and illegal R/P learn sources.")


def test_difficulty_roundtrip():
    """Verify the difficulty flag and load-screen label survive save/reload."""
    import struct

    from ffta2_tool.slots import SlotManager, calculate_metadata_checksum

    sample_path = get_sample_save_path()
    if not sample_path:
        print("[SKIP] No sample save found to test difficulty roundtrip.")
        return

    original_preview = SlotManager(sample_path.read_bytes()).get_slot_preview(0)
    save = FFTA2Save(sample_path)
    u0_before = save.get_unit(0)
    assert u0_before is not None
    build_before = (
        u0_before.job_id,
        u0_before.weapon_id,
        u0_before.shield_id,
        u0_before.r_ability,
        u0_before.p_ability,
    )

    try:
        save.difficulty = 3
        raise AssertionError("difficulty setter accepted an invalid value")
    except ValueError:
        pass

    save.difficulty = 1
    assert save.difficulty == 1

    with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        save.save(tmp_path, backup=False)
        raw = tmp_path.read_bytes()
        reloaded = FFTA2Save(tmp_path)
        assert reloaded.difficulty == 1

        u0_after = reloaded.get_unit(0)
        assert u0_after is not None
        assert (
            u0_after.job_id,
            u0_after.weapon_id,
            u0_after.shield_id,
            u0_after.r_ability,
            u0_after.p_ability,
        ) == build_before, "Changing difficulty must not touch unit data"

        sm = SlotManager(raw)
        assert sm.verify_slot(0)[0], "Slot 0 checksum invalid after difficulty change"
        preview = sm.get_slot_preview(0)
        assert preview["difficulty"] == 1
        assert preview["difficulty_label"] == "Hard"
        entry_off = sm.entry_offset(0)
        assert sm.raw[entry_off + 36] == 1, "Preview byte 36 must be 1 for Hard mode badge"
        assert preview["play_time_formatted"] == original_preview["play_time_formatted"]
        assert preview["cleared_quests"] == original_preview["cleared_quests"]
        for copy_base in (0x0000, 0x00DC):
            stored = struct.unpack_from("<I", sm.raw, copy_base)[0]
            calculated = calculate_metadata_checksum(sm.raw[copy_base : copy_base + 0xDC])
            assert stored == calculated, f"Metadata checksum invalid at 0x{copy_base:04X}"

        # Test set_slot_difficulty directly
        sm.set_slot_difficulty(0, 2)
        assert sm.get_slot_preview(0)["difficulty"] == 2
        assert sm.get_slot_preview(0)["difficulty_label"] == "Normal"
        assert sm.raw[sm.entry_offset(0) + 36] == 0
        sm.set_slot_difficulty(0, 1)
        assert sm.get_slot_preview(0)["difficulty"] == 1
        assert sm.raw[sm.entry_offset(0) + 36] == 1
        print("[PASS] Difficulty flag roundtrip and Hard preview verified.")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


EXAMPLE_SAVE = Path(__file__).resolve().parent.parent / "examples" / "FFTA2_Meta_Squad_Hard.sav"


def _set_entry_state(raw: bytearray, copy_base: int, pos: int, active: int, retired: int, slot_id: int) -> None:
    from ffta2_tool.slots import entry_offset

    off = entry_offset(copy_base, pos)
    raw[off + 4], raw[off + 5], raw[off + 6] = active, retired, slot_id


def _resign_copy(raw: bytearray, copy_base: int) -> None:
    import struct

    from ffta2_tool.slots import calculate_metadata_checksum

    struct.pack_into("<I", raw, copy_base, calculate_metadata_checksum(raw[copy_base : copy_base + 0xDC]))


def _move_slot(raw: bytearray, copy_base: int, src_pos: int, dst_pos: int) -> bytearray:
    """Return a copy of raw where the live slot at src_pos lives at dst_pos (record + entry)."""
    from ffta2_tool.slots import ENTRY_SIZE, RECORD_OFFSETS, SLOT_RECORD_SIZE, entry_offset

    out = bytearray(raw)
    rs, rd = RECORD_OFFSETS[src_pos], RECORD_OFFSETS[dst_pos]
    out[rd : rd + SLOT_RECORD_SIZE] = raw[rs : rs + SLOT_RECORD_SIZE]
    es, ed = entry_offset(copy_base, src_pos), entry_offset(copy_base, dst_pos)
    out[ed : ed + ENTRY_SIZE] = raw[es : es + ENTRY_SIZE]
    out[es + 5] = 1  # the old position is retired, as after an in-game save
    _resign_copy(out, copy_base)
    return out


def test_slot_record_mapping():
    """Slot edits must land in the record the game loads, not at a fixed offset.

    ARM9 0x0210D66C: a slot is the first of the 4 entries in the active metadata copy with
    +4 != 0, +5 == 0 and +6 == slot id; entry position N selects the record at
    0x01B8 + N * 0x3408. Each in-game save writes the slot to the first free position
    (+5 != 0, 0x0210D6BC) and retires the old one, so a slot can live in any record.
    Regression: the tool patched 0x01B8 and read +5 as the slot id while the game loaded
    Slot 1 from 0x35C0, so a Hard patch reverted to Normal on the first in-game save.
    """
    import struct

    from ffta2_tool.slots import (
        ENTRY_SIZE,
        RECORD_OFFSETS,
        SLOT_RECORD_SIZE,
        SlotManager,
        active_metadata_base,
        calculate_metadata_checksum,
        entry_offset,
    )

    raw = bytearray(EXAMPLE_SAVE.read_bytes())

    # Equal save counters: ARM9 0x0210D548 picks copy 2
    tie = bytearray(raw)
    for base in (0x0000, 0x00DC):
        struct.pack_into("<I", tie, base + 4, 7)
        _resign_copy(tie, base)
    assert active_metadata_base(tie) == 0x00DC

    # Shipped example: Slot 1 is live at position 1; the retired entry at position 0 and
    # the dead slot id 1 entry at position 2 (+4 == 0) are not Slot 2.
    act = active_metadata_base(raw)
    other_copy = 0x00DC if act == 0x0000 else 0x0000
    sm = SlotManager(raw)
    assert sm.slot_position(0) == 1 and sm.record_offset(0) == RECORD_OFFSETS[1]
    assert not sm.has_data(1) and sm.get_slot_preview(1)["has_data"] is False
    assert sm.verify_slot(1) == (False, 0, 0)
    try:
        sm.record_offset(1)
        raise AssertionError("record_offset accepted an empty slot")
    except ValueError:
        pass

    two_slots = bytearray(raw)
    _set_entry_state(two_slots, act, 0, 1, 0, 1)  # valid record at position 0 becomes Slot 2
    _resign_copy(two_slots, act)
    shadowed = bytearray(raw)
    _set_entry_state(shadowed, act, 0, 1, 0, 0)  # two live Slot 1 entries: the first one wins
    _resign_copy(shadowed, act)
    cases = [
        ("as shipped", raw, 0, 1),
        ("moved to position 3", _move_slot(raw, act, 1, 3), 0, 3),
        ("moved to position 2", _move_slot(raw, act, 1, 2), 0, 2),
        ("two slots, Slot 1", two_slots, 0, 1),
        ("two slots, Slot 2", two_slots, 1, 0),
        ("shadowed duplicate", shadowed, 0, 0),
    ]

    def check(name: str, image: bytes, out: bytes, slot: int, pos: int, want: int) -> None:
        for p in range(4):
            if p != pos:
                r = RECORD_OFFSETS[p]
                assert out[r : r + SLOT_RECORD_SIZE] == image[r : r + SLOT_RECORD_SIZE], f"{name}: record {p} touched"
                e = entry_offset(act, p)
                assert out[e : e + ENTRY_SIZE] == image[e : e + ENTRY_SIZE], f"{name}: entry {p} touched"
        assert out[other_copy : other_copy + 0xDC] == image[other_copy : other_copy + 0xDC], (
            f"{name}: the inactive metadata copy must stay untouched"
        )
        out_sm, in_sm = SlotManager(out), SlotManager(image)
        assert out_sm.active_copy_base() == act
        assert out_sm.slot_position(slot) == pos, f"{name}: slot moved"
        assert out_sm.slot_position(1 - slot) == in_sm.slot_position(1 - slot), f"{name}: other slot changed"
        assert out_sm.verify_slot(slot)[0], f"{name}: record checksum invalid"
        _, _, payload = out_sm.get_slot_payload(slot)
        assert payload[0x2798] == (1 if want == 1 else 0), f"{name}: difficulty not in the loaded record"
        assert out[entry_offset(act, pos) + 0x24] == (1 if want == 1 else 0), f"{name}: badge not updated"
        assert struct.unpack_from("<I", out, act)[0] == calculate_metadata_checksum(out[act : act + 0xDC])
        preview = out_sm.get_slot_preview(slot)
        assert preview["difficulty"] == want and not preview["badge_mismatch"]

    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "in.sav"
        dst = Path(td) / "out.sav"
        for name, image, slot, pos in cases:
            assert SlotManager(image).slot_position(slot) == pos, name
            src.write_bytes(image)
            for want in (1, 2):
                save = FFTA2Save(src, slot=slot)
                assert save.record_base == RECORD_OFFSETS[pos], name
                save.difficulty = want
                save.save(dst, backup=False)
                out = dst.read_bytes()
                assert len(out) == len(image)
                check(f"{name} (FFTA2Save, {want})", image, out, slot, pos, want)
                assert FFTA2Save(dst, slot=slot).difficulty == want

                direct = SlotManager(image)
                direct.set_slot_difficulty(slot, want)
                check(f"{name} (set_slot_difficulty, {want})", image, bytes(direct.raw[: len(image)]), slot, pos, want)

        # 64 KB melonDS image: same result, same size, no padding
        small = bytes(_move_slot(raw, act, 1, 3)[:0x10000])
        src.write_bytes(small)
        save = FFTA2Save(src)
        save.difficulty = 1
        save.save(dst, backup=False)
        out = dst.read_bytes()
        assert len(out) == 0x10000
        check("64 KB image", small, out, 0, 3, 1)

    # Writing an empty slot uses the game's allocator: first position with +5 != 0
    sm = SlotManager(raw)
    slot1_record = bytes(raw[RECORD_OFFSETS[1] : RECORD_OFFSETS[1] + SLOT_RECORD_SIZE])
    _, _, payload = sm.get_slot_payload(0)
    sm.put_slot_payload(1, payload, seed=0x0031, preview_source=sm.get_entry_bytes(0))
    assert sm.slot_position(1) == 0, "Slot 2 must take the first free position (the retired entry)"
    assert sm.verify_slot(1)[0]
    assert sm.get_entry_bytes(1)[4:7] == bytes([1, 0, 1]), "new entry must be active, live, slot id 1"
    assert sm.slot_position(0) == 1
    assert bytes(sm.raw[RECORD_OFFSETS[1] : RECORD_OFFSETS[1] + SLOT_RECORD_SIZE]) == slot1_record
    assert sm.get_slot_preview(1)["play_time_formatted"] == sm.get_slot_preview(0)["play_time_formatted"]
    print("[PASS] Slot edits follow the game's live metadata entry to the record it loads.")


def test_hardening():
    """Verify size guards, crypto boundaries, and inventory capacity limits."""
    # 1. Undersized file rejected by FFTA2Save
    with tempfile.TemporaryDirectory() as tmpdir:
        tiny_save = Path(tmpdir) / "tiny.sav"
        tiny_save.write_bytes(b"\x00" * 1024)
        try:
            FFTA2Save(tiny_save)
            raise AssertionError("FFTA2Save failed to reject truncated save file")
        except ValueError as e:
            assert "too small" in str(e)

    # 2. Inventory capacity bounds (400 items max)
    sample_path = get_sample_save_path()
    if sample_path:
        save = FFTA2Save(sample_path)
        # Start from an empty clan bag so the bound does not depend on the sample's items
        from ffta2_tool.save import INVENTORY_BASE, MAX_INVENTORY_SLOTS

        save.plaintext[INVENTORY_BASE : INVENTORY_BASE + MAX_INVENTORY_SLOTS * 4] = bytes(MAX_INVENTORY_SLOTS * 4)
        # Fill all 400 slots with dummy unique item IDs (1..400)
        for item_id in range(1, 401):
            assert save.set_inventory_item(item_id, total_count=1) is True

        # 401st item must be rejected (bag full)
        assert save.set_inventory_item(401, total_count=1) is False
        # But updating an existing item (e.g. item 1) must still succeed
        assert save.set_inventory_item(1, total_count=10) is True

    print("[PASS] Hardening checks verified (size guards and inventory capacity limits).")


def test_god_stats():
    """Verify compute_god_stats calculations and non-destructive topup_unit_stats."""
    from ffta2_tool.stats import JOB_STAT_TABLE, compute_god_stats, topup_clan_stats, topup_unit_stats

    # 1. Job stat table contains all 60 canonical jobs
    assert len(JOB_STAT_TABLE) == 60
    assert 0x08 in JOB_STAT_TABLE  # Parivir

    # 2. Level 1 Parivir (0x08)
    # Parivir ROM base: HP=86, Atk=93, Def=69, Mag=68, Res=69, SpdBase=10 (effective 60)
    st1 = compute_god_stats(0x08, level=1)
    assert st1["hp"] == int(86 * 1.15) == 98
    assert st1["watk"] == int(93 * 1.15) == 106
    assert st1["wdef"] == int(69 * 1.15) == 79
    assert st1["speed"] == int(60 * 1.15) == 69

    # 3. Level 10 Parivir (level_ups = 9)
    # Growth: HP=7 (var 1 -> 8), Atk=11 (var 2 -> 13)
    st10 = compute_god_stats(0x08, level=10)
    assert st10["hp"] == 98 + 9 * 8 == 170
    assert st10["watk"] == 106 + 9 * 13 == 223
    assert st10["speed"] == 69 + 9 == 78

    # 4. Non-destructive top-up verification on sample save
    sample_path = get_sample_save_path()
    if sample_path:
        save = FFTA2Save(sample_path)
        u0 = save.get_unit(0)
        assert u0 is not None
        orig_hp = u0.max_hp
        orig_atk = u0.attack

        # Set an artificially high defense to verify it is NOT reduced
        u0.defense = 999
        changes = topup_unit_stats(u0)

        assert u0.defense == 999, "Defense was lowered by topup_unit_stats!"
        assert u0.max_hp >= orig_hp
        assert u0.attack >= orig_atk
        assert "wdef" not in changes

        # Test clan-wide topup
        clan_changes = topup_clan_stats(save, max_units=6)
        assert isinstance(clan_changes, list)

    print("[PASS] 115% God Roll calculations and non-destructive top-up verified.")


def test_quicksave_deactivation():
    """The quicksave is the live entry with slot id 2 at any position; retiring it spares the slots.

    Regression: deactivate_quicksave() cleared entry position 2 and the record header at
    0x69C8 unconditionally, which deleted a live Slot 2 (or Slot 1) stored there.
    """
    import struct

    from ffta2_tool.slots import (
        RECORD_OFFSETS,
        SLOT_RECORD_SIZE,
        SlotManager,
        active_metadata_base,
        calculate_metadata_checksum,
        entry_offset,
    )

    raw = bytearray(EXAMPLE_SAVE.read_bytes())
    act = active_metadata_base(raw)

    # Live quicksave at position 3 next to Slot 1 at position 1
    image = bytearray(raw)
    _set_entry_state(image, act, 3, 1, 0, 2)
    _resign_copy(image, act)
    sm = SlotManager(image)
    sm.deactivate_quicksave()
    assert sm.raw[entry_offset(act, 3) + 5] == 1, "quicksave entry must be retired (+5 = 1)"
    assert sm.slot_position(0) == 1
    stored = struct.unpack_from("<I", sm.raw, act)[0]
    assert stored == calculate_metadata_checksum(sm.raw[act : act + 0xDC]), "Metadata checksum invalid"
    assert sm.raw[0x01B8:0xD1D8] == image[0x01B8:0xD1D8], "records must not be touched"
    assert sm.raw[:0x40000] == sm.raw[0x40000:0x80000], "bank 2 must mirror bank 1"

    # Slot 1 living at position 2 (record 0x69C8) must survive
    image = _move_slot(raw, act, 1, 2)
    sm = SlotManager(image)
    sm.deactivate_quicksave()
    assert sm.slot_position(0) == 2 and sm.verify_slot(0)[0]
    r = RECORD_OFFSETS[2]
    assert sm.raw[r : r + SLOT_RECORD_SIZE] == image[r : r + SLOT_RECORD_SIZE]
    assert sm.raw[:0x40000] == image[:0x40000], "no quicksave: bank 1 must be unchanged"
    print("[PASS] Quicksave retired by slot id; slots and records untouched; banks mirrored.")


if __name__ == "__main__":
    test_mappings()
    test_parse_simple_toml()
    test_load_builds()
    test_backup_snapshot()
    test_atomic_write()
    test_auto_detect_save()
    test_hardening()
    test_god_stats()
    test_quicksave_deactivation()
    test_validator_guards()
    test_difficulty_roundtrip()
    test_slot_record_mapping()
    test_meta_squad_patcher()
