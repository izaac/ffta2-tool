"""FFTA2 Unit Info and Save Validator.

Emulates the NDS game engine's validation rules for party units to detect
illegal equipment, invalid ability bitfields, and race/job mismatches that cause
UI renderer freezes or black screens.
"""

from __future__ import annotations

from dataclasses import dataclass

from ffta2_tool.charset import (
    CUSTOM_NAME_BUFFER_LEN,
    MAX_CUSTOM_NAME_CHARS,
    VALID_CUSTOM_NAME_BYTES,
    decode_ffta2_string,
    encode_ffta2_string,
)
from ffta2_tool.mappings import (
    CHARACTER_NAMES,
    MAX_VALID_EQUIP_ID,
    RACE_JOBS,
    REACTION_ABILITIES,
    SUPPORT_ABILITIES,
    get_item_name,
    get_job_name,
    get_job_race_id,
    get_race_name,
    is_heavy_armor_capable,
    is_shield_capable,
)
from ffta2_tool.save import (
    MAX_UNITS,
    OFF_CLAN_NAME,
    OFF_LEADER_NAME,
    OFF_UNIT_ABILITIES_END,
    OFF_UNIT_ABILITIES_START,
    OFF_UNIT_BASE_FLAGS_END,
    OFF_UNIT_BASE_FLAGS_START,
    FFTA2Save,
    Unit,
)

# Shields in FFTA2 equipment table (0x0120..0x0130)
SHIELD_ITEM_RANGE = range(0x0120, 0x0131)

# Items 0x0001..0x011F are weapons; anything below is a weapon when placed off-hand
WEAPON_ITEM_MAX = 0x011F

# Support ability required to legally equip a weapon in the off-hand slot (+0x4E)
DUAL_WIELD_ABILITY = 0x035C

# A run of this many 0xFF bytes inside the ability array signals a partial blanket fill
ABILITY_FF_RUN_WARNING = 16

# Races that can learn each R/S ability, verified against the FFTA2 job ability
# tables (Fandom / thonky / GameFAQs, 2026-10-16). Abilities absent from these
# tables are not checked.
REACTION_ABILITY_RACES: dict[int, set[int]] = {
    0x033A: {1, 2, 3, 4, 6},  # Reflex: Paladin, White Monk, Sage, Fencer, Raptor
    0x033C: {1, 2, 6},  # Strike Back: Parivir, Gladiator, Ravager
    0x033E: {1, 4, 5},  # Return Fire: Juggler (Hume/Moogle), Assassin
}

SUPPORT_ABILITY_RACES: dict[int, set[int]] = {
    0x0353: {1, 2, 6, 7},  # Attack Up: Hunter (Hume/Gria), Templar, Berserker
    0x0355: {3, 4},  # Magick Up: Alchemist, Red Mage
    0x0359: {1, 3},  # Pierce: Seer, Arcanist
    0x035C: {1},  # Dual Wield: Ninja (Hume only)
    0x0361: {1, 4, 5},  # Concentration: Archer (Hume/Viera), Fusilier
    0x0365: {2, 6},  # Unscarred: Master Monk, Ravager
    0x036A: {4},  # Blood Price: Spellblade (Viera)
}

