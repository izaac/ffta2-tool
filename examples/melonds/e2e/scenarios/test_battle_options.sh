#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/battle_options"
SAV="${FFTA2_SAVE:-$(dirname "$0")/../fixtures/merged.sav}"
PORT=3398
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"

# First, test moving up to the blue arrow at Camoa Highroad and pressing A
$M seq "$S" "up:0.4:2 a:0.6:4"
$M shot "$S" 09_camoa_entry

$M stop "$S"
