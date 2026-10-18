#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/trigger_encounter"
SAV="/home/izaac/Documents/FFTA2_Backups/071_FFTA2_both_slots_20261016_150437.sav"
PORT=3406
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"

# Move cursor left to Camoa Highroad ([?]) and press A
$M seq "$S" "left:0.4:1.5 a:0.6:4"
$M shot "$S" 12_walk_to_question_mark
$M seq "$S" "a:0.6:4"
$M shot "$S" 13_encounter_triggered

$M stop "$S"
