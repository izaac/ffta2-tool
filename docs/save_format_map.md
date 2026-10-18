# FFTA2 Save Format Map: Addresses, Offsets and How They Relate

One page that collects every verified address in one place, with the formulas that
connect them. Sources: ARM9/overlay disassembly, melonDS RAM pokes and cross-checks
against real saves (2026-10-16/17). Tool constants live in
`ffta2_tool/save.py` (payload offsets) and `ffta2_tool/slots.py` (container). Numbers
marked UNVERIFIED are best-guesses, do not rely on them.

## 1. The four layers and how to translate between them

```
SD/PC .sav file (512 KiB "image")
  └─ banks:        2 x 0x40000 (bank 1 = 0x00000, bank 2 = 0x40000, mirrored copies)
       └─ records: 0x1B8 + pos*0x3408, 4 positions per bank   (SLOT_RECORD_SIZE 0x3408)
            ├─ header 0x08: u32 checksum, u16 game/version (0x0002), u16 slot, seed u32 @+6
            └─ payload 0x3400: ENCRYPTED, decrypted in place with the LCG keystream
                 (plaintext = ram_state - base, see below)
  └─ metadata:     2 copies of 0xDC at 0x0000 and 0x00DC, per bank
       └─ 4 entries of 0x2C each at copy + 0x2C + pos*0x2C
```

Entry bytes (`slots.py`): +4 active, +5 retired (0 = live), +6 slot_id
(0 = SLOT 1, 1 = SLOT 2, 2 = quicksave, 0xFF = none), +0x08 u32 member count,
badge byte +0x24 bit 0 = Hard.

- One record owns one piece of "which copy is live" state, resolved by entry, never
  by position. `ffta2_tool.slots.SlotManager` does this resolution; the record for
  SLOT N is whatever entry with slot_id N-1 is active and not retired.
- The metadata copy with the higher 4-byte sequence counter is the one the game
  writes next (`active_copy_base()`).
- **Plaintext ↔ RAM:** `plaintext_offset = RAM_address - 0x0212AEE0`
  (so plaintext 0x0000 is ARM9 0x0212AEE0). RAM pokes in melonDS use this to find a
  field, then the same offset is what gets saved.
- The load-screen preview entry (metadata, unencrypted) is RE-DERIVED from the payload
  on save: leader name (10 bytes incl. terminator: 9 chars + 0x00), member count
  (counted as units with job_id != 0), difficulty badge. Editing the payload and
  running `slots.py` preview refresh keeps it in sync.

## 2. Decryption (crypto.py), exact game algorithm

- Keystream: LCG `state = (5 * state + 1) & 0xFF`, seeded from the record header
  seed field (header offset 6, i.e. u32 at record_base + 6); one keystream byte per
  payload byte: `payload[i] ^= keystream[i]`. Old builds that scanned padding at
  0x1000 for the seed corrupted payloads once >= 13 unit slots were occupied; the
  current code takes the header seed directly.
- Payload checksum header: `ffta2_tool.crypto.calculate_checksum` over the full
  0x3408 record (see save_architecture.md §3).
- Consequence: never edit the encrypted payload directly; go through
  `FFTA2Save`/`SlotManager`, which decrypt, edit, re-encrypt and re-sign.

## 3. Clan / party fields in the decrypted payload (save.py)

| Plaintext offset | Size | Meaning / relation |
|---|---|---|
| 0x0000..0x01B7 | 0x1B8 | system/quest area (quests, story flags; see scripts/inspect_save.py) |
| 0x01D8 | 20 | clan name, encoded text (see §5). Game RAM 0x020FA398 |
| 0x01EC | 20 | leader ("Luso") custom name. Game RAM 0x020FA380 |
| 0x0238 + i*0x11C | 0x11C | unit i, i in 0..23 (24 = full clan) |
| 0x1DFC | array | clan inventory: per item_id total/equipped counts |
| 0x2798 | 1 | difficulty: 1 = Hard, 2 = Normal (RAM 0x0212D878) |
| 0x281C | u32 | gil (RAM 0x0212D6FC, cap literal 99999999 in the code) |
| 0x2820 | u16 | clan points, cap 9999 (RAM 0x0212D700) |
| 0x2824 | 4 | talents Negotiation/Aptitude/Teamwork/Adaptability, cap 99 (RAM 0x0212D704) |
| 0x2937 | 9 | clan privilege bitfield (see §6, RAM 0x0212D817) |
| 0x2958 | 1 | difficulty copy used by the save validator (save_architecture.md §8) |

Unit fields (all offsets relative to unit base; UNIT_TABLE_BASE = 0x0238):

