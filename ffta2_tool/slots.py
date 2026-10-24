"""FFTA2 Multi-Slot Save Management Module.

Handles reverse-engineered slot metadata, dual-bank mirroring,
LCG stream cipher phase alignment, and checksum recalculation for
Slot 1 (index 0) and Slot 2 (index 1) in FFTA2 EEPROM saves.

Save layout (ARM9-verified):

- Two 0xDC-byte metadata copies at 0x0000 and 0x00DC. The game reads the one with the
  higher save counter at +0x04 (0x0210D548) and writes the other one, counter + 1, on
  every save.
- Each copy holds 4 entries of 0x2C bytes at +0x2C. Entry position N describes the
  physical record at 0x01B8 + N * 0x3408 (0x0210D960). Records are not tied to slots:
  each in-game save writes the slot to the first free position (0x0210D6BC) and retires
  the entry it was loaded from, so a slot can live in any of the 4 records.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from ffta2_tool.charset import decode_ffta2_string
from ffta2_tool.crypto import apply_keystream, calculate_checksum, generate_keystream
from ffta2_tool.layout import (
    DIFFICULTY_RAW_HARD,
    PAYLOAD_OFF_DIFFICULTY,
    PAYLOAD_OFF_LEADER_NAME,
    PAYLOAD_OFF_UNIT_TABLE,
    PAYLOAD_SIZE,
    RECORD_HEADER_SIZE,
    RECORD_STAGING_OFFSET,
    api_to_raw_difficulty,
    raw_to_api_difficulty,
)

# Constants
SLOT_PAYLOAD_SIZE = PAYLOAD_SIZE  # 0x3400
SLOT_RECORD_SIZE = RECORD_HEADER_SIZE + SLOT_PAYLOAD_SIZE  # 0x3408
RECORD_BASE = RECORD_STAGING_OFFSET  # 0x01B8
ENTRY_COUNT = 4
# Physical record base for each metadata entry position 0..3
RECORD_OFFSETS = [RECORD_BASE + pos * SLOT_RECORD_SIZE for pos in range(ENTRY_COUNT)]

METADATA_MAGIC = 0x12345678
METADATA_COPY_SIZE = 0xDC  # 220 bytes
METADATA_OFFSETS = [0x0000, 0x00DC]  # Copy 1 and Copy 2
ENTRY_SIZE = 44
PREVIEW_OFFSET_BASE = 0x2C

# Entry state bytes (ARM9 0x0210D66C lookup, 0x0210D6BC allocator, 0x0210D86C format)
ENTRY_OFF_ACTIVE = 0x04  # nonzero = entry has held a record
ENTRY_OFF_RETIRED = 0x05  # 0 = live; nonzero = free (retired previous save, or never used)
ENTRY_OFF_SLOT_ID = 0x06  # owner: 0 = SLOT 1, 1 = SLOT 2, 2 = quicksave, 0xFF = none
ENTRY_OFF_BADGE = 0x24  # load-screen difficulty badge, bit 0 (0x0210AECC): 1 = Hard
QUICKSAVE_SLOT_ID = 2

BANK_SIZE = 0x40000  # 256 KB


def compute_lcg_keystream(seed: int, length: int = PAYLOAD_SIZE) -> bytes:
    """Generate keystream bytes using the reverse-engineered 8-bit LCG.

    Thin wrapper over ffta2_tool.crypto.generate_keystream (ARM9 0x0210CF84):
        state = seed & 0xFF
        for each byte:
            state = (state * 5 + 1) & 0xFF
            yield state
    """
    return generate_keystream(seed, length)


def calculate_metadata_checksum(data: bytes | bytearray, start: int = 0) -> int:
    """Calculate the 32-bit checksum for a 220-byte metadata copy.

    Thin wrapper over ffta2_tool.crypto.calculate_checksum: the metadata checksum uses
    the same signed-byte weighting as the save record, over 0xDC bytes with the first
    four (the checksum field itself) treated as zero.
    """
    return calculate_checksum(data, start=start, count=METADATA_COPY_SIZE, zero_first=4)


def active_metadata_base(raw: bytes | bytearray) -> int:
    """Return the base of the metadata copy the game treats as current.

    ARM9 0x0210D548 compares the uint32 save counters at +0x04 of each copy:
    copy 1 (0x0000) is used only when its counter is strictly higher, otherwise
    copy 2 (0x00DC). A copy whose checksum fails is skipped when the other one
    verifies.
    """
    valid = [
        calculate_metadata_checksum(raw[base : base + METADATA_COPY_SIZE]) == struct.unpack_from("<I", raw, base)[0]
        for base in METADATA_OFFSETS
    ]
    if valid[0] != valid[1]:
        return METADATA_OFFSETS[0] if valid[0] else METADATA_OFFSETS[1]
    seq1 = struct.unpack_from("<I", raw, METADATA_OFFSETS[0] + 4)[0]
    seq2 = struct.unpack_from("<I", raw, METADATA_OFFSETS[1] + 4)[0]
    return METADATA_OFFSETS[0] if seq1 > seq2 else METADATA_OFFSETS[1]


def entry_offset(copy_base: int, pos: int) -> int:
    """File offset of the metadata entry at position pos (0..3) of a copy."""
    return copy_base + PREVIEW_OFFSET_BASE + pos * ENTRY_SIZE


def find_live_entry(raw: bytes | bytearray, copy_base: int, slot_id: int) -> int | None:
    """Return the entry position the game loads for slot_id, or None if the slot is empty.

    ARM9 0x0210D66C: first position 0..3 whose entry has +4 != 0, +5 == 0 and +6 == slot_id.
    """
    for pos in range(ENTRY_COUNT):
        off = entry_offset(copy_base, pos)
        if (
            raw[off + ENTRY_OFF_ACTIVE] != 0
            and raw[off + ENTRY_OFF_RETIRED] == 0
            and raw[off + ENTRY_OFF_SLOT_ID] == slot_id
        ):
            return pos
    return None


def find_free_entry(raw: bytes | bytearray, copy_base: int) -> int | None:
    """Return the position the game would write a new save to, or None if all are live.

    ARM9 0x0210D6BC: first position 0..3 whose entry has +5 != 0.
    """
    for pos in range(ENTRY_COUNT):
        if raw[entry_offset(copy_base, pos) + ENTRY_OFF_RETIRED] != 0:
            return pos
    return None


def _count_units(payload: bytes | bytearray) -> int:
    unit_count = 0
    for u in range(24):
        u_base = PAYLOAD_OFF_UNIT_TABLE + u * 0x11C
        if u_base + 0x0F < len(payload) and (payload[u_base + 0x0D] != 0 or payload[u_base + 0x0E] != 0):
            unit_count += 1
    return unit_count


def _check_slot(slot_idx: int) -> None:
    if slot_idx not in (0, 1):
        raise ValueError("slot_idx must be 0 (Slot 1) or 1 (Slot 2)")


class SlotManager:
    """Manages multi-slot operations across FFTA2 saves (64 KB melonDS or 512 KB cart dumps)."""

    def __init__(self, raw_save: bytearray | bytes) -> None:
        self.raw = bytearray(raw_save)
        self.size = len(self.raw)  # written back by save_to_file
        if len(self.raw) < 0x80000:
            # Pad to 512 KB so bank 2 offsets are always addressable
            self.raw.extend(b"\x00" * (0x80000 - len(self.raw)))

    # -- slot to record resolution ---------------------------------------------------

    def active_copy_base(self) -> int:
        """Base offset of the metadata copy the game reads (see active_metadata_base)."""
        return active_metadata_base(self.raw)

    def slot_position(self, slot_idx: int) -> int | None:
        """Entry position (0..3) the game loads slot_idx from, or None when it shows "No data"."""
        _check_slot(slot_idx)
        return find_live_entry(self.raw, self.active_copy_base(), slot_idx)

    def has_data(self, slot_idx: int) -> bool:
        return self.slot_position(slot_idx) is not None

    def record_offset(self, slot_idx: int) -> int:
        """Return the physical record base backing a load-screen slot, resolved like the game."""
        pos = self.slot_position(slot_idx)
        if pos is None:
            raise ValueError(f"Slot {slot_idx + 1} has no save data")
        return RECORD_OFFSETS[pos]

    def entry_offset(self, slot_idx: int) -> int:
        """File offset of the live metadata entry for slot_idx in the active copy."""
        pos = self.slot_position(slot_idx)
        if pos is None:
            raise ValueError(f"Slot {slot_idx + 1} has no save data")
        return entry_offset(self.active_copy_base(), pos)

    # -- record and metadata primitives -------------------------------------------

    def _read_record(self, base: int) -> tuple[int, int, bytearray]:
        stored_chk, _header_magic, seed = struct.unpack_from("<IHH", self.raw, base)
        ks = compute_lcg_keystream(seed, SLOT_PAYLOAD_SIZE)
        payload = bytearray(self.raw[base + 8 : base + 8 + SLOT_PAYLOAD_SIZE])
        apply_keystream(payload, ks, decrypt=True)
        return (stored_chk, seed, payload)

    @staticmethod
    def _record_checksum(payload: bytes | bytearray, seed: int) -> int:
        # Checksum covers the 8-byte header (checksum field zeroed) + decrypted payload
        work = bytearray(SLOT_RECORD_SIZE)
        work[4:6] = struct.pack("<H", 0x0002)
        work[6:8] = struct.pack("<H", seed)
        work[8:] = payload
        return calculate_checksum(work, count=len(work), zero_first=4)

    def _write_record(self, base: int, payload: bytes | bytearray, seed: int) -> None:
        new_chk = self._record_checksum(payload, seed)
        ks = compute_lcg_keystream(seed, SLOT_PAYLOAD_SIZE)
        enc_payload = bytearray(payload)
        apply_keystream(enc_payload, ks, decrypt=False)
        struct.pack_into("<IHH", self.raw, base, new_chk, 0x0002, seed)
        self.raw[base + 8 : base + 8 + SLOT_PAYLOAD_SIZE] = enc_payload

    def _sign_copy(self, copy_base: int) -> None:
        meta_chk = calculate_metadata_checksum(self.raw[copy_base : copy_base + METADATA_COPY_SIZE])
        struct.pack_into("<I", self.raw, copy_base, meta_chk)

    def _apply_preview(self, off: int, payload: bytes | bytearray) -> None:
        """Write the payload-derived preview fields (member count, leader name, badge) of an entry.

        Quests (+0x0C), subflag (+0x25), clan title rank (+0x26), leader level (+0x27), and
        play time (+0x28..+0x2B) keep their game-written values.
        """
        name_off = PAYLOAD_OFF_LEADER_NAME
        u0_name_raw = bytes(payload[name_off : name_off + 20])
        if 0 in u0_name_raw:
            u0_name_raw = u0_name_raw[: u0_name_raw.index(0)]
        struct.pack_into("<I", self.raw, off + 8, _count_units(payload))
        self.raw[off + 16 : off + 36] = (u0_name_raw[:19] + b"\x00" * 20)[:20]
        self.raw[off + ENTRY_OFF_BADGE] = (
            DIFFICULTY_RAW_HARD if payload[PAYLOAD_OFF_DIFFICULTY] == DIFFICULTY_RAW_HARD else 0
        )

    # -- public API -------------------------------------------------------------

    def get_slot_payload(self, slot_idx: int) -> tuple[int, int, bytearray]:
        """Decrypt and return (checksum, seed, plaintext_payload) for a slot.

        slot_idx: 0 for Slot 1, 1 for Slot 2. Raises ValueError when the slot is empty.
        """
        return self._read_record(self.record_offset(slot_idx))

    def verify_slot(self, slot_idx: int) -> tuple[bool, int, int]:
        """Verify the integrity of a slot. Returns (is_valid, stored, calculated); empty slots are invalid."""
        if not self.has_data(slot_idx):
            return (False, 0, 0)
        stored_chk, seed, payload = self.get_slot_payload(slot_idx)
        calc_chk = self._record_checksum(payload, seed)
        return (stored_chk == calc_chk, stored_chk, calc_chk)

    def get_slot_preview(self, slot_idx: int) -> dict[str, Any]:
        """Read the load-screen preview entry for a slot from the active metadata copy."""
        pos = self.slot_position(slot_idx)
        if pos is None:
            return {
                "slot_index": slot_idx,
                "slot_label": f"Slot {slot_idx + 1}",
                "has_data": False,
                "active": False,
                "magic_valid": False,
                "position": None,
                "record_offset": None,
                "leader_name": "",
                "leader_level": 0,
                "member_count": 0,
                "clan_title_rank": 0,
                "difficulty": None,
                "difficulty_label": "No data",
                "badge_difficulty": None,
                "badge_mismatch": False,
                "cleared_quests": 0,
                "play_time_hours": 0,
                "play_time_minutes": 0,
                "play_time_seconds": 0,
                "play_time_formatted": "-",
            }

        off = entry_offset(self.active_copy_base(), pos)
        entry = self.raw[off : off + ENTRY_SIZE]
        magic = struct.unpack_from("<I", entry, 0)[0]
        member_count = struct.unpack_from("<I", entry, 8)[0]
        cleared_quests = struct.unpack_from("<I", entry, 12)[0]
        name = decode_ffta2_string(entry[16:36])

        # Reverse-engineered preview metadata fields (proved via melonDS test rig,
        # cross-checked against load-screen display: "Lv", "Clan Members", "Quests Completed"):
        # +0x0C: quests completed (uint32) -- NOT leader job; do not overwrite
        # byte 36: difficulty badge (bit 0: 1 = Hard)
        # byte 37: subflag (always 0 in every observed save)
        # byte 38: clan title rank (e.g. 4)
        # byte 39: leader level (e.g. 4)
        # bytes 40..41: play time hours (uint16)
        # byte 42: play time minutes (uint8)
        # byte 43: play time seconds (uint8)
        diff_byte = entry[ENTRY_OFF_BADGE]
        hours = struct.unpack_from("<H", entry, 40)[0]
        mins = entry[42]
        secs = entry[43]

        # The game plays the difficulty byte stored in the decrypted payload
        # (payload 0x2798 / buffer 0x2958, 0 = Normal, 1 = Hard); the entry badge is
        # display only and can disagree.
        _, _, payload = self._read_record(RECORD_OFFSETS[pos])
        difficulty = raw_to_api_difficulty(payload[PAYLOAD_OFF_DIFFICULTY])
        badge_difficulty = raw_to_api_difficulty(diff_byte & 1)
        return {
            "slot_index": slot_idx,
            "slot_label": f"Slot {slot_idx + 1}",
            "has_data": True,
            "active": True,
            "magic_valid": magic == METADATA_MAGIC,
            "position": pos,
            "record_offset": RECORD_OFFSETS[pos],
            "leader_name": name,
            "leader_level": entry[39],
            "member_count": member_count,
            "clan_title_rank": entry[38],
            "difficulty": difficulty,
            "difficulty_label": "Hard" if difficulty == 1 else "Normal",
            "badge_difficulty": badge_difficulty,
            "badge_mismatch": badge_difficulty != difficulty,
            "cleared_quests": cleared_quests,
            "play_time_hours": hours,
            "play_time_minutes": mins,
            "play_time_seconds": secs,
            "play_time_formatted": f"{hours}:{mins:02d}:{secs:02d}",
        }

    def refresh_preview(self, slot_idx: int = 0) -> None:
        """Refresh a load-screen preview entry from an already-written slot record.

        Updates only the payload-derived fields (member count, leader name, difficulty
        badge) of the slot's live entry in the active metadata copy, then re-signs that
        copy. The entry state bytes, quests, rank, level, and play time are preserved, and
        the other copy (the game's previous save, which it overwrites next) is untouched.
        No-op when the slot is empty or its checksum is invalid.
        """
        if not self.verify_slot(slot_idx)[0]:
            return
        _, _, payload = self.get_slot_payload(slot_idx)
        # Resolve the copy before editing it: an edit breaks its checksum until re-signed
        copy_base = self.active_copy_base()
        self._apply_preview(self.entry_offset(slot_idx), payload)
        self._sign_copy(copy_base)

    def put_slot_payload(
        self,
        slot_idx: int,
        plaintext_payload: bytes | bytearray,
        seed: int = 0x0031,
        difficulty: int | None = None,
        preview_source: bytes | bytearray | None = None,
    ) -> None:
        """Encrypt, sign, and write a plaintext payload into the specified slot.

        Overwrites the slot's live record in place; an empty slot gets the first free
        position, exactly like the game's allocator. preview_source (a 44-byte entry, for
        example the source slot's) supplies quests, rank, level, and play time for the
        preview. Also deactivates the quicksave and mirrors Bank 1 to Bank 2.
        """
        _check_slot(slot_idx)
        if len(plaintext_payload) != SLOT_PAYLOAD_SIZE:
            raise ValueError(f"Payload must be {SLOT_PAYLOAD_SIZE} bytes")

        payload = bytearray(plaintext_payload)
        if difficulty is not None:
            payload[PAYLOAD_OFF_DIFFICULTY] = api_to_raw_difficulty(difficulty)

        copy_base = self.active_copy_base()
        pos = find_live_entry(self.raw, copy_base, slot_idx)
        if pos is None:
            pos = find_free_entry(self.raw, copy_base)
            if pos is None:
                raise ValueError("No free save position in the metadata table")

        self._write_record(RECORD_OFFSETS[pos], payload, seed)

        off = entry_offset(copy_base, pos)
        if preview_source is not None:
            self.raw[off + 8 : off + ENTRY_SIZE] = bytes(preview_source)[8:ENTRY_SIZE]
        struct.pack_into("<I", self.raw, off, METADATA_MAGIC)
        self.raw[off + ENTRY_OFF_ACTIVE] = 1
        self.raw[off + ENTRY_OFF_RETIRED] = 0
        self.raw[off + ENTRY_OFF_SLOT_ID] = slot_idx
        self._apply_preview(off, payload)
        self._sign_copy(copy_base)

        self.deactivate_quicksave()

    def get_entry_bytes(self, slot_idx: int) -> bytes:
        """Return the raw 44-byte live entry of a slot (for use as preview_source)."""
        off = self.entry_offset(slot_idx)
        return bytes(self.raw[off : off + ENTRY_SIZE])

    def deactivate_quicksave(self) -> None:
        """Retire the live quicksave (slot id 2) in the active copy and mirror Bank 1 to Bank 2.

        The quicksave can sit at any entry position, so it is located by slot id. It is
        retired the way the game frees an entry (+5 = 1); the record bytes are left alone.
        """
        copy_base = self.active_copy_base()
        pos = find_live_entry(self.raw, copy_base, QUICKSAVE_SLOT_ID)
        changed = pos is not None
        while pos is not None:
            self.raw[entry_offset(copy_base, pos) + ENTRY_OFF_RETIRED] = 1
            pos = find_live_entry(self.raw, copy_base, QUICKSAVE_SLOT_ID)
        if changed:
            self._sign_copy(copy_base)

        # Mirror Bank 1 to Bank 2
        self.raw[BANK_SIZE : BANK_SIZE * 2] = self.raw[:BANK_SIZE]

    def set_slot_difficulty(self, slot_idx: int, difficulty: int) -> None:
        """Set difficulty for a slot (1 = Hard, 2/0 = Normal), updating payload and preview."""
        _check_slot(slot_idx)
        diff_byte = api_to_raw_difficulty(difficulty)
        base = self.record_offset(slot_idx)
        _, seed, payload = self._read_record(base)
        payload[PAYLOAD_OFF_DIFFICULTY] = diff_byte
        self._write_record(base, payload, seed)

        # Badge on the slot's live entry in the copy the game reads (resolve the copy
        # before editing it: an edit breaks its checksum until re-signed)
        copy_base = self.active_copy_base()
        self.raw[self.entry_offset(slot_idx) + ENTRY_OFF_BADGE] = diff_byte
        self._sign_copy(copy_base)

        # Mirror Bank 1 to Bank 2 and deactivate quicksave
        self.deactivate_quicksave()

    def save_to_file(self, target_path: Path | str, wipe_quicksave: bool = True) -> None:
        """Write the updated image to disk at its original size, wiping quicksave by default."""
        if wipe_quicksave:
            self.deactivate_quicksave()
        path = Path(target_path)
        path.write_bytes(bytes(self.raw[: self.size]))
