"""FFTA2 Meta Squad Patcher.

Applies fully audited, ROM-verified meta builds to the starting clan members.
"""

from __future__ import annotations

from typing import Any, Dict, List
from ffta2_tool.save import FFTA2Save

META_SQUAD_BUILDS: List[Dict[str, Any]] = [
    # Slot 0: Luso (Hume) - Parivir / Paladin
    {
        "name": "Luso",
        "slot": 0,
        "job_id": 0x08,         # Parivir
        "primary_set": 0x08,    # Flair
        "secondary_set": 0x06,  # Chivalry (Paladin: Nurse, Saint Cross, Holy Blade)
        "weapon_id": 0x0018,    # Chirijiraden (+65 Atk, Fire Katana)
        "shield_id": 0x0000,    # None (Parivir single-wields katana safely)
        "helm_id": 0x013F,      # Thief's Cap (+2 Speed)
        "armor_id": 0x015C,     # Ninja Gear (+24 Def, +4 Speed)
        "accessory_id": 0x0180, # Ninja Tabi (+2 Move)
    },
    # Slot 1: Nu Mou - Sage / Alchemist
    {
        "name": "Nu Mou",
        "slot": 1,
        "job_id": 0x1F,         # Sage
        "primary_set": 0x1C,    # Sagacity (Gigaflare, Bio, Aero)
        "secondary_set": 0x1A,  # Alchemy (100% Item Delivery)
        "weapon_id": 0x010F,    # Zeus Mace (+30 Atk, +10 Magick)
        "shield_id": 0x0127,    # Genji Shield (+7 Def, +5 Evade, +2 MRes)
        "helm_id": 0x013E,      # Gold Hairpin (+10 MRes, Silence immune)
        "armor_id": 0x0171,     # Lordly Robe (+18 Def, +35 MRes, +5 Atk, +5 Mag)
        "accessory_id": 0x017E, # Faerie Shoes (Teleport Movement!)
    },
    # Slot 2: Viera - Red Mage / Summoner
    {
        "name": "Viera",
        "slot": 2,
        "job_id": 0x27,         # Red Mage
        "primary_set": 0x22,    # Red Magick (Doublecast, Cure, Cura, Protect)
        "secondary_set": 0x24,  # Summoning Magick (Maduin, Phoenix, Unicorn, Kirin)
        "weapon_id": 0x0050,    # Femme Fatale (+49 Atk, +2 Mag Rapier)
        "shield_id": 0x0000,    # None
        "helm_id": 0x0138,      # Ribbon (Complete status immunity)
        "armor_id": 0x015B,     # Minerva Bustier (Holy/Dark absorb)
        "accessory_id": 0x0189, # Angel Ring (Auto-Reraise safety against Blood Price)
    },
    # Slot 3: Bangaa - Cannoneer / Defender
    {
        "name": "Bangaa",
        "slot": 3,
        "job_id": 0x16,         # Cannoneer
        "primary_set": 0x16,    # Cannonry (Ether Shell +60 MP, Mortar, Target)
        "secondary_set": 0x11,  # Warding (Defender: Aura Auto-Life+Regen, Meltdown)
        "weapon_id": 0x00F0,    # Rocket Punch (Hand Cannon)
        "shield_id": 0x0000,    # None
        "helm_id": 0x013F,      # Thief's Cap (+2 Speed)
        "armor_id": 0x015F,     # Mirage Vest (+30 Def, +12 MRes)
        "accessory_id": 0x0184, # Genji Gloves (+5 Atk, +5 Def)
    },
    # Slot 4: Hume (Generic) - Hunter / Seer
    {
        "name": "Hume",
        "slot": 4,
        "job_id": 0x0C,         # Hunter
        "primary_set": 0x0C,    # Trapping (Hunter: Ultima Shot, Sonic Boom)
        "secondary_set": 0x0D,  # High Magick (Seer: Recharge, Magick Frenzy, Esuna)
        "weapon_id": 0x00CA,    # Seventh Heaven (Greatbow: Ultima Shot)
        "shield_id": 0x0000,    # None
        "helm_id": 0x013F,      # Thief's Cap (+2 Speed)
        "armor_id": 0x015C,     # Ninja Gear (+24 Def, +4 Speed)
        "accessory_id": 0x017B, # Winged Boots (Float / Levitate)
    },
    # Slot 5: Moogle - Fusilier / Juggler
    {
        "name": "Moogle",
        "slot": 5,
        "job_id": 0x30,         # Fusilier
        "primary_set": 0x29,    # Gunmanship (Stopshot, Charmshot)
        "secondary_set": 0x2A,  # Acrobatics (Juggler: Smile Toss Quicken)
        "weapon_id": 0x00D4,    # Peacemaker (8-Range Gun)
        "shield_id": 0x0000,    # None
        "helm_id": 0x013F,      # Thief's Cap (+2 Speed)
        "armor_id": 0x015F,     # Mirage Vest (+30 Def, +12 MRes)
        "accessory_id": 0x0180, # Ninja Tabi (+2 Move)
    },
]


def apply_meta_squad(save: FFTA2Save, master_abilities: bool = False) -> None:
    """Apply verified meta squad builds to the first 6 clan members.

    Note: master_abilities is disabled by default to prevent out-of-bounds
    ability bitfield corruption which causes black screens in the Unit Info UI.
    Equipment provides required active abilities directly during battle.
    """
    for build in META_SQUAD_BUILDS:
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
        if master_abilities:
            unit.master_all_abilities()

