"""FFTA2 (NDS) Save Cryptography and Checksum Module.

Reverse-engineered directly from ARM9 binary:
- Decryption/Encryption: Additive stream cipher (ARM9 0x0210D740 - 0x0210D75C)
- Checksum: Signed byte summation with reverse-index weighting (ARM9 0x0210D560 - 0x0210D590)

This module is the single source of truth for every cipher and checksum primitive in
the tool. The legacy, save-record-specific helpers at the bottom are thin wrappers
around the three generic building blocks:

- generate_keystream: the 8-bit LCG (state = 5 * state + 1)
- apply_keystream: additive stream cipher application (encrypt / decrypt)
- calculate_checksum: signed-byte sum with reverse-index weighting
"""

from __future__ import annotations

import struct

from ffta2_tool.layout import PAYLOAD_SIZE, PAYLOAD_START, RECORD_STAGING_OFFSET

# Standard offsets for FFTA2 NDS saves (512 KB EEPROM/Flash). They address record
# position 0; a slot can live in any of the 4 record positions (see ffta2_tool.slots),
# and FFTA2Save stages the slot's record into this window before using them.
# The canonical values live in ffta2_tool.layout; these names are kept for callers.
RECORD_HEADER_OFFSET = RECORD_STAGING_OFFSET  # 0x01B8
CHECKSUM_OFFSET = RECORD_STAGING_OFFSET
CHECKSUM_SIZE = 4
ENCRYPTED_START = PAYLOAD_START  # 0x01C0
ENCRYPTED_SIZE = PAYLOAD_SIZE  # 0x3400
ENCRYPTED_END = ENCRYPTED_START + ENCRYPTED_SIZE  # 0x35C0
KEY_SIZE = 256
CHECKSUM_RANGE_COUNT = 0x3408  # Record header (0x01B8) through 0x35BF
SEED_OFFSET_IN_HEADER = 6  # u32 checksum, u16 version, u16 seed


# -- unified primitives ---------------------------------------------------------------


def generate_keystream(seed: int, length: int) -> bytes:
    """Generate `length` keystream bytes from the reverse-engineered 8-bit LCG.

    ARM9 routine (0x0210CF84):
        state = seed & 0xFF
        for each byte:
            state = (state * 5 + 1) & 0xFF
            yield state

    Byte i of the result is the keystream for the i-th byte of the region being
    processed, so callers that need a phase-shifted key must shift it themselves
    (see extract_keystream for the save-record alignment).
    """
    if length < 0:
        raise ValueError(f"length must be non-negative, got {length}")
    state = seed & 0xFF
    stream = bytearray(length)
    for i in range(length):
        state = (state * 5 + 1) & 0xFF
        stream[i] = state
    return bytes(stream)


def apply_keystream(
    data: bytearray,
    keystream: bytes,
    *,
    start: int = 0,
    decrypt: bool = True,
) -> bytearray:
    """Apply the additive stream cipher in place over data[start:].

    Decrypt: data[i] = (data[i] - keystream[i % len]) & 0xFF
    Encrypt: data[i] = (data[i] + keystream[i % len]) & 0xFF

    The keystream index is the ABSOLUTE data index modulo the keystream length, so a
    phase-aligned key (as built by extract_keystream) lines up with its true byte
    positions. Callers encrypting a standalone buffer whose byte 0 is the keystream's
    byte 0 use start=0.
    """
    if not keystream:
        raise ValueError("Keystream must not be empty")
    key_len = len(keystream)
    if start < 0 or start > len(data):
        raise ValueError(f"start {start} out of range for buffer of {len(data)} bytes")
    for i in range(start, len(data)):
        k = keystream[i % key_len]
        data[i] = (data[i] - k) & 0xFF if decrypt else (data[i] + k) & 0xFF
    return data


def calculate_checksum(
    data: bytes | bytearray,
    *,
    start: int = 0,
    count: int | None = None,
    zero_first: int = 4,
) -> int:
    """Calculate the exact 32-bit FFTA2 signed-byte checksum over data.

    ARM9 assembly routine (0x0210D560 - 0x0210D590):
        sum = 0
        for i in 0 .. (count - 1):
            signed_byte = 0 if i < zero_first else (int8)buffer[start + i]
            term = signed_byte + (count - i)
            sum = (sum + term) & 0xFFFFFFFF
        return sum

    count defaults to the whole remaining buffer (len(data) - start). zero_first is
    the number of leading checksum-field bytes treated as zero; the weight term uses
    the full count, matching the ARM loop.
    """
    if start < 0:
        raise ValueError(f"start must be non-negative, got {start}")
    length = len(data) - start if count is None else count
    if length < 0:
        raise ValueError(f"count must be non-negative, got {length}")
    if len(data) < start + length:
        raise ValueError(f"Plaintext buffer too small ({len(data)} bytes), requires at least {start + length} bytes")

    total = 0
    for i in range(length):
        b = 0 if i < zero_first else data[start + i]
        # Interpret as signed 8-bit integer (LDRSB in ARM)
        signed_b = b if b < 128 else b - 256
        term = (signed_b + (length - i)) & 0xFFFFFFFF
        total = (total + term) & 0xFFFFFFFF
    return total


