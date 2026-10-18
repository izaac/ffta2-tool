#!/usr/bin/env bash
set -euo pipefail
S="${OUT_DIR:-/tmp}/e2e/enter_pub"
SAV="${FFTA2_SAVE:-$(dirname "$0")/../fixtures/merged.sav}"
PORT=3390
M="${MDS:-$(dirname "$0")/../mds.sh}"

rm -rf "$S"
$M start "$S" "$SAV" "$PORT"
sleep 27
$M seq "$S" "a:0.5:4"
$M seq "$S" "a:0.6:1.5 up:0.4:1 a:0.6:4 a:0.6:6"

# From wherever Luso starts, move to Wood Village
# In check_targ.sh, "right:0.3:1 a:0.5:3" put Luso on Wood Village with Pub/Shop menu open!
$M seq "$S" "right:0.3:1 a:0.5:3"
$M shot "$S" 01_village_menu

# On Pub/Shop menu, Pub is top item. Press A to enter Pub
$M seq "$S" "a:0.6:3"
$M shot "$S" 02_pub_screen

# Press A inside Pub (Quests / Rumors / Notice Board)
$M seq "$S" "a:0.6:3"
$M shot "$S" 03_quest_list

$M stop "$S"
