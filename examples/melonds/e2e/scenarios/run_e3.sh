#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/s3"
SAV="${OUT_DIR:-/tmp}/e2e/e3_test.sav"
OUT="${OUT_DIR:-/tmp}/e2e/e3_saved.sav"
PORT=3378
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M shot "$S" e3_01_loadscreen_7
cp "$S/e3_01_loadscreen_7.png" "${OUT_DIR:-/tmp}/e2e"/

# Load slot 1
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"

# Open Unit Info (X -> A)
$M seq "$S" "x:0.4:2.5 a:0.5:3"

# Move down to row 2 (Unit 7 Acia)
$M seq "$S" "down:0.15:1.5"
$M shot "$S" e3_02_roster_7
cp "$S/e3_02_roster_7.png" "${OUT_DIR:-/tmp}/e2e"/

# Open Unit Menu on Acia (Unit 7)
$M seq "$S" "a:0.5:3"
$M shot "$S" e3_03_unit7_status
cp "$S/e3_03_unit7_status.png" "${OUT_DIR:-/tmp}/e2e"/

# Option 1: Change Equipment
$M seq "$S" "a:0.5:3"
$M shot "$S" e3_04_unit7_equip
cp "$S/e3_04_unit7_equip.png" "${OUT_DIR:-/tmp}/e2e"/
$M seq "$S" "b:0.4:2"

# Option 2: Set Abilities
$M seq "$S" "down:0.15:1 a:0.5:3"
$M shot "$S" e3_05_unit7_abilities
cp "$S/e3_05_unit7_abilities.png" "${OUT_DIR:-/tmp}/e2e"/
$M seq "$S" "b:0.4:2"

# Option 3: Change Jobs
$M seq "$S" "down:0.15:1 a:0.5:3"
$M shot "$S" e3_06_unit7_jobs
cp "$S/e3_06_unit7_jobs.png" "${OUT_DIR:-/tmp}/e2e"/
$M seq "$S" "b:0.4:2 b:0.4:2 b:0.4:2"

# Save in game to slot 1
$M seq "$S" "x:0.6:3 down:0.5:1 down:0.5:1 a:0.6:3 a:0.6:3 a:0.6:3 up:0.4:1 a:0.6:6 a:0.6:4"

$M stop "$S" "$OUT"
echo "E3 part 1 complete, waiting 9s..."
sleep 9

# Reload from title screen
S3="${OUT_DIR:-/tmp}/e2e/s3_reload"
rm -rf "$S3"
$M start "$S3" "$OUT" 3380
sleep 27
$M seq "$S3" "a:0.5:4"
$M shot "$S3" e3_07_reloaded_loadscreen
cp "$S3/e3_07_reloaded_loadscreen.png" "${OUT_DIR:-/tmp}/e2e"/

# Load slot 1, open Unit Info, move down to row 2
$M seq "$S3" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"
$M seq "$S3" "x:0.4:2.5 a:0.5:3 down:0.15:1.5"
$M shot "$S3" e3_08_reloaded_roster
cp "$S3/e3_08_reloaded_roster.png" "${OUT_DIR:-/tmp}/e2e"/

$M stop "$S3"
echo "E3 fully complete!"
