# MelonDS Headless Debugging & Automated Save Verification

This guide outlines how to perform automated, headless emulation tests of Final Fantasy
Tactics A2 (FFTA2) save files using **melonDS**, **Xvfb**, and **xdotool**. This setup allows
verifying save integrity, load-screen preview badges (Hard vs Normal), playtime, and
in-game rendering stability in CI pipelines or terminal-only environments.

---

## 1. Architecture & Overview

When testing save modifications (such as difficulty flags, dual-wielding equipment, or
roster adjustments), static checksum verification only validates the data structure.
Full verification requires confirming:

1. **Load Screen Metadata**: The visual badge (Hard/Normal), leader level, unit count,
   and playtime render correctly without corruption.
2. **Game Engine Acceptance**: The engine reads the save payload without resetting
   options or falling back to defaults upon in-game save.
3. **In-Game Rendering**: Navigating to the world map and opening the Unit Info menu
   renders sprites, equipment, and ability sets without triggering black screens or hangs.

The headless runner automates this by:

- Spawning a virtual X11 framebuffer (`Xvfb`) on an isolated display (e.g. `:99`).
- Booting melonDS with dummy audio (`SDL_AUDIODRIVER=dummy`) and software OpenGL
  (`LIBGL_ALWAYS_SOFTWARE=1`).
- Driving title screen navigation programmatically using `xdotool`.
- Capturing full-screen and cropped status screenshots using ImageMagick (`import` / `magick`).

---

## 2. Prerequisites & Dependencies

The runner requires the following tools available in `PATH` (or specified via environment
variable overrides):

- **melonDS** (>= 0.9.5): Nintendo DS emulator.
- **xdotool**: X11 automation tool for programmatic keypresses.
- **Xvfb** (`xorg-server`): Virtual framebuffer X server.
- **ImageMagick** (`magick` or `convert`, `import`): For headless screen capture and cropping.

### Installation

#### Debian / Ubuntu

```bash
sudo apt-get update
sudo apt-get install -y melonds xdotool xvfb imagemagick
```

#### Arch Linux

```bash
sudo pacman -S melonds xdotool xorg-server-xvfb imagemagick
```

#### Nix / NixOS

You can run directly within an ad-hoc Nix shell:

```bash
nix-shell -p melonds xdotool xorg-server imagemagick
```

The runner script (`run_headless_test.sh`) includes automatic fallback to `nix-shell`
if tools are missing from the host environment on NixOS.

---

## 3. Configuration (`melonDS.toml`)

The headless runner utilizes `examples/melonds/melonDS.toml`. Key optimizations include:

- **Isolated Paths**: `RecentROM`, `SaveFilePath`, and firmware paths are empty to prevent
  leakage of host paths and ensure sandbox isolation.
- **Software Rendering**: Emulation uses `Renderer = 0` (software) with `UseGL = false`
  to guarantee deterministic execution on systems without hardware GPUs.
- **Audio Dummying**: Emulation runs with `AudioSync = false` and `SDL_AUDIODRIVER=dummy`.
- **Keyboard Mappings**:
  - `A Button`: `x` (Qt keycode 88)
  - `B Button`: `z` (Qt keycode 90)
  - `X Button`: `s` (Qt keycode 83)
  - `Y Button`: `a` (Qt keycode 65)
  - `Start`: `Return`
  - `Select`: `Backspace`
  - `D-Pad`: Arrow keys

---

## 4. Running Headless Tests

Use the automated test runner script located at `examples/melonds/run_headless_test.sh`:

```bash
./examples/melonds/run_headless_test.sh <path_to_rom.nds> [path_to_save.sav] [output_dir]
```

### Parameters

- `<path_to_rom.nds>`: Path to a clean North American or European FFTA2 NDS ROM (required).
- `[path_to_save.sav]`: Path to the 512 KiB `.sav` file to verify (optional; defaults to
  `examples/FFTA2_Meta_Squad_Hard.sav`).
- `[output_dir]`: Output directory for generated PNG screenshots (optional; defaults to
  `examples/melonds/output`).

### Environment Variable Overrides

If binaries are located in non-standard paths, override them using environment variables:

```bash
MELONDS_BIN=/usr/local/bin/melonDS \
XDOTOOL_BIN=/usr/bin/xdotool \
./examples/melonds/run_headless_test.sh path/to/game.nds
```

The ROM/save/output paths can also be supplied via environment variables instead of
positional arguments (`ROM_PATH`, `SAV_PATH`, `OUTPUT_DIR`), which is convenient for CI:

```bash
ROM_PATH=/data/roms/ffta2.nds \
SAV_PATH=/data/saves/patched.sav \
OUTPUT_DIR=/tmp/ffta2-shots \
./examples/melonds/run_headless_test.sh
```

