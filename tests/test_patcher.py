"""Test suite for FFTA2 Meta Squad Patcher."""

import tempfile
from pathlib import Path
from ffta2_tool.crypto import verify_save_checksum
from ffta2_tool.save import FFTA2Save
from ffta2_tool.patcher import apply_meta_squad, META_SQUAD_BUILDS


def get_sample_save_path() -> Path | None:
    candidates = [
        Path.home() / "Documents" / "FFTA2_Backups" / "071 Final Fantasy Tactics A2.sav.orig",
        Path.home() / "Documents" / "FFTA2_Backups" / "071 Final Fantasy Tactics A2.sav",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def test_meta_squad_patcher():
    sample_path = get_sample_save_path()
    if not sample_path:
        print("[SKIP] No sample save found to test patcher.")
        return

    save = FFTA2Save(sample_path)
    apply_meta_squad(save, master_abilities=True)

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

    # Verify write and cryptographic resigning
    with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        save.save(tmp_path)
        patched_raw = tmp_path.read_bytes()
        is_valid, stored, calculated = verify_save_checksum(patched_raw)
        assert is_valid, f"Patched save checksum invalid: stored 0x{stored:X} != calc 0x{calculated:X}"

        # Reload patched save
        reloaded = FFTA2Save(tmp_path)
        u0 = reloaded.get_unit(0)
        assert u0.job_id == 0x08  # Parivir
        assert u0.weapon_id == 0x0018  # Chirijiraden
        assert u0.shield_id == 0x0000  # Empty off-hand
        print(f"[PASS] Successfully patched, signed, and re-verified meta squad on {tmp_path}!")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


if __name__ == "__main__":
    test_meta_squad_patcher()
