#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/yellow_wings"
SAV="${OUT_DIR:-/tmp}/e2e/e5_test.sav"
PORT=3416
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"

# Move down to Traveler's Way and confirm
$M seq "$S" "down:0.15:1.5 a:0.6:6"

# Press A to enter Yellow Wings event
$M seq "$S" "a:0.6:4"
$M shot "$S" 20_after_enter

# Advance dialogue / cutscene
for i in $(seq 1 8); do
    $M seq "$S" "a:0.5:2 b:0.5:2"
done
$M shot "$S" 21_after_dialogue

$M stop "$S"
