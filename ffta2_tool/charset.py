"""FFTA2 Custom Charset Decoder and Encoder."""

CHAR_DECODE_MAP = {
    0x00: "\n",
    0x01: " ",
}

# A-Z: 0x02 - 0x1B
for i in range(26):
    CHAR_DECODE_MAP[0x02 + i] = chr(ord("A") + i)

# a-z: 0x1C - 0x35
for i in range(26):
    CHAR_DECODE_MAP[0x1C + i] = chr(ord("a") + i)

# Digits 0-9: 0x8E - 0x97
for i in range(10):
    CHAR_DECODE_MAP[0x8E + i] = str(i)

# Additional symbols
CHAR_DECODE_MAP.update(
    {
        0x78: "!",
        0x79: "?",
        0x7A: ":",
        0x7B: "/",
        0x7C: ".",
        0x7D: ",",
        0x7E: "-",
        0x80: "(",
        0x81: ")",
        0x84: '"',
        0x85: "'",
    }
)

CHAR_ENCODE_MAP = {v: k for k, v in CHAR_DECODE_MAP.items()}


def decode_ffta2_string(data: bytes, max_len: int = 16) -> str:
    """Decode a byte string using FFTA2 character mapping."""
    chars = []
    for b in data[:max_len]:
        if b == 0:
            break
        chars.append(CHAR_DECODE_MAP.get(b, f"[{b:02X}]"))
    return "".join(chars)


def encode_ffta2_string(text: str, length: int = 16) -> bytes:
    """Encode an ASCII/Unicode string into FFTA2 character bytes."""
    out = bytearray(length)
    for idx, ch in enumerate(text[:length]):
        out[idx] = CHAR_ENCODE_MAP.get(ch, 0x01)
    return bytes(out)
