"""Test suite for FFTA2 Save Cryptography and Checksum."""

import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ffta2_tool.crypto import (
    ENCRYPTED_END,
    ENCRYPTED_START,
    KEY_SIZE,
    RECORD_HEADER_OFFSET,
    SEED_OFFSET_IN_HEADER,
    apply_keystream,
    calculate_checksum,
    decrypt_save_payload,
    encrypt_save_payload,
    extract_keystream,
    generate_keystream,
    verify_save_checksum,
)
from ffta2_tool.save import FFTA2Save
from ffta2_tool.slots import SlotManager, calculate_metadata_checksum

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_SAVE = REPO_ROOT / "examples" / "FFTA2_Meta_Squad_Hard.sav"


def get_sample_save_path() -> Path | None:
    """Resolve the save exercised by the save-backed tests.

    Order is deterministic and hermetic: an explicit FFTA2_TEST_SAVE override, then the
    committed repo example (so CI and clean machines behave identically), then the
    user's own backups as a last resort.
    """
    override = os.environ.get("FFTA2_TEST_SAVE")
    if override:
        override_path = Path(override).expanduser()
        if not override_path.exists():
            raise FileNotFoundError(f"FFTA2_TEST_SAVE points at a missing save: {override_path}")
        return override_path
    if EXAMPLE_SAVE.exists():
        return EXAMPLE_SAVE
    for p in (
        Path.home() / "Documents" / "FFTA2_Backups" / "071 Final Fantasy Tactics A2.sav.orig",
        Path.home() / "Documents" / "FFTA2_Backups" / "071 Final Fantasy Tactics A2.sav",
    ):
        if p.exists():
            return p
    return None


def _reference_lcg(seed: int, length: int) -> bytes:
    """Independent reimplementation of the ARM9 LCG, used as the test oracle."""
    state = seed & 0xFF
    out = bytearray(length)
    for i in range(length):
        state = (state * 5 + 1) & 0xFF
        out[i] = state
    return bytes(out)


def _reference_checksum(data: bytes, start: int, count: int, zero_first: int = 4) -> int:
    """Independent reimplementation of the ARM9 signed-byte checksum."""
    total = 0
    for i in range(count):
        b = 0 if i < zero_first else data[start + i]
        signed_b = b if b < 128 else b - 256
        total = (total + signed_b + (count - i)) & 0xFFFFFFFF
    return total


# -- new unified primitives -------------------------------------------------------------


def test_generate_keystream_matches_arm9_lcg():
    for seed in (0x00, 0x01, 0x31, 0x7F, 0x80, 0xFF):
        assert generate_keystream(seed, KEY_SIZE) == _reference_lcg(seed, KEY_SIZE)
    assert generate_keystream(0x31, 0) == b""
    stream = generate_keystream(0x31, 300)
    # The LCG is 256-periodic: byte 256 restarts the cycle.
    assert stream[256:300] == stream[:44]
    assert len(stream) == 300
    print("[PASS] generate_keystream matches the ARM9 8-bit LCG")


def test_apply_keystream_roundtrip_and_parity():
    rng = random.Random(0xC0FFEE)
    ks = generate_keystream(0x42, KEY_SIZE)
    plain = bytearray(rng.randrange(256) for _ in range(1024))

    cipher = bytearray(plain)
    apply_keystream(cipher, ks, decrypt=False)
    assert cipher != plain
    apply_keystream(cipher, ks, decrypt=True)
    assert cipher == plain, "apply_keystream encrypt/decrypt roundtrip is not byte-identical"

    # start offset honors absolute keystream indexing, like the save-record cipher.
    buf = bytearray(plain)
    apply_keystream(buf, ks, start=ENCRYPTED_START, decrypt=False)
    assert buf[:ENCRYPTED_START] == plain[:ENCRYPTED_START]
    for i in range(ENCRYPTED_START, len(plain)):
        assert buf[i] == (plain[i] + ks[i % KEY_SIZE]) & 0xFF
    print("[PASS] apply_keystream roundtrip and absolute keystream alignment")


def test_calculate_checksum_parity():
    rng = random.Random(0xBEEF)
    data = bytes(rng.randrange(256) for _ in range(0x4000))

    for start, count in ((0, 0xDC), (0x1B8, 0x3408), (0, None)):
        expected = _reference_checksum(data, start, len(data) - start if count is None else count)
        actual = calculate_checksum(data, start=start, count=count)
        assert actual == expected, f"checksum mismatch for start=0x{start:X} count={count}"

    # Metadata wrapper through slots must match the generic primitive exactly.
    meta = bytearray(rng.randrange(256) for _ in range(0xDC + 8))
    assert calculate_metadata_checksum(meta) == calculate_checksum(meta, count=0xDC, zero_first=4)
    assert calculate_metadata_checksum(meta, start=8) == calculate_checksum(meta, start=8, count=0xDC, zero_first=4)

    # A raised checksum field (already-signed record) must not change the result.
    signed = bytearray(meta)
    signed[0:4] = b"\xde\xad\xbe\xef"
    assert calculate_metadata_checksum(signed) == calculate_metadata_checksum(meta)
    print("[PASS] calculate_checksum matches the ARM9 weighting and zeroes the checksum field")


