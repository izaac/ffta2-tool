"""FFTA2 (NDS) Save Cryptography and Checksum Module.

Reverse-engineered directly from ARM9 binary:
- Decryption/Encryption: Additive stream cipher (ARM9 0x0210D740 - 0x0210D75C)
- Checksum: Signed byte summation with reverse-index weighting (ARM9 0x0210D560 - 0x0210D590)
"""

from __future__ import annotations

import struct

# Standard offsets for FFTA2 NDS saves (512 KB EEPROM/Flash)
RECORD_HEADER_OFFSET = 0x01B8
CHECKSUM_OFFSET = 0x01B8
CHECKSUM_SIZE = 4
ENCRYPTED_START = 0x01C0
ENCRYPTED_SIZE = 0x3400
ENCRYPTED_END = ENCRYPTED_START + ENCRYPTED_SIZE  # 0x35C0
KEY_PAD_OFFSET = 0x1000
KEY_SIZE = 256
CHECKSUM_RANGE_COUNT = 0x3408  # Record header (0x01B8) through 0x35BF


def extract_keystream(save_bytes: bytes) -> bytes:
    """Extract the 256-byte additive keystream from the save padding."""
    if len(save_bytes) < KEY_PAD_OFFSET + KEY_SIZE:
        raise ValueError(f"Save file too small ({len(save_bytes)} bytes) to extract keystream")
    return save_bytes[KEY_PAD_OFFSET : KEY_PAD_OFFSET + KEY_SIZE]


def decrypt_save_payload(data: bytearray, key: bytes) -> bytearray:
    """Decrypt save payload in-place using the additive stream cipher.

    Formula: plaintext[i] = (ciphertext[i] - keystream[i % 256]) & 0xFF
    """
    if len(key) != KEY_SIZE:
        raise ValueError(f"Key must be exactly {KEY_SIZE} bytes")
    if len(data) < ENCRYPTED_END:
        raise ValueError(f"Save payload too small ({len(data)} bytes), requires at least {ENCRYPTED_END} bytes")
    for i in range(ENCRYPTED_START, ENCRYPTED_END):
        data[i] = (data[i] - key[i % KEY_SIZE]) & 0xFF
    return data


def encrypt_save_payload(data: bytearray, key: bytes) -> bytearray:
    """Encrypt save payload in-place using the additive stream cipher.

    Formula: ciphertext[i] = (plaintext[i] + keystream[i % 256]) & 0xFF
    """
    if len(key) != KEY_SIZE:
        raise ValueError(f"Key must be exactly {KEY_SIZE} bytes")
    if len(data) < ENCRYPTED_END:
        raise ValueError(f"Save payload too small ({len(data)} bytes), requires at least {ENCRYPTED_END} bytes")
    for i in range(ENCRYPTED_START, ENCRYPTED_END):
        data[i] = (data[i] + key[i % KEY_SIZE]) & 0xFF
    return data


def calculate_checksum(
    plaintext_data: bytes | bytearray,
    header_offset: int = RECORD_HEADER_OFFSET,
    count: int = CHECKSUM_RANGE_COUNT,
) -> int:
    """Calculate the exact 32-bit FFTA2 save checksum over plaintext.

    ARM9 assembly routine (0x0210D560 - 0x0210D590):
        sum = 0
        for i in 0 .. (count - 1):
            signed_byte = (int8)buffer[i]
            term = signed_byte + (count - i)
            sum = (sum + term) & 0xFFFFFFFF
        return sum
    """
    min_len = header_offset + count
    if len(plaintext_data) < min_len:
        raise ValueError(f"Plaintext buffer too small ({len(plaintext_data)} bytes), requires at least {min_len} bytes")
    total = 0

    # The checksum field (first 4 bytes of header) MUST be zeroed for checksum computation
    for i in range(count):
        offset = header_offset + i
        b = 0 if i < 4 else plaintext_data[offset]

        # Interpret as signed 8-bit integer (LDRSB in ARM)
        signed_b = b if b < 128 else b - 256
        term = (signed_b + (count - i)) & 0xFFFFFFFF
        total = (total + term) & 0xFFFFFFFF

    return total


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

    calc_checksum = calculate_checksum(work)
    return (stored_checksum == calc_checksum, stored_checksum, calc_checksum)


def patch_and_sign_save(plaintext_data: bytearray, key: bytes) -> bytearray:
    """Recalculate checksum, write to header, and re-encrypt payload.

    Returns ready-to-write raw save bytearray.
    """
    new_checksum = calculate_checksum(plaintext_data)
    plaintext_data[CHECKSUM_OFFSET : CHECKSUM_OFFSET + 4] = struct.pack("<I", new_checksum)

    raw_data = bytearray(plaintext_data)
    encrypt_save_payload(raw_data, key)
    return raw_data
