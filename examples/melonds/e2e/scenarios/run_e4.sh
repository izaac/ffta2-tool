#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/s4"
SAV="${OUT_DIR:-/tmp}/e2e/e4_test.sav"
PORT=3382
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M shot "$S" e4_01_loadscreen_24
cp "$S/e4_01_loadscreen_24.png" "${OUT_DIR:-/tmp}/e2e"/

# Load slot 1
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"

# Open Unit Info (X -> A)
$M seq "$S" "x:0.4:2.5 a:0.5:3"
$M shot "$S" e4_02_roster_row1
cp "$S/e4_02_roster_row1.png" "${OUT_DIR:-/tmp}/e2e"/

# Scroll down row by row
$M seq "$S" "down:0.15:1.5"
$M shot "$S" e4_03_roster_row2
cp "$S/e4_03_roster_row2.png" "${OUT_DIR:-/tmp}/e2e"/

$M seq "$S" "down:0.15:1.5"
$M shot "$S" e4_04_roster_row3
cp "$S/e4_04_roster_row3.png" "${OUT_DIR:-/tmp}/e2e"/

$M seq "$S" "down:0.15:1.5"
$M shot "$S" e4_05_roster_row4
cp "$S/e4_05_roster_row4.png" "${OUT_DIR:-/tmp}/e2e"/

# Move right to pedestal 6 (Unit 24), open unit menu
$M seq "$S" "right:0.15:1 right:0.15:1 right:0.15:1 right:0.15:1 right:0.15:1.5 a:0.5:3"
$M shot "$S" e4_06_unit24_status
cp "$S/e4_06_unit24_status.png" "${OUT_DIR:-/tmp}/e2e"/

$M stop "$S"
echo "E4 complete!"
