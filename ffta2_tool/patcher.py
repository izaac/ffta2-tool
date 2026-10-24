"""FFTA2 Meta Squad Patcher.

Applies fully audited, ROM-verified meta builds to the starting clan members.
Also optionally injects full sets of ability-learning equipment into the clan bag.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ffta2_tool.builds import DEFAULT_META_SQUAD_BUILDS, get_meta_squad_builds, resolve_build
from ffta2_tool.mappings import get_job_race_id
from ffta2_tool.save import FFTA2Save
from ffta2_tool.stats import topup_clan_stats, topup_unit_stats

__all__ = [
    "DEFAULT_META_SQUAD_BUILDS",
    "META_INVENTORY_ITEMS",
    "META_SQUAD_BUILDS",  # noqa: F822 - resolved lazily by __getattr__ below
    "apply_meta_squad",
    "equip_unit_build",
    "get_meta_squad_builds",
    "resolve_build",
]


def __getattr__(name: str) -> Any:
    """Resolve ``META_SQUAD_BUILDS`` on first access instead of at import time.

    Importing this module must not touch the filesystem, so the builds database is
    loaded lazily; ``from ffta2_tool.patcher import META_SQUAD_BUILDS`` still works.
    """
    if name == "META_SQUAD_BUILDS":
        return get_meta_squad_builds()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Expose dynamic attribute META_SQUAD_BUILDS to dir() and inspect tooling."""
    return sorted(set(globals().keys()) | set(__all__))


# Ability-teaching weapons and gear for clan inventory injection
META_INVENTORY_ITEMS: list[int] = [
    # Parivir / Paladin / Ninja
    0x0018,
    0x0074,
    0x006F,
    0x006E,
    0x006A,
    0x0065,  # Katanas & Dual Wield Ninja Knife
    0x0033,
    0x002D,
    0x0032,
    0x0034,
    0x002F,
    0x0031,  # Knightswords
    # Sage / Alchemist
    0x010F,
    0x0107,
    0x0101,
    0x0105,
    0x0104,
    0x0103,  # Maces
    0x0127,
    0x0122,  # Shields
    # Red Mage / Summoner
    0x0050,
    0x0051,
    0x004E,
    0x004F,
    0x004C,  # Rapiers
    0x0089,
    0x008A,
    0x008C,
    0x0085,
    0x0086,
    0x0087,  # Rods
    # Cannoneer / Defender
    0x00F0,
    0x00EE,
    0x00ED,
    0x00EC,
    0x00EB,
    0x00EA,  # Hand Cannons
    0x002E,
    0x0030,  # Defender Swords
    # Hunter / Seer
    0x00CA,
    0x00BC,
    0x00BB,
    0x00BA,
    0x00B9,
    0x00B4,  # Greatbows & Bows
    0x0099,
    0x0098,
    0x0097,
    0x0096,
    0x0094,
    0x0092,  # Staves
    # Fusilier / Juggler
    0x00D4,
    0x00D3,
    0x00D2,
    0x00D1,
    0x00D6,
    0x00D7,  # Guns
    0x000C,
    0x000B,
    0x000A,
    0x0009,
    0x0007,
    0x0001,  # Daggers
    # Endgame Gear & Accessories
    0x0138,
    0x0139,
    0x013A,
    0x013B,
    0x013E,
    0x013F,  # Head
    0x0153,
    0x0156,
    0x015B,
    0x015C,
    0x015E,
    0x015F,
    0x0171,  # Armor & Robes
    0x0176,
    0x0179,
    0x017B,
    0x017E,
    0x0180,
    0x0184,
    0x0185,
    0x0187,
    0x0189,  # Accessories
]


def equip_unit_build(
    save: FFTA2Save,
    unit_index: int,
    build_key: str,
    master_abilities: bool = False,
    topup_stats: bool = True,
    builds_path: str | Path | None = None,
) -> dict[str, Any]:
    """Equip a single unit (0..23) with a named build from builds.toml."""
    unit = save.get_unit(unit_index)
    if unit is None:
        raise ValueError(f"Invalid unit index: {unit_index} (must be 0..23)")
    if not unit.is_recruited:
        raise ValueError(f"Unit slot {unit_index + 1} is empty (no recruited clan member)")

    build = resolve_build(build_key, builds_path=builds_path)
    if build is None:
        available = ", ".join(b.get("key", b["name"]).lower() for b in get_meta_squad_builds())
        raise ValueError(f"Unknown build '{build_key}'. Available builds: {available}")

    job_id = int(build["job_id"])
    unit.race_id = get_job_race_id(job_id)
    unit.job_id = job_id
    unit.primary_ability_set = int(build["primary_set"])
    unit.secondary_ability_set = int(build["secondary_set"])
    unit.weapon_id = int(build["weapon_id"])
    unit.shield_id = int(build["shield_id"])
    unit.helm_id = int(build["helm_id"])
    unit.armor_id = int(build["armor_id"])
    unit.accessory_id = int(build["accessory_id"])
    if build.get("r_ability"):
        unit.r_ability = int(build["r_ability"])
    if build.get("p_ability"):
        unit.p_ability = int(build["p_ability"])
    if master_abilities:
        unit.master_all_abilities()

    if topup_stats:
        topup_unit_stats(unit)

    save.sync_equipped_to_inventory()
    return build


def apply_meta_squad(
    save: FFTA2Save,
    builds: list[dict[str, Any]] | None = None,
    inject_inventory: bool = True,
    inventory_count: int = 50,
    master_abilities: bool = False,
    unlock_jobs: bool = True,
    topup_stats: bool = True,
) -> None:
    """Apply verified meta squad builds to the first 6 clan members.

    Optionally injects 50x of ability-teaching weapons/armor into the clan inventory bag,
    unlocks all standard and hidden job classes in clan data, and non-destructively tops
    up stats to 115% god-roll maximums.

    Ability mastery is OFF by default: blanket-filling the unit ability array
    (0x5A..0x11C) with 0xFF does not crash the game, but it also masters abilities
    of other races' jobs and unreleased "???" jobs, which no legal save can have.
    """
    target_builds = builds if builds is not None else get_meta_squad_builds()

    if unlock_jobs:
        save.unlock_all_jobs()

    for build in target_builds:
        unit = save.get_unit(build["slot"])
        if unit is None:
            continue
        unit.job_id = build["job_id"]
        unit.primary_ability_set = build["primary_set"]
        unit.secondary_ability_set = build["secondary_set"]
        unit.weapon_id = build["weapon_id"]
        unit.shield_id = build["shield_id"]
        unit.helm_id = build["helm_id"]
        unit.armor_id = build["armor_id"]
        unit.accessory_id = build["accessory_id"]
        if "r_ability" in build and build["r_ability"]:
            unit.r_ability = build["r_ability"]
        if "p_ability" in build and build["p_ability"]:
            unit.p_ability = build["p_ability"]
        if master_abilities:
            unit.master_all_abilities()

    if topup_stats:
        topup_clan_stats(save, max_units=len(target_builds))

    if inject_inventory:
        save.inject_clan_equipment(META_INVENTORY_ITEMS, count=inventory_count)
        save.sync_equipped_to_inventory(default_count=inventory_count)
