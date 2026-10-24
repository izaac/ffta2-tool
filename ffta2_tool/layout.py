"""Canonical offset coordinates for FFTA2 save records.

Each slot lives in a 0x3408-byte record: an 8-byte header followed by a
0x3400-byte encrypted payload. Two coordinate systems are used across the
codebase, and mixing them silently reads or writes the wrong byte:

* buffer offsets -- absolute offsets into the staged record window that starts
  at 0x01B8 (``RECORD_STAGING_OFFSET``). ``FFTA2Save.plaintext`` is such a
  window, so every ``OFF_*`` constant in ``save.py`` uses these coordinates.
  The payload therefore starts at 0x01C0, not at 0.
* payload offsets -- offsets into a bare decrypted payload, where byte 0 is the
  first plaintext byte after the record header. ``slots.py`` works in these
  coordinates (``SlotManager.get_slot_payload`` returns exactly 0x3400 bytes).

The relation is fixed: ``buffer = payload + PAYLOAD_START``. Use the helpers
below instead of arithmetic with magic numbers, and prefer the paired
``BUFFER_OFF_*`` / ``PAYLOAD_OFF_*`` constants over literals.
"""

from __future__ import annotations

# -- staged record window ---------------------------------------------------------
RECORD_STAGING_OFFSET = 0x01B8  # first record position in a save image
RECORD_HEADER_SIZE = 0x08  # u32 checksum, u16 version, u16 seed
PAYLOAD_START = RECORD_STAGING_OFFSET + RECORD_HEADER_SIZE  # 0x01C0
PAYLOAD_SIZE = 0x3400
RECORD_SIZE = RECORD_HEADER_SIZE + PAYLOAD_SIZE  # 0x3408


def buffer_to_payload_offset(offset: int) -> int:
    """Convert a staged-window (buffer) offset to a bare-payload offset."""
    return offset - PAYLOAD_START


def payload_to_buffer_offset(offset: int) -> int:
    """Convert a bare-payload offset to a staged-window (buffer) offset."""
    return offset + PAYLOAD_START


# -- clan name / leader name (20-byte encoded name buffers) ------------------------
BUFFER_OFF_CLAN_NAME = 0x01D8
PAYLOAD_OFF_CLAN_NAME = 0x0018

BUFFER_OFF_LEADER_NAME = 0x01EC
PAYLOAD_OFF_LEADER_NAME = 0x002C

# -- party and clan tables ---------------------------------------------------------
BUFFER_OFF_UNIT_TABLE = 0x0238
PAYLOAD_OFF_UNIT_TABLE = 0x0078

BUFFER_OFF_INVENTORY = 0x1DFC
PAYLOAD_OFF_INVENTORY = 0x1C3C

BUFFER_OFF_GIL = 0x281C
PAYLOAD_OFF_GIL = 0x265C

BUFFER_OFF_CLAN_POINTS = 0x2820
PAYLOAD_OFF_CLAN_POINTS = 0x2660

BUFFER_OFF_CLAN_TALENTS = 0x2824
PAYLOAD_OFF_CLAN_TALENTS = 0x2664

BUFFER_OFF_CLAN_PRIVILEGES = 0x2937
PAYLOAD_OFF_CLAN_PRIVILEGES = 0x2777

BUFFER_OFF_DIFFICULTY = 0x2958
PAYLOAD_OFF_DIFFICULTY = 0x2798

# (field name, buffer offset, payload offset) for the paired constants above.
# Every entry must satisfy buffer - payload == PAYLOAD_START (see tests).
FIELD_OFFSET_PAIRS: tuple[tuple[str, int, int], ...] = (
    ("clan_name", BUFFER_OFF_CLAN_NAME, PAYLOAD_OFF_CLAN_NAME),
    ("leader_name", BUFFER_OFF_LEADER_NAME, PAYLOAD_OFF_LEADER_NAME),
    ("unit_table", BUFFER_OFF_UNIT_TABLE, PAYLOAD_OFF_UNIT_TABLE),
    ("inventory", BUFFER_OFF_INVENTORY, PAYLOAD_OFF_INVENTORY),
    ("gil", BUFFER_OFF_GIL, PAYLOAD_OFF_GIL),
    ("clan_points", BUFFER_OFF_CLAN_POINTS, PAYLOAD_OFF_CLAN_POINTS),
    ("clan_talents", BUFFER_OFF_CLAN_TALENTS, PAYLOAD_OFF_CLAN_TALENTS),
    ("clan_privileges", BUFFER_OFF_CLAN_PRIVILEGES, PAYLOAD_OFF_CLAN_PRIVILEGES),
    ("difficulty", BUFFER_OFF_DIFFICULTY, PAYLOAD_OFF_DIFFICULTY),
)

# -- difficulty --------------------------------------------------------------------
# One byte, stored raw on disk: 0 = Normal, 1 = Hard (ARM9 0x0210D7A8).
DIFFICULTY_RAW_NORMAL = 0
DIFFICULTY_RAW_HARD = 1

# The tool API keeps its historical convention: 1 = Hard, 2 = Normal.
DIFFICULTY_API_HARD = 1
DIFFICULTY_API_NORMAL = 2


def raw_to_api_difficulty(raw: int) -> int:
    """Translate the on-disk difficulty byte to the API value (1 = Hard, 2 = Normal).

    The game tests ``raw == 1`` for Hard, so any other stored value is Normal.
    """
    return DIFFICULTY_API_HARD if raw == DIFFICULTY_RAW_HARD else DIFFICULTY_API_NORMAL


def api_to_raw_difficulty(val: int) -> int:
    """Translate an API difficulty to the on-disk byte (1 = Hard, 0 = Normal).

    0 is accepted as an alias for Normal. Raises ValueError for anything else.
    """
    if isinstance(val, bool) or val not in (0, DIFFICULTY_API_HARD, DIFFICULTY_API_NORMAL):
        raise ValueError(
            f"difficulty must be 1 (Hard) or 2 (Normal); 0 is accepted as an alias for Normal (got {val!r})"
        )
    return DIFFICULTY_RAW_HARD if val == DIFFICULTY_API_HARD else DIFFICULTY_RAW_NORMAL
