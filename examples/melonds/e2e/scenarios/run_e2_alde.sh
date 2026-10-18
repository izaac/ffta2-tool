#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/s2_alde"
SAV="${OUT_DIR:-/tmp}/e2e/e2_test.sav"
PORT=3376
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"

# Open Unit Info (X -> A)
$M seq "$S" "x:0.4:2.5 a:0.5:3"

# Short tap right to Unit 2 (Nu Mou), press A
$M seq "$S" "right:0.15:1.5 a:0.5:3"
$M shot "$S" e2_02_alde_status
cp "$S/e2_02_alde_status.png" "${OUT_DIR:-/tmp}/e2e"/

$M stop "$S"
