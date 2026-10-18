#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/probe_traveler"
SAV="${OUT_DIR:-/tmp}/e2e/e5_test.sav"
PORT=3410
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"

# Cursor starts on Luso (Camoa Highroad).
# Move left, then down to Traveler's Way
$M seq "$S" "left:0.3:1.5 down:0.3:1.5"
$M shot "$S" 14_travelers_way
$M seq "$S" "a:0.6:4"
$M shot "$S" 15_after_entering_node

$M stop "$S"
