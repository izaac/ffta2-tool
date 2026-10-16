"""Test suite for FFTA2 Save Cryptography and Checksum."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ffta2_tool.crypto import (
    decrypt_save_payload,
    encrypt_save_payload,
    extract_keystream,
    verify_save_checksum,
)
from ffta2_tool.save import FFTA2Save


def get_sample_save_path() -> Path | None:
    candidates = [
        Path.home() / "Documents" / "FFTA2_Backups" / "071 Final Fantasy Tactics A2.sav.orig",
        Path.home() / "Documents" / "FFTA2_Backups" / "071 Final Fantasy Tactics A2.sav",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def test_checksum_and_crypto():
    save_path = get_sample_save_path()
    if not save_path:
        print("[SKIP] No sample save found on system to test.")
        return

    raw = save_path.read_bytes()
    is_valid, stored, calculated = verify_save_checksum(raw)
    assert is_valid, f"Checksum verification failed: stored 0x{stored:X} != calc 0x{calculated:X}"
    print(f"[PASS] verify_save_checksum verified stored 0x{stored:08X} == 0x{calculated:08X}")

    # Test roundtrip decryption and encryption
    key = extract_keystream(raw)
    work = bytearray(raw)
    decrypt_save_payload(work, key)
    encrypt_save_payload(work, key)
    assert work == raw, "Roundtrip decrypt -> encrypt did not match original raw bytes!"
    print("[PASS] Roundtrip decrypt -> encrypt is byte-identical!")

    # Test FFTA2Save wrapper on clean save
    save = FFTA2Save(save_path)
    assert save.slot_0_player_name.startswith("Luso"), f"Unexpected leader name: {save.slot_0_player_name}"
    unit0 = save.get_unit(0)
    assert unit0 is not None
    assert unit0.character_id == 0x01, f"Expected character ID 0x01 (Luso), got 0x{unit0.character_id:X}"
    assert unit0.job_id == 0x01, f"Expected job ID 0x01 (Soldier), got 0x{unit0.job_id:X}"
    assert unit0.weapon_id == 0x0019, f"Expected weapon ID 0x0019 (Shortsword), got 0x{unit0.weapon_id:X}"
    assert unit0.shield_id == 0x0121, f"Expected shield ID 0x0121 (Round Shield), got 0x{unit0.shield_id:X}"
    assert unit0.helm_id == 0x0139, f"Expected helm ID 0x0139 (Green Beret), got 0x{unit0.helm_id:X}"
    assert unit0.armor_id == 0x0144, f"Expected armor ID 0x0144 (Bronze Armor), got 0x{unit0.armor_id:X}"
    print("[PASS] FFTA2Save loaded unit 0 equipment:")
    print(f"       Weapon: 0x{unit0.weapon_id:04X} (Shortsword)")
    print(f"       Shield: 0x{unit0.shield_id:04X} (Round Shield)")
    print(f"       Helm:   0x{unit0.helm_id:04X} (Green Beret)")
    print(f"       Armor:  0x{unit0.armor_id:04X} (Bronze Armor)")


if __name__ == "__main__":
    test_checksum_and_crypto()
