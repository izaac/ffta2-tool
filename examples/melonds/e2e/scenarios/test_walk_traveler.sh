#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/walk_traveler"
SAV="${OUT_DIR:-/tmp}/e2e/e5_test.sav"
PORT=3414
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"

# Cursor starts on Luso (Camoa Highroad).
# Single down moves cursor directly to Traveler's Way (verified in node_1_musk.png!)
$M seq "$S" "down:0.15:1.5"
$M shot "$S" 16_cursor_on_traveler

# Press A to confirm walking to Traveler's Way
$M seq "$S" "a:0.6:6"
$M shot "$S" 17_walked_to_traveler

$M stop "$S"