| Unit offset | Meaning / relation |
|---|---|
| +0x00..0x0C | zeroed prefix (13 bytes) |
| +0x0D | character_id: 1 = Luso (only slot 0), 0 = everyone |
| +0x0E | job_id (0x01 = Soldier); drives +0x18/+0x1A, see below |
| +0x0F | race_id (1..7); must equal race of the job (`get_job_race_id`) |
| +0x10 | zero on real saves |
| +0x11 | roster_index, 1-based unique 1..24 (`0x020BA748` picks lowest unused); on a contiguous roster == slot+1. Party order in menus derives from this, not a separate array |
| +0x12 | u16 status_flags: 0x0080 recruited; 0x2080 seen while deployed in battle formation |
| +0x14 | u16 name_id: 0x8001 = "use custom leader string at 0x01EC" (slot 0 only); otherwise a JD_message_0.pak subfile-0 name id (see §5) |
| +0x16 | primary A-ability set id |
| +0x17 | secondary A-ability set id |
| +0x18 | u16 job title message id = 1000 + job_id (the `job_id` setter keeps this in sync; older "pre fixed-titles" saves predate that fix) |
| +0x1A | u16 job string id = 0x9470 + job_id (same setter sync) |
| +0x1C..0x21 | runtime party/dispatch state; zero on fresh recruits |
| +0x22 | level 1..99 |
| +0x23 | exp (1 byte) |
| +0x24 | speed |
| +0x25..0x2D | 9 base job-mastery flag bytes, all 0x01 on every recruited unit |
| +0x2E..0x3B | runtime status buffer, zero outside battle |
| +0x3C/0x3E | u16 cur_hp / max_hp (verified `0x020B9158` level_up_unit; cur==max on healthy saves, cur_mp is 0 outside battle) |
| +0x40/0x42 | u16 cur_mp / max_mp |
| +0x44..0x4A | u16 attack, defense, magick, resistance |
| +0x4C..0x54 | 5 x u16 equipment: weapon, shield, helm, armor, accessory (item ids) |
| +0x56 | u16 reaction ability id |
| +0x58 | u16 passive/support ability id |
| +0x5A..0x11B | per-ability AP/mastery array (0x00 = unlearned, mid = AP, 0xFF = mastered) |

Grow dots / hired stat quality live in `stats.py` (god-roll topup), not in these fields.

## 4. Recruitment: what writing a "joined the clan" must touch (RECRUIT_DIFF.md)

The game's recruit callee is ARM9 `0x020BA92C`; callers are the pub questionnaire
statement `0x0209B3E4`, post-battle offer `0x02079C9C` and quest reward `0x02096780`
(outer wrapper `0x02096494`, which also seeds starting abilities/AP via
`0x020B84B4`). When the tool injects (save.py `inject_unit`) it must reproduce:

1. Clear the 0x11C unit struct, set char/race/job (+0x18/+0x1A job ids), status 0x0080.
2. roster_index = lowest unused 1..24 (contiguous roster assumed).
3. Base flags +0x25..+0x2D = 01 x9; HP/MP from the game's growth loop
   (`0x020B9158`); default speed 50 pre-growth (tool uses god-roll stats instead).
4. Name roll with duplicate check `0x020B96C8` (see §5).
5. Clan inventory counts at 0x1DFC: +1 total and +1 equipped per equipped item.
6. Nothing else in the payload changes; load-screen member_count re-derives on save.

Dismissal (`0x020BAA4C`) unequips (decrement 0x1DFC), zeroes the struct. Survivors
keep their roster_index, so rosters CAN have holes after a dismiss in principle; the
tool refuses holes/beyond-the-first-free-slot until proven safe.

## 5. Names, text and the ROM tables

- Names come from `JD_message_0.pak` subfile 0 (779 entries 0..778), extracted into
  `ffta2_tool/character_names.py`. Story/special ranges (0..67, 266..280, 430..444,
  649..778) are rejected for generics unless forced; generic pools:
  - male (Hume/Bangaa/Nu Mou/Moogle): 68..265
  - female (Viera/Gria): 281..429
  - seeq/monster: 445..648
- `name_id` high bit on slot 0 (0x8001) means "display the custom leader string"
  stored at payload 0x01EC; `get_unit_name` resolves both cases. ARM9 name lookup
  `0x02085100`.
- Custom names/clan name: max 9 chars + terminator, 20-byte buffer, checked in the
  name-entry overlay OVL_12 `0x02135FE8`/`0x02135FFC` and the preview copy
  `0x0210D800` (`cmp r2, #0x0A`).
