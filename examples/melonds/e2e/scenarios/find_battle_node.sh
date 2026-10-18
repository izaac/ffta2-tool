#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/find_battle"
SAV="${OUT_DIR:-/tmp}/e2e/e5_test.sav"
PORT=3412
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"

# From Camoa Highroad:
# Step 1: move down to Muskmallow Field
$M seq "$S" "down:0.15:1.5"
$M shot "$S" node_1_musk

# Step 2: move left to Targ Wood
$M seq "$S" "left:0.15:1.5"
$M shot "$S" node_2_targ

# Step 3: move down to Traveler's Way
$M seq "$S" "down:0.15:1.5"
$M shot "$S" node_3_traveler

# Press A on Traveler's Way
$M seq "$S" "a:0.6:3"
$M shot "$S" node_3_entered

$M stop "$S"
