#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/probe_roster"
SAV="${FFTA2_SAVE:-$(dirname "$0")/../fixtures/merged.sav}"
PORT=3392
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"
$M seq "$S" "right:0.3:1 a:0.5:3 a:0.6:3"

# Move down to Quest Roster and press A
$M seq "$S" "down:0.3:1 a:0.6:3"
$M shot "$S" 04_quest_roster

# Press A on first quest in list
$M seq "$S" "a:0.6:3"
$M shot "$S" 05_quest_detail

$M stop "$S"
