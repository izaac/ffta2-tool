#!/bin/sh
# Interactive melonDS session driver. State lives in the session dir.
# POSIX sh: no bashisms (works with dash, busybox sh, bash-as-sh).
#   mds.sh start <sdir> <sav> [gdb_port]   boot ROM with <sav>, GDB ARM9 stub on gdb_port (default 3333)
#   mds.sh seq   <sdir> "btn[:hold[:after]] ..."  DS buttons: a b x y l r start select up down left right
#   mds.sh shot  <sdir> <name>             DS screens (256x384) at 2x -> <sdir>/<name>.png
#   mds.sh gdb   <sdir> <gdb-cmd>...       one-shot gdb batch against the stub (pauses+resumes)
#   mds.sh waitchange <sdir> [timeout s] [interval s]        return 0 once the frame content differs from the first poll
#   mds.sh waitidle   <sdir> [timeout] [interval] [stable N]  return 0 once the frame is unchanged for N consecutive polls
#   mds.sh lookslike  <sdir> <ref.png> [fuzz %] [timeout s]   return 0 once the frame is within fuzz RMSE of the reference shot
#   mds.sh savediff   <a.sav> <b.sav>                         byte-diff two saves (exit 1 on nonzero diff)
#   mds.sh stop  <sdir> [out.sav] [ref.sav]  TERM melonDS, copy game.sav to out.sav; with ref.sav, exit 3 when unchanged
# shellcheck source=/dev/null
set -eu
export PATH="/nix/store/vkhy10hwyfzlblr4748qdxn8zx88gr34-xdotool-3.20211022.1/bin:/nix/store/vdpfrvny2hz0cd14yrsnk11xns9n35yp-xorg-server-21.1.24/bin:/nix/store/b1k97zdkdshx5hm95r1g9cfdgl22j4fm-gdb-17.2/bin:/nix/store/g10qxbm4svmxmg2niwbgmxgcb89jxwwk-imagemagick-7.1.2-32/bin:$PATH"
REPO_ROOT="/home/izaac/repos/ffta2-tool"
ROM_PATH="${ROM_PATH:-/tmp/opencode/ffta2.nds}"
cmd="$1"; shift
case "$cmd" in
savediff)
    A="$1"; B="$2"
    ;;
*)
    S="$(realpath -m "$1")"; shift
    ;;
esac

keyname() {
    case "$1" in
        a) echo x ;; b) echo z ;; x) echo s ;; y) echo a ;; l) echo q ;; r) echo w ;;
        start) echo Return ;; select) echo BackSpace ;;
        up) echo Up ;; down) echo Down ;; left) echo Left ;; right) echo Right ;;
        *) echo "bad button $1" >&2; exit 2 ;;
    esac
}

frame_hash() {
    T="$1"
    import -window root "$T" 2>/dev/null || { echo "[mds] frame grab failed: emulator/X dead?" >&2; return 1; }
    # hash raw pixels, not PNG bytes: IM embeds metadata chunks whose timestamps change per save
    magick "$T" -crop 256x384+0+22 +repage -colorspace gray -scale 32x48 -strip RGB:- | md5sum | cut -d' ' -f1
}

case "$cmd" in
start)
    SAV="$1"; PORT="${2:-3333}"
    mkdir -p "$S"
    W="$S/work"; rm -rf "$W"; mkdir -p "$W/cfg/melonDS" "$W/data" "$W/home"
    D=""
    d=130
    while [ "$d" -le 160 ]; do
        if [ ! -e "/tmp/.X11-unix/X$d" ] && [ ! -e "/tmp/.X$d-lock" ]; then D=":$d"; break; fi
        d=$((d + 1))
    done
    if [ -z "$D" ]; then echo "[mds] start: no free display in 130..160" >&2; exit 1; fi
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
    n=0
    while [ "$n" -lt 35 ]; do
        WID=$(DISPLAY="$D" xdotool search --onlyvisible --name "melonDS" 2>/dev/null | head -1 || true)
        [ -n "$WID" ] && break
        sleep 1
        n=$((n + 1))
    done
    printf 'D=%s\nXPID=%s\nMPID=%s\nWID=%s\nPORT=%s\nW=%s\n' "$D" "$XPID" "$MPID" "$WID" "$PORT" "$W" >"$S/env"
    echo "started display=$D wid=$WID mpid=$MPID gdb=$PORT"
    ;;
