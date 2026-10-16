"""Final Fantasy Tactics A2: Grimoire of the Rift (NDS) Data Mappings & Constants.

Contains canonical lookup dictionaries for races, jobs, equipment IDs,
ability specifications, and memory structures used by ffta2_tool.
Modeled after ffta_tool/mappings.py.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Races (1..7)
# ---------------------------------------------------------------------------
RACE_NAMES: dict[int, str] = {
    1: "Hume",
    2: "Bangaa",
    3: "Nu Mou",
    4: "Viera",
    5: "Moogle",
    6: "Gria",
    7: "Seeq",
}

# ---------------------------------------------------------------------------
# Jobs (Hex ID -> (Job Name, Race))
# ---------------------------------------------------------------------------
JOB_NAMES: dict[int, tuple[str, str]] = {
    # Hume (0x01..0x0D)
    0x01: ("Soldier", "Hume"),
    0x02: ("Paladin", "Hume"),
    0x03: ("Fighter", "Hume"),
    0x04: ("Thief", "Hume"),
    0x05: ("Archer", "Hume"),
    0x06: ("Ninja", "Hume"),
    0x07: ("White Mage", "Hume"),
    0x08: ("Parivir", "Hume"),
    0x09: ("Black Mage", "Hume"),
    0x0A: ("Illusionist", "Hume"),
    0x0B: ("Blue Mage", "Hume"),
    0x0C: ("Hunter", "Hume"),
    0x0D: ("Seer", "Hume"),
    # Bangaa (0x0E..0x17)
    0x0E: ("Warrior", "Bangaa"),
    0x0F: ("White Monk", "Bangaa"),
    0x10: ("Dragoon", "Bangaa"),
    0x11: ("Defender", "Bangaa"),
    0x12: ("Gladiator", "Bangaa"),
    0x13: ("Master Monk", "Bangaa"),
    0x14: ("Bishop", "Bangaa"),
    0x15: ("Templar", "Bangaa"),
    0x16: ("Cannoneer", "Bangaa"),
    0x17: ("Trickster", "Bangaa"),
    # Nu Mou (0x18..0x20)
    0x18: ("White Mage", "Nu Mou"),
    0x19: ("Black Mage", "Nu Mou"),
    0x1A: ("Beastmaster", "Nu Mou"),
    0x1B: ("Time Mage", "Nu Mou"),
    0x1C: ("Illusionist", "Nu Mou"),
    0x1D: ("Alchemist", "Nu Mou"),
    0x1E: ("Arcanist", "Nu Mou"),
    0x1F: ("Sage", "Nu Mou"),
    0x20: ("Scholar", "Nu Mou"),
    # Viera (0x22..0x2B)
    0x22: ("Fencer", "Viera"),
    0x23: ("White Mage", "Viera"),
    0x24: ("Green Mage", "Viera"),
    0x25: ("Archer", "Viera"),
    0x26: ("Elementalist", "Viera"),
    0x27: ("Red Mage", "Viera"),
    0x28: ("Spellblade", "Viera"),
    0x29: ("Summoner", "Viera"),
    0x2A: ("Assassin", "Viera"),
    0x2B: ("Sniper", "Viera"),
    # Moogle (0x2C..0x35)
    0x2C: ("Animist", "Moogle"),
    0x2D: ("Thief", "Moogle"),
    0x2E: ("Black Mage", "Moogle"),
    0x2F: ("Moogle Knight", "Moogle"),
    0x30: ("Fusilier", "Moogle"),
    0x31: ("Juggler", "Moogle"),
    0x32: ("Tinker", "Moogle"),
    0x33: ("Time Mage", "Moogle"),
    0x34: ("Chocobo Knight", "Moogle"),
    0x35: ("Flintlock", "Moogle"),
    # Gria (0x36..0x39)
    0x36: ("Hunter", "Gria"),
    0x37: ("Ravager", "Gria"),
    0x38: ("Geomancer", "Gria"),
    0x39: ("Raptor", "Gria"),
    # Seeq (0x3E..0x41)
    0x3E: ("Berserker", "Seeq"),
    0x3F: ("Ranger", "Seeq"),
    0x40: ("Lanista", "Seeq"),
    0x41: ("Viking", "Seeq"),
}

# ---------------------------------------------------------------------------
# Race to Job Range Mapping
# ---------------------------------------------------------------------------
RACE_JOBS: dict[int, range] = {
    1: range(0x01, 0x0E),  # Hume: 0x01..0x0D
    2: range(0x0E, 0x18),  # Bangaa: 0x0E..0x17
    3: range(0x18, 0x21),  # Nu Mou: 0x18..0x20
    4: range(0x22, 0x2C),  # Viera: 0x22..0x2B
    5: range(0x2C, 0x36),  # Moogle: 0x2C..0x35
    6: range(0x36, 0x3A),  # Gria: 0x36..0x39
    7: range(0x3E, 0x42),  # Seeq: 0x3E..0x41
}

# ---------------------------------------------------------------------------
# Primary Action Ability (A-Ability) Set ID per Job
# ---------------------------------------------------------------------------
JOB_PRIMARY_A_SETS: dict[int, int] = {
    0x01: 0x01,  # Soldier -> First Aid / Battle Tech
    0x02: 0x06,  # Paladin -> Chivalry
    0x03: 0x03,  # Fighter -> Rush Tech
    0x04: 0x02,  # Thief -> Thievery
    0x05: 0x05,  # Archer -> Bowmanship
    0x06: 0x07,  # Ninja -> Ninjutsu
    0x07: 0x03,  # White Mage -> White Magick
    0x08: 0x08,  # Parivir -> Flair
    0x09: 0x04,  # Black Mage -> Black Magick
    0x0A: 0x0A,  # Illusionist -> Phantasm
    0x0B: 0x0B,  # Blue Mage -> Blue Magick
    0x0C: 0x0C,  # Hunter -> Hunting / Trapping
    0x0D: 0x0D,  # Seer -> High Magick
    0x0E: 0x0E,  # Warrior -> War Dance
    0x0F: 0x0F,  # White Monk -> Martial Arts
    0x10: 0x10,  # Dragoon -> Dragon Tech
    0x11: 0x11,  # Defender -> Warding
    0x12: 0x12,  # Gladiator -> Battle Cry
    0x13: 0x13,  # Master Monk -> Unarmed Tech
    0x14: 0x14,  # Bishop -> Blessing
    0x15: 0x15,  # Templar -> Sacred Tech
    0x16: 0x16,  # Cannoneer -> Cannonry
    0x17: 0x17,  # Trickster -> Sleight
    0x18: 0x03,  # Nu Mou White Mage -> White Magick
    0x19: 0x04,  # Nu Mou Black Mage -> Black Magick
    0x1A: 0x18,  # Beastmaster -> Control
    0x1B: 0x19,  # Time Mage -> Time Magick
    0x1C: 0x0A,  # Illusionist -> Phantasm
    0x1D: 0x1A,  # Alchemist -> Alchemy
    0x1E: 0x1B,  # Arcanist -> Nether Magick
    0x1F: 0x1C,  # Sage -> Sagacity
    0x20: 0x1D,  # Scholar -> Tome Magick
    0x22: 0x20,  # Fencer -> Lunge Tech
    0x23: 0x03,  # Viera White Mage -> White Magick
    0x24: 0x21,  # Green Mage -> Green Magick
    0x25: 0x05,  # Viera Archer -> Bowmanship
    0x26: 0x23,  # Elementalist -> Spirit Magick
    0x27: 0x22,  # Red Mage -> Red Magick
    0x28: 0x25,  # Spellblade -> Swordcraft
    0x29: 0x24,  # Summoner -> Summoning
    0x2A: 0x26,  # Assassin -> Corner
    0x2B: 0x27,  # Sniper -> Marksman
    0x2C: 0x28,  # Animist -> Call
    0x2D: 0x02,  # Moogle Thief -> Thievery
    0x2E: 0x04,  # Moogle Black Mage -> Black Magick
    0x2F: 0x2B,  # Moogle Knight -> Charge
    0x30: 0x29,  # Fusilier -> Gunmanship
    0x31: 0x2A,  # Juggler -> Acrobatics
    0x32: 0x2C,  # Tinker -> Gadget
    0x33: 0x19,  # Moogle Time Mage -> Time Magick
    0x34: 0x2D,  # Chocobo Knight -> Knight Tech
    0x35: 0x2E,  # Flintlock -> Hand Cannon Tech
    0x36: 0x0C,  # Gria Hunter -> Hunting
    0x37: 0x30,  # Ravager -> Scourge
    0x38: 0x31,  # Geomancer -> Gaia
    0x39: 0x32,  # Raptor -> Aerial Tech
    0x3E: 0x33,  # Berserker -> Rage
    0x3F: 0x34,  # Ranger -> Survival
    0x40: 0x35,  # Lanista -> Arena Tech
    0x41: 0x36,  # Viking -> Pillaging
}

# ---------------------------------------------------------------------------
# Shield & Armor Legality
# ---------------------------------------------------------------------------
SHIELD_CAPABLE_JOBS: set[int] = {
    0x01,
    0x02,
    0x03,
    0x0B,  # Hume: Soldier, Paladin, Fighter, Blue Mage
    0x0E,
    0x10,
    0x11,
    0x12,
    0x15,  # Bangaa: Warrior, Dragoon, Defender, Gladiator, Templar
    0x1F,  # Nu Mou: Sage
    0x22,
    0x28,  # Viera: Fencer, Spellblade
    0x2F,  # Moogle: Moogle Knight
    0x39,
    0x40,
    0x41,  # Raptor, Lanista, Viking
}

HEAVY_ARMOR_JOBS: set[int] = {
    0x01,
    0x02,
    0x03,  # Soldier, Paladin, Fighter
    0x0E,
    0x10,
    0x11,
    0x12,
    0x15,  # Warrior, Dragoon, Defender, Gladiator, Templar
    0x2F,  # Moogle Knight
    0x37,
    0x40,
    0x41,  # Ravager, Lanista, Viking
}

# ---------------------------------------------------------------------------
# Reaction & Support Abilities (ROM 16-bit IDs)
# ---------------------------------------------------------------------------
REACTION_ABILITIES: dict[int, str] = {
    0x0336: "Critical: Quicken",
    0x0337: "Critical: Haste",
    0x0338: "Critical: Berserk",
    0x0339: "Sticky Fingers",
    0x033A: "Reflex",
    0x033B: "Archer's Bane",
    0x033C: "Strike Back",
    0x033D: "Counter",
    0x033E: "Return Fire",
    0x033F: "Bonecrusher",
    0x0340: "Magick Counter",
    0x0341: "Dragonheart",
    0x0342: "MP Shield",
    0x0343: "Regenerate",
    0x0344: "Absorb MP",
    0x0345: "Blur",
    0x0346: "Absorb Damage",
    0x0347: "Evade Magick",
    0x0348: "Critical: Evasion↑",
    0x0349: "Blink Counter",
    0x034A: "Gil Snapper",
    0x034B: "Critical: Vanish",
    0x034C: "Replenish MP",
}

SUPPORT_ABILITIES: dict[int, str] = {
    0x0353: "Attack↑",
    0x0354: "Defense↑",
    0x0355: "Magick↑",
    0x0356: "Resistance↑",
    0x0357: "Turbo MP",
    0x0358: "Geomancy",
    0x0359: "Pierce",
    0x035A: "Monkey Grip",
    0x035B: "Doublehand",
    0x035C: "Dual Wield",
    0x035D: "Safeguard",
    0x035E: "Halve MP",
    0x035F: "Immunity",
    0x0360: "Learn",
    0x0361: "Concentration",
    0x0362: "Reveal",
    0x0363: "Shieldbearer",
    0x0364: "Death Strike",
    0x0365: "Unscarred",
    0x0366: "Item Lore",
    0x0367: "Spellbound",
    0x0368: "Charged Attacks",
    0x0369: "Avoid Traps",
    0x036A: "Blood Price",
    0x036B: "Smasher",
    0x036C: "Vigilance",
    0x036D: "Pugilist",
    0x036E: "Archmage",
    0x036F: "Destroyer",
    0x0370: "Lifespring",
    0x0371: "Elusion",
    0x0372: "Impervious",
    0x0373: "Ribbon-bearer",
    0x0374: "Tank",
}

# ---------------------------------------------------------------------------
# Canonical Equipment & Item Lookup Table (NDS ROM IDs 0x0001..0x019A)
# ---------------------------------------------------------------------------
KNOWN_ITEMS: dict[int, str] = {
    # Daggers & Knives (0x0001..)
    0x0001: "Dagger",
    0x0002: "Jack Knife",
    0x0003: "Kris Knife",
    0x0004: "Khukuri",
    0x0005: "Kard",
    0x0006: "Scramasax",
    0x0007: "Rondell Dagger",
    0x0008: "Jambiya",
    0x0009: "Zorlin Shape",
    0x000A: "Swordbreaker",
    0x000B: "Orichalcum",
    0x000C: "Cinquedea",
    0x000D: "Mythril Knife",
    0x000E: "Tonberrian",
    # Swords & Greatswords
    0x000F: "Buster Sword",
    0x0010: "Silver Sword",
    0x0011: "Burglar Sword",
    0x0012: "Gale Sword",
    0x0013: "Blood Sword",
    0x0014: "Restorer",
    0x0015: "Vitanova",
    0x0016: "Mythril Sword",
    0x0017: "Victor Sword",
    0x0018: "Chirijiraden",
    0x0019: "Shortsword",
    0x001A: "Laglace Sword",
    0x001B: "Sweep Blade",
    0x001C: "Shadow Blade",
    0x001D: "Sun Blade",
    0x001E: "Atmos Blade",
    0x001F: "Flametongue",
    0x0020: "Air Blade",
    0x0021: "Icebrand",
    0x0022: "Kwigon Blade",
    0x0023: "Ogun Blade",
    0x0024: "Pearl Blade",
    0x0025: "Paraiba Blade",
    0x0026: "Venus Blade",
    0x0027: "Materia Blade",
    0x0028: "Mythril Blade",
    0x0029: "Ebon Blade",
    0x002A: "Adaman Blade",
    0x002B: "Ayvuir Red",
    0x002C: "Ayvuir Blue",
    # Knightswords
    0x002D: "Defender",
    0x002E: "Apocalypse",
    0x002F: "Lionheart",
    0x0030: "Ragnarok",
    0x0031: "Lohengrin",
    0x0032: "Save the Queen",
    0x0033: "Arch Sword",
    0x0034: "Excalibur",
    0x0035: "Mythril Brand",
    0x0036: "Excalibur II",
    0x0037: "Nagrarok",
    0x0038: "Sequence",
    # Rapiers (0x0045..0x0055)
    0x0045: "Stinger",
    0x0046: "Estoc",
    0x0047: "Fleuret",
    0x0048: "Scarlette",
    0x0049: "Flamberge",
    0x004A: "Silver Rapier",
    0x004B: "Djinn Flyssa",
    0x004C: "Joyeuse",
    0x004D: "Mage Masher",
    0x004E: "Colichemarde",
    0x004F: "Gupti Aga",
    0x0050: "Femme Fatale",
    0x0051: "Madu",
    0x0052: "Epeprism",
    0x0053: "Mythril Rapier",
    0x0054: "Last Letter",
    0x0055: "Diabolique",
    # Katanas (0x0065..0x0078)
    0x0065: "Ninja Knife",
    0x0066: "Murasame",
    0x0067: "Ashura",
    0x0068: "Osafune",
    0x0069: "Petalchaser",
    0x006A: "Kotetsu",
    0x006B: "Kiku-ichimonji",
    0x006C: "Heaven's Cloud",
    0x006D: "Nosada",
    0x006E: "Masamune",
    0x006F: "Zanmato",
    0x0070: "Mythril Epee",
    0x0071: "Masamune 100",
    0x0072: "Charfire",
    0x0073: "Silkmoon",
    0x0074: "Hyakushiki-masamune",
    # Rods & Staves (0x0080..0x009F)
    0x0080: "Rod",
    0x0081: "Firewheel Rod",
    0x0082: "Thunder Rod",
    0x0083: "Sleet Rod",
    0x0084: "Terre Rod",
    0x0085: "Force Rod",
    0x0086: "Flame Rod",
    0x0087: "Thor Rod",
    0x0088: "Chill Rod",
    0x0089: "Stardust Rod",
    0x008A: "Princess Rod",
    0x008B: "Mythril Rod",
    0x008C: "Heretic Rod",
    0x008D: "Sapere Aude",
    0x008E: "Staff",
    0x008F: "White Staff",
    0x0090: "Guard Staff",
    0x0091: "Judge Staff",
    0x0092: "Cure Staff",
    0x0093: "Pure Staff",
    0x0094: "Bless Staff",
    0x0095: "Snake Staff",
    0x0096: "Spring Staff",
    0x0097: "Garnet Staff",
    0x0098: "Cheer Staff",
    0x0099: "Nirvana Staff",
    0x009A: "Mythril Staff",
    0x009B: "Power Staff",
    0x009C: "Dream Watcher",
    # Bows & Greatbows (0x00B0..0x00D0)
    0x00B0: "Target Bow",
    0x00B1: "Perseus Bow",
    0x00B2: "Mythril Bow",
    0x00B3: "Crescent Bow",
    0x00B4: "Silver Bow",
    0x00B5: "Malbow",
    0x00B6: "Windslash Bow",
    0x00B7: "Ranger Bow",
    0x00B8: "Cranequin",
    0x00B9: "Twin Bow",
    0x00BA: "Hunt Bow",
    0x00BB: "Fey Bow",
    0x00BC: "Hades Bow",
    0x00BD: "Bow",
    0x00BE: "Nike Bow",
    0x00BF: "Master Bow",
    0x00C0: "Max's Oathbow",
    0x00CA: "Seventh Heaven",
    # Guns (0x00D1..0x00DF)
    0x00D1: "Aiot Gun",
    0x00D2: "Silver Cannon",
    0x00D3: "Riot Gun",
    0x00D4: "Peacemaker",
    0x00D5: "Lost Gun",
    0x00D6: "Chaos Rifle",
    0x00D7: "Longbarrel",
    0x00D8: "Outsider",
    0x00D9: "Mythril Gun",
    # Hand Cannons (0x00E8..0x00F8)
    0x00EA: "Iron Cannon",
    0x00EB: "Hand Cannon",
    0x00EC: "Super Cannon",
    0x00ED: "Heavy Cannon",
    0x00EE: "Titan Cannon",
    0x00F0: "Rocket Punch",
    # Maces (0x0100..0x0115)
    0x0100: "Battle Mace",
    0x0101: "Energy Mace",
    0x0102: "Druid Mace",
    0x0103: "Sage Crosier",
    0x0104: "Morning Star",
    0x0105: "Mandragora",
    0x0106: "Life Crosier",
    0x0107: "Lotus Mace",
    0x0108: "Scorpion Tail",
    0x010F: "Zeus Mace",
    0x0110: "Mythril Mace",
    0x0111: "Cactus Stick",
    0x0112: "Vesper",
    # Shields (0x0120..0x0130)
    0x0120: "Buckler",
    0x0121: "Bronze Shield",
    0x0122: "Round Shield",
    0x0123: "Platinum Shield",
    0x0124: "Ice Shield",
    0x0125: "Flame Shield",
    0x0126: "Aegis Shield",
    0x0127: "Genji Shield",
    0x0128: "Sacristan Shield",
    0x0129: "Chocobo Shield",
    # Headgear / Helms / Hats (0x0135..0x0145)
    0x0135: "Circlet",
    0x0136: "Green Beret",
    0x0137: "Headband",
    0x0138: "Ribbon",
    0x0139: "Plumed Hat",
    0x013A: "Green Beret (Speed)",
    0x013B: "Feathered Cap",
    0x013C: "Haste Hat",
    0x013D: "Black Hat",
    0x013E: "Gold Hairpin",
    0x013F: "Thief's Cap",
    0x0140: "Barbut",
    0x0141: "Iron Helm",
    0x0142: "Platinum Helm",
    0x0143: "Cross Helm",
    0x0144: "Cuirass",
    0x0145: "Genji Helm",
    # Armor / Robes / Clothing (0x0150..0x0175)
    0x0150: "Leather Armor",
    0x0151: "Chainmail",
    0x0152: "Bronze Armor",
    0x0153: "Leather Clothing",
    0x0154: "Hard Leather",
    0x0155: "Judo Uniform",
    0x0156: "Survival Vest",
    0x0157: "Brigandine",
    0x0158: "Power Vest",
    0x0159: "Gaia Gear",
    0x015A: "Ninja Vest",
    0x015B: "Minerva Bustier",
    0x015C: "Ninja Gear",
    0x015D: "Dark Gear",
    0x015E: "Wygar",
    0x015F: "Mirage Vest",
    0x0160: "Dragon Mail",
    0x0161: "Genji Armor",
    0x0162: "Maximillian",
    0x0163: "Adaman Armor",
    0x0164: "Materia Armor",
    0x0165: "Peytral",
    0x0167: "Hempen Robe",
    0x0168: "Silken Robe",
    0x0169: "Magus Robe",
    0x016A: "Mistle Robe",
    0x016B: "Geomancer Robe",
    0x016C: "White Robe",
    0x016D: "Black Robe",
    0x016E: "Silver Coat",
    0x016F: "Sage Robe",
    0x0170: "Magic Robe",
    0x0171: "Lordly Robe",
    # Footwear & Accessories (0x0175..0x019A)
    0x0175: "Battle Boots",
    0x0176: "Spiked Boots",
    0x0177: "Dash Boots",
    0x0178: "Red Boots",
    0x0179: "Sprint Shoes",
    0x017A: "Germinas Boots",
    0x017B: "Winged Boots",
    0x017C: "Galmia Shoes",
    0x017D: "Caligula",
    0x017E: "Faerie Shoes",
    0x017F: "Rubber Suits",
    0x0180: "Ninja Tabi",
    0x0181: "Gauntlets (Basic)",
    0x0182: "Thief Armlets",
    0x0183: "Bracers",
    0x0184: "Genji Gloves",
    0x0185: "Gauntlets",
    0x0186: "Bone Armlets",
    0x0187: "Fortune Ring",
    0x0188: "Magic Ring",
    0x0189: "Angel Ring",
    0x018A: "Scarab Charm",
    0x018B: "Ruby Earring",
    0x018C: "Star Armlet",
    0x018D: "Mind Cuffs",
}

MAX_VALID_EQUIP_ID: int = 0x019A
MAX_VALID_ABILITY_ID: int = 482


# ---------------------------------------------------------------------------
# Helper Lookup Functions
# ---------------------------------------------------------------------------
def get_job_name(job_id: int) -> str:
    """Returns canonical job name for a given job ID."""
    entry = JOB_NAMES.get(job_id)
    return entry[0] if entry else f"Unknown_Job_0x{job_id:02X}"


def get_job_race(job_id: int) -> str:
    """Returns the associated race name for a given job ID."""
    entry = JOB_NAMES.get(job_id)
    return entry[1] if entry else "Unknown"


def get_race_name(race_id: int) -> str:
    """Returns canonical race name for a given race ID."""
    return RACE_NAMES.get(race_id, f"Unknown_Race_0x{race_id:02X}")


def get_item_name(item_id: int) -> str:
    """Returns canonical equipment or item name for a given item ID."""
    if item_id == 0:
        return "None"
    return KNOWN_ITEMS.get(item_id, f"Item_0x{item_id:04X}")


def get_item_id(item_name: str) -> int | None:
    """Finds first matching item ID for a given name string (case-insensitive)."""
    clean = item_name.strip().lower()
    for item_id, name in KNOWN_ITEMS.items():
        if name.lower() == clean:
            return item_id
    return None


def is_valid_item_id(item_id: int) -> bool:
    """Checks whether an item ID is within valid ROM equipment boundaries."""
    return 0 <= item_id <= MAX_VALID_EQUIP_ID


def is_shield_capable(job_id: int) -> bool:
    """Checks whether a job can legally equip a shield."""
    return job_id in SHIELD_CAPABLE_JOBS


def is_heavy_armor_capable(job_id: int) -> bool:
    """Checks whether a job can legally equip heavy armor/helmets."""
    return job_id in HEAVY_ARMOR_JOBS


__all__ = [
    "HEAVY_ARMOR_JOBS",
    "JOB_NAMES",
    "JOB_PRIMARY_A_SETS",
    "KNOWN_ITEMS",
    "MAX_VALID_ABILITY_ID",
    "MAX_VALID_EQUIP_ID",
    "RACE_JOBS",
    "RACE_NAMES",
    "REACTION_ABILITIES",
    "SHIELD_CAPABLE_JOBS",
    "SUPPORT_ABILITIES",
    "get_item_id",
    "get_item_name",
    "get_job_name",
    "get_job_race",
    "get_race_name",
    "is_heavy_armor_capable",
    "is_shield_capable",
    "is_valid_item_id",
]
