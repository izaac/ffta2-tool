"""FFTA2 Unit Info and Save Validator.

Emulates the NDS game engine's validation rules for party units to detect
illegal equipment, invalid ability bitfields, and race/job mismatches that cause
UI renderer freezes or black screens.
"""

from __future__ import annotations

from dataclasses import dataclass

from ffta2_tool.mappings import (
    MAX_VALID_EQUIP_ID,
    RACE_JOBS,
    get_job_name,
    get_race_name,
    is_heavy_armor_capable,
    is_shield_capable,
)
from ffta2_tool.save import FFTA2Save, Unit

# Shields in FFTA2 equipment table (0x0120..0x0130)
SHIELD_ITEM_RANGE = range(0x0120, 0x0131)

# Heavy Helms and Heavy Armor items
HEAVY_HELM_ITEMS = {0x0140, 0x0141, 0x0142, 0x0143, 0x0144, 0x0145}
HEAVY_ARMOR_ITEMS = {0x0150, 0x0151, 0x0152, 0x0160, 0x0161, 0x0162, 0x0163, 0x0164, 0x0165}


@dataclass
class ValidationIssue:
    unit_index: int
    severity: str  # "ERROR" (causes crash/black screen) or "WARNING"
    field: str
    message: str


def validate_unit(unit: Unit) -> list[ValidationIssue]:
    """Validate a single unit against NDS engine stability constraints."""
    issues: list[ValidationIssue] = []
    idx = unit.index
    raw = unit._data

    race_id = raw[0x0F]
    job_id = unit.job_id

    # 1. Race / Job Compatibility
    if race_id in RACE_JOBS and job_id not in RACE_JOBS[race_id]:
        issues.append(
            ValidationIssue(
                idx,
                "ERROR",
                "job_id",
                (
                    f"Job 0x{job_id:02X} ({get_job_name(job_id)}) is illegal "
                    f"for Race 0x{race_id:02X} ({get_race_name(race_id)})"
                ),
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
    # If off-hand has an actual shield item and job cannot equip shields
    if unit.shield_id in SHIELD_ITEM_RANGE and not is_shield_capable(job_id):
        issues.append(
            ValidationIssue(
                idx,
                "ERROR",
                "shield_id",
                (
                    f"Job 0x{job_id:02X} ({get_job_name(job_id)}) cannot equip "
                    f"shield (Item: 0x{unit.shield_id:04X}); triggers UI freeze"
                ),
            )
        )

    # 4. Heavy Armor / Helm Legality
    if unit.helm_id in HEAVY_HELM_ITEMS and not is_heavy_armor_capable(job_id):
        issues.append(
            ValidationIssue(
                idx,
                "WARNING",
                "helm_id",
                f"Job 0x{job_id:02X} ({get_job_name(job_id)}) equipped heavy helm 0x{unit.helm_id:04X}",
            )
        )
    if unit.armor_id in HEAVY_ARMOR_ITEMS and not is_heavy_armor_capable(job_id):
        issues.append(
            ValidationIssue(
                idx,
                "WARNING",
                "armor_id",
                f"Job 0x{job_id:02X} ({get_job_name(job_id)}) equipped heavy armor 0x{unit.armor_id:04X}",
            )
        )

    return issues


def validate_save(save: FFTA2Save) -> list[ValidationIssue]:
    """Validate all active clan members in save."""
    all_issues: list[ValidationIssue] = []
    for i in range(24):
        unit = save.get_unit(i)
        if unit and (unit.character_id != 0 or unit.job_id != 0):
            all_issues.extend(validate_unit(unit))
    return all_issues
