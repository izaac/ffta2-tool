"""FFTA2 High-Level Save File Interface."""

from __future__ import annotations

import glob
import os
import shutil
import struct
from datetime import datetime
from pathlib import Path

from ffta2_tool.crypto import (
    CHECKSUM_OFFSET,
    ENCRYPTED_END,
    RECORD_HEADER_OFFSET,
    calculate_checksum,
    decrypt_save_payload,
    encrypt_save_payload,
    extract_keystream,
)

# Party units in the decrypted save file
UNIT_TABLE_BASE = 0x0238  # Unit 0 starts at 0x0238
UNIT_STRIDE = 0x11C  # 284 bytes per unit slot
MAX_UNITS = 24

# Exact offsets within a Unit entry (relative to unit base):
OFF_UNIT_CHAR_ID = 0x0D  # 1 byte (0x01 = Luso)
OFF_UNIT_JOB_ID = 0x0E  # 1 byte (0x01 = Soldier)
OFF_UNIT_RACE_ID = 0x0F  # 1 byte (0x01 = Hume)
OFF_UNIT_PRIMARY_A_SET = 0x16  # 1 byte (Action Ability Set 1)
OFF_UNIT_SECONDARY_A_SET = 0x17  # 1 byte (Action Ability Set 2)
OFF_UNIT_JOB_MSG_ID = 0x18  # 16-bit (Job Title Message ID: 1000 + Job ID)
OFF_UNIT_JOB_STR_ID = 0x1A  # 16-bit (Job String ID: 0x9470 + Job ID)
OFF_UNIT_LEVEL = 0x22  # 1 byte
OFF_UNIT_SPEED = 0x24  # 1 byte
OFF_UNIT_MAX_HP = 0x3C  # 16-bit
OFF_UNIT_CUR_HP = 0x3E  # 16-bit
OFF_UNIT_MAX_MP = 0x40  # 16-bit
OFF_UNIT_CUR_MP = 0x42  # 16-bit
OFF_UNIT_ATTACK = 0x44  # 16-bit
OFF_UNIT_DEFENSE = 0x46  # 16-bit
OFF_UNIT_MATK = 0x48  # 16-bit
OFF_UNIT_MDEF = 0x4A  # 16-bit
OFF_UNIT_EQUIP1 = 0x4C  # 16-bit (Main Hand Weapon)
OFF_UNIT_EQUIP2 = 0x4E  # 16-bit (Off Hand / Shield)
OFF_UNIT_EQUIP3 = 0x50  # 16-bit (Head / Helmet)
OFF_UNIT_EQUIP4 = 0x52  # 16-bit (Body / Armor)
OFF_UNIT_EQUIP5 = 0x54  # 16-bit (Accessory)
OFF_UNIT_R_ABILITY = 0x56  # 16-bit (Reaction Ability)
OFF_UNIT_P_ABILITY = 0x58  # 16-bit (Passive / Support Ability)
OFF_UNIT_ABILITIES_START = 0x5A  # Byte offset of ability AP array start (apIndex 0)
OFF_UNIT_ABILITIES_END = 0x11C  # Byte offset of ability AP array end / unit boundary (apIndex 193)

# Clan Inventory in decrypted save payload
INVENTORY_BASE = 0x1DFC
MAX_INVENTORY_SLOTS = 400

# Difficulty setting in the slot 0 payload (1 = Hard, 0 = Normal)
# ARM9 routine (0x0210D7A8 / 0x020D0C58 / 0x020D0C80):
# Relative offset in payload is 0x2798 (file offset 0x01C0 + 0x2798 = 0x2958)
OFF_DIFFICULTY = 0x2958

