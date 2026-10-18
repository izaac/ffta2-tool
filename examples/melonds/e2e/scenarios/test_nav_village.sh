#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/nav_village"
SAV="${FFTA2_SAVE:-$(dirname "$0")/../fixtures/merged.sav}"
PORT=3402
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"

# From Camoa Highroad, press right, then right again to Wood Village
$M seq "$S" "right:0.4:1.5 right:0.4:1.5"
$M shot "$S" on_wood_village
$M seq "$S" "a:0.6:3"
$M shot "$S" village_menu_open

$M stop "$S"
