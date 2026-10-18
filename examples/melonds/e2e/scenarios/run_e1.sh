#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/s1"
SAV="${OUT_DIR:-/tmp}/e2e/e1_test.sav"
OUT="${OUT_DIR:-/tmp}/e2e/e1_saved.sav"
PORT=3370
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M shot "$S" e1_01_loadscreen
cp "$S/e1_01_loadscreen.png" "${OUT_DIR:-/tmp}/e2e"/

# Load slot 1
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"
$M shot "$S" e1_02_worldmap
cp "$S/e1_02_worldmap.png" "${OUT_DIR:-/tmp}/e2e"/

# Open Clan Info (X -> down -> A)
$M seq "$S" "x:0.4:2.5 down:0.4:1 a:0.5:3"
$M shot "$S" e1_03_claninfo
cp "$S/e1_03_claninfo.png" "${OUT_DIR:-/tmp}/e2e"/

# Back to X menu, up to Unit Info, open Roster
$M seq "$S" "b:0.4:2 up:0.4:1 a:0.5:3"
$M shot "$S" e1_04_roster
cp "$S/e1_04_roster.png" "${OUT_DIR:-/tmp}/e2e"/

# Select Luso (first pedestal), open unit menu
$M seq "$S" "a:0.5:3"
$M shot "$S" e1_05_luso_status
cp "$S/e1_05_luso_status.png" "${OUT_DIR:-/tmp}/e2e"/

# Back to world map
$M seq "$S" "b:0.4:2 b:0.4:2 b:0.4:2"

# Save in game to slot 1
$M seq "$S" "x:0.6:3 down:0.5:1 down:0.5:1 a:0.6:3 a:0.6:3 a:0.6:3 up:0.4:1 a:0.6:6 a:0.6:4"

# Stop and capture saved save
$M stop "$S" "$OUT"
echo "E1 part 1 complete, waiting 9s..."
sleep 9

# Reload from title screen
S2="${OUT_DIR:-/tmp}/e2e/s1_reload"
rm -rf "$S2"
$M start "$S2" "$OUT" 3372
sleep 27
$M seq "$S2" "a:0.5:4"
$M shot "$S2" e1_06_reloaded_loadscreen
cp "$S2/e1_06_reloaded_loadscreen.png" "${OUT_DIR:-/tmp}/e2e"/

# Load slot 1 and open roster
$M seq "$S2" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"
$M seq "$S2" "x:0.4:2.5 a:0.5:3"
$M shot "$S2" e1_07_reloaded_roster
cp "$S2/e1_07_reloaded_roster.png" "${OUT_DIR:-/tmp}/e2e"/

$M stop "$S2"
echo "E1 fully complete!"
