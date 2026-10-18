#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/probe_battle"
SAV="/home/izaac/Documents/FFTA2_Backups/071_FFTA2_both_slots_20261016_150437.sav"
PORT=3404
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"
$M shot "$S" battle_save_loaded
$M stop "$S"
