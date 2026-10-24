#!/usr/bin/env bash
# Headless melonDS automated verification runner for FFTA2 saves.
#
# Launches an isolated Xvfb display, boots melonDS with a specified ROM and
# save file, automates UI navigation via xdotool, and captures load-screen and
# in-game screenshots to verify save integrity, difficulty badges, and party state.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Resolve binary paths portably from PATH or environment overrides
MELONDS="${MELONDS_BIN:-$(command -v melonDS 2>/dev/null || true)}"
XDOTOOL="${XDOTOOL_BIN:-$(command -v xdotool 2>/dev/null || true)}"
XVFB="${XVFB_BIN:-$(command -v Xvfb 2>/dev/null || true)}"
MAGICK="${MAGICK_BIN:-$(command -v magick 2>/dev/null || command -v convert 2>/dev/null || true)}"
IMPORT="${IMPORT_BIN:-$(command -v import 2>/dev/null || true)}"

# If on NixOS and tools are missing from PATH, auto re-exec within nix-shell.
# Arguments are passed via environment variables (printf %q quoted) so paths
# containing spaces (e.g. SD-card ROM names) survive the nix-shell --run round-trip.
if { [ -z "${XDOTOOL}" ] || [ -z "${XVFB}" ]; } && command -v nix-shell >/dev/null 2>&1; then
    if [ "${NIX_SHELL_ACTIVE:-0}" -ne 1 ]; then
        echo "[*] Missing Xvfb/xdotool in PATH. Re-running inside nix-shell environment..."
        export NIX_SHELL_ACTIVE=1
        REEXEC_CMD="ROM_PATH=$(printf '%q' "${1:-}") SAV_PATH=$(printf '%q' "${2:-}") OUTPUT_DIR=$(printf '%q' "${3:-}") exec $(printf '%q' "$0")"
        exec nix-shell -p melonds xdotool xorg-server imagemagick --run "${REEXEC_CMD}"
    fi
fi

# Validation check for required tools
missing=()
[ -z "${MELONDS}" ] && missing+=("melonDS")
[ -z "${XDOTOOL}" ] && missing+=("xdotool")
[ -z "${XVFB}" ] && missing+=("Xvfb (xorg-server)")
[ -z "${MAGICK}" ] && missing+=("ImageMagick (magick/convert)")
[ -z "${IMPORT}" ] && missing+=("ImageMagick (import)")