seq)
    . "$S/env"; export DISPLAY="$D"
    for tok in $1; do
        b=${tok%%:*}
        case $tok in
            *:*) rest=${tok#*:} ;;
            *) rest="" ;;
        esac
        case $rest in
            *:*) hold=${rest%%:*}; after=${rest#*:} ;;
            "") hold=""; after="" ;;
            *) hold=$rest; after="" ;;
        esac
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
    TD=$(mktemp -d)
    {
        printf '%s\n' "set architecture arm" "target remote 127.0.0.1:$PORT"
        printf '%s\n' "$@"
        printf '%s\n' detach quit
    } >"$TD/cmds"
    gdb -batch -x "$TD/cmds" >"$TD/out" 2>&1
    grep -v -E "warning: No executable|determining executable|target architecture is set|Inferior 1|^$" "$TD/out" || true
    rm -rf "$TD"
    ;;
waitchange)
    timeout="${1:-30}"; interval="${2:-0.5}"
    . "$S/env"; export DISPLAY="$D"
    TD=$(mktemp -d); T="$TD/f.png"
    h0=$(frame_hash "$T") || exit 1
    t0=$(date +%s)
    while [ $(( $(date +%s) - t0 )) -lt "$timeout" ]; do
        sleep "$interval"
        h1=$(frame_hash "$T") || exit 1
        if [ "$h1" != "$h0" ]; then
            echo "[mds] waitchange: frame changed after $(( $(date +%s) - t0 ))s"
            rm -rf "$TD"; exit 0
        fi
    done
    echo "[mds] waitchange: no frame change within ${timeout}s (screen static or emulator hung)" >&2
    import -window root "$S/timeout_frame.png" 2>/dev/null || true
    rm -rf "$TD"; exit 1
    ;;
waitidle)
    timeout="${1:-30}"; interval="${2:-0.5}"; stable="${3:-4}"
    . "$S/env"; export DISPLAY="$D"
    TD=$(mktemp -d); T="$TD/f.png"
    h0=$(frame_hash "$T") || exit 1
    run=1; t0=$(date +%s)
    while [ $(( $(date +%s) - t0 )) -lt "$timeout" ]; do
        sleep "$interval"
        h1=$(frame_hash "$T") || exit 1
        if [ "$h1" = "$h0" ]; then run=$((run + 1)); else run=1; h0="$h1"; fi
        if [ "$run" -ge "$stable" ]; then
            echo "[mds] waitidle: stable after $run polls ($(( $(date +%s) - t0 ))s)"
            rm -rf "$TD"; exit 0
        fi
    done
    echo "[mds] waitidle: no stability within ${timeout}s (animated screen? lower stable or use waitchange/lookslike)" >&2
    rm -rf "$TD"; exit 1
    ;;
