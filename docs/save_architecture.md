# FFTA2 Save Architecture & Reverse Engineering Reference

Technical reference for *Final Fantasy Tactics A2: Grimoire of the Rift* (Nintendo DS) save data structure and ARM9 binary routines.

---

## 1. High-Level Memory & Save Layout

FFTA2 saves are 512 KB (524,288 bytes) EEPROM / Flash images.

| Offset Range | Length | Description |
|---|---|---|
| `0x0000 - 0x00DC` | 220 B | Slot metadata table copy 1 (Sequence number, slot 0-3 preview data) |
| `0x00DC - 0x01B8` | 220 B | Slot metadata table copy 2 (Redundant backup for power-loss safety) |
| `0x01B8 - 0x01BF` | 8 B | Record header for active save slot |
| `0x01C0 - 0x35BF` | 13,312 B (`0x3400`) | Encrypted save payload (Units, inventory, clan, quests) |
| `0x1000 - 0x10FF` | 256 B | Unused save padding (Contains exposed raw 256-byte keystream) |

---

## 2. Cryptographic System: Additive Stream Cipher

The game uses an **additive byte-stream cipher** modulo 256 over the payload from `0x01C0` to `0x35BF` (13,312 bytes).

### ARM9 Disassembly Reference (`0x0210D740` - `0x0210D75C`):
```arm
0x0210D744: bl  0x0210CF84       ; Get next pseudorandom byte in r0
0x0210D748: ldrb r1, [r5, r4]    ; r1 = plaintext[i]
0x0210D74C: add  r0, r1, r0      ; r0 = (plaintext[i] + key_byte) & 0xFF
0x0210D750: strb r0, [r5, r4]    ; ciphertext[i] = r0
0x0210D754: add  r4, r4, #1      ; i++
0x0210D758: cmp  r4, #0x3400     ; 13,312 bytes
0x0210D75C: bcc  0x0210D744
```

### Encryption & Decryption Formulas:
- **Encryption**: `ciphertext[i] = (plaintext[i] + keystream[i % 256]) & 0xFF`
- **Decryption**: `plaintext[i] = (ciphertext[i] - keystream[i % 256]) & 0xFF`

Because unused padding in the save file is `0x00` prior to encryption, `0 + keystream = keystream`. Thus, the exact 256-byte keystream is preserved verbatim at `0x1000..0x10FF`.

---

## 3. Checksum Verification Routine

FFTA2 calculates a 32-bit checksum over the **plaintext** data starting from the record header `0x01B8` for `0x3408` bytes (13,320 bytes).

### Critical Pre-Condition:
Prior to computing the checksum, the 4-byte checksum field at `0x01B8:0x01BC` must be cleared to `0x00000000` (`ARM9 0x0210D6F8: str r0, [r5, #0]`).

### ARM9 Disassembly Reference (`0x0210D560` - `0x0210D590`):
```arm
0x0210D560: push {r3, lr}
0x0210D564: mov  lr, #0                  ; sum = 0
0x0210D568: mov  r12, lr                 ; i = 0
0x0210D56C: b    0x0210D584

; Loop body
0x0210D570: ldrsb r3, [r0, r12]          ; r3 = (int8)buffer[i] (LOAD SIGNED BYTE)
0x0210D574: sub   r2, r1, r12            ; r2 = count - i
0x0210D578: add   r12, r12, #1           ; i++
0x0210D57C: add   r2, r3, r2             ; r2 = (int8)buffer[i] + (count - i)
0x0210D580: add   lr, lr, r2             ; sum = (sum + r2) & 0xFFFFFFFF
0x0210D584: cmp   r12, r1                ; i < count (0x3408)
0x0210D588: blt   0x0210D570
0x0210D58C: mov   r0, lr                 ; return sum
0x0210D590: pop  {r3, pc}
```

### Python Implementation:
```python
total = 0
count = 0x3408
for i in range(count):
    if i < 4:
        signed_b = 0  # Checksum field is 0 during computation
    else:
        b = plaintext[0x01B8 + i]
        signed_b = b if b < 128 else b - 256
    total = (total + signed_b + (count - i)) & 0xFFFFFFFF
```

---

## 4. Unit Roster Structure

Party units are stored starting at offset `0x0238` with a fixed stride of `0x11C` (284 bytes) per unit, supporting up to 24 units.

| Relative Offset | Type | Description |
|---|---|---|
| `+0x0D` | uint8 | Character / Special Unit ID (e.g. `0x1F` = Luso) |
| `+0x0E` | uint8 | Job ID (e.g. `0x01` = Soldier) |
| `+0x0F` | uint8 | Race / Species ID (e.g. `0x03` = Hume) |
| `+0x22` | uint8 | Unit Level |
| `+0x3C` | uint16 | Max HP |
| `+0x3E` | uint16 | Current HP |
| `+0x40` | uint16 | Max MP |
| `+0x42` | uint16 | Current MP |
| `+0x44` | uint16 | Attack |
| `+0x46` | uint16 | Defense |
| `+0x48` | uint16 | Magic Attack |
| `+0x4A` | uint16 | Magic Defense |
| `+0x4C` | uint16 | Speed |
| `+0x4E` | uint16 | Main Hand Weapon: `(item_id << 5) | flags` |

### Equipment Encoding:
Equipment items are stored as 16-bit halfwords:
```
[15 ...................... 5] [4 ... 0]
          Item ID                Flags (1 = Main Hand)
```
Example: Shortsword (Item `0x19`): `(0x19 << 5) | 1 = 0x0321`.
