"""FFTA2 Unit Info and Save Validator.

Emulates the NDS game engine's validation rules for party units to detect
illegal equipment, invalid ability bitfields, and race/job mismatches that cause
UI renderer freezes or black screens.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from ffta2_tool.save import Unit, FFTA2Save

# Race ID to allowed Job ID ranges
RACE_JOBS = {
    0x01: range(0x01, 0x0E),  # Hume: Soldier (0x01) to Seer (0x0D)
    0x02: range(0x0E, 0x18),  # Bangaa: Warrior (0x0E) to Trickster (0x17)
    0x03: range(0x18, 0x21),  # Nu Mou: White Mage (0x18) to Scholar (0x20)
    0x04: range(0x22, 0x2C),  # Viera: Fencer (0x22) to Sniper (0x2B)
    0x05: range(0x2C, 0x36),  # Moogle: Animist (0x2C) to Flintlock (0x35)
    0x06: range(0x36, 0x3E),  # Gria: Berserker (0x36) to Geomancer (0x3D)
    0x07: range(0x3E, 0x42),  # Seeq
}

# Jobs that can legally equip Shields
SHIELD_CAPABLE_JOBS = {
    0x01, 0x06, 0x07, 0x0B,  # Hume: Soldier, Paladin, Fighter, Blue Mage
    0x0E, 0x10, 0x11, 0x12, 0x15,  # Bangaa: Warrior, Dragoon, Defender, Gladiator, Templar
    0x1F,  # Nu Mou: Sage
    0x22, 0x28,  # Viera: Fencer, Spellblade
    0x2F,  # Moogle: Moogle Knight
    0x38, 0x39, 0x3C,  # Gria: Lanista, Viking, Ravager
}

# Jobs that can legally equip Heavy Armor / Heavy Helms
HEAVY_ARMOR_JOBS = {
    0x01, 0x06, 0x07,  # Soldier, Paladin, Fighter
    0x0E, 0x10, 0x11, 0x12, 0x15,  # Warrior, Dragoon, Defender, Gladiator, Templar
    0x2F,  # Moogle Knight
    0x38, 0x39, 0x3C,  # Lanista, Viking, Ravager
}

# Max valid ability ID in FFTA2 ROM table
MAX_VALID_ABILITY_ID = 482
MAX_VALID_EQUIP_ID = 0x019A


@dataclass
class ValidationIssue:
    unit_index: int
    severity: str  # "ERROR" (causes crash/black screen) or "WARNING"
    field: str
    message: str


def validate_unit(unit: Unit) -> List[ValidationIssue]:
    """Validate a single unit against NDS engine stability constraints."""
    issues: List[ValidationIssue] = []
    idx = unit.index
    raw = unit._data

    race_id = raw[0x0F]
    job_id = unit.job_id

    # 1. Race / Job Compatibility
    if race_id in RACE_JOBS:
        if job_id not in RACE_JOBS[race_id]:
            issues.append(
                ValidationIssue(
                    idx,
                    "ERROR",
                    "job_id",
                    f"Job 0x{job_id:02X} is illegal for Race 0x{race_id:02X}",
                )
            )

    # 2. Equipment ID boundaries
    equips = [
        ("weapon", unit.weapon_id),
        ("shield", unit.shield_id),
        ("helm", unit.helm_id),
        ("armor", unit.armor_id),
        ("accessory", unit.accessory_id),
    ]
    for slot_name, item_id in equips:
        if item_id != 0 and item_id > MAX_VALID_EQUIP_ID:
            issues.append(
                ValidationIssue(
                    idx,
                    "ERROR",
                    slot_name,
                    f"Item ID 0x{item_id:04X} exceeds ROM equipment bounds (max 0x{MAX_VALID_EQUIP_ID:04X})",
                )
            )

    # 3. Off-hand / Shield Legality
    # If off-hand has an item and job cannot equip shields (and no Dual Wield active)
    if unit.shield_id != 0:
        if job_id not in SHIELD_CAPABLE_JOBS:
            issues.append(
                ValidationIssue(
                    idx,
                    "ERROR",
                    "shield_id",
                    f"Job 0x{job_id:02X} cannot equip shields/offhand (Item: 0x{unit.shield_id:04X}); triggers UI freeze",
                )
            )

    # 4. Ability Bitfield Corruption Check (+0x56 to +0x11B)
    # The ROM ability table only has 482 entries.
    ability_bytes = raw[0x56:]
    total_ff = sum(1 for b in ability_bytes if b == 0xFF)
    if total_ff > 10:
        issues.append(
            ValidationIssue(
                idx,
                "ERROR",
                "abilities",
                f"Abilities bitfield has wholesale 0xFF fill ({total_ff} bytes); causes fatal out-of-bounds crash on Unit Info",
            )
        )

    # Check for bits set beyond 482 abilities
    # 482 bits = 60 bytes and 2 bits (offset 0x56 + 60 = 0x92)
    max_safe_byte_index = 0x56 + (MAX_VALID_ABILITY_ID // 8) + 1
    out_of_bounds_bits = any(b != 0 for b in raw[max_safe_byte_index:])
    if out_of_bounds_bits:
        issues.append(
            ValidationIssue(
                idx,
                "ERROR",
                "abilities",
                f"Nonzero ability bits set past ability index {MAX_VALID_ABILITY_ID}; causes pointer dereference crash",
            )
        )

    return issues


def validate_save(save: FFTA2Save) -> List[ValidationIssue]:
    """Validate all active clan members in save."""
    all_issues: List[ValidationIssue] = []
    for i in range(24):
        unit = save.get_unit(i)
        if unit and (unit.character_id != 0 or unit.job_id != 0):
            all_issues.extend(validate_unit(unit))
    return all_issues
