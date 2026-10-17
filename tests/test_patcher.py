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

    # Verify ability mastery is NOT blanket-filled by default (0xFF fill black-screens Unit Info)
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
        assert preview["leader_job"] == 0x08, f"Stale preview job 0x{preview['leader_job']:02X}"
        assert preview["leader_name"] == "Luso"
        assert preview["member_count"] == 6
        assert preview["play_time"] == original_preview["play_time"]
        assert preview["location_id"] == original_preview["location_id"]
        assert preview["clan_title"] == original_preview["clan_title"]
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

    # Blanket 0xFF ability array -> ERROR
    u0.shield_id = 0x0000
    u0.p_ability = 0x035C
    u0._data[OFF_UNIT_ABILITIES_START:OFF_UNIT_ABILITIES_END] = b"\xff" * (
        OFF_UNIT_ABILITIES_END - OFF_UNIT_ABILITIES_START
    )
    errors = [i for i in validate_unit(u0) if i.field == "abilities" and i.severity == "ERROR"]
    assert errors, "All-0xFF ability array was not flagged as ERROR"

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
        assert sm.raw[0x0000 + 0x2C + 36] == 1, "Preview byte 36 must be 1 for Hard mode badge"
        assert preview["play_time"] == original_preview["play_time"]
        assert preview["location_id"] & 0xFF == 1
        assert preview["clan_title"] & 0xFF == original_preview["clan_title"] & 0xFF
        for copy_base in (0x0000, 0x00DC):
            stored = struct.unpack_from("<I", sm.raw, copy_base)[0]
            calculated = calculate_metadata_checksum(sm.raw[copy_base : copy_base + 0xDC])
            assert stored == calculated, f"Metadata checksum invalid at 0x{copy_base:04X}"

        # Test set_slot_difficulty directly
        sm.set_slot_difficulty(0, 2)
        assert sm.get_slot_preview(0)["difficulty"] == 2
        assert sm.get_slot_preview(0)["difficulty_label"] == "Normal"
        assert sm.raw[0x0000 + 0x2C + 36] == 0
        sm.set_slot_difficulty(0, 1)
        assert sm.get_slot_preview(0)["difficulty"] == 1
        assert sm.raw[0x0000 + 0x2C + 36] == 1
        print("[PASS] Difficulty flag roundtrip and Hard preview verified.")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


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
    """Verify SlotManager always wipes quicksave slot and record header."""
    import struct

    from ffta2_tool.slots import SlotManager, calculate_metadata_checksum

    raw = bytearray(0x80000)
    # Mark quicksave active in metadata copy 1
    raw[0x84 + 4] = 1
    # Add dummy header at 0x69C8
    raw[0x69C8:0x69D0] = b"\x01\x02\x03\x04\x05\x06\x07\x08"

    sm = SlotManager(raw)
    sm.deactivate_quicksave()

    # Verify quicksave is inactive in copy 1 and copy 2
    for base in (0x0000, 0x00DC):
        assert sm.raw[base + 0x84 + 4] == 0, f"Quicksave active flag not zeroed in copy at 0x{base:04X}"
        stored_chk = struct.unpack_from("<I", sm.raw, base)[0]
        calc_chk = calculate_metadata_checksum(sm.raw[base : base + 0xDC])
        assert stored_chk == calc_chk, "Metadata checksum invalid after quicksave wipe"

    # Verify quicksave record header is cleared
    assert sm.raw[0x69C8:0x69D0] == b"\x00" * 8
    # Verify bank 2 is mirrored
    assert sm.raw[:0x40000] == sm.raw[0x40000:0x80000]
    print("[PASS] Quicksave deactivation and dual-bank mirroring verified.")


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
    test_meta_squad_patcher()