def test_extract_keystream_phase_alignment():
    seed = 0x31
    save = bytearray(0x400)
    save[RECORD_HEADER_OFFSET + SEED_OFFSET_IN_HEADER] = seed
    key = extract_keystream(bytes(save))
    assert len(key) == KEY_SIZE

    seq = generate_keystream(seed, KEY_SIZE)
    shift = ENCRYPTED_START % KEY_SIZE
    for pos in range(ENCRYPTED_START, ENCRYPTED_START + 3 * KEY_SIZE):
        assert key[pos % KEY_SIZE] == seq[(pos - shift) % KEY_SIZE]
    # The alignment means the first payload byte consumes the first LCG output.
    assert key[ENCRYPTED_START % KEY_SIZE] == seq[0]

    # Legacy wrappers must agree with the generic primitive byte for byte.
    payload = bytearray(0x400)
    payload[ENCRYPTED_START:ENCRYPTED_END] = bytes(range(256)) * 52
    direct = bytearray(payload)
    apply_keystream(direct, key, start=ENCRYPTED_START, decrypt=True)
    legacy = bytearray(payload)
    decrypt_save_payload(legacy, key)
    assert direct == legacy

    reenc = bytearray(legacy)
    encrypt_save_payload(reenc, key)
    assert reenc == payload
    print("[PASS] extract_keystream phase alignment and legacy wrapper parity")


def test_crypto_edge_cases():
    try:
        generate_keystream(0x42, -1)
    except ValueError:
        pass
    else:
        raise AssertionError("negative length did not raise ValueError")

    try:
        apply_keystream(bytearray(10), b"")
    except ValueError:
        pass
    else:
        raise AssertionError("empty keystream did not raise ValueError")

    for bad_start in (-1, 11):
        try:
            apply_keystream(bytearray(10), b"key", start=bad_start)
        except ValueError:
            pass
        else:
            raise AssertionError(f"bad start={bad_start} did not raise ValueError")

    try:
        calculate_checksum(b"short", count=100)
    except ValueError:
        pass
    else:
        raise AssertionError("count exceeding buffer length did not raise ValueError")

    # zero_first=0 includes all bytes without zeroing
    data = b"\x01\x02\x03\x04"
    assert calculate_checksum(data, zero_first=0) == _reference_checksum(data, 0, len(data), zero_first=0)
    print("[PASS] crypto edge cases and parameter guards verified")


# -- save-file backed tests -------------------------------------------------------------


def test_checksum_and_crypto():
    save_path = get_sample_save_path()
    if save_path is None or not save_path.exists():
        try:
            import pytest

            pytest.skip(f"No sample save found at {EXAMPLE_SAVE}")
        except ImportError:
            print(f"[SKIP] No sample save found at {EXAMPLE_SAVE}")
            return
    print(f"[INFO] Sample save: {save_path}")

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

    # The generic keystream must reproduce the phase-aligned save key.
    seq = generate_keystream(raw[RECORD_HEADER_OFFSET + SEED_OFFSET_IN_HEADER], KEY_SIZE)
    shift = ENCRYPTED_START % KEY_SIZE
    assert bytes(seq[(i - shift) % KEY_SIZE] for i in range(KEY_SIZE)) == key
    print("[PASS] generate_keystream reproduces the save-record key")

    # Test FFTA2Save wrapper on clean save
    save = FFTA2Save(save_path)
    assert save.slot_0_player_name.startswith("Luso"), f"Unexpected leader name: {save.slot_0_player_name}"
    unit0 = save.get_unit(0)
    assert unit0 is not None
    assert unit0.character_id == 0x01, f"Expected character ID 0x01 (Luso), got 0x{unit0.character_id:X}"
    if unit0.job_id == 0x01:
        assert unit0.weapon_id == 0x0019, f"Expected weapon ID 0x0019 (Shortsword), got 0x{unit0.weapon_id:X}"
        assert unit0.shield_id == 0x0121, f"Expected shield ID 0x0121 (Round Shield), got 0x{unit0.shield_id:X}"
        assert unit0.helm_id == 0x0139, f"Expected helm ID 0x0139 (Green Beret), got 0x{unit0.helm_id:X}"
        assert unit0.armor_id == 0x0144, f"Expected armor ID 0x0144 (Bronze Armor), got 0x{unit0.armor_id:X}"
        print("[PASS] FFTA2Save loaded unit 0 equipment:")
        print(f"       Weapon: 0x{unit0.weapon_id:04X} (Shortsword)")
        print(f"       Shield: 0x{unit0.shield_id:04X} (Round Shield)")
        print(f"       Helm:   0x{unit0.helm_id:04X} (Green Beret)")
        print(f"       Armor:  0x{unit0.armor_id:04X} (Bronze Armor)")
    else:
        assert unit0.job_id == 0x08, f"Expected job ID 0x08 (Parivir), got 0x{unit0.job_id:X}"
        print("[PASS] FFTA2Save loaded unit 0 equipment:")
        print(f"       Weapon: 0x{unit0.weapon_id:04X}")
        print(f"       Shield: 0x{unit0.shield_id:04X}")

    # SlotManager read path goes through apply_keystream; verify it still validates.
    sm = SlotManager(raw)
    assert sm.has_data(0), "Slot 1 has no data in the sample save"
    ok, slot_stored, slot_calc = sm.verify_slot(0)
    assert ok, f"Slot 1 checksum invalid: 0x{slot_stored:08X} != 0x{slot_calc:08X}"
    print("[PASS] SlotManager record decrypt/checksum validated via shared primitives")


if __name__ == "__main__":
    test_generate_keystream_matches_arm9_lcg()
    test_apply_keystream_roundtrip_and_parity()
    test_calculate_checksum_parity()
    test_extract_keystream_phase_alignment()
    test_crypto_edge_cases()
    test_checksum_and_crypto()
