# FFTA2 melonDS end-to-end scenarios

Replayable driving scripts for proving save edits in the real game
(melonDS + GDB Teak). Every scenario follows the same arc: prepare a save
with the CLI, boot the ROM on it, drive the menus, screenshot each proof
point, save in-game, reload from the title screen, verify persistence.

## Layout

```
e2e/
├── mds.sh            driver: start/seq/shot/stop a melonDS session plus
│                     frame/settle guards and byte-level save checks. POSIX sh.
│                     (start <sdir> <save> <port> | seq <sdir> "k:hold:after ..." |
│                      shot <sdir> <name> [pct] | raw <sdir> | touch <sdir> <x> <y> [hold] |
│                      state <sdir> save|load [slot] | gdb <sdir> <cmd>... |
│                      waitchange <sdir> [t] [iv] | waitidle <sdir> [t] [iv] [n] |
│                      lookslike <sdir> <ref.png> [fuzz%] [t] |
│                      savediff <a.sav> <b.sav> | stop <sdir> [<out.sav> [<ref.sav>]])
├── flow.sh           higher-level: boot/load/save/stop recipe
├── dsbot.py          pixel detectors (COMMANDS menu, forecast, world map, save slot) and key/touch helpers
├── rsp.py            single long-lived gdb connection to the stub: halt, read, resume, plus a unix socket daemon
├── battle.py         live battle bot: roster and cursor from RAM, Move / Action > Attack / Wait on the DS buttons
├── nav.sh, nav2.sh   cursor-walking helpers used by some scenarios
├── fixtures/         save states to drop in (*.sav gitignored, never committed)
└── scenarios/        one script per proof (e1..e4, run_e5_full.sh, run_e6_battle.py)
```

The wait-until guards replace fixed sleeps in fragile steps:

- `waitchange` returns 0 the moment the DS screen content differs from the
  first poll instead of sleeping a fixed number of seconds.
- `waitidle` returns 0 once the screen has been unchanged for N polls
  (modal popups, save dialogs).
- `lookslike` compares the live screen with a reference screenshot and
  returns 0 within `fuzz` percent RMSE (menu states, dialog captions).
- `savediff` byte-diffs two saves and lists changed byte runs; `stop
  <sdir> <out.sav> <ref.sav>` exits 3 when the save never changed since
  boot, which catches "the game never flushed" instantly.

All of them exit 1 after their timeout with a `timeout_frame.png` left
behind for manual inspection.

## Fixtures (drop the saves here yourself, do not commit them)

