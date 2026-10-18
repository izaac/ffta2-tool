#!/bin/sh
# High-level FFTA2 melonDS flows on top of mds.sh. Steps run in order:
#   boot                 start + wait for title, press A -> load list
#   shot:<name>          screenshot (DS screens, 2x)
#   load:<1|2>           from load list: pick slot, confirm, wait for world map
#   flag:<name>          GDB read flag4 (0x0212D838) -> <sdir>/<name>.flag
#   save:<1|2>:<ow>      world map -> X menu -> System -> Save -> slot; ow=1 confirms overwrite
#   stop:<out.sav>       quit melonDS and copy the save
# usage: MDS=/path/mds.sh flow.sh <sdir> <sav> <gdb_port> step...
set -eu
M="${MDS:-/tmp/opencode/mds.sh}"
S="$(realpath -m "$1")"; SAV="$(realpath -m "$2")"; PORT="$3"; shift 3
mkdir -p "$S"; LOG="$S/flow.log"; : >"$LOG"
log() { echo "[$(date +%T)] $*" | tee -a "$LOG"; }
# run_log <mds args...>: run the driver, stream stdout into the flow log,
# propagate the driver's exit code (incl. stop's 3 = save unchanged since boot)
run_log() {
    rc=0; out=$("$M" "$@") || rc=$?
    printf '%s\n' "$out" | tee -a "$LOG"
    return "$rc"
}
for step in "$@"; do
    op=${step%%:*}
    case $step in
        *:*) r1=${step#*:} ;;
        *) r1="" ;;
    esac
    case $r1 in
        *:*) a1=${r1%%:*}; a2=${r1#*:} ;;
        "") a1=""; a2="" ;;
        *) a1=$r1; a2="" ;;
    esac
    case "$op" in
    boot)
        run_log start "$S" "$SAV" "$PORT"
        sleep 27
        $M seq "$S" "a:0.5:4"
        ;;
    shot) $M shot "$S" "$a1" >/dev/null; log "shot $a1" ;;
    load)
        # load-list cursor starts on the last saved slot: active metadata copy +0x0A
        CUR=$(python3 -c "
import sys; sys.path.insert(0, '/home/izaac/repos/ffta2-tool')
from ffta2_tool.slots import active_metadata_base
raw = open('$SAV', 'rb').read(); print(raw[active_metadata_base(raw) + 0x0A] + 1)")
        log "load list cursor starts on slot $CUR"
        if [ "$a1" != "$CUR" ]; then
            if [ "$a1" = 2 ]; then $M seq "$S" "down:0.4:1"; else $M seq "$S" "up:0.4:1"; fi
        fi
        LOADED="$a1"
        $M seq "$S" "a:0.6:1.5"
        $M shot "$S" "load_prompt_s$a1" >/dev/null
        $M seq "$S" "up:0.4:1 a:0.6:4 a:0.6:6"
        log "loaded slot $a1"
        ;;
    flag)
        out=$($M gdb "$S" "x/1bx 0x0212d838" | grep 0x212d838 || true)
        echo "$out" >"$S/$a1.flag"; log "flag $a1: $out"
        ;;
    save)
        $M seq "$S" "x:0.6:3 down:0.5:1 down:0.5:1 a:0.6:3 a:0.6:3"
        $M shot "$S" "save_list_s$a1" >/dev/null
        # save-list cursor starts on the loaded slot
        if [ "$a1" != "${LOADED:-1}" ]; then
            if [ "$a1" = 2 ]; then $M seq "$S" "down:0.5:1"; else $M seq "$S" "up:0.5:1"; fi
        fi
        $M seq "$S" "a:0.6:3"
        if [ "${a2:-0}" = 1 ]; then $M seq "$S" "up:0.4:1 a:0.6:6"; fi
        $M shot "$S" "saved_s$a1" >/dev/null
        $M seq "$S" "a:0.6:4"
        log "saved slot $a1 (overwrite=${a2:-0})"
        ;;
    stop)
        if [ -n "$a1" ]; then run_log stop "$S" "$a1"; else run_log stop "$S"; fi
        ;;
    *) log "bad step $step"; exit 2 ;;
    esac
done
log "flow done"
