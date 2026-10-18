#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/check_notice"
SAV="${FFTA2_SAVE:-$(dirname "$0")/../fixtures/merged.sav}"
PORT=3394
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"
$M seq "$S" "right:0.3:1 a:0.5:3 a:0.6:3"

# Inside pub, press A to open Notices list
$M seq "$S" "a:0.6:3"
# Press A on Crying Wolf
$M seq "$S" "a:0.6:3"
$M shot "$S" 06_crying_wolf

# Press A again (confirm/read)
$M seq "$S" "a:0.6:3"
$M shot "$S" 07_crying_wolf_read

$M stop "$S"
