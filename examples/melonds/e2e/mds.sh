#!/usr/bin/env bash
# Interactive melonDS session driver (OpenCode). State lives in the session dir.
#   mds.sh start <sdir> <sav> [gdb_port]   boot ROM with <sav>, GDB ARM9 stub on gdb_port (default 3333)
#   mds.sh seq   <sdir> "btn[:hold[:after]] ..."  DS buttons: a b x y l r start select up down left right
#   mds.sh shot  <sdir> <name>             DS screens (256x384) at 2x -> <sdir>/<name>.png
#   mds.sh gdb   <sdir> <gdb-cmd>...       one-shot gdb batch against the stub (pauses+resumes)
#   mds.sh stop  <sdir> [out.sav]          TERM melonDS (flushes save), copy game.sav to out.sav
set -euo pipefail
export PATH="/nix/store/vkhy10hwyfzlblr4748qdxn8zx88gr34-xdotool-3.20211022.1/bin:/nix/store/vdpfrvny2hz0cd14yrsnk11xns9n35yp-xorg-server-21.1.24/bin:/nix/store/b1k97zdkdshx5hm95r1g9cfdgl22j4fm-gdb-17.2/bin:/nix/store/g10qxbm4svmxmg2niwbgmxgcb89jxwwk-imagemagick-7.1.2-32/bin:$PATH"
REPO_ROOT="/home/izaac/repos/ffta2-tool"
ROM_PATH="${ROM_PATH:-/tmp/opencode/ffta2.nds}"
cmd="$1"; S="$(realpath -m "$2")"; shift 2

keyname() {
    case "$1" in
        a) echo x ;; b) echo z ;; x) echo s ;; y) echo a ;; l) echo q ;; r) echo w ;;
        start) echo Return ;; select) echo BackSpace ;;
        up) echo Up ;; down) echo Down ;; left) echo Left ;; right) echo Right ;;
        *) echo "bad button $1" >&2; exit 2 ;;
    esac
}

case "$cmd" in
start)
    SAV="$1"; PORT="${2:-3333}"
    mkdir -p "$S"
    W="$S/work"; rm -rf "$W"; mkdir -p "$W/cfg/melonDS" "$W/data" "$W/home"
    D=""
    for d in $(seq 130 160); do
        if [ ! -e "/tmp/.X11-unix/X$d" ] && [ ! -e "/tmp/.X$d-lock" ]; then D=":$d"; break; fi
    done
    Xvfb "$D" -screen 0 800x600x24 -nolisten tcp >"$W/xvfb.log" 2>&1 &
    XPID=$!; sleep 1
    cp "$REPO_ROOT/examples/melonds/melonDS.toml" "$W/cfg/melonDS/melonDS.toml"
    python3 - "$W/cfg/melonDS/melonDS.toml" "$PORT" <<'PY'
import sys
p, port = sys.argv[1], int(sys.argv[2])
t = open(p).read()
t = t.replace("Enabled = false\n\n[Instance0.Gdb.ARM7]", "Enabled = true\n\n[Instance0.Gdb.ARM7]")
t = t.replace("[Instance0.Gdb.ARM7]\nPort = 3334", f"[Instance0.Gdb.ARM7]\nPort = {port + 1}")
t = t.replace("[Instance0.Gdb.ARM9]\nPort = 3333", f"[Instance0.Gdb.ARM9]\nPort = {port}")
open(p, "w").write(t)
PY
    cp "$ROM_PATH" "$W/game.nds"; cp "$SAV" "$W/game.sav"
    DISPLAY="$D" QT_QPA_PLATFORM=xcb SDL_AUDIODRIVER=dummy XDG_CONFIG_HOME="$W/cfg" XDG_DATA_HOME="$W/data" \
        HOME="$W/home" LIBGL_ALWAYS_SOFTWARE=1 setsid melonDS "$W/game.nds" >"$W/melonds.log" 2>&1 &
    MPID=$!
    WID=""
    for i in $(seq 1 35); do
        WID=$(DISPLAY="$D" xdotool search --onlyvisible --name "melonDS" 2>/dev/null | head -1 || true)
        [ -n "$WID" ] && break; sleep 1
    done
    printf 'D=%s\nXPID=%s\nMPID=%s\nWID=%s\nPORT=%s\nW=%s\n' "$D" "$XPID" "$MPID" "$WID" "$PORT" "$W" >"$S/env"
    echo "started display=$D wid=$WID mpid=$MPID gdb=$PORT"
    ;;
seq)
    . "$S/env"; export DISPLAY="$D"
    for tok in $1; do
        IFS=: read -r b hold after <<<"$tok"
        k=$(keyname "$b")
        xdotool windowfocus "$WID"; xdotool keydown "$k"; sleep "${hold:-0.5}"; xdotool keyup "$k"
        sleep "${after:-1}"
    done
    ;;
shot)
    . "$S/env"; export DISPLAY="$D"
    import -window root "$S/$1.full.png"
    magick "$S/$1.full.png" -crop 256x384+0+22 +repage -scale 200% "$S/$1.png"
    echo "$S/$1.png"
    ;;
gdb)
    . "$S/env"
    args=(-batch -ex "set architecture arm" -ex "target remote 127.0.0.1:$PORT")
    for c in "$@"; do args+=(-ex "$c"); done
    args+=(-ex detach -ex quit)
    gdb "${args[@]}" 2>&1 | grep -v -E "warning: No executable|determining executable|target architecture is set|Inferior 1|^$"
    ;;
stop)
    . "$S/env"
    kill -TERM "$MPID" 2>/dev/null || true
    for i in $(seq 1 10); do kill -0 "$MPID" 2>/dev/null || break; sleep 0.5; done
    kill -9 "$MPID" 2>/dev/null || true
    kill -TERM "$XPID" 2>/dev/null || true
    if [ -n "${1:-}" ]; then cp "$W/game.sav" "$1"; ls -la "$1"; fi
    ;;
*) echo "unknown cmd $cmd" >&2; exit 2 ;;
esac
