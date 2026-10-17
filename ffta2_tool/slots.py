"""FFTA2 Multi-Slot Save Management Module.

Handles reverse-engineered slot metadata, dual-bank mirroring,
LCG stream cipher phase alignment, and checksum recalculation for
Slot 1 (index 0) and Slot 2 (index 1) in 512 KB EEPROM saves.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from ffta2_tool.charset import decode_ffta2_string
from ffta2_tool.crypto import calculate_checksum

# Constants
SLOT_PAYLOAD_SIZE = 0x3400
RECORD_HEADER_SIZE = 8
SLOT_RECORD_SIZE = RECORD_HEADER_SIZE + SLOT_PAYLOAD_SIZE  # 0x3408
SLOT_OFFSETS = [0x01B8, 0x35C0]  # Base offsets for Slot 0 and Slot 1

METADATA_MAGIC = 0x12345678
METADATA_COPY_SIZE = 0xDC  # 220 bytes
METADATA_OFFSETS = [0x0000, 0x00DC]  # Copy 1 and Copy 2
ENTRY_SIZE = 44
PREVIEW_OFFSET_BASE = 0x2C

BANK_SIZE = 0x40000  # 256 KB


def compute_lcg_keystream(seed: int, length: int = 0x3400) -> bytes:
    """Generate keystream bytes using the reverse-engineered 8-bit LCG.

    ARM9 routine (0x0210CF84):
        state = seed & 0xFF
        for each byte:
            state = (state * 5 + 1) & 0xFF
            yield state
    """
    state = seed & 0xFF
    stream = bytearray(length)
    for i in range(length):
        state = (state * 5 + 1) & 0xFF
        stream[i] = state
    return bytes(stream)


def calculate_metadata_checksum(data: bytes | bytearray) -> int:
    """Calculate the 32-bit checksum for a 220-byte metadata copy."""
    count = METADATA_COPY_SIZE
    total = 0
    for i in range(count):
        b = 0 if i < 4 else data[i]
        signed_b = b if b < 128 else b - 256
        term = (signed_b + (count - i)) & 0xFFFFFFFF
        total = (total + term) & 0xFFFFFFFF
    return total


class SlotManager:
    """Manages multi-slot operations across 512 KB FFTA2 saves."""

    def __init__(self, raw_save: bytearray | bytes) -> None:
        self.raw = bytearray(raw_save)
        if len(self.raw) < 0x80000:
            # Pad to 512 KB if needed
            self.raw.extend(b"\x00" * (0x80000 - len(self.raw)))

    def get_slot_payload(self, slot_idx: int) -> tuple[int, int, bytearray]:
        """Decrypt and return (checksum, seed, plaintext_payload) for a slot.

        slot_idx: 0 for Slot 1, 1 for Slot 2.
        """
        if slot_idx not in (0, 1):
            raise ValueError("slot_idx must be 0 (Slot 1) or 1 (Slot 2)")

        base = SLOT_OFFSETS[slot_idx]
        header = self.raw[base : base + 8]
        stored_chk, header_magic, seed = struct.unpack_from("<IHH", header, 0)

        # Generate keystream using the header seed
        ks = compute_lcg_keystream(seed, SLOT_PAYLOAD_SIZE)

        # Decrypt payload
        payload = bytearray(SLOT_PAYLOAD_SIZE)
        for i in range(SLOT_PAYLOAD_SIZE):
            payload[i] = (self.raw[base + 8 + i] - ks[i]) & 0xFF

        return (stored_chk, seed, payload)

    def verify_slot(self, slot_idx: int) -> tuple[bool, int, int]:
        """Verify the integrity of a slot. Returns (is_valid, stored, calculated)."""
        stored_chk, seed, payload = self.get_slot_payload(slot_idx)

        # Checksum is computed over 8-byte header (with checksum cleared) + decrypted payload
        work = bytearray(SLOT_RECORD_SIZE)
        work[0:4] = b"\x00\x00\x00\x00"
        work[4:6] = struct.pack("<H", 0x0002)
        work[6:8] = struct.pack("<H", seed)
        work[8:] = payload

        calc_chk = calculate_checksum(work, header_offset=0, count=SLOT_RECORD_SIZE)
        is_valid = stored_chk == calc_chk
        return (is_valid, stored_chk, calc_chk)

    def _find_entry_offset(self, slot_idx: int, copy_base: int = 0) -> int:
        """Find the metadata entry offset for the specified slot_idx (0 or 1).

        First checks if an active entry exists with slot_id == slot_idx.
        Falls back to canonical index: PREVIEW_OFFSET_BASE + slot_idx * ENTRY_SIZE.
        """
        for i in range(4):
            off = copy_base + PREVIEW_OFFSET_BASE + i * ENTRY_SIZE
            magic, active, s_id = struct.unpack_from("<IBB", self.raw, off)
            if magic == METADATA_MAGIC and active == 1 and s_id == slot_idx:
                return off
        return copy_base + PREVIEW_OFFSET_BASE + slot_idx * ENTRY_SIZE

    def get_slot_preview(self, slot_idx: int) -> dict[str, Any]:
        """Read the metadata preview entry for a slot."""
        if slot_idx not in (0, 1):
            raise ValueError("slot_idx must be 0 (Slot 1) or 1 (Slot 2)")

        # Inspect active metadata copy
        active_copy_base = 0x0000
        seq1 = struct.unpack_from("<I", self.raw, 4)[0]
        seq2 = struct.unpack_from("<I", self.raw, 0xDC + 4)[0]
        chk1_match = calculate_metadata_checksum(self.raw[:0xDC]) == struct.unpack_from("<I", self.raw, 0)[0]
        chk2_match = calculate_metadata_checksum(self.raw[0xDC:0x1B8]) == struct.unpack_from("<I", self.raw, 0xDC)[0]
        if chk2_match and (not chk1_match or seq2 > seq1):
            active_copy_base = 0x00DC

        off = self._find_entry_offset(slot_idx, active_copy_base)
        entry = self.raw[off : off + ENTRY_SIZE]
        magic, active, slot_id, pad = struct.unpack_from("<IBBH", entry, 0)
        member_count = struct.unpack_from("<I", entry, 8)[0]
        cleared_quests = struct.unpack_from("<I", entry, 12)[0]
        name = decode_ffta2_string(entry[16:36])

        # Reverse-engineered preview metadata fields (proved via melonDS test rig,
        # cross-checked against load-screen display: "Lv", "Clan Members", "Quests Completed"):
        # +0x0C: quests completed (uint32) -- NOT leader job; do not overwrite
        # byte 36: difficulty (1 = Hard, 0 or 2 = Normal)
        # byte 37: subflag (always 0 in every observed save)
        # byte 38: clan title rank (e.g. 4)
        # byte 39: leader level (e.g. 4)
        # bytes 40..41: play time hours (uint16)
        # byte 42: play time minutes (uint8)
        # byte 43: play time seconds (uint8)
        diff_byte = entry[36]
        clan_title_rank = entry[38]
        leader_level = entry[39]
        hours = struct.unpack_from("<H", entry, 40)[0]
        mins = entry[42]
        secs = entry[43]

        # In decrypted payload, difficulty is stored at offset 0x3558 (0x3398 from payload start):
        # 1 = Hard, 2 = Normal.
        _, _, payload = self.get_slot_payload(slot_idx)
        payload_diff = payload[0x3558 - 0x01C0] if len(payload) > 0x3558 - 0x01C0 else 1

        difficulty = 1 if diff_byte == 1 else (2 if diff_byte in (0, 2) else payload_diff)
        difficulty_label = "Hard" if difficulty == 1 else "Normal"

        return {
            "slot_index": slot_idx,
            "slot_label": f"Slot {slot_idx + 1}",
            "active": active == 1,
            "magic_valid": magic == METADATA_MAGIC,
            "leader_name": name,
            "leader_level": leader_level,
            "member_count": member_count,
            "clan_title_rank": clan_title_rank,
            "difficulty": difficulty,
            "difficulty_label": difficulty_label,
            "cleared_quests": cleared_quests,
            "play_time_hours": hours,
            "play_time_minutes": mins,
            "play_time_seconds": secs,
            "play_time_formatted": f"{hours}:{mins:02d}:{secs:02d}",
        }

    def refresh_preview(self, slot_idx: int = 0) -> None:
        """Refresh a load-screen preview entry from an already-written slot record.

        Updates only the payload-derived fields (leader name, leader job, member
        count) and preserves the existing active flag, slot id, padding,
        location, clan title, cleared quest count, and play time. Both metadata
        copies are rewritten and re-signed. No-op when the slot checksum is
        invalid.
        """
        if slot_idx not in (0, 1):
            raise ValueError("slot_idx must be 0 (Slot 1) or 1 (Slot 2)")
        if not self.verify_slot(slot_idx)[0]:
            return

        _, _, payload = self.get_slot_payload(slot_idx)
        diff_val = payload[0x3558 - 0x01C0] if len(payload) > 0x3558 - 0x01C0 else 1
        u0_off = 0x0238 - 0x01C0  # Unit 0 relative to payload start
        name_off = 0x01EC - 0x01C0
        u0_name_raw = payload[name_off : name_off + 16]

        unit_count = 0
        for u in range(24):
            u_base = u0_off + u * 0x11C
            if payload[u_base + 0x0D] != 0 or payload[u_base + 0x0E] != 0:
                unit_count += 1

        for copy_base in METADATA_OFFSETS:
            entry_off = self._find_entry_offset(slot_idx, copy_base)
            magic, active, slot_id, pad = struct.unpack_from("<IBBH", self.raw, entry_off)
            if magic != METADATA_MAGIC:
                active = 1 if slot_idx == 0 else 0
                slot_id = slot_idx
                pad = 0xFF00

            struct.pack_into(
                "<IBBHI",
                self.raw,
                entry_off,
                METADATA_MAGIC,
                active,
                slot_id,
                pad,
                unit_count,
            )
            # Leader name (20 bytes, null padded)
            self.raw[entry_off + 16 : entry_off + 36] = (u0_name_raw + b"\x00" * 20)[:20]

            # Byte 36: difficulty (1 = Hard, 0 = Normal). All other preview bytes
            # (quests, subflag, rank, level, play time) keep their existing values.
            self.raw[entry_off + 36] = 1 if diff_val == 1 else 0

            meta_chk = calculate_metadata_checksum(self.raw[copy_base : copy_base + METADATA_COPY_SIZE])
            struct.pack_into("<I", self.raw, copy_base, meta_chk)

    def put_slot_payload(
        self,
        slot_idx: int,
        plaintext_payload: bytes | bytearray,
        seed: int = 0x0031,
        active: bool = True,
        difficulty: int | None = None,
    ) -> None:
        """Encrypt, sign, and write a plaintext payload into the specified slot.

        Also updates the metadata table and mirrors changes to Bank 2.
        """
        if slot_idx not in (0, 1):
            raise ValueError("slot_idx must be 0 (Slot 1) or 1 (Slot 2)")
        if len(plaintext_payload) != SLOT_PAYLOAD_SIZE:
            raise ValueError(f"Payload must be {SLOT_PAYLOAD_SIZE} bytes")

        if difficulty is not None and len(plaintext_payload) > 0x3558 - 0x01C0:
            plaintext_payload[0x3558 - 0x01C0] = difficulty & 0xFF

        base = SLOT_OFFSETS[slot_idx]

        # 1. Compute checksum over record (header with chk=0 + plaintext)
        work = bytearray(SLOT_RECORD_SIZE)
        work[0:4] = b"\x00\x00\x00\x00"
        work[4:6] = struct.pack("<H", 0x0002)
        work[6:8] = struct.pack("<H", seed)
        work[8:] = plaintext_payload

        new_chk = calculate_checksum(work, header_offset=0, count=SLOT_RECORD_SIZE)

        # 2. Encrypt payload
        ks = compute_lcg_keystream(seed, SLOT_PAYLOAD_SIZE)
        enc_payload = bytearray(SLOT_PAYLOAD_SIZE)
        for i in range(SLOT_PAYLOAD_SIZE):
            enc_payload[i] = (plaintext_payload[i] + ks[i]) & 0xFF

        # 3. Write record into Bank 1
        struct.pack_into("<IHH", self.raw, base, new_chk, 0x0002, seed)
        self.raw[base + 8 : base + 8 + SLOT_PAYLOAD_SIZE] = enc_payload

        # 4. Extract preview info from plaintext payload
        name_off = 0x01EC - 0x01C0
        u0_name_raw = plaintext_payload[name_off : name_off + 16]

        # Count active units
        unit_count = 0
        for u in range(24):
            u_base = 0x0238 - 0x01C0 + u * 0x11C
            if u_base + 0x0F < len(plaintext_payload) and (
                plaintext_payload[u_base + 0x0D] != 0 or plaintext_payload[u_base + 0x0E] != 0
            ):
                unit_count += 1

        diff_val = (
            difficulty
            if difficulty is not None
            else (plaintext_payload[0x3558 - 0x01C0] if len(plaintext_payload) > 0x3558 - 0x01C0 else 1)
        )
        diff_byte = 1 if diff_val == 1 else 0

        # 5. Update preview entry in metadata copy 1 and copy 2
        for copy_base in METADATA_OFFSETS:
            entry_off = self._find_entry_offset(slot_idx, copy_base)
            existing_magic = struct.unpack_from("<I", self.raw, entry_off)[0]
            existing_pad = (
                struct.unpack_from("<H", self.raw, entry_off + 6)[0] if existing_magic == METADATA_MAGIC else 0xFF00
            )

            # Only the identity fields (+0x00..+0x0B), leader name, and the difficulty
            # badge (+0x24) are rewritten. Quests (+0x0C), subflag (+0x25), clan title
            # rank (+0x26), leader level (+0x27), and play time (+0x28..+0x2B) keep
            # their game-written values so the load-screen preview is not clobbered.
            struct.pack_into(
                "<IBBHI",
                self.raw,
                entry_off,
                METADATA_MAGIC,
                1 if active else 0,
                slot_idx,
                existing_pad,
                unit_count,
            )
            # Leader name (20 bytes, null padded)
            self.raw[entry_off + 16 : entry_off + 36] = b"\x00" * 20
            self.raw[entry_off + 16 : entry_off + 16 + min(len(u0_name_raw), 20)] = u0_name_raw[:20]

            # Byte 36: difficulty (1 = Hard, 0 = Normal)
            self.raw[entry_off + 36] = diff_byte

            # Recompute metadata copy checksum
            meta_chk = calculate_metadata_checksum(self.raw[copy_base : copy_base + METADATA_COPY_SIZE])
            struct.pack_into("<I", self.raw, copy_base, meta_chk)

        # 6. Always deactivate quicksave and mirror Bank 1 to Bank 2
        self.deactivate_quicksave()

    def deactivate_quicksave(self) -> None:
        """Deactivate and clear quicksave slot across both metadata copies and payload."""
        for copy_base in METADATA_OFFSETS:
            entry_off = copy_base + PREVIEW_OFFSET_BASE + 2 * ENTRY_SIZE
            # Set active = 0
            self.raw[entry_off + 4] = 0
            meta_chk = calculate_metadata_checksum(self.raw[copy_base : copy_base + METADATA_COPY_SIZE])
            struct.pack_into("<I", self.raw, copy_base, meta_chk)

        # Clear quicksave record header at 0x69C8
        self.raw[0x69C8 : 0x69C8 + 8] = b"\x00" * 8

        # Mirror Bank 1 to Bank 2
        self.raw[BANK_SIZE : BANK_SIZE * 2] = self.raw[:BANK_SIZE]

    def set_slot_difficulty(self, slot_idx: int, difficulty: int) -> None:
        """Set difficulty for a slot (1 = Hard, 2 = Normal), updating payload and preview."""
        if slot_idx not in (0, 1):
            raise ValueError("slot_idx must be 0 (Slot 1) or 1 (Slot 2)")
        if difficulty not in (1, 2):
            raise ValueError("difficulty must be 1 (Hard) or 2 (Normal)")

        base = SLOT_OFFSETS[slot_idx]
        _, seed, payload = self.get_slot_payload(slot_idx)
        if len(payload) > 0x3558 - 0x01C0:
            payload[0x3558 - 0x01C0] = difficulty & 0xFF

        work = bytearray(SLOT_RECORD_SIZE)
        work[0:4] = b"\x00\x00\x00\x00"
        work[4:6] = struct.pack("<H", 0x0002)
        work[6:8] = struct.pack("<H", seed)
        work[8:] = payload
        new_chk = calculate_checksum(work, header_offset=0, count=SLOT_RECORD_SIZE)

        ks = compute_lcg_keystream(seed, SLOT_PAYLOAD_SIZE)
        enc_payload = bytearray(SLOT_PAYLOAD_SIZE)
        for i in range(SLOT_PAYLOAD_SIZE):
            enc_payload[i] = (payload[i] + ks[i]) & 0xFF

        struct.pack_into("<IHH", self.raw, base, new_chk, 0x0002, seed)
        self.raw[base + 8 : base + 8 + SLOT_PAYLOAD_SIZE] = enc_payload

        # Update preview byte 36 (badge) on the slot's descriptor in both copies
        diff_byte = 1 if difficulty == 1 else 0
        for copy_base in METADATA_OFFSETS:
            off = self._find_entry_offset(slot_idx, copy_base)
            self.raw[off + 36] = diff_byte
            meta_chk = calculate_metadata_checksum(self.raw[copy_base : copy_base + METADATA_COPY_SIZE])
            struct.pack_into("<I", self.raw, copy_base, meta_chk)

        # Mirror Bank 1 to Bank 2 and deactivate quicksave
        self.deactivate_quicksave()

    def save_to_file(self, target_path: Path | str, wipe_quicksave: bool = True) -> None:
        """Write the updated 512 KB raw image to disk, always wiping quicksave by default."""
        if wipe_quicksave:
            self.deactivate_quicksave()
        path = Path(target_path)
        path.write_bytes(self.raw)
