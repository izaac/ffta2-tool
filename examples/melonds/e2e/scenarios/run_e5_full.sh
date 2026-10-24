#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

SAVE_SRC="${FFTA2_SAVE:-$SCRIPT_DIR/../fixtures/merged.sav}"
if [ ! -f "$SAVE_SRC" ]; then
    echo "missing source save $SAVE_SRC (drop the Traveler's Way fixture there or set FFTA2_SAVE)" >&2
    exit 2
fi

OUT="${OUT_DIR:-/tmp}/e2e"
SAV_TEST="$OUT/e5_final.sav"
S="$OUT/e5_final_session"
PORT=3700
M="${MDS:-$(dirname "$0")/../mds.sh}"

mkdir -p "$OUT"
rm -rf "$S"

echo "=== 1. Inject Unit 7 Acia onto fresh save ==="
cp "$SAVE_SRC" "$SAV_TEST"
"$PYTHON" -m ffta2_tool.cli inject "$SAV_TEST" --slot 1 --job "Viera White Mage" --name "Acia" --level 10 --no-backup

echo "=== 2. Validate injected save ==="
"$PYTHON" -m ffta2_tool.cli validate "$SAV_TEST" --slot 1 || true

echo "=== 3. Boot melonDS ==="
$M start "$S" "$SAV_TEST" "$PORT"
sleep 27

# Load game: Slot 1
$M seq "$S" "a:0.5:4"
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"

# Pub -> accept "You Say Tomato"
$M seq "$S" "right:0.3:1 a:0.5:3 a:0.6:4 b:0.4:2 down:0.15:1.5 a:0.5:3 a:0.5:3"
$M seq "$S" "a:0.4:2 a:0.4:2 a:0.4:2 up:0.3:1 a:0.6:3 a:0.6:3 a:0.6:3"
$M seq "$S" "b:0.5:2 b:0.5:2 b:0.5:2 b:0.5:2"

# Walk to Camoa Adventurer's Rest
$M seq "$S" "left:0.2:2 a:0.6:5"
$M seq "$S" "left:0.2:2 a:0.6:6"
$M seq "$S" "up:0.2:2 a:0.6:6"
$M seq "$S" "down:0.2:2 a:0.6:8"
$M seq "$S" "left:0.2:2 a:0.6:8"
$M seq "$S" "b:0.4:2 up:0.2:2 a:0.6:8 a:0.6:5"

# Skip cutscene & law screen
for _ in $(seq 1 30); do
    $M seq "$S" "a:0.2:0.8 b:0.2:0.8"
done
for _ in $(seq 1 10); do
    $M seq "$S" "a:0.3:1"
done

# Place Acia
$M seq "$S" "l:0.3:1.5 l:0.3:1.5 l:0.3:1.5 l:0.3:1.5"
$M seq "$S" "a:0.5:2"
for _ in $(seq 1 8); do
    $M seq "$S" "a:0.3:1.5"
done
$M seq "$S" "a:0.5:2 a:0.5:2"
$M shot "$S" e5_01_deployment
cp "$S/e5_01_deployment.png" "$OUT"/

# Confirm party and privilege -> enter battle
$M seq "$S" "x:0.6:3 up:0.3:1 a:0.6:4"
$M seq "$S" "a:0.5:2 up:0.3:1 a:0.6:4"

# Advance battle intro text
for _ in $(seq 1 15); do
    $M seq "$S" "a:0.3:1.5"
done

# Turn 1: Acia active on grid
$M shot "$S" e5_02_mid_battle_turn1
cp "$S/e5_02_mid_battle_turn1.png" "$OUT"/

# Cancel movement mode
$M seq "$S" "b:0.5:2"

# Open menu with X, navigate to Quick Save, confirm
$M seq "$S" "x:0.5:2"
$M seq "$S" "up:0.3:1 up:0.3:1 a:0.6:2"
$M seq "$S" "up:0.3:1 a:0.6:4"

# Wait for "Save complete." dialog
sleep 3
$M shot "$S" e5_03_save_complete
cp "$S/e5_03_save_complete.png" "$OUT"/

# Dismiss "Save complete." dialog with A to return to Title Screen
$M seq "$S" "a:0.6:4"
sleep 4
$M shot "$S" e5_04_title_screen
cp "$S/e5_04_title_screen.png" "$OUT"/

# At Title Screen: press A to select Continue / resume quicksave
$M seq "$S" "a:0.6:4"
sleep 6
$M shot "$S" e5_05_reloaded_battle
cp "$S/e5_05_reloaded_battle.png" "$OUT"/

# Stop melonDS and dump final save
$M stop "$S" "$OUT/e5_final_saved.sav"

echo "=== 4. Post-save slot and validation check ==="
"$PYTHON" "$REPO_ROOT/scripts/manage_slots.py" --save "$OUT/e5_final_saved.sav" list
"$PYTHON" -m ffta2_tool.cli info "$OUT/e5_final_saved.sav" --slot 1
"$PYTHON" -m ffta2_tool.cli validate "$OUT/e5_final_saved.sav" --slot 1 || true