lookslike)
    REF="$1"; fuzz="${2:-5}"; timeout="${3:-60}"; interval="${4:-1}"
    . "$S/env"; export DISPLAY="$D"
    TD=$(mktemp -d); C="$TD/f.png"
    t0=$(date +%s); d=""
    while [ $(( $(date +%s) - t0 )) -lt "$timeout" ]; do
        import -window root "$C" 2>/dev/null || { echo "[mds] frame grab failed: emulator/X dead?" >&2; rm -rf "$TD"; exit 1; }
        magick "$C" -crop 256x384+0+22 +repage -scale 200% "$TD/m.png" 2>/dev/null || { rm -rf "$TD"; exit 1; }
        # magick compare -metric RMSE ... null: is unreliable in this IM build (returns 0 for all pairs);
        # compute RMSE on raw RGB streams instead
        magick "$TD/m.png" -strip RGB:- 2>/dev/null >"$TD/a.raw" || { rm -rf "$TD"; exit 1; }
        magick "$REF" -strip RGB:- 2>/dev/null >"$TD/b.raw" || { echo "[mds] lookslike: unreadable REF $REF" >&2; rm -rf "$TD"; exit 1; }
        d=$(python3 - "$TD/a.raw" "$TD/b.raw" <<'PY'
import math, sys
a, b = open(sys.argv[1], "rb"), open(sys.argv[2], "rb").read()
sa = a.read()
n = min(len(sa), len(b))
if n == 0 or len(sa) != len(b) or len(sa) % 3 != 0:
    print("9999")
else:
    acc = 0
    for i in range(n):
        delta = sa[i] - b[i]
        acc += delta * delta
    print(f"{round(math.sqrt(acc / n) / 255, 4):.4f}")
PY
); rc=$?
        [ "$rc" -eq 0 ] || { echo "[mds] lookslike: python failed rc=$rc" >&2; rm -rf "$TD"; exit 1; }
        case $d in ''|*[!0-9.]) d=9999 ;; esac
        if awk -v d="$d" -v f="$fuzz" 'BEGIN { exit !(d <= f / 100) }'; then
            cp "$C" "$S/lookslike_last.full.png"; cp "$TD/m.png" "$S/lookslike_last.png"
            echo "[mds] lookslike: matched within $d RMSE after $(( $(date +%s) - t0 ))s -> $S/lookslike_last.png"
            rm -rf "$TD"; exit 0
        fi
        sleep "$interval"
    done
    echo "[mds] lookslike: no match within ${timeout}s (last RMSE $d vs fuzz $fuzz%)" >&2
    cp "$C" "$S/timeout_frame.png"
    rm -rf "$TD"; exit 1
    ;;
savediff)
    python3 - "$A" "$B" <<'PY'
import sys
p1, p2 = sys.argv[1], sys.argv[2]
try:
    a, b = open(p1, "rb").read(), open(p2, "rb").read()
except OSError as e:
    print(f"[mds] savediff: {e}", file=sys.stderr)
    raise SystemExit(2)
if a == b:
    print(f"[mds] savediff: {p1} and {p2} are byte-identical ({len(a)} bytes)")
    raise SystemExit(0)
diff = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
groups = []
for i in diff:
    if groups and i == groups[-1][-1] + 1:
        groups[-1].append(i)
    else:
        groups.append([i])
runs = [(hex(g[0]), hex(g[-1]), len(g)) for g in groups]
tail = f" + {len(runs) - 8} more runs" if len(runs) > 8 else ""
print(f"[mds] savediff: {len(diff)} differing bytes in {len(runs)} runs over {len(a)} vs {len(b)} bytes")
for r in runs[:8]:
    print(f"    {r[0]}..{r[1]} ({r[2]} bytes)")
if tail:
    print(f"    {tail}")
if len(a) != len(b):
    print(f"[mds] savediff: sizes differ: {p1}={len(a)}, {p2}={len(b)}", file=sys.stderr)
raise SystemExit(1)
PY
    ;;
stop)
    . "$S/env"
    kill -TERM "$MPID" 2>/dev/null || true
    n=0
    while [ "$n" -lt 10 ] && kill -0 "$MPID" 2>/dev/null; do
        sleep 0.5
        n=$((n + 1))
    done
    kill -9 "$MPID" 2>/dev/null || true
    kill -TERM "$XPID" 2>/dev/null || true
    if [ -n "${1:-}" ]; then cp "$W/game.sav" "$1"; ls -la "$1"; fi
    if [ -n "${2:-}" ] && cmp -s "$W/game.sav" "$2"; then
        echo "[mds] stop: game.sav is byte-identical to $2 (no flush since boot?)" >&2
        exit 3
    fi
    ;;
*) echo "unknown cmd $cmd" >&2; exit 2 ;;
esac
