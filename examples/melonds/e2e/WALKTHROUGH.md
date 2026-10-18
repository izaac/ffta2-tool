# FFTA2 melonDS E2E Walkthrough — step by step with screenshots

How to replay every end-to-end proof (rename, inject, full roster, live battle)
with melonDS, the exact keys pressed at each step, the screenshot to expect, and
what has to be true at the end. Written for `examples/melonds/e2e/` on a
host with `melonDS`, `Xvfb`, `xdotool`, ImageMagick (`import`/`magick`), `gdb`
and `bash`. The NFT: nothing in here asserts pass/fail automatically — every
scenario ends with a human looking at screenshots and save files.

Prerequisites:

1. Environment (see repo README): `ROM_PATH` (default `/tmp/opencode/ffta2.nds`),
   `OUT_DIR` (default `/tmp`), `FFTA2_SAVE` (the fixture you run from),
   `MDS` (driver override). All scenario paths land under `$OUT_DIR/e2e/`.
2. Fixture saves: `fixtures/merged.sav` (SLOT 1 Hard, story flag 0x00AA,
   6 members, 6450 Gil; this is the Traveler's Way state all scenarios start
   from). Copy it into each scenario's `_test.sav` name before running.
   Save files are never committed.
3. melonDS low-level rules: sessions stagger >= 8 s if started concurrently,
   ONE gdb session per emulator start, aligned-word ARM9 writes only.
   Port is per-session (ARM9 = PORT, ARM7 = PORT+1, so leave gaps of >= 2).
4. Key notation: `btn:hold:after` in seconds (`a:0.5:4` = press A for 0.5 s,
   wait 4 s). Button → keyboard mapping (mds.sh): a=x, b=z, x=s, y=a,
   l=q, r=w, start=Return, select=BackSpace, dpad = arrows.

Common macros (used in every scenario):

| macro | what it does |
|---|---|
| BOOT | `mds.sh start <sdir> <sav> <port>`, then `sleep 27`, then `a:0.5:4` (pass title) |
| LOAD1 | `a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6` — cursor starts on slot 2, so `up` before A |
| SAVE_S1 | `x:0.6:3 down:0.5:1 down:0.5:1 a:0.6:3 a:0.6:3 a:0.6:3 up:0.4:1 a:0.6:6 a:0.6:4` — in-game save, overwrite slot 1 |
| RELOAD | `mds.sh stop <sdir> <out.sav>`, `sleep 9`, BOOT again on the saved file (new port + sdir), title reload |
| shot | `mds.sh shot <sdir> <name>` → crops + 2x scales to `<sdir>/<name>.png` |

The two fragility rules that bite hardest: (1) fixed sleeps — load waits are
empirically tuned; on a slower host or under CPU load they break silently;
(2) `mds.sh stop` is what flushes melonDS's save to disk — never read
`game.sav` before stopping the session.

---

## E1 — rename (Luso + clan), full menu pass, save/reload persistence

Purpose. Proving a renamed leader and clan survive the game's own save,
across every screen that reads the name strings (payload 0x01EC / 0x01D8).

Prep (repo root):

```bash
cp $FFTA2_SAVE "$OUT_DIR/e2e/e1_test.sav"
python3 -m ffta2_tool.cli rename "$OUT_DIR/e2e/e1_test.sav" --name "RamzaBeou"
python3 -m ffta2_tool.cli rename "$OUT_DIR/e2e/e1_test.sav" --clan-name "Ivalice99"
scenarios/run_e1.sh        # port 3370, sdir $OUT_DIR/e2e/s1
```

Steps (from run_e1.sh):

1. BOOT on `e1_test.sav` → `e1_01_loadscreen.png`: load screen shows SLOT 1
   leader "RamzaBeou", SLOT 2 still "Luso".
2. LOAD1 → `e1_02_worldmap.png`: world map, clan name "Ivalice99" on the clan
   panel.
3. `x:0.4:2.5 down:0.4:1 a:0.5:3` (X menu → Clan Info) → `e1_03_claninfo.png`.
4. `b:0.4:2 up:0.4:1 a:0.5:3` (back, Roster) → `e1_04_roster.png`: unit 01
   reads "RamzaBeou".