if [ ${#missing[@]} -gt 0 ]; then
    echo "[!] Error: Missing required dependencies: ${missing[*]}" >&2
    echo "    Install them via your system package manager, or run with nix-shell:" >&2
    echo "    nix-shell -p melonds xdotool xorg-server imagemagick" >&2
    exit 1
fi

ROM_PATH="${1:-${ROM_PATH:-}}"
SAV_PATH="${2:-${SAV_PATH:-${REPO_ROOT}/examples/FFTA2_Meta_Squad_Hard.sav}}"
OUTPUT_DIR="${3:-${OUTPUT_DIR:-${SCRIPT_DIR}/output}}"

if [ -z "${ROM_PATH}" ] || [ ! -f "${ROM_PATH}" ]; then
    echo "Usage: $0 <path_to_ffta2_rom.nds> [path_to_save.sav] [output_dir]"
    echo ""
    echo "Arguments:"
    echo "  ROM:       Path to clean Final Fantasy Tactics A2 NDS ROM (required)"
    echo "  SAV:       Path to 512 KiB .sav file (default: examples/FFTA2_Meta_Squad_Hard.sav)"
    echo "  OUTPUT:    Directory to store generated screenshots (default: examples/melonds/output)"
    echo ""
    echo "Environment Variables (optional overrides):"
    echo "  ROM_PATH, SAV_PATH, OUTPUT_DIR (alternatives to the positional arguments)"
    echo "  MELONDS_BIN, XDOTOOL_BIN, XVFB_BIN, MAGICK_BIN, IMPORT_BIN"
    exit 1
fi

if [ ! -f "${SAV_PATH}" ]; then
    echo "[!] Error: Save file not found: ${SAV_PATH}" >&2
    exit 1
fi

mkdir -p "${OUTPUT_DIR}"

# Select available display
DISPLAY_NUM=":99"
for d in {99..120}; do
    if [ ! -e "/tmp/.X11-unix/X$d" ] && [ ! -e "/tmp/.X$d-lock" ]; then
        DISPLAY_NUM=":$d"
        break
    fi
done

WORK_DIR="$(mktemp -d -t ffta2_melonds_XXXXXX)"
XVFB_PID=""
MELONDS_PID=""

cleanup() {
    set +e
    if [ -n "${MELONDS_PID}" ] && kill -0 "${MELONDS_PID}" 2>/dev/null; then
        kill -9 "${MELONDS_PID}" 2>/dev/null || true
    fi
    # Catch any emulator child that escaped the direct PID (e.g. future wrappers),
    # scoped to this run's private ROM copy.
    if [ -n "${WORK_DIR}" ]; then
        pkill -9 -f "${WORK_DIR}/game.nds" 2>/dev/null || true
    fi
    if [ -n "${XVFB_PID}" ] && kill -0 "${XVFB_PID}" 2>/dev/null; then
        # Ask Xvfb to exit gracefully first so it removes its lock and socket,
        # then force-kill if it is still alive.
        kill -TERM "${XVFB_PID}" 2>/dev/null || true
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            kill -0 "${XVFB_PID}" 2>/dev/null || break
            sleep 0.2
        done
        kill -9 "${XVFB_PID}" 2>/dev/null || true
    fi
    rm -rf "${WORK_DIR}"
}
trap cleanup EXIT INT TERM

echo "[*] Setting up headless environment on display ${DISPLAY_NUM}..."
"${XVFB}" "${DISPLAY_NUM}" -screen 0 800x600x24 -nolisten tcp > "${WORK_DIR}/xvfb.log" 2>&1 &
XVFB_PID=$!
sleep 1

# Setup isolated sandbox configuration
mkdir -p "${WORK_DIR}/cfg/melonDS" "${WORK_DIR}/data" "${WORK_DIR}/home"
cp "${SCRIPT_DIR}/melonDS.toml" "${WORK_DIR}/cfg/melonDS/melonDS.toml"
cp "${ROM_PATH}" "${WORK_DIR}/game.nds"
cp "${SAV_PATH}" "${WORK_DIR}/game.sav"

echo "[*] Launching melonDS with ROM: $(basename "${ROM_PATH}") and SAV: $(basename "${SAV_PATH}")..."
DISPLAY="${DISPLAY_NUM}" \
QT_QPA_PLATFORM=xcb \
SDL_AUDIODRIVER=dummy \
XDG_CONFIG_HOME="${WORK_DIR}/cfg" \
XDG_DATA_HOME="${WORK_DIR}/data" \
HOME="${WORK_DIR}/home" \
LIBGL_ALWAYS_SOFTWARE=1 \
"${MELONDS}" "${WORK_DIR}/game.nds" > "${WORK_DIR}/melonds.log" 2>&1 &
MELONDS_PID=$!

export DISPLAY="${DISPLAY_NUM}"
WID=""
for _ in {1..35}; do
    WID=$("${XDOTOOL}" search --onlyvisible --name "melonDS" 2>/dev/null | head -1 || true)
    if [ -n "${WID}" ]; then
        break
    fi
    sleep 1
done

if [ -z "${WID}" ]; then
    echo "[!] Error: melonDS failed to render a visible window within 35 seconds." >&2
    if [ -f "${WORK_DIR}/melonds.log" ]; then
        cat "${WORK_DIR}/melonds.log" >&2
    fi
    exit 1
fi

echo "[*] Found melonDS window (ID: ${WID}). Waiting 28s for intro logos and title screen..."
"${XDOTOOL}" windowfocus "${WID}"
sleep 28

echo "[*] Sending 'A' button input (x key) to enter save load screen..."
"${XDOTOOL}" windowfocus "${WID}"
"${XDOTOOL}" keydown x
sleep 0.5
"${XDOTOOL}" keyup x
sleep 4

echo "[*] Capturing load screen..."
LOAD_FULL="${OUTPUT_DIR}/load_screen_full.png"
LOAD_SLOT1="${OUTPUT_DIR}/load_screen_slot1.png"
"${IMPORT}" -window root "${LOAD_FULL}"
"${MAGICK}" "${LOAD_FULL}" -crop 256x100+0+240 "${LOAD_SLOT1}"

echo "[*] Opening Slot 1 load prompt..."
"${XDOTOOL}" windowfocus "${WID}"
"${XDOTOOL}" keydown x; sleep 0.6; "${XDOTOOL}" keyup x
sleep 1

echo "[*] Selecting 'Load' option (Up arrow)..."
"${XDOTOOL}" windowfocus "${WID}"
"${XDOTOOL}" keydown Up; sleep 0.4; "${XDOTOOL}" keyup Up
sleep 1

echo "[*] Confirming Load..."
"${XDOTOOL}" windowfocus "${WID}"
"${XDOTOOL}" keydown x; sleep 0.6; "${XDOTOOL}" keyup x
sleep 4

echo "[*] Dismissing 'Slot 1 data loaded' message..."
"${XDOTOOL}" windowfocus "${WID}"
"${XDOTOOL}" keydown x; sleep 0.6; "${XDOTOOL}" keyup x
sleep 5

echo "[*] Capturing world map screen..."
MAP_FULL="${OUTPUT_DIR}/world_map_full.png"
MAP_CROP="${OUTPUT_DIR}/world_map.png"
"${IMPORT}" -window root "${MAP_FULL}"
"${MAGICK}" "${MAP_FULL}" -crop 256x384+0+144 "${MAP_CROP}"

echo "[*] Opening Main Menu ('s' key / DS X button)..."
"${XDOTOOL}" windowfocus "${WID}"
"${XDOTOOL}" keydown s; sleep 0.6; "${XDOTOOL}" keyup s
sleep 3

echo "[*] Opening Unit Info and inspecting Luso..."
"${XDOTOOL}" windowfocus "${WID}"
"${XDOTOOL}" keydown x; sleep 0.6; "${XDOTOOL}" keyup x
sleep 2
"${XDOTOOL}" keydown x; sleep 0.6; "${XDOTOOL}" keyup x
sleep 4

echo "[*] Capturing Unit Info screen..."
UNIT_FULL="${OUTPUT_DIR}/unit_info_full.png"
UNIT_CROP="${OUTPUT_DIR}/unit_info.png"
"${IMPORT}" -window root "${UNIT_FULL}"
"${MAGICK}" "${UNIT_FULL}" -crop 256x384+0+144 "${UNIT_CROP}"

echo "[+] melonDS headless test completed successfully!"
echo "    Screenshots saved to: ${OUTPUT_DIR}/"
echo "      - ${LOAD_FULL}"
echo "      - ${LOAD_SLOT1}"
echo "      - ${MAP_FULL}"
echo "      - ${MAP_CROP}"
echo "      - ${UNIT_FULL}"
echo "      - ${UNIT_CROP}"
