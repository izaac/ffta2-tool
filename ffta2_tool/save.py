"""FFTA2 High-Level Save File Interface."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional

from ffta2_tool.charset import decode_ffta2_string
from ffta2_tool.crypto import (
    calculate_checksum,
    decrypt_save_payload,
    encrypt_save_payload,
    extract_keystream,
    verify_save_checksum,
    CHECKSUM_OFFSET,
    ENCRYPTED_START,
    ENCRYPTED_END,
)

# Party units in the decrypted save file
UNIT_TABLE_BASE = 0x0238  # Unit 0 starts at 0x0238
UNIT_STRIDE = 0x11C       # 284 bytes per unit slot
MAX_UNITS = 24

# Exact offsets within a Unit entry (relative to unit base):
OFF_UNIT_CHAR_ID = 0x0D   # 1 byte (0x01 = Luso)
OFF_UNIT_JOB_ID = 0x0E    # 1 byte (0x01 = Soldier)
OFF_UNIT_RACE_ID = 0x0F   # 1 byte (0x01 = Hume)
OFF_UNIT_LEVEL = 0x22     # 1 byte
OFF_UNIT_MAX_HP = 0x3C    # 16-bit
OFF_UNIT_CUR_HP = 0x3E    # 16-bit
OFF_UNIT_MAX_MP = 0x40    # 16-bit
OFF_UNIT_CUR_MP = 0x42    # 16-bit
OFF_UNIT_ATTACK = 0x44    # 16-bit
OFF_UNIT_DEFENSE = 0x46   # 16-bit
OFF_UNIT_MATK = 0x48      # 16-bit
OFF_UNIT_MDEF = 0x4A      # 16-bit
OFF_UNIT_EQUIP1 = 0x4C    # 16-bit (Main Hand Weapon)
OFF_UNIT_EQUIP2 = 0x4E    # 16-bit (Off Hand / Shield)
OFF_UNIT_EQUIP3 = 0x50    # 16-bit (Head / Helmet)
OFF_UNIT_EQUIP4 = 0x52    # 16-bit (Body / Armor)
OFF_UNIT_EQUIP5 = 0x54    # 16-bit (Accessory)


class Unit:
    """Represents a unit entry inside the FFTA2 save."""

    def __init__(self, raw_unit: bytearray, index: int):
        self._data = raw_unit
        self.index = index

    @property
    def character_id(self) -> int:
        return self._data[OFF_UNIT_CHAR_ID]

    @property
    def job_id(self) -> int:
        return self._data[OFF_UNIT_JOB_ID]

    @job_id.setter
    def job_id(self, val: int) -> None:
        self._data[OFF_UNIT_JOB_ID] = val & 0xFF

    @property
    def primary_ability_set(self) -> int:
        return self._data[0x16]

    @primary_ability_set.setter
    def primary_ability_set(self, val: int) -> None:
        self._data[0x16] = val & 0xFF

    @property
    def secondary_ability_set(self) -> int:
        return self._data[0x17]

    @secondary_ability_set.setter
    def secondary_ability_set(self, val: int) -> None:
        self._data[0x17] = val & 0xFF

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
    def attack(self) -> int:
        return struct.unpack_from("<H", self._data, OFF_UNIT_ATTACK)[0]

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

    def master_all_abilities(self) -> None:
        """Set all ability mastery bitfields to 0xFF."""
        for i in range(0x56, len(self._data)):
            self._data[i] = 0xFF



class FFTA2Save:
    """FFTA2 Save File manager."""

    def __init__(self, filepath: str | Path):
        self.path = Path(filepath)
        self.raw_data = bytearray(self.path.read_bytes())
        self.keystream = extract_keystream(self.raw_data)
        self.plaintext = bytearray(self.raw_data)
        decrypt_save_payload(self.plaintext, self.keystream)

    @property
    def slot_0_player_name(self) -> str:
        name_bytes = self.raw_data[0x3C : 0x3C + 16]
        return decode_ffta2_string(name_bytes)

    def get_unit(self, index: int) -> Optional[Unit]:
        if not (0 <= index < MAX_UNITS):
            return None
        offset = UNIT_TABLE_BASE + index * UNIT_STRIDE
        unit_view = memoryview(self.plaintext)[offset : offset + UNIT_STRIDE]
        return Unit(unit_view, index)

    def save(self, output_path: Optional[str | Path] = None) -> Path:
        """Recompute checksum, re-encrypt payload, and save to disk."""
        out = Path(output_path) if output_path else self.path

        # Recalculate checksum over plaintext
        new_checksum = calculate_checksum(self.plaintext)
        self.plaintext[CHECKSUM_OFFSET : CHECKSUM_OFFSET + 4] = struct.pack("<I", new_checksum)

        # Re-encrypt
        final_data = bytearray(self.plaintext)
        encrypt_save_payload(final_data, self.keystream)

        out.write_bytes(final_data)
        return out