# Clan Economy & Privileges in decrypted save payload
# File offsets are 0x01C0 + payload offset
OFF_GIL = 0x281C  # uint32, max 99,999,999 (RAM 0x0212D6FC)
OFF_CLAN_POINTS = 0x2820  # uint16, max 9,999 (RAM 0x0212D700)
OFF_CLAN_TALENTS = 0x2824  # 4 bytes: Negotiation, Aptitude, Teamwork, Adaptability (RAM 0x0212D704)
OFF_CLAN_PRIVILEGES_START = 0x2937  # 9-byte Clan Privilege bitfield (RAM 0x0212D817)
# Privilege bits within those 9 bytes (flags 0x071C..0x075B from sysdata.pak file 0x23 /
# ARM9 0x0210695C..0x021069FC and JD_message_0.pak file 15):
# - 0x2937 bits 0..3 (0x0718..0x071B) precede entry 1 of the privilege table.
# - 0x293C bits 4..7 and 0x293D bits 0..1 (entries 41..46, 0x0744..0x0749) are nameless "-".
# - 0x293F bits 4..7 (0x075C..0x075F) lie past the final entry 64 (0x075B, Always Counter).
# The remaining 58 bits (entries 1..40 and 47..64) are the exact 58 named Clan Privileges.
CLAN_PRIVILEGE_MASK = bytes.fromhex("f0ffffffff0ffcff0f")

# Minimum plausible FFTA2 save size (NDS saves are 512 KiB; floor filters junk matches)
MIN_SAVE_SIZE = 0x10000

# Common save-file name fragment used across emulators and handheld SD cards
SAVE_NAME_GLOB = "*Final Fantasy Tactics A2*.sav"


