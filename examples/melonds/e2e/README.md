# FFTA2 melonDS end-to-end scenarios

Replayable driving scripts for proving save edits in the real game
(melonDS + GDB Teak). Every scenario follows the same arc: prepare a save
with the CLI, boot the ROM on it, drive the menus, screenshot each proof
point, save in-game, reload from the title screen, verify persistence.

## Layout

```
e2e/
├── mds.sh            driver: start/seq/shot/stop a melonDS session
│                     (start <sdir> <save> <port> | seq <sdir> "k:t:hold ..." |
│                      shot <sdir> <name> | stop <sdir> [<out.sav>])
├── flow.sh           higher-level: boot/load/save/stop recipe
├── nav.sh, nav2.sh   cursor-walking helpers used by some scenarios
├── fixtures/         save states to drop in (*.sav gitignored, never committed)
└── scenarios/        one script per proof (e1..e4 done, e5 in progress)
```

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
examples/melonds/e2e/scenarios/run_e4.sh   # prep = loop of inject (see below)
for j in Parivir "Cannoneer" "Ranger" "Bishop"; do
  python3 -m ffta2_tool.cli inject "$ROM" --job "$j" --level 30 --force
done
```

Each scenario writes PNGs and the in-game-saved `.sav` back into
`$OUT_DIR/e2e/`, named like the HARDEN_REPORT evidence (e1_01..., e3_03...).

## e5 (battle) —Traveler's Way proof, in progress

Scenario: from `merged.sav`, accept-free route since the quest is already
accepted: boot, load SLOT 1, close the clan menu, walk the Targ Wood
region map to the bottom-left `!` node, enter the encounter, deploy the
injected unit for at least one turn, screenshot mid-battle, then finish
or retreat, save, reload from title, verify roster + HP.

Current building blocks in `scenarios/` (Gemini's live scripts, WIP):
`walk_north.sh`, `find_battle_node.sh`, `nav_traveler.sh`,
`enter_traveler.sh`, `enter_pub.sh`, `check_targ.sh`, `check_notice.sh`,
`probe_pub.sh`, `open_roster.sh`, `test_battle_options.sh`,
`test_nav_village.sh`, `test_walk_traveler.sh`, `probe_battle_save.sh`,
`trigger_encounter.sh`, `trigger_yellow_wings.sh`.

They are kept as-is (running against the fixed 8-second stagger rule);
when the e5 proof lands they should be folded into a single
`run_e5_battle.sh` in the same style as e1..e4.

## Non-EMU checklists that pair with these

- CLI-only idempotency: `just test` (`test_operations_idempotent`).
- Validator on every real backup: see `docs/save_format_map.md` §8.