The default save (`examples/FFTA2_Meta_Squad_Hard.sav`) and default output directory
(`examples/melonds/output`) are resolved relative to the repository, so a fresh clone
works on any machine once a ROM path is supplied. The ROM itself is never committed
(bring your own dump); the 512 KiB example save is committed and needs no setup.

### Troubleshooting

- **Stale X11 display locks**: hard-killed Xvfb sessions can leave `/tmp/.X*-lock` files
  behind. The runner skips occupied display numbers and picks the first free one, and it
  shuts Xvfb down gracefully (SIGTERM first) so it no longer leaves locks of its own.
- **Paths with spaces**: when the runner auto re-execs inside `nix-shell`, arguments are
  passed through quoted environment variables, so ROM/save paths like
  `/run/media/.../071 Final Fantasy Tactics A2.nds` survive intact.

---

## 5. Interpreting Test Artifacts

The runner captures verification screenshots in the output directory:

| Artifact | Resolution | Verification Purpose |
| :--- | :--- | :--- |
| `load_screen_full.png` | 800x600 | Full emulator window showing Title and Save Slot menu. |
| `load_screen_slot1.png` | 256x100 | Cropped Slot 1 preview: inspect orange **Hard** badge, playtime, and level. |
| `world_map_full.png` | 800x600 | Confirms save loaded successfully into the world map without crashes. |
| `world_map.png` | 256x384 | Cropped dual-screen view of the world map. |
| `unit_info_full.png` | 800x600 | Full window showing Unit Info menu with party member stats. |
| `unit_info.png` | 256x384 | Cropped view of Luso's detailed Unit Info, abilities, and equipment. |

### Visual Verification Criteria

1. **Difficulty Indicator**:
   - **Hard**: Displays an orange badge labelled `[ Hard ]` on the save preview card.
   - **Normal**: Displays a blue badge labelled `[ Normal ]`.
2. **Playtime**: Confirms hours, minutes, and seconds match expected values (e.g. `0:40:32`).
3. **Clan State**: Confirms clan leader name, clan title rank, and party unit count match
   the save payload.
4. **Unit Info & Stability**: Confirms dual-wielded weapons and ability sets render
   without triggering black screens or frozen animations.

---

## 6. Driving menus and battles (e2e harness)

The scenario drivers under `examples/melonds/e2e/` share a few hard-won rules:

- **D-pad steps need short taps.** Hold a direction 0.12 s per step. Holds of 0.4 s or more cross
  the game's key repeat and move two menu rows or two tiles (the old "down then A" that opened
  Attack actually selected Wait). `A` and `B` can keep 0.25 to 0.4 s holds.
- **Guard with pixels, not sleeps.** `dsbot.py` grabs raw frames through `mds.sh raw` and has
  detectors for the COMMANDS menu, the B (cancel) button, the attack forecast, the world map and
  the save slot cursor. Wait for the signature, then act. Pick signatures that cannot move: the
  COMMANDS header shifts up a row when a trait banner such as "Fleet of foot!" shows, the amber
  Config button at the bottom right does not.
- **RAM comes from two places.** `rsp.py` keeps the single gdb connection a session is allowed and
  answers small peeks in about 0.2 s (battle roster, map cursor, HP). Bulk dumps come from
  savestates (`mds.sh state <sdir> save <slot>`), never from the stub (12 minutes for 4 MiB).
  `docs/save_format_map.md` section 10 holds the battle addresses.
- **The gdb stub is single client.** Once that client leaves, the stub never accepts another and
  floods `melonds.log`. `mds.sh` appends to the log and truncates it every few seconds while the
  emulator lives, hard links `game.nds` instead of copying 128 MiB per session, and starts Xvfb
  under `setsid` so a dying parent shell cannot take the display down.
- **Touch works.** `mds.sh touch <sdir> x y` taps the bottom screen (DS coordinates) and moves
  the battle cursor like the stylus would.
- **Savestates need the menu.** Qt shortcuts such as Shift+F1 never fire without a window manager,
  so `mds.sh state` clicks File > Save state / Load state.
- **Check free space first** (`df -h /tmp`). A full tmpfs makes screenshots and the in-game save
  fail silently.

### Battle scenario

`scenarios/run_e5_full.sh` produces an in-battle quicksave with an injected unit.
`scenarios/run_e6_battle.py` resumes it and plays the fight with real attacks until VICTORY, mashes
through the results to the world map, saves to slot 1, stops melonDS to flush, validates the file,
diffs it against the pre-battle slot and reloads from the title screen, where the game's clan table
in RAM must equal the decrypted save byte for byte. See `examples/melonds/e2e/WALKTHROUGH.md` (E6).