5. `a:0.5:3` → `e1_05_luso_status.png`: status screen "01 RamzaBeou" (Parivir
   Lv.5 on the fixture).
6. `b:0.4:2 b:0.4:2 b:0.4:2` back to world map, then SAVE_S1.
7. RELOAD to `s1_reload` (port 3372) on `e1_saved.sav` →
   `e1_06_reloaded_loadscreen.png`: "RamzaBeou" persisted (play time ticked).
8. LOAD1 + `x:0.4:2.5 a:0.5:3` → `e1_07_reloaded_roster.png`: roster row 1
   pedestal 1 "RamzaBeou" after the game's own save/reload.

End condition: screenshot names above exist, and the reloaded screens still
show the new names. Playtime must have advanced >= 1 min between 06 and 01.

Fragile: the load-screen cursor assumption in LOAD1 (on merged.sav the game
starts with the cursor on slot 2; on a fresh different fixture the first
`up` may move off the end). If e1_01 shows the cursor on slot 1, drop `up`.

---

## E2 — rename a generic unit to a race-pool ROM name

Purpose. Proving unit-level name_id edits resolve through
JD_message_0.pak names and the in-game status screen.

Prep:

```bash
cp $FFTA2_SAVE "$OUT_DIR/e2e/e2_test.sav"
python3 -m ffta2_tool.cli rename "$OUT_DIR/e2e/e2_test.sav" --unit 2 --name "Alde"
scenarios/run_e2_alde.sh   # port 3376, sdir s2_alde (run_e2.sh = original variant)
```

Steps:

1. BOOT, LOAD1.
2. `x:0.4:2.5 a:0.5:3` → `e2_01_roster.png`.
3. `right:0.15:1.5 a:0.5:3` (short tap, unit 2's pedestal) →
   `e2_02_alde_status.png`: "02 Alde", Nu Mou Sage Lv.5 (was "Ganoslal").
4. Stop. Read-only scenario: no save, no reload.

End condition: status screen name matches and Job title still reads "Nu Mou
Sage" (the job string ids at unit +0x18/+0x1A replayed correctly).

Fragile: `right:0.15` is the only input that differs between run_e2.sh and
the alde variant; if the roster cursor overshoots, halve the hold time.

---

## E3 — inject a recruit (Viera Red Mage Lv.50), menus, save/reload

Purpose. The synthetic-struct cocktails: a brand-new unit must render and
act sane in status, equipment, abilities, job list — and the load screen must
count 7 members.

Prep:

```bash
cp $FFTA2_SAVE "$OUT_DIR/e2e/e3_test.sav"
python3 -m ffta2_tool.cli inject "$OUT_DIR/e2e/e3_test.sav" --slot 1 \
    --job "Red Mage" --level 50 --master-abilities --no-backup -u 7
scenarios/run_e3.sh        # port 3378, sdir s3
```

Steps:

1. BOOT → `e3_01_loadscreen_7.png`: load screen says Clan Members: 7.
2. LOAD1 + `x:0.4:2.5 a:0.5:3` → roster, then `down:0.15:1.5` →
   `e3_02_roster_7.png`: unit 7 "Acia" on row 2 pedestal 1.
3. `a:0.5:3` → `e3_03_unit7_status.png`: "07 Acia" Red Mage Lv.50,
   HP 438/438, MP 0/179 (MP 0 outside battle is correct game semantics).
4. `a:0.5:3` → `e3_04_unit7_equip.png` (equipment sane), `b:0.4:2`.
5. `down:0.15:1 a:0.5:3` → `e3_05_unit7_abilities.png`: Summoning Magick
   listed MASTER (our 0xFF AP bytes render as mastered, hot path), `b:0.4:2`.
6. `down:0.15:1 a:0.5:3` → `e3_06_unit7_jobs.png`: Viera job list marked
   MASTER, then `b:0.4:2` x3 out.
7. SAVE_S1, RELOAD (s3_reload, port 3380) → `e3_07_reloaded_loadscreen.png`
   (members 7 persisted) and LOAD1 + roster + `down:0.15:1.5` →
   `e3_08_reloaded_roster.png` (Acia still there).

End condition: all 8 screenshots exist, reload keeps member count 7 and the
unit, and `python3 scripts/manage_slots.py --save e3_saved.sav list` shows
slot 1 checksum VALID.

---

## E4 — full roster injection to 24/24 and roster scrolling

Purpose. The crypto/preview stress case: >= 13 unit slots occupied is
exactly what the old keystream extraction corrupted; 24/24 is the extreme.

Prep (README's 4-job loop gets you to 10 members only; from 6 you need 18
injections to hit 24 — iterate different job/race names until
`cli info` reports 24, or reuse the e4_test.sav already prepared):

```bash
while :; do
  n=$(python3 -c "from ffta2_tool.save import FFTA2Save;s=FFTA2Save('$OUT_DIR/e2e/e4_test.sav');print(sum(u.is_recruited for u in s.units))")
  [ "$n" = 24 ] && break
  python3 -m ffta2_tool.cli inject "$OUT_DIR/e2e/e4_test.sav" --slot 1 \
      --job "$((RANDOM%7))" --level 30 --no-backup 2>/dev/null || true
done
scenarios/run_e4.sh        # port 3382, sdir s4
```

Steps: BOOT → `e4_01_loadscreen_24.png` (members 24/24); LOAD1 +
`x:0.4:2.5 a:0.5:3` → four `down:0.15:1.5` shots `e4_02_roster_row1.png` …
`e4_05_roster_row4.png` (rows of 6 pedestal units, 1..24, no blank rows);
`right:0.15:1` x5 then `a:0.5:3` → `e4_06_unit24_status.png`
("24 Rodahl", Bangaa Cannoneer Lv.30). Stop. Read-only.

End condition: roster rows all 24 units, unit 24's status opens, and
`python3 -m ffta2_tool.cli validate` passes; decryption of this save with
`scripts/inspect_save.py` must not fail (that failure mode is the whole
point of E4).

---

## E5 — live battle: deployment, turn 1 with the injected unit, quicksave

Purpose: the hard proof. A tool-injected unit must survive real-time battle:
turn order (speed/level fields), action menus, AP writes, Law card, and
in-battle save/resume.

Prep + run (consolidated driver `run_e5_full.sh`, port 3600,
sdir e5_final_session):

```bash
cp $FFTA2_SAVE "$OUT_DIR/e2e/e5_final.sav"
python3 -m ffta2_tool.cli inject "$OUT_DIR/e2e/e5_final.sav" --slot 1 \
    --job "Viera White Mage" --name "Acia" --level 10 --no-backup
python3 -m ffta2_tool.cli validate "$OUT_DIR/e2e/e5_final.sav" --slot 1
bash examples/melonds/e2e/scenarios/run_e5_full.sh
bash examples/melonds/e2e/scenarios/verify_reload_exact.sh   # port 3610
```

Sequence (spawned by run_e5_full.sh):

1. Accept a pub combat quest in-game (the driver does the pub nav + accept —
   on this fixture the merged "Yellow Wings" route in Targ Wood and the
   Wood Village "You Say Tomato" route are both valid; E5 used Tomato).
2. Walk the world/region map to the quest `!` node (six scripted hops),
   enter, mash through the cutscene (30 A/B taps) and the Law card.
3. Deployment: rotate the 7-unit carousel with 4 x `l:0.3:1.5`, confirm
   Acia, place, then confirm party + clan privilege →
   `e5_01_deployment.png`: Acia Lv.10 White Mage placed, HP 156/156.
4. Battle intro (15 x `a`) → `e5_02_mid_battle_turn1.png`: Acia is turn 1 —
   highlighted in the turn queue, movement tiles lit, HP 156/156, MP 10/95
   (battle grants MP; saves store cur_mp = 0), Law card shows
   PRIVILEGE Power↑1 from our unlocked mask.
5. In-battle Quick Save (`x:0.5:2` → menu up:up:A → up:A) →
   `e5_03_save_complete.png` ("Save complete."), back out to
   `e5_04_title_screen.png` (Continue now present).
6. `verify_reload_exact.sh`: choose Continue from the title →
   `e5_05_reloaded_battle.png` (resume prompt) →
   `e5_06_reloaded_battle_grid.png` (same battle, units in formation) →
   `e5_07_reloaded_acia_commands.png` (Acia's command menu, law reminder).
7. Stop → `e5_final_saved.sav`. Post checks:
   `scripts/manage_slots.py --save $OUT_DIR/e2e/e5_final_saved.sav list`
   (slot 1 VALID), `cli info --slot 1`, `cli validate --slot 1` (0 errors).

End condition: 07 screenshots exist; the reloaded battle shows Acia on the
grid with her commands open.

Remaining E5 leg at the time of writing: FINISH or RETREAT the battle, save
on the world map, reload from title, verify roster 7 — the post-battle
bookkeeping half. In-battle quicksave records themselves do NOT decrypt with
the tool's record algebra (see HARDEN_REPORT "known limitation"): the game
encrypts quicksave records differently.

---

## Screenshot gallery (what the images show)

| file | scenario | caption |
|---|---|---|
| e1_01_loadscreen | E1 | SLOT 1 leader "RamzaBeou", SLOT 2 "Luso" |
| e1_02_worldmap | E1 | world map, clan name "Ivalice99" |
| e1_03_claninfo | E1 | Clan Info "Ivalice99" |
| e1_04_roster | E1 | roster unit 01 "RamzaBeou" |
| e1_05_luso_status | E1 | status "01 RamzaBeou", Parivir Lv.5 |
| e1_06_reloaded_loadscreen | E1 | persisted after in-game save (playtime 0:57:19) |
| e1_07_reloaded_roster | E1 | roster after reload |
| e2_01_roster / e2_02_alde_status | E2 | unit 02 renamed "Alde", Nu Mou Sage Lv.5 |
| e3_01_loadscreen_7 | E3 | Clan Members: 7 |
| e3_02_roster_7 | E3 | unit 7 "Acia" row 2 pedestal 1 |
| e3_03_unit7_status | E3 | Red Mage Lv.50, 438/438 HP, MP 0/179 |
| e3_04_unit7_equip | E3 | equipment screen (Ribbon/Minerva Bustier/Angel Ring) |
| e3_05_unit7_abilities | E3 | Summoning Magick MASTER |
| e3_06_unit7_jobs | E3 | Viera jobs MASTER |
| e3_07/08_reloaded_* | E3 | members 7 + Acia persist after save/reload |
| e4_01_loadscreen_24 | E4 | Clan Members: 24 |
| e4_02..05_roster_row* | E4 | all 24 units on 4 roster rows |
| e4_06_unit24_status | E4 | unit 24 "Rodahl", Bangaa Cannoneer Lv.30 |
| e5_01_deployment | E5 | Acia placed on deployment grid |
| e5_02_mid_battle_turn1 | E5 | Acia acting in turn 1 of live battle |
| e5_03_save_complete | E5 | in-battle Save complete |
| e5_04_title_screen | E5 | title Continue available |
| e5_05/06/07_reloaded_* | E5 | Continue → battle resumed, Acia commands |

Screenshots are produced into `$OUT_DIR/e2e/…` and are not committed.

## Known limitations & fragility (read before tuning anything)

- Load waits are fixed sleeps (27 s boot, 9 s reload, 6 s continue); the
  scripts assume the load cursor starts on slot 2; SAVE_S1 assumes the
  overwrite prompt. On any other fixture, verify each assumption against the
  first screenshot of that step before going further.
- Blind mash loops (cutscene 30x, battle intro 15x, deploy 8x) count cursor
  moves; a dropped keystroke desyncs everything after.
- `mds.sh stop` is the only safe point to read a save file (flush + kill).
- Parallel sessions: >= 8 s start stagger and non-overlapping ports.
- Do not run scripts that strip `/tmp/.X{99..250}-lock` while another
  session is alive (mds.sh allocates :130-:160).
- Every scenario ends in human screenshot review; the only automated gate is
  the CLI (`validate`, `manage_slots list`) — never adorn it with `|| true`.
