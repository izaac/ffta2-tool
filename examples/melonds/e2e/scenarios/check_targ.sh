#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/probe_targ"
SAV="${FFTA2_SAVE:-$(dirname "$0")/../fixtures/merged.sav}"
PORT=3386
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"

# Move right to Targ Wood (green house) and enter
$M seq "$S" "right:0.3:1 a:0.5:3"
$M shot "$S" targ_entered

# Check if menu appeared (Shop, Pub, etc)
$M shot "$S" targ_menu

$M stop "$S"
