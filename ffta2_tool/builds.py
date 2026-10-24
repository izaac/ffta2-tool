"""Builds database: loads builds.toml and resolves build keys/names to entries.

Pure domain/config layer. It must not import ``ffta2_tool.patcher`` or
``ffta2_tool.save``: the save layer resolves builds from here, which is what
keeps ``save`` and ``patcher`` free of a circular import.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from ffta2_tool.mappings import get_job_name
from ffta2_tool.toml_lite import read_toml

_PACKAGE_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_ROOT.parent

# Fields every meta squad build entry must provide to the patcher
REQUIRED_BUILD_KEYS = (
    "name",
    "slot",
    "job_id",
    "primary_set",
    "secondary_set",
    "weapon_id",
    "shield_id",
    "helm_id",
    "armor_id",
    "accessory_id",
)

# Built-in fallback used when builds.toml is missing or unreadable
DEFAULT_META_SQUAD_BUILDS: list[dict[str, Any]] = [
    # Slot 0: Luso (Hume) - Parivir / Paladin
    {
        "key": "luso",
        "name": "Luso",
        "slot": 0,
        "job_id": 0x08,  # Parivir
        "primary_set": 0x08,  # Flair
        "secondary_set": 0x06,  # Chivalry (Paladin: Nurse, Saint Cross, Holy Blade)
        "r_ability": 0x033C,  # Strike Back (Hume Parivir)
        "p_ability": 0x035C,  # Dual Wield (Hume Ninja only)
        "weapon_id": 0x0074,  # Hyakushiki-masamune (+78 Atk, Katana)
        "shield_id": 0x0000,  # None (Parivir safely single-wields; off-hand weapon black-screened Unit Info)
        "helm_id": 0x013F,  # Thief's Cap (+2 Speed)
        "armor_id": 0x015C,  # Ninja Gear (+24 Def, +4 Speed)
        "accessory_id": 0x0180,  # Ninja Tabi (+2 Move)
    },
    # Slot 1: Nu Mou - Sage / Alchemist
    {
        "key": "nu_mou",
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
        "key": "viera",
        "name": "Viera",
        "slot": 2,
        "job_id": 0x27,  # Red Mage
        "primary_set": 0x22,  # Red Magick (Doublecast, Cure, Cura, Protect)
        "secondary_set": 0x24,  # Summoning Magick (Maduin, Phoenix, Unicorn, Kirin)
        "r_ability": 0x033A,  # Reflex (Viera Fencer)
        "p_ability": 0x036A,  # Blood Price (Viera Spellblade)
        "weapon_id": 0x0050,  # Femme Fatale (+49 Atk, +2 Mag Rapier)
        "shield_id": 0x0000,  # None
        "helm_id": 0x0138,  # Ribbon (Complete status immunity)
        "armor_id": 0x015B,  # Minerva Bustier (Holy/Dark absorb)
        "accessory_id": 0x0189,  # Angel Ring (Auto-Reraise safety against Blood Price)
    },
    # Slot 3: Bangaa - Cannoneer / Defender
    {
        "key": "bangaa",
        "name": "Bangaa",
        "slot": 3,
        "job_id": 0x16,  # Cannoneer
        "primary_set": 0x16,  # Cannonry (Ether Shell +60 MP, Mortar, Target)
        "secondary_set": 0x11,  # Warding (Defender: Aura Auto-Life+Regen, Meltdown)
        "r_ability": 0x033C,  # Strike Back (Bangaa Gladiator)
        "p_ability": 0x0353,  # Attack Up (Bangaa Templar)
        "weapon_id": 0x00F0,  # Rocket Punch (Hand Cannon)
        "shield_id": 0x0000,  # None
        "helm_id": 0x013F,  # Thief's Cap (+2 Speed)
        "armor_id": 0x015F,  # Mirage Vest (+30 Def, +12 MRes)
        "accessory_id": 0x0184,  # Genji Gloves (+5 Atk, +5 Def)
    },
    # Slot 4: Hume (Generic) - Hunter / Seer
    {
        "key": "hume",
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
        "key": "moogle",
        "name": "Moogle",
        "slot": 5,
        "job_id": 0x30,  # Fusilier
        "primary_set": 0x29,  # Gunmanship (Stopshot, Charmshot)
        "secondary_set": 0x2A,  # Acrobatics (Juggler: Smile Toss Quicken)
        "r_ability": 0x033E,  # Return Fire (Moogle Juggler)
        "p_ability": 0x0361,  # Concentration (Moogle Fusilier)
        "weapon_id": 0x00D4,  # Peacemaker (8-Range Gun)
        "shield_id": 0x0000,  # None
        "helm_id": 0x013F,  # Thief's Cap (+2 Speed)
        "armor_id": 0x015F,  # Mirage Vest (+30 Def, +12 MRes)
        "accessory_id": 0x0180,  # Ninja Tabi (+2 Move)
    },
]


def _resolve_builds_file(builds_path: str | Path | None = None) -> Path | None:
    """Resolves the builds database file.

    Search priority:
    1. Explicit builds_path argument
    2. Repository-root builds.toml
    3. ./builds.toml (current working directory)
    4. Bundled ffta2_tool/data/builds.toml (installed wheels)
    """
    if builds_path:
        target = Path(os.path.expanduser(str(builds_path)))
        return target if target.is_file() else None
    repo_root = _REPO_ROOT / "builds.toml"
    if repo_root.is_file():
        return repo_root
    local = Path("builds.toml")
    if local.is_file():
        return local
    pkg_data = _PACKAGE_ROOT / "data" / "builds.toml"
    return pkg_data if pkg_data.is_file() else None


def load_builds_by_key(builds_path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Loads builds from builds.toml keyed by their TOML table key (e.g. 'luso', 'nu_mou')."""
    target = _resolve_builds_file(builds_path)
    if target is None:
        return {}
    try:
        raw_data = read_toml(target)
        raw_builds = raw_data.get("builds", {})
    except OSError:
        return {}

    keyed: dict[str, dict[str, Any]] = {}
    if isinstance(raw_builds, dict):
        for k, entry in raw_builds.items():
            if isinstance(entry, dict) and all(req in entry for req in REQUIRED_BUILD_KEYS):
                entry_copy = dict(entry)
                entry_copy.setdefault("key", str(k).lower())
                keyed[str(k).lower()] = entry_copy
    elif isinstance(raw_builds, list):
        for entry in raw_builds:
            if isinstance(entry, dict) and all(req in entry for req in REQUIRED_BUILD_KEYS):
                k = str(entry["name"]).lower().replace(" ", "_")
                entry_copy = dict(entry)
                entry_copy.setdefault("key", k)
                keyed[k] = entry_copy
    return keyed