- `fixtures/merged.sav` — SLOT 1 Hard 0:56:23, story flag `0x00AA`,
  accepted quest "Drive off those brigands, the Yellow Wings" whose `!`
  node sits in Targ Wood (Traveler's Way). Gully clan, 6 members,
  6450 Gil / 22 CP. This is the Traveler's Way state the battle proof
  (e5) needs.
- `fixtures/071_FFTA2_both_slots_20261016_150437.sav` — earlier state
  (story `0x0082`), accepted quest "What's in the woods? Wolves...!"
  at Muskmallow Field. Alternative battle route.
- No fixture in the repo opens Camoa pub recruitment; Pub proofs
  (probe_pub/enter_pub/check_notice) are exploratory only.

## Environment

| var | default | purpose |
|---|---|---|
| `ROM_PATH` | `/tmp/opencode/ffta2.nds` | NDS ROM |
| `FFTA2_SAVE` | `fixtures/merged.sav` | source save a scenario copies from |
| `OUT_DIR` | `/tmp` | session dirs + artifacts land in `$OUT_DIR/e2e/` |
| `MDS` | `$SCRIPT_DIR/../mds.sh` | driver override |

Rules encoded in the driver: stagger parallel sessions >= 8 s, ONE gdb
session per emulator start, and melonDS saves live in the session dir
until `mds.sh stop` pulls them out. See
`docs/melonds_headless_debugging.md` for the full gotcha list.

## Scenario prep and run

The scenario scripts drive the emulator only; the save prep is below
(run from the repo root, `python3 -m ffta2_tool.cli`). Every command is
idempotent and costs a `.bak_` snapshot automatically.

```bash
ROM=examples/melonds/e2e/fixtures/merged.sav   # or $FFTA2_SAVE copy

# e1: rename Luso + clan to the 9-char cap, verify load screen/menu/persist
python3 -m ffta2_tool.cli rename "$ROM" --name "RamzaBeou"
python3 -m ffta2_tool.cli rename "$ROM" --clan-name "Ivalice99"
examples/melonds/e2e/scenarios/run_e1.sh

# e2: rename a generic to a pool-compliant ROM name
python3 -m ffta2_tool.cli rename "$ROM" --unit 2 --name "Alde"
examples/melonds/e2e/scenarios/run_e2_alde.sh   # (run_e2.sh = variant)

# e3: inject unit 7 (Viera Red Mage), check her menus + member count 7
python3 -m ffta2_tool.cli inject "$ROM" --job "Red Mage" --level 50 -u 7 --master-abilities
examples/melonds/e2e/scenarios/run_e3.sh

# e4: fill the roster to 24/24 and scroll the whole roster screen
# (from 6 members you need 18 injections; see WALKTHROUGH.md E4 prep loop)
examples/melonds/e2e/scenarios/run_e4.sh
```

Each scenario writes PNGs and the in-game-saved `.sav` back into
`$OUT_DIR/e2e/`, named like the HARDEN_REPORT evidence (e1_01..., e3_03...).

Read `WALKTHROUGH.md` for the full step-by-step walkthrough with per-step
screenshots, expected results, and fragility notes.

## e5 and e6 (live battle)

```bash
# e5: inject Acia, accept the quest, walk to the node, deploy, fight one turn, quick save, resume it
OUT_DIR=/tmp/opencode/e2e_run bash examples/melonds/e2e/scenarios/run_e5_full.sh

# e6: win that battle with real attacks, save on the world map, reload, verify (about 15 minutes)
OUT_DIR=/tmp/opencode/e2e_run python3 examples/melonds/e2e/scenarios/run_e6_battle.py
```

`run_e5_full.sh` leaves `$OUT_DIR/e2e/e5_final.sav` (the injected pre-battle save) and
`e5_final_saved.sav` (melonDS dump holding the quicksave). `run_e6_battle.py` takes those two by
default (`--sav`, `--ref`), resumes the quicksave and plays our units with the DS buttons. The bot
reads the battle roster and the map cursor from RAM through the gdb stub (see
`docs/save_format_map.md` section 10), keeps the injected healer back, and uses Move or
Action > Attack on the nearest foe. No HP, position or flag is forged.

The run ends only when every gate holds, otherwise it exits 1 naming the failed gate:

1. the battle ends in VICTORY (the last foe's HP read from RAM is 0 and the world map returns),
2. the in-game save on the world map flushed (`mds.sh stop` exit 3 would mean an unchanged file),
3. both slot checksums are valid and the validator reports no errors and no issue the pre-battle
   slot did not already have,
4. gil or clan points moved (the quest reward landed),
5. a fresh boot, title > Load > slot 1, shows the game's in-RAM clan table equal to the decrypted
   save byte for byte for every recruited unit.

Artifacts: `e6_battle.log` (every turn, foe HP and decision), `e6_aftermath.sav`, `e6_report.txt`
(checksums, validator, field diff) and `e6_01..e6_10_*.png`, embedded in `WALKTHROUGH.md`.

The loose building blocks in `scenarios/` (`walk_north.sh`, `find_battle_node.sh`, `nav_traveler.sh`,
`enter_traveler.sh`, `enter_pub.sh`, `check_targ.sh`, `check_notice.sh`, `probe_pub.sh`,
`open_roster.sh`, `test_battle_options.sh`, `test_nav_village.sh`, `test_walk_traveler.sh`,
`probe_battle_save.sh`, `trigger_encounter.sh`, `trigger_yellow_wings.sh`) are the exploratory
scripts that led to `run_e5_full.sh`. They are kept as reference and are not part of the proof.

## Non-EMU checklists that pair with these

- CLI-only idempotency: `just test` (`test_operations_idempotent`).
- Validator on every real backup: see `docs/save_format_map.md` §8.