# Valid ability IDs with no player job learn source (NPC-only).
UNLEARNABLE_ABILITIES: set[int] = {0x0371}  # Elusion (illegal Geomancer NPC)

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
    """Validate a single recruited unit against NDS engine stability constraints."""
    issues: list[ValidationIssue] = []
    idx = unit.index
    raw = unit._data

    race_id = raw[0x0F]
    job_id = unit.job_id

    # 1. Race / Job Compatibility (get_job_race_id & RACE_JOBS)
    expected_race = get_job_race_id(job_id)
    if expected_race == 0 or race_id != expected_race or (race_id in RACE_JOBS and job_id not in RACE_JOBS[race_id]):
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

    # 1b. Character ID and Name ID invariants
    if idx == 0:
        if unit.character_id != 1:
            issues.append(
                ValidationIssue(
                    idx,
                    "ERROR",
                    "character_id",
                    f"Slot 0 (Luso) must have character_id == 1 (got 0x{unit.character_id:02X})",
                )
            )
        if unit.name_id != 0x8001:
            issues.append(
                ValidationIssue(
                    idx,
                    "ERROR",
                    "name_id",
                    f"Slot 0 (Luso) must have name_id == 0x8001 (got 0x{unit.name_id:04X})",
                )
            )
    else:
        if unit.character_id != 0:
            issues.append(
                ValidationIssue(
                    idx,
                    "ERROR",
                    "character_id",
                    f"Generic slot {idx + 1} must have character_id == 0 (got 0x{unit.character_id:02X})",
                )
            )
        if (unit.name_id & 0x8000) != 0 or not (1 <= unit.name_id < len(CHARACTER_NAMES)):
            issues.append(
                ValidationIssue(
                    idx,
                    "ERROR",
                    "name_id",
                    (
                        f"Generic slot {idx + 1} must have plain ROM name_id in 1..{len(CHARACTER_NAMES) - 1} "
                        f"with high bit clear (got 0x{unit.name_id:04X})"
                    ),
                )
            )

    # 1c. Structural invariants (+0x10, roster_index +0x11, status_flags +0x12, base_flags +0x25..0x2D)
    if raw[0x10] != 0:
        issues.append(
            ValidationIssue(idx, "ERROR", "reserved_0x10", f"Unit +0x10 must be 0x00 (got 0x{raw[0x10]:02X})")
        )
    if unit.roster_index != idx + 1:
        issues.append(
            ValidationIssue(
                idx,
                "ERROR",
                "roster_index",
                f"Unit roster_index (+0x11) must equal slot+1 ({idx + 1}), got {unit.roster_index}",
            )
        )
    # Note: 0x0080 is standard recruited flag; 0x2080 occurs on real saves
    # (e.g. 071_FFTA2_both_slots_20261016_150437.sav) when the unit is marked in the active battle formation.
    if (unit.status_flags & 0x0080) == 0 or (unit.status_flags & ~0x2080) != 0:
        issues.append(
            ValidationIssue(
                idx,
                "ERROR",
                "status_flags",
                f"Unit status_flags (+0x12) must be 0x0080 (or 0x2080), got 0x{unit.status_flags:04X}",
            )
        )
    expected_base_flags = b"\x01" * (OFF_UNIT_BASE_FLAGS_END - OFF_UNIT_BASE_FLAGS_START)
    if bytes(raw[OFF_UNIT_BASE_FLAGS_START:OFF_UNIT_BASE_FLAGS_END]) != expected_base_flags:
        issues.append(
            ValidationIssue(
                idx,
                "ERROR",
                "base_flags",
                (
                    f"Unit base_flags (+0x25..+0x2D) must be 01x9, got "
                    f"{bytes(raw[OFF_UNIT_BASE_FLAGS_START:OFF_UNIT_BASE_FLAGS_END]).hex()}"
                ),
            )
        )

    # 1d. Level and HP/MP bounds
    if not (1 <= unit.level <= 99):
        issues.append(ValidationIssue(idx, "ERROR", "level", f"Unit level must be 1..99 (got {unit.level})"))
    if unit.max_hp == 0 or unit.cur_hp > unit.max_hp:
        issues.append(ValidationIssue(idx, "ERROR", "hp", f"Invalid HP: cur_hp={unit.cur_hp} > max_hp={unit.max_hp}"))
    if unit.cur_mp > unit.max_mp:
        issues.append(ValidationIssue(idx, "ERROR", "mp", f"Invalid MP: cur_mp={unit.cur_mp} > max_mp={unit.max_mp}"))

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

    # 3b. Off-hand weapon legality: a weapon in the off-hand slot requires Dual Wield
    off_hand = unit.shield_id
    if 0 < off_hand <= WEAPON_ITEM_MAX:
        if unit.p_ability != DUAL_WIELD_ABILITY:
            issues.append(
                ValidationIssue(
                    idx,
                    "ERROR",
                    "shield_id",
                    (
                        f"Off-hand weapon 0x{off_hand:04X} ({get_item_name(off_hand)}) without "
                        f"Dual Wield (passive 0x{unit.p_ability:04X}); Unit Info black screen"
                    ),
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    idx,
                    "WARNING",
                    "shield_id",
                    (
                        f"Off-hand weapon 0x{off_hand:04X} ({get_item_name(off_hand)}) with Dual Wield; "
                        "single-wield if Unit Info still black-screens"
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
            ),
        )

    # 5. Blanket ability mastery (0x5A..0x11C). Not a crash: an all-0xFF array renders
    # Unit Info, Change Jobs, Set Abilities, and the ability pickers normally (melonDS,
    # 2026-10-17). It is still not a legal state: abilities of other races' jobs and
    # unreleased "???" jobs show as mastered.
    ability_region = bytes(raw[OFF_UNIT_ABILITIES_START:OFF_UNIT_ABILITIES_END])
    if ability_region:
        if all(b == 0xFF for b in ability_region):
            issues.append(
                ValidationIssue(
                    idx,
                    "WARNING",
                    "abilities",
                    (
                        f"Ability array 0x{OFF_UNIT_ABILITIES_START:02X}..0x{OFF_UNIT_ABILITIES_END:02X} "
                        "is entirely 0xFF (blanket mastery); other races' and '???' jobs show as mastered"
                    ),
                )
            )
        else:
            run = best = 0
            for b in ability_region:
                run = run + 1 if b == 0xFF else 0
                best = max(best, run)
            if best >= ABILITY_FF_RUN_WARNING:
                issues.append(
                    ValidationIssue(
                        idx,
                        "WARNING",
                        "abilities",
                        f"Ability array contains a {best}-byte 0xFF run; likely blanket mastery corruption",
                    )
                )

    # 6. Assigned reaction / passive ability IDs must exist in the ROM tables
    if unit.r_ability != 0 and unit.r_ability not in REACTION_ABILITIES:
        issues.append(ValidationIssue(idx, "ERROR", "r_ability", f"Unknown reaction ability 0x{unit.r_ability:04X}"))
    if unit.p_ability != 0 and unit.p_ability not in SUPPORT_ABILITIES:
        issues.append(ValidationIssue(idx, "ERROR", "p_ability", f"Unknown passive ability 0x{unit.p_ability:04X}"))

    # 7. Race learn-source legality (race-locked R/S abilities)
    reaction_races = REACTION_ABILITY_RACES.get(unit.r_ability)
    if reaction_races is not None and race_id not in reaction_races:
        allowed = ", ".join(get_race_name(r) for r in sorted(reaction_races))
        issues.append(
            ValidationIssue(
                idx,
                "WARNING",
                "r_ability",
                (
                    f"Reaction 0x{unit.r_ability:04X} ({REACTION_ABILITIES[unit.r_ability]}) is not "
                    f"learnable by {get_race_name(race_id)} (only {allowed})"
                ),
            )
        )

    support_races = SUPPORT_ABILITY_RACES.get(unit.p_ability)
    if support_races is not None and race_id not in support_races:
        allowed = ", ".join(get_race_name(r) for r in sorted(support_races))
        issues.append(
            ValidationIssue(
                idx,
                "WARNING",
                "p_ability",
                (
                    f"Passive 0x{unit.p_ability:04X} ({SUPPORT_ABILITIES[unit.p_ability]}) is not "
                    f"learnable by {get_race_name(race_id)} (only {allowed})"
                ),
            )
        )

    if unit.p_ability in UNLEARNABLE_ABILITIES:
        issues.append(
            ValidationIssue(
                idx,
                "WARNING",
                "p_ability",
                (
                    f"Passive 0x{unit.p_ability:04X} ({SUPPORT_ABILITIES[unit.p_ability]}) has "
                    "no player job learn source (NPC-only ability)"
                ),
            )
        )

    return issues


def _validate_custom_name_buffer(raw_buf: bytes, field_name: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if 0 not in raw_buf:
        issues.append(
            ValidationIssue(
                -1,
                "ERROR",
                field_name,
                f"{field_name} buffer is missing a 0x00 terminator inside {len(raw_buf)} bytes",
            )
        )
        return issues

    null_idx = raw_buf.index(0)
    prefix = raw_buf[:null_idx]
    if not prefix:
        issues.append(ValidationIssue(-1, "ERROR", field_name, f"{field_name} cannot be empty"))
        return issues

    if len(prefix) > MAX_CUSTOM_NAME_CHARS:
        issues.append(
            ValidationIssue(
                -1,
                "ERROR",
                field_name,
                f"{field_name} length ({len(prefix)}) exceeds cap of {MAX_CUSTOM_NAME_CHARS} characters",
            )
        )

    bad_bytes = [b for b in prefix if b not in VALID_CUSTOM_NAME_BYTES]
    if bad_bytes:
        issues.append(
            ValidationIssue(
                -1,
                "ERROR",
                field_name,
                f"{field_name} contains unsupported character byte(s): {[f'0x{b:02X}' for b in bad_bytes]}",
            )
        )
        return issues

    decoded = decode_ffta2_string(raw_buf, max_len=len(raw_buf))
    try:
        reencoded = encode_ffta2_string(decoded, length=len(raw_buf))
        if decode_ffta2_string(reencoded, max_len=len(raw_buf)) != decoded:
            issues.append(ValidationIssue(-1, "ERROR", field_name, f"{field_name} failed encode/decode round-trip"))
    except ValueError as exc:
        issues.append(ValidationIssue(-1, "ERROR", field_name, str(exc)))

    return issues


def validate_save(save: FFTA2Save) -> list[ValidationIssue]:
    """Validate save-level invariants (custom names, contiguous roster) and all active clan members."""
    all_issues: list[ValidationIssue] = []

    leader_buf = bytes(save.plaintext[OFF_LEADER_NAME : OFF_LEADER_NAME + CUSTOM_NAME_BUFFER_LEN])
    clan_buf = bytes(save.plaintext[OFF_CLAN_NAME : OFF_CLAN_NAME + CUSTOM_NAME_BUFFER_LEN])
    all_issues.extend(_validate_custom_name_buffer(leader_buf, "leader_name"))
    all_issues.extend(_validate_custom_name_buffer(clan_buf, "clan_name"))

    seen_empty = False
    seen_roster_indices: dict[int, int] = {}
    for i in range(MAX_UNITS):
        unit = save.get_unit(i)
        if unit and unit.is_recruited:
            if seen_empty:
                all_issues.append(
                    ValidationIssue(
                        i,
                        "ERROR",
                        "roster",
                        f"Recruited unit at slot {i + 1} appears after an empty slot (non-contiguous roster)",
                    )
                )
            r_idx = unit.roster_index
            if r_idx in seen_roster_indices:
                all_issues.append(
                    ValidationIssue(
                        i,
                        "ERROR",
                        "roster_index",
                        (
                            f"Duplicate roster_index {r_idx} on Unit {i + 1} "
                            f"(already used by Unit {seen_roster_indices[r_idx] + 1})"
                        ),
                    )
                )
            else:
                seen_roster_indices[r_idx] = i
            all_issues.extend(validate_unit(unit))
        else:
            seen_empty = True

    return all_issues
