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

    # Package-data copy must stay byte-identical to repository root
    root_builds = Path(__file__).resolve().parent.parent / "builds.toml"
    data_builds = Path(__file__).resolve().parent.parent / "ffta2_tool" / "data" / "builds.toml"
    assert data_builds.exists(), "ffta2_tool/data/builds.toml missing"
    assert root_builds.read_bytes() == data_builds.read_bytes(), "ffta2_tool/data/builds.toml out of sync"

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
    """Verify create_backup_snapshot writes a timestamped copy to the backup folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        save_path = root / "Test Save.sav"
        bdir = root / "backups"
        payload = b"FFTA2-SAVE-DATA" * 8
        save_path.write_bytes(payload)

        backup_path = create_backup_snapshot(save_path, backup_dir=bdir)

        assert backup_path.exists(), "Backup snapshot was not created"
        assert backup_path.parent == bdir.resolve(), f"Expected backup in {bdir}, got {backup_path.parent}"
        assert backup_path.name.startswith("Test Save.sav.bak_"), backup_path.name
        stamp = backup_path.name.split(".bak_", 1)[1]
        assert len(stamp) == len("YYYYMMDD_HHMMSS") and stamp[8] == "_", f"Bad timestamp: {stamp}"
        assert backup_path.read_bytes() == payload, "Backup content mismatch"

        # Verify FFTA2_BACKUP_DIR environment variable override
        env_bdir = root / "env_backups"
        old_env = os.environ.get("FFTA2_BACKUP_DIR")
        os.environ["FFTA2_BACKUP_DIR"] = str(env_bdir)
        try:
            env_backup = create_backup_snapshot(save_path)
            assert env_backup.parent == env_bdir.resolve()
            assert env_backup.read_bytes() == payload
        finally:
            if old_env is None:
                os.environ.pop("FFTA2_BACKUP_DIR", None)
            else:
                os.environ["FFTA2_BACKUP_DIR"] = old_env
    print("[PASS] Timestamped backup snapshot created in centralized backup folder.")


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


def test_layout_offset_parity():
    """Buffer and payload coordinates are two views of one byte; every pair must agree."""
    from ffta2_tool import crypto, layout, save, slots

    assert layout.RECORD_STAGING_OFFSET == 0x01B8
    assert layout.RECORD_HEADER_SIZE == 0x08
    assert layout.PAYLOAD_START == layout.RECORD_STAGING_OFFSET + layout.RECORD_HEADER_SIZE == 0x01C0
    assert layout.PAYLOAD_START + layout.PAYLOAD_SIZE == 0x35C0

    for name, buffer_off, payload_off in layout.FIELD_OFFSET_PAIRS:
        assert buffer_off - payload_off == layout.PAYLOAD_START, f"{name}: buffer/payload pair drift"
        assert layout.buffer_to_payload_offset(buffer_off) == payload_off, name
        assert layout.payload_to_buffer_offset(payload_off) == buffer_off, name

    # Modules must derive their constants from the canonical pairs, not own copies.
    assert crypto.RECORD_HEADER_OFFSET == layout.RECORD_STAGING_OFFSET
    assert crypto.ENCRYPTED_START == layout.PAYLOAD_START
    assert crypto.ENCRYPTED_SIZE == layout.PAYLOAD_SIZE
    assert slots.RECORD_BASE == layout.RECORD_STAGING_OFFSET
    assert slots.RECORD_HEADER_SIZE == layout.RECORD_HEADER_SIZE
    assert slots.SLOT_PAYLOAD_SIZE == layout.PAYLOAD_SIZE
    aliases = {
        "OFF_CLAN_NAME": layout.BUFFER_OFF_CLAN_NAME,
        "OFF_LEADER_NAME": layout.BUFFER_OFF_LEADER_NAME,
        "UNIT_TABLE_BASE": layout.BUFFER_OFF_UNIT_TABLE,
        "INVENTORY_BASE": layout.BUFFER_OFF_INVENTORY,
        "OFF_GIL": layout.BUFFER_OFF_GIL,
        "OFF_CLAN_POINTS": layout.BUFFER_OFF_CLAN_POINTS,
        "OFF_CLAN_TALENTS": layout.BUFFER_OFF_CLAN_TALENTS,
        "OFF_CLAN_PRIVILEGES_START": layout.BUFFER_OFF_CLAN_PRIVILEGES,
        "OFF_DIFFICULTY": layout.BUFFER_OFF_DIFFICULTY,
    }
    for attr, want in aliases.items():
        assert getattr(save, attr) == want, f"save.{attr} lost its layout alias"
    print("[PASS] Buffer/payload offset pairs agree with PAYLOAD_START 0x01C0.")


def test_difficulty_helpers():
    """The stored 0/1 byte and the API 1/2 convention convert and validate correctly."""
    from ffta2_tool.layout import (
        BUFFER_OFF_DIFFICULTY,
        DIFFICULTY_API_HARD,
        DIFFICULTY_API_NORMAL,
        DIFFICULTY_RAW_HARD,
        DIFFICULTY_RAW_NORMAL,
        api_to_raw_difficulty,
        raw_to_api_difficulty,
    )

    assert (DIFFICULTY_RAW_NORMAL, DIFFICULTY_RAW_HARD) == (0, 1)
    assert (DIFFICULTY_API_HARD, DIFFICULTY_API_NORMAL) == (1, 2)
    assert raw_to_api_difficulty(0) == DIFFICULTY_API_NORMAL
    assert raw_to_api_difficulty(1) == DIFFICULTY_API_HARD
    assert raw_to_api_difficulty(2) == DIFFICULTY_API_NORMAL  # anything but 1 plays as Normal
    assert api_to_raw_difficulty(1) == DIFFICULTY_RAW_HARD
    assert api_to_raw_difficulty(2) == DIFFICULTY_RAW_NORMAL
    assert api_to_raw_difficulty(0) == DIFFICULTY_RAW_NORMAL  # 0 is a Normal alias

    for bad in (3, -1, 4, 255, True, False, "1"):
        try:
            api_to_raw_difficulty(bad)
        except ValueError:
            continue
        raise AssertionError(f"api_to_raw_difficulty accepted invalid value {bad}")

    save = FFTA2Save(EXAMPLE_SAVE)
    for value, raw in ((1, 1), (2, 0), (0, 0)):
        save.difficulty = value
        assert save.plaintext[BUFFER_OFF_DIFFICULTY] == raw, f"difficulty={value} wrote {raw}"
        assert save.difficulty == (1 if raw == 1 else 2)
    for bad in (3, -1):
        try:
            save.difficulty = bad
        except ValueError:
            pass
        else:
            raise AssertionError(f"difficulty setter accepted invalid value {bad}")
    assert save.plaintext[BUFFER_OFF_DIFFICULTY] == 0, "a rejected difficulty must not be written"
    print("[PASS] Difficulty raw/API helpers and setter validation verified.")


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

    from ffta2_tool.layout import PAYLOAD_OFF_DIFFICULTY
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
        assert payload[PAYLOAD_OFF_DIFFICULTY] == (1 if want == 1 else 0), (
            f"{name}: difficulty not in the loaded record"
        )
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


def _two_slot_example() -> bytes:
    """Example save with Slot 1 copied into the empty Slot 2 (first free position)."""
    from ffta2_tool.slots import SlotManager

    sm = SlotManager(EXAMPLE_SAVE.read_bytes())
    _, seed, payload = sm.get_slot_payload(0)
    sm.put_slot_payload(1, payload, seed=seed, preview_source=sm.get_entry_bytes(0))
    return bytes(sm.raw)


def test_clan_perks():
    from ffta2_tool.save import CLAN_PRIVILEGE_MASK, OFF_CLAN_PRIVILEGES_START

    save = FFTA2Save(EXAMPLE_SAVE)
    # Offsets match the in-game Clan Info screen of the example save
    assert (save.gil, save.clan_points, save.clan_talents) == (3920, 16, (5, 3, 5, 6))

    save.gil = 10**9
    save.clan_points = 10**6
    save.clan_talents = (150, -1, 99, 7)
    assert (save.gil, save.clan_points, save.clan_talents) == (99999999, 9999, (99, 0, 99, 7))

    # Unlocking ORs the 58-bit privilege mask: owned privileges and non-privilege bits survive
    assert sum(b.bit_count() for b in CLAN_PRIVILEGE_MASK) == 58
    base = OFF_CLAN_PRIVILEGES_START
    save.plaintext[base] = 0x05  # bits 0..3 are not privileges
    save.plaintext[base + 5] = 0xA0  # bits 4..7 are nameless "-" entries
    save.plaintext[base + 8] = 0x50  # bits 4..7 lie past entry 64 (0x075B)
    save.unlock_clan_privileges()
    field = bytes(save.plaintext[base : base + len(CLAN_PRIVILEGE_MASK)])
    assert field[0] == 0xF5 and field[5] == 0xAF and field[8] == 0x5F, field.hex()
    assert all(b & m == m for b, m in zip(field, CLAN_PRIVILEGE_MASK, strict=True))

    # master-abilities --unit must refuse an empty unit slot instead of writing 0xFF into it
    empty = next(i for i in range(24) if not save.get_unit(i).is_recruited)
    before = bytes(save.plaintext)
    try:
        save.master_all_unit_abilities(empty)
        raise AssertionError("Mastering an empty unit slot must raise ValueError")
    except ValueError:
        pass
    assert bytes(save.plaintext) == before
    assert save.master_all_unit_abilities() == 6
    print("[PASS] Clan perks clamp, privileges OR the mask, empty unit slots are refused.")


def test_operations_idempotent():
    """Every save-modifying operation, applied twice through a save/load cycle, is byte-stable."""
    from ffta2_tool.slots import SLOT_RECORD_SIZE, SlotManager
    from ffta2_tool.stats import topup_clan_stats

    def via_save(slot, fn):
        def op(path):
            save = FFTA2Save(path, slot=slot)
            fn(save)
            save.save(path, backup=False)

        return op

    def via_slots(fn):
        def op(path):
            sm = SlotManager(path.read_bytes())
            fn(sm)
            sm.save_to_file(path)

        return op

    def copy_slot(sm):
        _, seed, payload = sm.get_slot_payload(0)
        sm.put_slot_payload(1, payload, seed=seed, preview_source=sm.get_entry_bytes(0))

    def set_weapon(save):
        save.get_unit(0).weapon_id = 0x0018
        save.sync_equipped_to_inventory()

    def clan_all(save):
        save.gil, save.clan_points, save.clan_talents = 99999999, 9999, (99, 99, 99, 99)
        save.unlock_clan_privileges()

    def set_hard(save):
        save.difficulty = 1

    def rename_ops(save):
        save.clan_name = "Kupo"
        save.rename_unit(0, "Ramza")
        save.rename_unit(1, "Alde")

    def clan_name_op(save):
        save.clan_name = "Ivalice"

    def inject_slot7(save):
        save.inject_unit("viera", level=50, name="Acia", unit_index=6, master_abilities=True, force=True)

    def equip_slot2(save):
        from ffta2_tool.patcher import equip_unit_build

        equip_unit_build(save, 1, "nu_mou", master_abilities=True, topup_stats=True)

    ops = {
        "load/save": (0, via_save(0, lambda save: None)),
        "set-weapon slot 2": (1, via_save(1, set_weapon)),
        "patch-meta-squad slot 2": (1, via_save(1, apply_meta_squad)),
        "topup-stats slot 2": (1, via_save(1, topup_clan_stats)),
        "set-difficulty slot 2": (1, via_save(1, set_hard)),
        "master-abilities": (0, via_save(0, FFTA2Save.master_all_unit_abilities)),
        "clan --all": (1, via_save(1, clan_all)),
        "clan --clan-name slot 2": (1, via_save(1, clan_name_op)),
        "rename slot 2": (1, via_save(1, rename_ops)),
        "inject unit 7 slot 2": (1, via_save(1, inject_slot7)),
        "equip-build unit 2 slot 2": (1, via_save(1, equip_slot2)),
        "slots set-difficulty": (1, via_slots(lambda sm: sm.set_slot_difficulty(1, 2))),
        "slots wipe-quicksave": (None, via_slots(SlotManager.deactivate_quicksave)),
        "slots copy 1->2": (1, via_slots(copy_slot)),
    }
    source = _two_slot_example()
    src_sm = SlotManager(source)
    s1_off = src_sm.record_offset(0)
    s1_record = source[s1_off : s1_off + SLOT_RECORD_SIZE]
    with tempfile.TemporaryDirectory() as tmp:
        for name, (target_slot, op) in ops.items():
            path = Path(tmp) / "op.sav"
            path.write_bytes(source)
            op(path)
            once = path.read_bytes()
            op(path)
            assert path.read_bytes() == once, f"{name} is not idempotent"
            assert len(once) == len(source), f"{name} changed the file size"
            sm = SlotManager(once)
            assert sm.verify_slot(0)[0] and sm.verify_slot(1)[0], f"{name} broke a slot checksum"
            if target_slot == 1:
                assert once[s1_off : s1_off + SLOT_RECORD_SIZE] == s1_record, f"{name} touched Slot 1 record"
    print(f"[PASS] {len(ops)} save operations are byte-for-byte idempotent and keep both slots valid.")


def test_load_config():
    """Verify load_config parses config.example.toml and custom TOML files."""
    from ffta2_tool.config import DEFAULT_CONFIG_EXAMPLE_PATH, load_builds_by_key, load_config

    assert DEFAULT_CONFIG_EXAMPLE_PATH.exists(), "config.example.toml missing"
    root_cfg = Path(__file__).resolve().parent.parent / "config.example.toml"
    data_cfg = Path(__file__).resolve().parent.parent / "ffta2_tool" / "data" / "config.example.toml"
    assert data_cfg.exists(), "ffta2_tool/data/config.example.toml missing"
    assert root_cfg.read_bytes() == data_cfg.read_bytes(), "ffta2_tool/data/config.example.toml out of sync"
    example_cfg = load_config(DEFAULT_CONFIG_EXAMPLE_PATH)
    assert "paths" in example_cfg and "defaults" in example_cfg
    assert example_cfg["defaults"]["slot"] == 1

    by_key = load_builds_by_key()
    assert set(by_key.keys()) == {"luso", "nu_mou", "viera", "bangaa", "hume", "moogle"}

    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_file = Path(tmpdir) / "custom_config.toml"
        cfg_file.write_text(
            '[paths]\nsave_search_paths = [\n  "/tmp/a/*.sav",\n  "/tmp/b/*.sav",\n]\n'
            'backup_dir = "/tmp/my_backups"\n\n[defaults]\nslot = 2\n',
            encoding="utf-8",
        )
        cfg = load_config(cfg_file)
        assert cfg["paths"]["save_search_paths"] == ["/tmp/a/*.sav", "/tmp/b/*.sav"]
        assert cfg["paths"]["backup_dir"] == "/tmp/my_backups"
        assert cfg["defaults"]["slot"] == 2
    print("[PASS] load_config and load_builds_by_key verified.")


def test_character_names_and_charset():
    """Verify FFTA2 character name table, charset digits/punctuation, and name resolver."""
    from ffta2_tool.character_names import (
        CHARACTER_NAMES,
        get_character_name,
        get_default_name_id_for_race,
        get_race_name_pool,
        resolve_character_name_id,
    )
    from ffta2_tool.charset import MAX_CUSTOM_NAME_CHARS, decode_ffta2_string, encode_ffta2_string

    assert len(CHARACTER_NAMES) == 779
    assert MAX_CUSTOM_NAME_CHARS == 9
    assert get_character_name(0x8001) == "Luso"
    assert get_character_name(0x8003) == "Adelle"
    assert get_character_name(48) == "Frimelda"
    assert get_character_name(109) == "Ganoslal"
    assert get_character_name(408) == "Yuma"

    # Generic race pool resolution succeeds for matching race
    assert resolve_character_name_id("Ganoslal", race_id=1) == 109
    assert resolve_character_name_id("408", race_id=4) == 408
    assert resolve_character_name_id(408, race_id=4) == 408
    nid = resolve_character_name_id("random", race_id=4)
    assert nid in get_race_name_pool(4)
    assert get_default_name_id_for_race(4, 2) in get_race_name_pool(4)

    # High-bit (0x8000) values and out-of-range IDs are always rejected
    for bad_id in (0, -1, 779, 0x8001, 0x8005, "0x8005", "0", "779"):
        try:
            resolve_character_name_id(bad_id, race_id=1, allow_any_pool=True)
            raise AssertionError(f"resolve_character_name_id accepted {bad_id!r}")
        except ValueError:
            pass

    # Story names (Luso, Cid, Vaan, Frimelda, "-") and wrong-race pools are rejected unless allow_any_pool=True
    for story_or_wrong in ("Luso", "Cid", "Vaan", "Frimelda", "-", "Yuma", 408):
        try:
            resolve_character_name_id(story_or_wrong, race_id=1, allow_any_pool=False)
            raise AssertionError(f"resolve_character_name_id accepted {story_or_wrong!r} for Hume without force")
        except ValueError:
            pass
    assert resolve_character_name_id("Frimelda", race_id=1, allow_any_pool=True) == 48
    assert resolve_character_name_id("Yuma", race_id=1, allow_any_pool=True) == 408

    # Roundtrip charset encoding with letters, digits, and punctuation
    for text in ("Luso", "Gully", "Clan 99!", "A-B's?", "R,D.1:2"):
        encoded = encode_ffta2_string(text, length=20)
        assert len(encoded) == 20
        assert encoded[-1] == 0
        assert decode_ffta2_string(encoded) == text

    # Unsupported characters and missing-terminator buffer overflow raise ValueError
    for bad_text in ("Ramza@", "Clan#1", "Name$9", "Luso\n", "A" * 20):
        try:
            encode_ffta2_string(bad_text, length=20)
            raise AssertionError(f"encode_ffta2_string accepted {bad_text!r}")
        except ValueError:
            pass
    print("[PASS] Character names table and FFTA2 string encoding/decoding verified.")


def test_rename_unit_and_clan():
    """Verify renaming Luso (custom string), generic units (ROM race pool), and clan name with slot isolation."""
    import warnings

    from ffta2_tool.slots import SLOT_RECORD_SIZE, SlotManager

    two_slot_bytes = _two_slot_example()
    base_sm = SlotManager(two_slot_bytes)
    s2_off = base_sm.record_offset(1)
    s2_record_before = two_slot_bytes[s2_off : s2_off + SLOT_RECORD_SIZE]

    with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp_path.write_bytes(two_slot_bytes)

    try:
        save = FFTA2Save(tmp_path, slot=0)
        assert save.leader_name == "Luso"
        assert save.clan_name == "Gully"
        assert save.get_unit_name(0) == "Luso"
        assert save.get_unit_name(1) == "Ganoslal"
        assert save.get_unit_name(2) == "Yuma"

        # 1. Rename Luso (up to 9-char cap) and clan with custom strings
        assert save.rename_unit(0, "RamzaBeou") == "RamzaBeou"
        save.clan_name = "Ivalice99"
        assert save.leader_name == "RamzaBeou"
        assert save.clan_name == "Ivalice99"
        assert save.get_unit_name(0) == "RamzaBeou"
        assert save.get_unit(0).name_id == 0x8001

        # 2. Luso refuses ROM IDs and "random"
        for bad_luso in (109, "109", "0x006D", "random"):
            try:
                save.rename_unit(0, bad_luso)
                raise AssertionError(f"Luso accepted {bad_luso!r}")
            except ValueError:
                pass

        # 3. Over-cap (>9 chars) and bad characters raise on leader_name and clan_name
        for bad_custom in ("TenCharNam", " fifteenchars123 ", "Bad@Name", ""):
            try:
                save.rename_unit(0, bad_custom)
                raise AssertionError(f"leader_name accepted {bad_custom!r}")
            except ValueError:
                pass
            try:
                save.clan_name = bad_custom
                raise AssertionError(f"clan_name accepted {bad_custom!r}")
            except ValueError:
                pass

        # 4. Generic unit (Unit 2, index 1, Nu Mou -> Male pool 68..265) accepts pool name/ID
        assert save.rename_unit(1, "Alde") == "Alde"
        assert save.get_unit_name(1) == "Alde"
        assert save.get_unit(1).name_id == 72

        # Generic unit (Unit 3, index 2, Viera -> Female pool 281..429) accepts Viera pool ID
        assert save.rename_unit(2, "408") == "Yuma"
        assert save.get_unit(2).name_id == 408

        # 5. Generic unit rejects story names and wrong-race names unless force=True
        for rejected in ("Frimelda", "Vaan", "Luso", "Yuma", 408, "NotARomName"):
            try:
                save.rename_unit(1, rejected)
                raise AssertionError(f"Generic Nu Mou unit accepted {rejected!r} without force")
            except ValueError:
                pass
        assert save.rename_unit(1, "Frimelda", force=True) == "Frimelda"
        assert save.rename_unit(1, "Alde") == "Alde"

        # 6. Duplicate name across clan units emits UserWarning
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", UserWarning)
            save.rename_unit(3, "Alde")  # Unit 4 (Bangaa) shares Male pool with Unit 2
            assert any("already used" in str(w.message) for w in caught)

        # 7. Empty unit slot is refused
        try:
            save.rename_unit(6, "Alde")
            raise AssertionError("rename_unit accepted empty unit slot")
        except ValueError as e:
            assert "empty" in str(e)

        # 8. Save/reload updates load-screen preview leader_name and leaves Slot 2 record untouched
        save.save(tmp_path, backup=False)
        reloaded = FFTA2Save(tmp_path, slot=0)
        assert reloaded.leader_name == "RamzaBeou"
        assert reloaded.clan_name == "Ivalice99"
        assert reloaded.get_unit_name(0) == "RamzaBeou"
        assert reloaded.get_unit_name(1) == "Alde"
        after_bytes = tmp_path.read_bytes()
        sm = SlotManager(after_bytes)
        assert sm.get_slot_preview(0)["leader_name"] == "RamzaBeou"
        assert after_bytes[s2_off : s2_off + SLOT_RECORD_SIZE] == s2_record_before, "Slot 2 record was modified"
        assert not [i for i in validate_save(reloaded) if i.severity == "ERROR"]
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    print("[PASS] Unit and clan renaming verified with cap, race pools, preview sync, and slot isolation.")


def test_inject_unit():
    """Verify injecting new recruits, template cloning, contiguity, slot refusal rules, and slot isolation."""
    from ffta2_tool.save import UNIT_STRIDE, UNIT_TABLE_BASE
    from ffta2_tool.slots import SLOT_RECORD_SIZE, SlotManager

    two_slot_bytes = _two_slot_example()
    base_sm = SlotManager(two_slot_bytes)
    s2_off = base_sm.record_offset(1)
    s2_record_before = two_slot_bytes[s2_off : s2_off + SLOT_RECORD_SIZE]

    with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp_path.write_bytes(two_slot_bytes)

    try:
        save = FFTA2Save(tmp_path, slot=0)
        assert sum(1 for u in save.units if u.is_recruited) == 6
        units_0_to_5_before = [bytes(save.get_unit(i)._data) for i in range(6)]
        units_7_to_23_before = [bytes(save.get_unit(i)._data) for i in range(7, 24)]

        # 1. Refuses slot 0 (Luso) even with force=True
        for f_flag in (False, True):
            try:
                save.inject_unit("viera", unit_index=0, force=f_flag)
                raise AssertionError("inject_unit allowed slot 0")
            except ValueError as e:
                assert "Luso" in str(e)

        # 2. Refuses occupied slot (1..5) without force=True
        try:
            save.inject_unit("viera", unit_index=2, force=False)
            raise AssertionError("inject_unit allowed overwriting occupied slot without force")
        except ValueError as e:
            assert "already occupied" in str(e)

        # 3. Refuses injecting into a gap (slot 8 / index 7 when slot 7 / index 6 is empty)
        try:
            save.inject_unit("viera", unit_index=7)
            raise AssertionError("inject_unit allowed creating a roster hole at index 7")
        except ValueError as e:
            assert "contiguous" in str(e) or "empty" in str(e)

        # 4. Inject into first free slot (index 6 -> Unit 7) using valid Viera pool name
        idx1, u1 = save.inject_unit("viera", level=50, name="Acia")
        assert idx1 == 6
        assert u1.is_recruited
        assert u1.character_id == 0
        assert u1.job_id == 0x27  # Red Mage
        assert u1.race_id == 4  # Viera
        assert u1.roster_index == 7
        assert u1.status_flags == 0x0080
        assert u1.level == 50
        assert u1.cur_hp == u1.max_hp and u1.max_hp > 0
        assert u1.cur_mp == 0 and u1.max_mp > 0
        assert bytes(u1._data[0x25:0x2E]) == b"\x01" * 9
        assert u1.weapon_id == 0x0050  # Femme Fatale
        assert save.get_unit_name(idx1) == "Acia"

        # Untouched units 0..5 and 7..23 are byte-identical
        assert [bytes(save.get_unit(i)._data) for i in range(6)] == units_0_to_5_before
        assert [bytes(save.get_unit(i)._data) for i in range(7, 24)] == units_7_to_23_before

        # 5. Save -> Load stability and Slot 2 byte-isolation
        save.save(tmp_path, backup=False)
        after_first_save = tmp_path.read_bytes()
        assert after_first_save[s2_off : s2_off + SLOT_RECORD_SIZE] == s2_record_before
        reloaded = FFTA2Save(tmp_path, slot=0)
        assert bytes(reloaded.get_unit(6)._data) == bytes(u1._data)
        sm = SlotManager(after_first_save)
        assert sm.get_slot_preview(0)["member_count"] == 7
        assert not [i for i in validate_save(reloaded) if i.severity == "ERROR"]

        # 6. Fill roster up to 24 units and verify full-roster refusal on the 25th
        for expected_idx in range(7, 24):
            idx_n, u_n = reloaded.inject_unit("Parivir", level=30)
            assert idx_n == expected_idx
            assert u_n.roster_index == expected_idx + 1
        assert sum(1 for u in reloaded.units if u.is_recruited) == 24
        assert not [i for i in validate_save(reloaded) if i.severity == "ERROR"]

        try:
            reloaded.inject_unit("Parivir", level=30)
            raise AssertionError("inject_unit allowed injecting into a full 24/24 roster")
        except ValueError as e:
            assert "full" in str(e).lower()

        # 7. Verify roster hole detection when an intermediate unit is zeroed out
        reloaded.plaintext[UNIT_TABLE_BASE + 3 * UNIT_STRIDE : UNIT_TABLE_BASE + 4 * UNIT_STRIDE] = (
            b"\x00" * UNIT_STRIDE
        )
        try:
            reloaded.inject_unit("Parivir", level=30)
            raise AssertionError("inject_unit allowed injecting when roster has a hole")
        except ValueError as e:
            assert "hole" in str(e).lower()
        hole_issues = [i for i in validate_save(reloaded) if i.severity == "ERROR" and i.field == "roster"]
        assert hole_issues, "validate_save must flag non-contiguous roster hole"
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    print("[PASS] Recruit injection verified for contiguity, slot guards, template overrides, and slot isolation.")


def test_equip_unit_build():
    """Verify equipping a build from builds.toml onto a single unit."""
    from ffta2_tool.patcher import equip_unit_build

    save = FFTA2Save(EXAMPLE_SAVE)
    info = equip_unit_build(save, 2, "viera", master_abilities=True, topup_stats=True)
    u2 = save.get_unit(2)
    assert u2.job_id == 0x27
    assert u2.weapon_id == 0x0050
    assert u2.p_ability == 0x036A  # Blood Price
    assert info["job_id"] == 0x27
    errors = [i for i in validate_save(save) if i.severity == "ERROR"]
    assert not errors, f"Validation errors after equip_unit_build: {errors}"
    print("[PASS] equip_unit_build verified.")


def test_cli_new_commands():
    """Verify CLI subcommands backup, rename, inject, equip-build, and clan --clan-name."""
    import subprocess

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        sav = root / "test.sav"
        bdir = root / "backups"
        cfg = root / "config.toml"
        sav.write_bytes(EXAMPLE_SAVE.read_bytes())
        cfg.write_text(
            f'[paths]\nsave_search_paths = ["{sav.as_posix()}"]\n'
            f'backup_dir = "{bdir.as_posix()}"\n[defaults]\nslot = 1\n',
            encoding="utf-8",
        )

        def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, "-m", "ffta2_tool.cli", *args],
                capture_output=True,
                text=True,
                check=True,
            )

        # 1. Standalone backup command (auto-detecting save via config.toml save_search_paths)
        res = run_cli("backup", "--config", str(cfg))
        assert "Backup snapshot created" in res.stdout
        backups = list(bdir.glob("test.sav.bak_*"))
        assert len(backups) == 1

        # 2. Rename unit 1 and clan (within 9-char cap)
        run_cli(
            "rename",
            str(sav),
            "--config",
            str(cfg),
            "--unit",
            "1",
            "--name",
            "Ramza",
            "--clan-name",
            "Beoulve",
        )
        reloaded = FFTA2Save(sav)
        assert reloaded.leader_name == "Ramza"
        assert reloaded.clan_name == "Beoulve"

        # 3. Inject unit 7 with a valid Viera race-pool name ("Acia")
        run_cli(
            "inject",
            str(sav),
            "--config",
            str(cfg),
            "--job",
            "viera",
            "--level",
            "60",
            "--name",
            "Acia",
            "--master-abilities",
        )
        reloaded = FFTA2Save(sav)
        assert reloaded.get_unit(6).is_recruited
        assert reloaded.get_unit(6).level == 60
        assert reloaded.get_unit_name(6) == "Acia"

        # 4. Equip build on unit 7 (using Viera build to match unit 7's Viera race-pool name)
        run_cli(
            "equip-build",
            str(sav),
            "--config",
            str(cfg),
            "--unit",
            "7",
            "--build",
            "viera",
            "--master-abilities",
        )
        reloaded = FFTA2Save(sav)
        assert reloaded.get_unit(6).job_id == 0x27  # Red Mage
    print("[PASS] CLI subcommands backup, rename, inject, and equip-build verified.")


if __name__ == "__main__":
    test_mappings()
    test_parse_simple_toml()
    test_load_builds()
    test_load_config()
    test_character_names_and_charset()
    test_backup_snapshot()
    test_atomic_write()
    test_auto_detect_save()
    test_hardening()
    test_god_stats()
    test_quicksave_deactivation()
    test_validator_guards()
    test_difficulty_roundtrip()
    test_layout_offset_parity()
    test_difficulty_helpers()
    test_slot_record_mapping()
    test_clan_perks()
    test_rename_unit_and_clan()
    test_inject_unit()
    test_equip_unit_build()
    test_cli_new_commands()
    test_operations_idempotent()
    test_meta_squad_patcher()