- Text encoding (`charset.py`): A = 0x02, a = 0x1C (i.e. letter + base), digits
  0x67..0x70, `!` 0x73, `?` 0x74, `,` 0x7E, `.` 0x7F, `'` 0x83, `-` 0x8E-region
  fallback, `↑` 0x9B, `↓` 0x9C; 0x00 terminates. The encoder rejects unknown
  characters instead of silently writing 0x01 (retail keyboard map came from
  JD_message subfiles 19/21).

## 6. Clan privileges (verified by melonDS RAM pokes)

Field = plaintext 0x2937..0x293F (RAM 0x0212D817..0x0212D81F) = game flags
0x0718..0x0720. The privilege table has 64 entries (ARM9 `0x0210695C..0x021069FC`,
names in sysdata/JD_message_0.pak file 15), one entry per flag bit 0x071C..0x075B:

- 0x0718..0x071B (= 0x2937 bits 0..3): NOT privileges, list stays empty. Preserve.
- 0x0744..0x0749 (= 0x293C bits 4..7 + 0x293D bits 0..1): entries 41..46, nameless
  "–" rows in the menu.
- 0x075C..0x075F (= 0x293F bits 4..7): past the last entry; never set.
- Everything else (58 bits) = the 58 named privileges, no blank rows with the full
  mask. Mask constant: `CLAN_PRIVILEGE_MASK = f0ffffffff0ffcff0f`
  (save.py); `unlock_clan_privileges()` ORs it in, never overwrites.

## 7. Addresses beyond the payload (ROM/game side)

| ARM9 address | Role |
|---|---|
| 0x020FA380 / 0x020FA398 | leader/clan custom name buffers (RAM mirror of 0x01EC/0x01D8) |
| 0x0210D66C | metadata entry lookup; 0x0210D6BC allocator; 0x0210D740 LCG/encrypt |
| 0x0210D560 | record checksum; 0x0210D790/0x0210D800 preview entry population |
| 0x0210AECC | difficulty badge rule (bit 0) on the load screen |
| 0x0210CF74/0x0210CF84 | LCG constants cross-reference |
| 0x020B92FC | random generic name roll base; 0x020B96C8 duplicate-name reroll |
| 0x020BA92C | recruit callee; 0x020BA748 roster_index assign; 0x020B98A8 first-free-slot |
| 0x020B9368 | unit struct populate; 0x020B9158 level_up_unit (stat growth loop) |
| 0x020BAA4C | dismiss unit; 0x020F1554 clan inventory equipped-count update |
| 0x0212D6FC..0x0212D704 | gil/CP/talents RAM (plaintext 0x281C/0x2820/0x2824) |
| 0x0212D787/0x0212D788 | difficulty byte in RAM (plaintext 0x2798/0x2958 copies) |
| 0x0212D817..0x0212D81F | privilege bitfield RAM |

## 8. Invariants the tool checks before writing (validator.py)

Per recruited unit: roster_index == slot+1 and unique, no holes, status in
{0x0080, 0x2080}, +0x10 == 0, base flags 01 x9, char_id 1 only on slot 0,
name_id rules of §5, race == job race, level 1..99, cur <= max for HP/MP.
Names: <= 9 chars, known charset, terminator, roundtrip equality.
Any rule must produce 0 errors across every real user save (checked before each rule
was added) a rule that fires on a real save is the rule's fault, not the save's.

## 9. melonDS workflow A-Z (tooling, not save format)

- `examples/melonds/` + ROM `/tmp/opencode/ffta2.nds` (ROM_PATH override in mds.sh),
  stagger parallel sessions >= 8 s.
- GDB stub: it serves ONE client per emulator start. After a `detach` or a dropped socket the
  stub keeps the dead connection, never accepts another, and spams `[GDB] receiving from stream 0`
  (31 GiB of log once filled a 32 GiB tmpfs). Either do every poke in one gdb batch
  (`mds.sh gdb`) or hold a single long-lived connection (`examples/melonds/e2e/rsp.py`) and use
  halt/read/resume around each peek. Unaligned BYTE writes kill the stub: write whole words.
  The plaintext+RAM formula of §1 converts addresses.
- Reads cost about 85 ms per 512 B packet, so never dump the 4 MiB RAM through the stub (12 min).
  For bulk RAM use `mds.sh state <sdir> save <slot>` (File > Save state, 3 s) and read the main
  RAM out of the savestate: it is the 4 MiB at file offset 36 of `work/game.ml<slot>` (NDSG
  section). Savestates also give instant rewinds (`state load`) while probing.
- Proof standard for any new field edit: menus that display it, in-game save,
  reload from title, values persist. Screenshot into /tmp/opencode/.

## 10. In-battle RAM (melonDS, verified 2026-10-18)

