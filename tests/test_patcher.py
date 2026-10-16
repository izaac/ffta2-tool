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
from ffta2_tool.validator import validate_save


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

    save = FFTA2Save(sample_path)
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

    # Verify ability mastery bounds (0x5A..0x11C mastered across entire unit ability array)
    u0 = save.get_unit(0)
    assert u0 is not None
    assert u0.r_ability == 0x033C
    assert u0.p_ability == 0x035C
    assert all(b == 0xFF for b in u0._data[OFF_UNIT_ABILITIES_START:OFF_UNIT_ABILITIES_END])

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
        assert u0.shield_id == 0x0074  # Hyakushiki-masamune
        assert u0.r_ability == 0x033C  # Strike Back
        assert u0.p_ability == 0x035C  # Dual Wield
        print(f"[PASS] Successfully patched, signed, and re-verified meta squad on {tmp_path}!")
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


if __name__ == "__main__":
    test_mappings()
    test_parse_simple_toml()
    test_load_builds()
    test_backup_snapshot()
    test_atomic_write()
    test_auto_detect_save()
    test_hardening()
    test_god_stats()
    test_meta_squad_patcher()
