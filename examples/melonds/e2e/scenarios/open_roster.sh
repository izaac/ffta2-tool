#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/open_roster"
SAV="${FFTA2_SAVE:-$(dirname "$0")/../fixtures/merged.sav}"
PORT=3396
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"
$M seq "$S" "right:0.3:1 a:0.5:3 a:0.6:3"

# Inside pub, dismiss speech bubble with B, then down to Quest Roster, press A
$M seq "$S" "b:0.4:1 down:0.3:1 a:0.6:3"
$M shot "$S" 08_quest_roster_open

$M stop "$S"
