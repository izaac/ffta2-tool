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
