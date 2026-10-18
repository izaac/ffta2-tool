"""FFTA2 Custom Charset Decoder and Encoder.

Verified against retail US ROM:
- JD_message_0.pak subfile 19 (Roman keyboard tab: A-Z 0x02..0x1B, a-z 0x1C..0x35, space 0x01)
- JD_message_0.pak subfile 21 (Digits/Symbols keyboard tab: 0-9 0x67..0x70 and punctuation)
- OVL_12 0x02135FE8 (Leader Name) & 0x02135FFC (Clan Name): mov r0, #0x9; strb r0, [r6, #0x86]
  (9-character cap + 0x00 terminator = 10 bytes)
- ARM9 0x0210D800..0x0210D814 (populate_preview_entry): copies 0x0A (10) bytes (0..9) from
  payload+0x2C (0x01EC leader_name) to preview_entry+0x10..0x19.
"""

from __future__ import annotations

# Real in-game Name Entry character cap (OVL_12 0x02135FE8 / 0x02135FFC & ARM9 0x0210D810)
MAX_CUSTOM_NAME_CHARS = 9
CUSTOM_NAME_BUFFER_LEN = 20

CHAR_DECODE_MAP: dict[int, str] = {
    0x00: "\n",
    0x01: " ",
}

# A-Z: 0x02 - 0x1B
for i in range(26):
    CHAR_DECODE_MAP[0x02 + i] = chr(ord("A") + i)

# a-z: 0x1C - 0x35
for i in range(26):
    CHAR_DECODE_MAP[0x1C + i] = chr(ord("a") + i)

# Digits 0-9: 0x67 - 0x70 in ROM message tables (and 0x8E - 0x97 legacy fallback)
for i in range(10):
    CHAR_DECODE_MAP[0x8E + i] = str(i)
    CHAR_DECODE_MAP[0x67 + i] = str(i)

# Additional symbols (verified against JD_message_0.pak subfile 21 and ROM strings)
CHAR_DECODE_MAP.update(
    {
        0x73: "!",
        0x74: "?",
        0x76: "%",
        0x78: "!",
        0x79: "?",
        0x7A: ":",
        0x7B: "/",
        0x7C: ".",
        0x7D: ",",
        0x7E: ",",
        0x7F: ".",
        0x80: ";",
        0x81: ":",
        0x83: "'",
        0x84: '"',
        0x85: "'",
        0x86: "(",
        0x87: ")",
        0x8D: "-",
        0x93: "+",
        0x96: "&",
        0x9B: "↑",
        0x9C: "↓",
    }
)

# Canonical 1-to-1 keyboard encoding table (JD_message_0.pak subfiles 19 & 21)
CHAR_ENCODE_MAP: dict[str, int] = {
    " ": 0x01,
}
for i in range(26):
    CHAR_ENCODE_MAP[chr(ord("A") + i)] = 0x02 + i
    CHAR_ENCODE_MAP[chr(ord("a") + i)] = 0x1C + i
for i in range(10):
    CHAR_ENCODE_MAP[str(i)] = 0x67 + i
CHAR_ENCODE_MAP.update(
    {
        "!": 0x73,
        "?": 0x74,
        "%": 0x76,
        ":": 0x7A,
        "/": 0x7B,
        ",": 0x7E,
        ".": 0x7F,
        ";": 0x80,
        "'": 0x83,
        '"': 0x84,
        "(": 0x86,
        ")": 0x87,
        "-": 0x8D,
        "+": 0x93,
        "&": 0x96,
    }
)

VALID_CUSTOM_NAME_BYTES: frozenset[int] = frozenset(CHAR_ENCODE_MAP.values())


def decode_ffta2_string(data: bytes, max_len: int = CUSTOM_NAME_BUFFER_LEN) -> str:
    """Decode a null-terminated byte string using FFTA2 character mapping."""
    chars = []
    for b in data[:max_len]:
        if b == 0:
            break
        chars.append(CHAR_DECODE_MAP.get(b, f"[{b:02X}]"))
    return "".join(chars)


def encode_ffta2_string(text: str, length: int = CUSTOM_NAME_BUFFER_LEN) -> bytes:
    """Encode an ASCII keyboard string into FFTA2 character bytes with a 0x00 terminator.

    Raises ValueError if `text` contains any character outside the in-game keyboard
    charset or if `len(text) >= length` (leaving no room for a 0x00 terminator).
    """
    if len(text) >= length:
        raise ValueError(
            f"String {text!r} ({len(text)} chars) must be shorter than buffer length {length} "
            "to preserve a 0x00 terminator"
        )
    out = bytearray(length)
    for idx, ch in enumerate(text):
        byte_val = CHAR_ENCODE_MAP.get(ch)
        if byte_val is None:
            raise ValueError(f"Unsupported character {ch!r} in FFTA2 name {text!r}")
        out[idx] = byte_val
    result = bytes(out)
    assert decode_ffta2_string(result, max_len=length) == text
    return result
