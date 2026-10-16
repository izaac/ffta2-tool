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
| `+0x4C` | uint16 | Main Hand Weapon (16-bit unshifted item ID) |
| `+0x4E` | uint16 | Off Hand / Shield (16-bit unshifted item ID) |
| `+0x50` | uint16 | Head / Helmet (16-bit unshifted item ID) |
| `+0x52` | uint16 | Body / Armor (16-bit unshifted item ID) |
| `+0x54` | uint16 | Accessory (16-bit unshifted item ID) |
| `+0x56` | uint16 | Active Equipped Reaction Ability ID |
| `+0x58` | uint16 | Active Equipped Passive / Support Ability ID |

### Equipment & Ability Encoding:

Equipment items and equipped abilities are stored as direct 16-bit little-endian IDs matching the internal ROM tables (`sysdata.pak` Files 6, 7, and 16).
Example: Strike Back (`0x033C`) at `+0x56`, Dual Wield (`0x035C`) at `+0x58`.

---

## 5. Ability AP & Mastery Architecture

Reversed from ARM9 function `0x020BBDF0` (ability status loader) and `0x020B4E20` (unit accessor jump table).

Within each 284-byte unit struct, the entire byte range from `+0x5A` to `+0x11B` (194 bytes) constitutes the unit's ability progression array indexed by `apIndex`:

| Relative Offset Range | Length | Ability Category | `apIndex` Range |
|---|---|---|---|
| `+0x00 - +0x55` | 86 B | Core attributes, base stats, and equipment slots | N/A |
| `+0x56 - +0x57` | 2 B | Active equipped Reaction ability ID | N/A |
| `+0x58 - +0x59` | 2 B | Active equipped Passive ability ID | N/A |
| `+0x5A - +0x70` | 23 B | Reaction Abilities (Reflex, Strike Back, Return Fire, etc.) | `0 - 22` |
| `+0x71 - +0x92` | 34 B | Passive Abilities (Dual Wield, Halve MP, Blood Price, etc.) | `23 - 56` |
| `+0x93 - +0x11B` | 137 B | Action Abilities (Flair, Chivalry, High Magick, etc.) | `57 - 193` |

### AP Byte Format:

- **Bit 7 (`0x80`)**: Mastered flag (`1` = Mastered, `0` = In progress).
- **Bits 0-6 (`0x7F`)**: Current accumulated AP (in increments of 10 AP).
- Writing `0xFF` across `+0x5A..+0x11B` fully masters all Reaction, Passive, and Action abilities legally for the unit without UI freezes or crashes.

> [!NOTE]
> Historical "Unit Info black screen" crashes were not caused by ability bytes, but by equipping off-hand shields or dual weapons on jobs without shield proficiency or Dual Wield active in `+0x58`.

---

## 6. Clan Inventory Array (`0x1DFC`)

The clan inventory starts at payload offset `0x1DFC` with 400 slots (1,600 bytes).

Each slot uses a 4-byte packed layout:

```text
[Item ID (uint16 LE)] [Equipped Count (uint8)] [Total Count (uint8)]
```

- Byte 0-1: 16-bit item ID (`0x0001..0x019A`).
- Byte 2: Number of copies currently equipped across all clan members.
- Byte 3: Total number of copies owned in clan storage.
- If Byte 3 is `0` or Byte 2 > Byte 3, the game hides the item stack from inventory menus.

---

## 7. Clan Job Unlock Flags

In FFTA2, advanced jobs (e.g. Parivir, Sage, Cannoneer, Assassin) and hidden jobs are governed by clan unlock bitfields in the plaintext save payload:

| Plaintext Offset | Length | Action Replay RAM Match | Purpose |
|---|---|---|---|
| `0x2814 - 0x2816` | 3 B | `0x0212D784..0x0212D786` | Unlocks standard and advanced job trees |
| `0x28AF - 0x28B0` | 2 B | `0x0212D81F..0x0212D820` | Unlocks special/hidden job classes |

Setting these 5 bytes to `0xFF` instantly opens all job classes across all 7 races in the Job Change menu without needing quest prerequisites.