# -- save-record wrappers (legacy API, 100% backwards compatible) ---------------------


def extract_keystream(save_bytes: bytes, header_offset: int = RECORD_HEADER_OFFSET) -> bytes:
    """Extract and generate the 256-byte additive keystream from the record header seed.

    ARM9 binary (0x0210CF74 / 0x0210CF84 / 0x0210D740):
    The 8-bit seed at header_offset + 6 initializes an LCG: state = (5 * state + 1) & 0xFF.
    Because the cipher loop starts at offset 0x01C0 (RECORD_HEADER_OFFSET + 8),
    the generated cycle is aligned so key[i % 256] matches byte position i.
    """
    seed_offset = header_offset + SEED_OFFSET_IN_HEADER
    if len(save_bytes) <= seed_offset:
        raise ValueError(f"Save file too small ({len(save_bytes)} bytes) to extract keystream seed")
    seed = save_bytes[seed_offset]

    seq = generate_keystream(seed, KEY_SIZE)

    shift = ENCRYPTED_START % KEY_SIZE
    return bytes(seq[(i - shift) % KEY_SIZE] for i in range(KEY_SIZE))


def decrypt_save_payload(data: bytearray, key: bytes) -> bytearray:
    """Decrypt save payload in-place using the additive stream cipher.

    Formula: plaintext[i] = (ciphertext[i] - keystream[i % 256]) & 0xFF
    """
    if len(key) != KEY_SIZE:
        raise ValueError(f"Key must be exactly {KEY_SIZE} bytes")
    if len(data) < ENCRYPTED_END:
        raise ValueError(f"Save payload too small ({len(data)} bytes), requires at least {ENCRYPTED_END} bytes")
    return apply_keystream(data, key, start=ENCRYPTED_START, decrypt=True)


def encrypt_save_payload(data: bytearray, key: bytes) -> bytearray:
    """Encrypt save payload in-place using the additive stream cipher.

    Formula: ciphertext[i] = (plaintext[i] + keystream[i % 256]) & 0xFF
    """
    if len(key) != KEY_SIZE:
        raise ValueError(f"Key must be exactly {KEY_SIZE} bytes")
    if len(data) < ENCRYPTED_END:
        raise ValueError(f"Save payload too small ({len(data)} bytes), requires at least {ENCRYPTED_END} bytes")
    return apply_keystream(data, key, start=ENCRYPTED_START, decrypt=False)


def verify_save_checksum(save_bytes: bytes) -> tuple[bool, int, int]:
    """Verify if a raw save file has a valid checksum.

    Returns (is_valid, stored_checksum, calculated_checksum).
    """
    if len(save_bytes) < ENCRYPTED_END:
        return (False, 0, 0)
    stored_checksum = struct.unpack("<I", save_bytes[CHECKSUM_OFFSET : CHECKSUM_OFFSET + 4])[0]
    key = extract_keystream(save_bytes)

    # Decrypt a working copy
    work = bytearray(save_bytes)
    decrypt_save_payload(work, key)

    calc_checksum = calculate_checksum(work, start=RECORD_HEADER_OFFSET, count=CHECKSUM_RANGE_COUNT)
    return (stored_checksum == calc_checksum, stored_checksum, calc_checksum)


def patch_and_sign_save(plaintext_data: bytearray, key: bytes) -> bytearray:
    """Recalculate checksum, write to header, and re-encrypt payload.

    Returns ready-to-write raw save bytearray.
    """
    new_checksum = calculate_checksum(plaintext_data, start=RECORD_HEADER_OFFSET, count=CHECKSUM_RANGE_COUNT)
    plaintext_data[CHECKSUM_OFFSET : CHECKSUM_OFFSET + 4] = struct.pack("<I", new_checksum)

    raw_data = bytearray(plaintext_data)
    encrypt_save_payload(raw_data, key)
    return raw_data