def load_builds(builds_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Loads the meta squad builds database from builds.toml.

    Search priority:
    1. Explicit builds_path argument
    2. Repository-root builds.toml
    3. ./builds.toml (working directory)
    4. Bundled ffta2_tool/data/builds.toml from an installed wheel

    Returns a list of build dicts sorted by slot. Invalid or missing entries are
    skipped; an empty list is returned when no usable builds file is found.
    """
    keyed = load_builds_by_key(builds_path)
    builds = list(keyed.values())
    builds.sort(key=lambda b: int(b["slot"]))
    return builds


def resolve_build(key_or_name: str, builds_path: str | Path | None = None) -> dict[str, Any] | None:
    """Resolve a build dictionary from builds.toml by TOML key, build name, or primary job name."""
    keyed = load_builds_by_key(builds_path)
    if not keyed:
        keyed = {str(b.get("key", b["name"])).lower().replace(" ", "_"): b for b in DEFAULT_META_SQUAD_BUILDS}

    norm = key_or_name.strip().lower().replace("-", "_")
    if norm in keyed:
        return keyed[norm]

    norm_space = norm.replace("_", " ")
    for b in keyed.values():
        if str(b.get("name", "")).lower() == norm_space:
            return b
        if str(b.get("job", "")).lower() == norm_space:
            return b
        if get_job_name(int(b["job_id"])).lower() == norm_space:
            return b
    return None


@lru_cache(maxsize=1)
def get_meta_squad_builds() -> list[dict[str, Any]]:
    """Returns the active squad builds: builds.toml when readable, else the built-in defaults.

    Resolved lazily (never at import time) so importing a module that uses builds
    does not touch the filesystem. Cached so it acts as a stable module singleton.
    """
    return load_builds() or DEFAULT_META_SQUAD_BUILDS
