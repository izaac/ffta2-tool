#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/walk_traveler"
M="${MDS:-$(dirname "$0")/../mds.sh}"

# Luso is on Traveler's Way. Press A to trigger/enter
$M seq "$S" "a:0.6:4"
$M shot "$S" 18_pressed_a_traveler
$M seq "$S" "a:0.6:4"
$M shot "$S" 19_dialog_or_battle

$M stop "$S"
