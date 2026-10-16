"""FFTA2 Meta Squad Patcher.

Applies fully audited, ROM-verified meta builds to the starting clan members.
Also optionally injects full sets of ability-learning equipment into the clan bag.
"""

from __future__ import annotations

from typing import Any

from ffta2_tool.config import load_builds
from ffta2_tool.save import FFTA2Save

# Built-in fallback used when builds.toml is missing or unreadable
DEFAULT_META_SQUAD_BUILDS: list[dict[str, Any]] = [
    # Slot 0: Luso (Hume) - Parivir / Paladin
    {
        "name": "Luso",
        "slot": 0,
        "job_id": 0x08,  # Parivir
        "primary_set": 0x08,  # Flair
        "secondary_set": 0x06,  # Chivalry (Paladin: Nurse, Saint Cross, Holy Blade)
        "r_ability": 0x033C,  # Strike Back
        "p_ability": 0x035C,  # Dual Wield
        "weapon_id": 0x0074,  # Hyakushiki-masamune (+78 Atk, Katana)
        "shield_id": 0x0074,  # Hyakushiki-masamune (+78 Atk, Dual Wield off-hand)
        "helm_id": 0x013F,  # Thief's Cap (+2 Speed)
        "armor_id": 0x015C,  # Ninja Gear (+24 Def, +4 Speed)
        "accessory_id": 0x0180,  # Ninja Tabi (+2 Move)
    },
    # Slot 1: Nu Mou - Sage / Alchemist
    {
        "name": "Nu Mou",
        "slot": 1,
        "job_id": 0x1F,  # Sage
        "primary_set": 0x1C,  # Sagacity (Gigaflare, Bio, Aero)
        "secondary_set": 0x1A,  # Alchemy (100% Item Delivery)
        "r_ability": 0x033A,  # Reflex
        "p_ability": 0x0355,  # Magick Up
        "weapon_id": 0x010F,  # Zeus Mace (+30 Atk, +10 Magick)
        "shield_id": 0x0127,  # Genji Shield (+7 Def, +5 Evade, +2 MRes)
        "helm_id": 0x013E,  # Gold Hairpin (+10 MRes, Silence immune)
        "armor_id": 0x0171,  # Lordly Robe (+18 Def, +35 MRes, +5 Atk, +5 Mag)
        "accessory_id": 0x017E,  # Faerie Shoes (Teleport Movement!)
    },
    # Slot 2: Viera - Red Mage / Summoner
    {
        "name": "Viera",
        "slot": 2,
        "job_id": 0x27,  # Red Mage
        "primary_set": 0x22,  # Red Magick (Doublecast, Cure, Cura, Protect)
        "secondary_set": 0x24,  # Summoning Magick (Maduin, Phoenix, Unicorn, Kirin)
        "r_ability": 0x033A,  # Reflex
        "p_ability": 0x0371,  # Elusion
        "weapon_id": 0x0050,  # Femme Fatale (+49 Atk, +2 Mag Rapier)
        "shield_id": 0x0000,  # None
        "helm_id": 0x0138,  # Ribbon (Complete status immunity)
        "armor_id": 0x015B,  # Minerva Bustier (Holy/Dark absorb)
        "accessory_id": 0x0189,  # Angel Ring (Auto-Reraise safety against Blood Price)
    },
    # Slot 3: Bangaa - Cannoneer / Defender
    {
        "name": "Bangaa",
        "slot": 3,
        "job_id": 0x16,  # Cannoneer
        "primary_set": 0x16,  # Cannonry (Ether Shell +60 MP, Mortar, Target)
        "secondary_set": 0x11,  # Warding (Defender: Aura Auto-Life+Regen, Meltdown)
        "r_ability": 0x033C,  # Strike Back
        "p_ability": 0x0371,  # Elusion
        "weapon_id": 0x00F0,  # Rocket Punch (Hand Cannon)
        "shield_id": 0x0000,  # None
        "helm_id": 0x013F,  # Thief's Cap (+2 Speed)
        "armor_id": 0x015F,  # Mirage Vest (+30 Def, +12 MRes)
        "accessory_id": 0x0184,  # Genji Gloves (+5 Atk, +5 Def)
    },
    # Slot 4: Hume (Generic) - Hunter / Seer
    {
        "name": "Hume",
        "slot": 4,
        "job_id": 0x0C,  # Hunter
        "primary_set": 0x0C,  # Trapping (Hunter: Ultima Shot, Sonic Boom)
        "secondary_set": 0x0D,  # High Magick (Seer: Recharge, Magick Frenzy, Esuna)
        "r_ability": 0x033A,  # Reflex
        "p_ability": 0x0359,  # Pierce
        "weapon_id": 0x00CA,  # Seventh Heaven (Greatbow: Ultima Shot)
        "shield_id": 0x0000,  # None
        "helm_id": 0x013F,  # Thief's Cap (+2 Speed)
        "armor_id": 0x015C,  # Ninja Gear (+24 Def, +4 Speed)
        "accessory_id": 0x017B,  # Winged Boots (Float / Levitate)
    },
    # Slot 5: Moogle - Fusilier / Juggler
    {
        "name": "Moogle",
        "slot": 5,
        "job_id": 0x30,  # Fusilier
        "primary_set": 0x29,  # Gunmanship (Stopshot, Charmshot)
        "secondary_set": 0x2A,  # Acrobatics (Juggler: Smile Toss Quicken)
        "r_ability": 0x033E,  # Return Fire
        "p_ability": 0x0371,  # Elusion
        "weapon_id": 0x00D4,  # Peacemaker (8-Range Gun)
        "shield_id": 0x0000,  # None
        "helm_id": 0x013F,  # Thief's Cap (+2 Speed)
        "armor_id": 0x015F,  # Mirage Vest (+30 Def, +12 MRes)
        "accessory_id": 0x0180,  # Ninja Tabi (+2 Move)
    },
]

# Active squad builds: loaded from repo-root builds.toml, defaulting to the built-ins
META_SQUAD_BUILDS: list[dict[str, Any]] = load_builds() or DEFAULT_META_SQUAD_BUILDS

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


def apply_meta_squad(
    save: FFTA2Save,
    builds: list[dict[str, Any]] | None = None,
    inject_inventory: bool = True,
    inventory_count: int = 50,
    master_abilities: bool = True,
    unlock_jobs: bool = True,
    topup_stats: bool = True,
) -> None:
    """Apply verified meta squad builds to the first 6 clan members.

    Optionally injects 50x of ability-teaching weapons/armor into the clan inventory bag,
    unlocks all standard and hidden job classes in clan data, sets the full ability array
    (0x5A..0x11C) to master all skills safely without black-screening Unit Info,
    and non-destructively tops up stats to 115% god-roll maximums.
    """
    target_builds = builds if builds is not None else META_SQUAD_BUILDS

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
        from ffta2_tool.stats import topup_clan_stats

        topup_clan_stats(save, max_units=len(target_builds))

    if inject_inventory:
        save.inject_clan_equipment(META_INVENTORY_ITEMS, count=inventory_count)
        save.sync_equipped_to_inventory(default_count=inventory_count)
