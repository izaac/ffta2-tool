#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/walk_north"
SAV="${FFTA2_SAVE:-$(dirname "$0")/../fixtures/merged.sav}"
PORT=3400
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"

# Luso is on Camoa Highroad. Press up to cross region boundary
$M seq "$S" "up:0.6:3"
$M shot "$S" 10_after_up
$M seq "$S" "a:0.6:3"
$M shot "$S" 11_after_a

$M stop "$S"