def atomic_write(filepath: str | Path, data: bytes) -> None:
    """Safely writes data to a temporary sibling file then replaces target atomically with fsync."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp_{os.getpid()}")
    try:
        with open(tmp_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        if hasattr(os, "sync"):
            import contextlib

            with contextlib.suppress(AttributeError, OSError):
                os.sync()
    finally:
        if tmp_path.exists():
            import contextlib

            with contextlib.suppress(OSError):
                tmp_path.unlink()


def auto_detect_save(search_paths: list[str] | None = None) -> str | None:
    """Attempts to find the most relevant FFTA2 save file automatically.

    Checks mounted handheld/media SD cards, ~/Documents/FFTA2_Backups/, and the
    current directory (in that priority order) unless custom glob patterns are
    supplied via search_paths. Returns the most recently modified valid
    candidate, or None when nothing is found.
    """
    candidates: list[str] = []

    if search_paths is not None:
        for pattern in search_paths:
            candidates.extend(glob.glob(os.path.expanduser(pattern)))
    else:
        # Removable media mounts (retro handheld SD cards, flashcards, volumes)
        # Note: /mnt is intentionally excluded to avoid slow/hanging network or FUSE cloud mounts (e.g. rclone/CIFS).
        for mount_root in ("/run/media", "/media", "/Volumes"):
            for layout in (
                "*/*/*/Saves/nds/common",
                "*/*/*/Saves/NDS/common",
                "*/*/*/Saves/nds",
                "*/*/*/Saves/NDS",
                "*/Saves/nds/common",
                "*/Saves/NDS/common",
                "*/Saves/nds",
                "*/Saves/NDS",
                "*/*/*/*",
                "*/*/*",
                "*/*",
                "*",
            ):
                candidates.extend(glob.glob(f"{mount_root}/{layout}/{SAVE_NAME_GLOB}"))

        if os.name == "nt":
            import string

            for letter in string.ascii_uppercase[2:]:
                candidates.extend(glob.glob(f"{letter}:\\Saves\\nds\\common\\{SAVE_NAME_GLOB}"))
                candidates.extend(glob.glob(f"{letter}:\\Saves\\NDS\\common\\{SAVE_NAME_GLOB}"))
                candidates.extend(glob.glob(f"{letter}:\\Saves\\nds\\{SAVE_NAME_GLOB}"))
                candidates.extend(glob.glob(f"{letter}:\\Saves\\NDS\\{SAVE_NAME_GLOB}"))

        # Local backup directory, repo examples directory, and current directory fallbacks
        backup_dir = Path.home() / "Documents" / "FFTA2_Backups"
        try:
            if backup_dir.is_dir():
                candidates.extend(glob.glob(str(backup_dir / "*.sav")))
        except OSError:
            pass

        repo_examples = Path(__file__).resolve().parent.parent / "examples"
        try:
            if repo_examples.is_dir():
                candidates.extend(glob.glob(str(repo_examples / "*.sav")))
        except OSError:
            pass

        candidates.extend(glob.glob("*.sav"))

    valid = [p for p in candidates if os.path.isfile(p) and os.path.getsize(p) >= MIN_SAVE_SIZE]
    if not valid:
        return None

    def _save_priority(path_str: str) -> tuple[int, float]:
        name_lower = Path(path_str).name.lower()
        is_scratch = any(k in name_lower for k in ("test", "sample", "copy", "bak"))
        return (0 if not is_scratch else -1, os.path.getmtime(path_str))

    valid.sort(key=_save_priority, reverse=True)
    return valid[0]


def create_backup_snapshot(filepath: str | Path) -> Path:
    """Creates a timestamped sibling snapshot '<name>.bak_YYYYMMDD_HHMMSS' before overwriting."""
    path = Path(filepath)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak_{timestamp}")
    shutil.copy2(path, backup_path)
    return backup_path


class Unit:
    """Represents a unit entry inside the FFTA2 save."""

    def __init__(self, raw_unit: bytearray | memoryview, index: int):
        self._data = raw_unit
        self.index = index

    @property
    def character_id(self) -> int:
        return self._data[OFF_UNIT_CHAR_ID]

    @property
    def is_recruited(self) -> bool:
        """True when the slot holds a clan member (same test as the load-screen member count)."""
        return self._data[OFF_UNIT_CHAR_ID] != 0 or self._data[OFF_UNIT_JOB_ID] != 0

    @property
    def job_id(self) -> int:
        return self._data[OFF_UNIT_JOB_ID]

    @job_id.setter
    def job_id(self, val: int) -> None:
        job = val & 0xFF
        self._data[OFF_UNIT_JOB_ID] = job
        struct.pack_into("<H", self._data, OFF_UNIT_JOB_MSG_ID, 1000 + job)
        struct.pack_into("<H", self._data, OFF_UNIT_JOB_STR_ID, 0x9470 + job)

    @property
    def race_id(self) -> int:
        return self._data[OFF_UNIT_RACE_ID]

    @property
    def primary_ability_set(self) -> int:
        return self._data[OFF_UNIT_PRIMARY_A_SET]

    @primary_ability_set.setter
    def primary_ability_set(self, val: int) -> None:
        self._data[OFF_UNIT_PRIMARY_A_SET] = val & 0xFF

    @property
    def secondary_ability_set(self) -> int:
        return self._data[OFF_UNIT_SECONDARY_A_SET]

    @secondary_ability_set.setter
    def secondary_ability_set(self, val: int) -> None:
        self._data[OFF_UNIT_SECONDARY_A_SET] = val & 0xFF

    @property
    def max_hp(self) -> int:
        return struct.unpack_from("<H", self._data, OFF_UNIT_MAX_HP)[0]

    @max_hp.setter
    def max_hp(self, val: int) -> None:
        struct.pack_into("<H", self._data, OFF_UNIT_MAX_HP, val & 0xFFFF)

    @property
    def cur_hp(self) -> int:
        return struct.unpack_from("<H", self._data, OFF_UNIT_CUR_HP)[0]

    @cur_hp.setter
    def cur_hp(self, val: int) -> None:
        struct.pack_into("<H", self._data, OFF_UNIT_CUR_HP, val & 0xFFFF)

    @property
    def max_mp(self) -> int:
        return struct.unpack_from("<H", self._data, OFF_UNIT_MAX_MP)[0]

    @max_mp.setter
    def max_mp(self, val: int) -> None:
        struct.pack_into("<H", self._data, OFF_UNIT_MAX_MP, val & 0xFFFF)

    @property
    def cur_mp(self) -> int:
        return struct.unpack_from("<H", self._data, OFF_UNIT_CUR_MP)[0]

    @cur_mp.setter
    def cur_mp(self, val: int) -> None:
        struct.pack_into("<H", self._data, OFF_UNIT_CUR_MP, val & 0xFFFF)

    @property
    def level(self) -> int:
        return self._data[OFF_UNIT_LEVEL]

    @level.setter
    def level(self, val: int) -> None:
        self._data[OFF_UNIT_LEVEL] = val & 0xFF

    @property
    def speed(self) -> int:
        return self._data[OFF_UNIT_SPEED]

    @speed.setter
    def speed(self, val: int) -> None:
        self._data[OFF_UNIT_SPEED] = val & 0xFF

    @property
    def attack(self) -> int:
        return struct.unpack_from("<H", self._data, OFF_UNIT_ATTACK)[0]

    @attack.setter
    def attack(self, val: int) -> None:
        struct.pack_into("<H", self._data, OFF_UNIT_ATTACK, val & 0xFFFF)

    @property
    def defense(self) -> int:
        return struct.unpack_from("<H", self._data, OFF_UNIT_DEFENSE)[0]

    @defense.setter
    def defense(self, val: int) -> None:
        struct.pack_into("<H", self._data, OFF_UNIT_DEFENSE, val & 0xFFFF)

    @property
    def matk(self) -> int:
        return struct.unpack_from("<H", self._data, OFF_UNIT_MATK)[0]

    @matk.setter
    def matk(self, val: int) -> None:
        struct.pack_into("<H", self._data, OFF_UNIT_MATK, val & 0xFFFF)

    @property
    def mdef(self) -> int:
        return struct.unpack_from("<H", self._data, OFF_UNIT_MDEF)[0]

    @mdef.setter
    def mdef(self, val: int) -> None:
        struct.pack_into("<H", self._data, OFF_UNIT_MDEF, val & 0xFFFF)

    @property
    def weapon_id(self) -> int:
        return struct.unpack_from("<H", self._data, OFF_UNIT_EQUIP1)[0]

    @weapon_id.setter
    def weapon_id(self, item_id: int) -> None:
        struct.pack_into("<H", self._data, OFF_UNIT_EQUIP1, item_id & 0xFFFF)

    @property
    def shield_id(self) -> int:
        return struct.unpack_from("<H", self._data, OFF_UNIT_EQUIP2)[0]

    @shield_id.setter
    def shield_id(self, item_id: int) -> None:
        struct.pack_into("<H", self._data, OFF_UNIT_EQUIP2, item_id & 0xFFFF)

    @property
    def helm_id(self) -> int:
        return struct.unpack_from("<H", self._data, OFF_UNIT_EQUIP3)[0]

    @helm_id.setter
    def helm_id(self, item_id: int) -> None:
        struct.pack_into("<H", self._data, OFF_UNIT_EQUIP3, item_id & 0xFFFF)

    @property
    def armor_id(self) -> int:
        return struct.unpack_from("<H", self._data, OFF_UNIT_EQUIP4)[0]

    @armor_id.setter
    def armor_id(self, item_id: int) -> None:
        struct.pack_into("<H", self._data, OFF_UNIT_EQUIP4, item_id & 0xFFFF)

    @property
    def accessory_id(self) -> int:
        return struct.unpack_from("<H", self._data, OFF_UNIT_EQUIP5)[0]

    @accessory_id.setter
    def accessory_id(self, item_id: int) -> None:
        struct.pack_into("<H", self._data, OFF_UNIT_EQUIP5, item_id & 0xFFFF)

    @property
    def r_ability(self) -> int:
        return struct.unpack_from("<H", self._data, OFF_UNIT_R_ABILITY)[0]

    @r_ability.setter
    def r_ability(self, val: int) -> None:
        struct.pack_into("<H", self._data, OFF_UNIT_R_ABILITY, val & 0xFFFF)

    @property
    def p_ability(self) -> int:
        return struct.unpack_from("<H", self._data, OFF_UNIT_P_ABILITY)[0]

    @p_ability.setter
    def p_ability(self, val: int) -> None:
        struct.pack_into("<H", self._data, OFF_UNIT_P_ABILITY, val & 0xFFFF)

    def master_all_abilities(self) -> None:
        """Master all abilities by setting the full ability array (0x5A..0x11C) to 0xFF.

        Offsets 0x00..0x59 contain unit stats, job IDs, equipment, and active R/P slots.
        Offsets 0x5A..0x70 contain Reaction abilities (apIndex 0..22).
        Offsets 0x71..0x92 contain Passive abilities (apIndex 23..56).
        Offsets 0x93..0x11B contain Action abilities (apIndex 57..193).
        """
        self._data[OFF_UNIT_ABILITIES_START:OFF_UNIT_ABILITIES_END] = b"\xff" * (
            OFF_UNIT_ABILITIES_END - OFF_UNIT_ABILITIES_START
        )

    def unlock_ability_byte(self, offset: int, bit_mask: int = 0x80) -> None:
        """Safely unlock an ability at a specific relative offset within the unit struct (0x5A..0x11C)."""
        if OFF_UNIT_ABILITIES_START <= offset < OFF_UNIT_ABILITIES_END:
            self._data[offset] |= bit_mask & 0xFF


class FFTA2Save:
    """FFTA2 Save File manager."""

    def __init__(self, filepath: str | Path, slot: int = 0):
        from ffta2_tool.slots import SlotManager

        self.path = Path(filepath)
        self.raw_data = bytearray(self.path.read_bytes())
        if len(self.raw_data) < MIN_SAVE_SIZE:
            raise ValueError(
                f"Save file too small ({len(self.raw_data)} bytes); expected at least 0x{MIN_SAVE_SIZE:X} bytes"
            )
        # The game has no fixed slot-to-record mapping (see SlotManager.record_offset):
        # every in-game save moves the slot to another of the 4 physical records.
        # Stage the record backing `slot` in the canonical 0x01B8 window so all fixed
        # OFF_* offsets address that slot; save() writes it back to its real location.
        self.slot = slot
        self.record_base = SlotManager(self.raw_data).record_offset(slot)
        work = bytearray(self.raw_data)
        if self.record_base != RECORD_HEADER_OFFSET:
            record_size = ENCRYPTED_END - RECORD_HEADER_OFFSET
            work[RECORD_HEADER_OFFSET:ENCRYPTED_END] = self.raw_data[self.record_base : self.record_base + record_size]
        self.keystream = extract_keystream(work)
        self.plaintext = work
        decrypt_save_payload(self.plaintext, self.keystream)

    @property
    def slot_player_name(self) -> str:
        """Leader name shown on the load-screen card of the loaded slot."""
        from ffta2_tool.slots import SlotManager

        return SlotManager(self.raw_data).get_slot_preview(self.slot)["leader_name"]

    @property
    def slot_0_player_name(self) -> str:
        """Backward-compatible alias of slot_player_name."""
        return self.slot_player_name

    @property
    def difficulty(self) -> int:
        """Return the loaded slot's difficulty (1 = Hard, 2 = Normal)."""
        val = self.plaintext[OFF_DIFFICULTY]
        return 1 if val == 1 else 2

    @difficulty.setter
    def difficulty(self, value: int) -> None:
        if value not in (0, 1, 2):
            raise ValueError("difficulty must be 1 (Hard) or 2 (Normal)")
        self.plaintext[OFF_DIFFICULTY] = 1 if value == 1 else 0

    def get_unit(self, index: int) -> Unit | None:
        if not (0 <= index < MAX_UNITS):
            return None
        offset = UNIT_TABLE_BASE + index * UNIT_STRIDE
        unit_view = memoryview(self.plaintext)[offset : offset + UNIT_STRIDE]
        return Unit(unit_view, index)

    def get_inventory(self) -> dict[int, tuple[int, int]]:
        """Returns mapping of item_id -> (total_count, equipped_count) from clan bag."""
        items: dict[int, tuple[int, int]] = {}
        for i in range(MAX_INVENTORY_SLOTS):
            off = INVENTORY_BASE + i * 4
            item_id = struct.unpack_from("<H", self.plaintext, off)[0]
            equipped = self.plaintext[off + 2]
            total = self.plaintext[off + 3]
            if item_id != 0 or total != 0 or equipped != 0:
                items[item_id] = (total, equipped)
        return items

    def set_inventory_item(self, item_id: int, total_count: int = 50, equipped_count: int = 0) -> bool:
        """Add or update an item in the clan inventory.

        Slot layout: [Item ID (uint16)] [Equipped Count (uint8)] [Total Count (uint8)]
        Returns True if item was added or updated, False if clan inventory bag is full.
        """
        # Check if already present
        first_free_slot = None
        for i in range(MAX_INVENTORY_SLOTS):
            off = INVENTORY_BASE + i * 4
            cur_id = struct.unpack_from("<H", self.plaintext, off)[0]
            cur_eq = self.plaintext[off + 2]
            cur_tot = self.plaintext[off + 3]
            if cur_id == item_id:
                # Update existing slot
                self.plaintext[off + 2] = min(equipped_count, 24)
                self.plaintext[off + 3] = min(total_count, 99)
                return True
            if cur_id == 0 and cur_tot == 0 and cur_eq == 0 and first_free_slot is None:
                first_free_slot = off

        if first_free_slot is not None:
            struct.pack_into("<H", self.plaintext, first_free_slot, item_id & 0xFFFF)
            self.plaintext[first_free_slot + 2] = min(equipped_count, 24)
            self.plaintext[first_free_slot + 3] = min(total_count, 99)
            return True

        return False

    def inject_clan_equipment(self, item_ids: list[int], count: int = 50) -> int:
        """Add a list of equipment items to clan inventory bag."""
        added = 0
        for item_id in item_ids:
            if item_id > 0 and self.set_inventory_item(item_id, total_count=count):
                added += 1
        return added

    def sync_equipped_to_inventory(self, default_count: int = 50) -> None:
        """Ensure all equipped items on units 0..5 are registered in the clan inventory table."""
        for i in range(6):
            unit = self.get_unit(i)
            if unit and (unit.character_id != 0 or unit.job_id != 0):
                equips = [unit.weapon_id, unit.shield_id, unit.helm_id, unit.armor_id, unit.accessory_id]
                for eq in equips:
                    if eq != 0:
                        inv = self.get_inventory()
                        if eq in inv:
                            total, eq_count = inv[eq]
                            self.set_inventory_item(
                                eq, total_count=max(total, default_count), equipped_count=max(eq_count, 1)
                            )
                        else:
                            self.set_inventory_item(eq, total_count=default_count, equipped_count=1)

    def unlock_all_jobs(self) -> None:
        """Unlock all standard and hidden job classes for all races in the clan menu.

        Corresponds to canonical Action Replay unlock addresses:
        0x0212D784..0x0212D786 (offsets 0x2814..0x2816 in save payload) and
        0x0212D81F..0x0212D820 (offsets 0x28AF..0x28B0 in save payload).
        """
        self.plaintext[0x2814:0x2817] = b"\xff\xff\xff"
        self.plaintext[0x28AF:0x28B1] = b"\xff\xff"

    @property
    def gil(self) -> int:
        """Current clan Gil balance."""
        return struct.unpack_from("<I", self.plaintext, OFF_GIL)[0]

    @gil.setter
    def gil(self, amount: int) -> None:
        """Set clan Gil balance (clamped to 0..99,999,999)."""
        clamped = max(0, min(amount, 99999999))
        struct.pack_into("<I", self.plaintext, OFF_GIL, clamped)

    @property
    def clan_points(self) -> int:
        """Current Clan Points (CP)."""
        return struct.unpack_from("<H", self.plaintext, OFF_CLAN_POINTS)[0]

    @clan_points.setter
    def clan_points(self, points: int) -> None:
        """Set Clan Points (clamped to 0..9999)."""
        clamped = max(0, min(points, 9999))
        struct.pack_into("<H", self.plaintext, OFF_CLAN_POINTS, clamped)

    @property
    def clan_talents(self) -> tuple[int, int, int, int]:
        """Clan talents as (Negotiation, Aptitude, Teamwork, Adaptability)."""
        return tuple(self.plaintext[OFF_CLAN_TALENTS : OFF_CLAN_TALENTS + 4])

    @clan_talents.setter
    def clan_talents(self, values: tuple[int, int, int, int] | list[int]) -> None:
        """Set all four clan talents (clamped to 0..99 each)."""
        if len(values) != 4:
            raise ValueError("clan_talents requires 4 values: (Negotiation, Aptitude, Teamwork, Adaptability)")
        clamped = bytes(max(0, min(v, 99)) for v in values)
        self.plaintext[OFF_CLAN_TALENTS : OFF_CLAN_TALENTS + 4] = clamped

    def unlock_clan_privileges(self) -> None:
        """Unlock every Clan Privilege in the Judge menu, preserving bits outside the mask."""
        for i, mask in enumerate(CLAN_PRIVILEGE_MASK):
            self.plaintext[OFF_CLAN_PRIVILEGES_START + i] |= mask

    def master_all_unit_abilities(self, unit_index: int | None = None) -> int:
        """Master all abilities for a specific unit (0..23) or all recruited clan units.

        Returns the number of units whose ability arrays were mastered.
        """
        if unit_index is not None:
            unit = self.get_unit(unit_index)
            if unit is None:
                raise ValueError(f"Invalid unit index: {unit_index} (must be 0..{MAX_UNITS - 1})")
            if not unit.is_recruited:
                raise ValueError(f"Unit slot {unit_index + 1} is empty (no recruited clan member)")
            unit.master_all_abilities()
            return 1

        count = 0
        for i in range(MAX_UNITS):
            unit = self.get_unit(i)
            if unit is not None and unit.is_recruited:
                unit.master_all_abilities()
                count += 1
        return count

    def save(self, output_path: str | Path | None = None, backup: bool = True) -> Path:
        """Recompute checksum, re-encrypt payload, and save to disk.

        When overwriting an existing file and backup is True, a timestamped
        '<name>.bak_YYYYMMDD_HHMMSS' snapshot is created first.
        """
        out = Path(output_path) if output_path else self.path

        # Recalculate checksum over plaintext
        new_checksum = calculate_checksum(self.plaintext)
        self.plaintext[CHECKSUM_OFFSET : CHECKSUM_OFFSET + 4] = struct.pack("<I", new_checksum)

        # Re-encrypt
        final_data = bytearray(self.plaintext)
        encrypt_save_payload(final_data, self.keystream)

        # Move the staged record back to the physical record that backs this slot and
        # restore the other slot's record untouched.
        if self.record_base != RECORD_HEADER_OFFSET:
            record = bytes(final_data[RECORD_HEADER_OFFSET:ENCRYPTED_END])
            final_data[RECORD_HEADER_OFFSET:ENCRYPTED_END] = self.raw_data[RECORD_HEADER_OFFSET:ENCRYPTED_END]
            final_data[self.record_base : self.record_base + len(record)] = record

        # Always refresh the load-screen preview and wipe the quicksave (any save size),
        # and mirror dual banks when the image has a second bank. The written image keeps
        # the input size (64 KB melonDS or 512 KB cart dumps).
        from ffta2_tool.slots import SlotManager

        sm = SlotManager(final_data)
        sm.refresh_preview(self.slot)
        sm.deactivate_quicksave()
        final_data = bytearray(sm.raw[: len(final_data)])

        if backup and out.exists():
            backup_path = create_backup_snapshot(out)
            print(f"[*] Backup snapshot created: {backup_path}")

        atomic_write(out, final_data)
        return out