Battle state lives in RAM only. The save never contains it; what a fight changes in the save is
the clan unit structs (§3), gil, clan points and the quest counters (§10.6). Addresses are main
RAM as seen by melonDS (base 0x02000000). They were found with savestate diffs and confirmed by
the E6 run in `examples/melonds/e2e/WALKTHROUGH.md`, which plays a whole battle on them.

### 10.1 Unit structs

Every combatant uses the 0x11C unit struct of §3 (job +0x0E, status u16 +0x12, level +0x22,
HP u16 pair +0x3C/+0x3E, MP +0x40/+0x42, stats +0x44..).

- Our deployed units are the clan table itself: `0x0212B118 + i*0x11C`
  (plaintext 0x0238 + `0x0212AEE0`). After title > Load > world map this table equals the
  decrypted slot byte for byte, all 0x11C bytes of every unit (E6 reload gate).
- Foes and guests sit in a second table of the same stride starting at `0x02129FAC`, in deployment
  order. "You Say Tomato": slot 0 Alraune (job 87), slots 1 to 4 Deadly Nightshade (job 88),
  slot 5 Bangaa Warrior guest (job 14), slot 6 Hume Thief guest (job 2). Status bit 0x0001 marks
  hostile units (0x0099 foes, 0x009C guests).
- The HP word at +0x3C is `(max << 16) | cur` and is the live combat value: forecasts read it and
  attacks write it. A real run shows the Alraune going 114, 78, 48, 24 and then KO.
- A KO'd foe leaves its struct behind with cur HP 0.

### 10.2 Position records

The battle map keeps one 0x48 byte record per unit starting at `0x02129AAC`:

| Offset | Meaning |
|---|---|
| +0x00 / +0x01 | tile x / y |
| +0x07 | Move stat, tiles the unit may walk (Luso 6, Bangaa Cannoneer 3, Viera White Mage 3 match Unit Info) |
| -0x08 (end of the previous record) | u32 pointer to the unit struct + 8 |

Order is foes, guests, then our units in deployment order. A record whose pointer misses both unit
tables (or whose struct has level 0) is a placeholder and must be skipped.

### 10.3 Map cursor

The cursor tile is a u16 pair at `0x0212F01A` (x) and `0x0212F01C` (y), mirrored in two bytes at
`0x021298D3` / `0x021298D2`. With the E6 camera D-pad right and left change x by one, down and up
change y by one. Touch taps and the L/R unit cycling write the same cells. At the start of one of
our turns the cursor sits on the acting unit, which identifies it without any pixel reading.

### 10.4 Controls that matter

- D-pad steps need SHORT taps (hold 0.12 s). Holds of 0.4 s or more hit the game's key repeat and
  move two rows or tiles, which is what made earlier harness runs press Wait instead of Attack.
- COMMANDS menu rows: Move, Action, Wait. Action opens the ability list with Attack first.
- Attack: Action > Attack > walk the cursor onto the foe tile > A shows the forecast (HIT %, points,
  both name plates) > A again confirms. No forecast means the tile is out of reach.
- Move: Move > cursor onto a blue tile > A. A tile that is not reachable simply does nothing.
- Wait: A, then A again to keep the facing.
- L/R in target mode step through the next 20 turn-order slots (units repeat, no wrap), they do not
  list each unit once.

### 10.5 Corrections to earlier notes

- The `0x0212` window is not a HUD-only buffer. It is the foe unit table of §10.1.
- The "connected Horn Shot" recorded in `e6_attack_mode` was a foe attacking the Bangaa guest.
  `down a down a r a` at 0.4 s holds selected Wait, so no player attack had happened yet.
- The archived `guaranteed_win` and `complete_win` runs never show a foe dying. Filenames and
  captions are not evidence, a victory needs the results screen, the world map and a flushed save.
- The `0x22f5xxx` combatant records named in the first draft were never needed and are unverified.

### 10.6 What a won battle changes in the save

E6 diff of slot 1, pre-battle injected save versus the in-game save made on the world map after the
fight (offsets are the plaintext offsets of this document):

- units that levelled up (Nyrood 6 to 7, Phonis 5 to 6, Otz 5 to 6) change level, exp, speed,
  HP and MP caps and all four stats through the game's own growth; units that did not (Luso,
  the injected White Mage) change exp only, Luso 25 to 97 and the White Mage 0 to 54.
- gil `0x281C` and clan points `0x2820` rise by the quest reward (6450 to 6910 gil, 22 to 32 CP);
  the quest counters and the preview entry (quests completed, play time) follow.
- status flags stay 0x0080 in the saved record, the in-battle 0x0088 bit only exists in RAM.
- the validator reports no new issue and both slot checksums are valid.
