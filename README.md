# FFTA2 Tool

Save editor and reverse engineering toolkit for **Final Fantasy Tactics A2: Grimoire of the Rift** (Nintendo DS).

## Features

- **Pure Python**: Zero heavy external dependencies.
- **Save Cryptography**: Native support for FFTA2's additive byte-stream cipher.
- **Checksum Calculation**: Exact replication of the game's signed byte (`LDRSB`) weighted checksum routine (`0x0210D560`).
- **Party & Equipment Management**: Direct inspection and modification of party units, equipment slots, and stats.
- **ROM Tools**: Utilities to inspect NDS ROM headers and extract ARM9 and overlay binaries.

## CLI Usage

```bash
# Inspect save metadata, clan stats, and recruited party roster (1-based units 1..24)
python3 -m ffta2_tool.cli info path/to/save.sav

# Create a standalone timestamped backup snapshot in ~/Documents/FFTA2_Backups
python3 -m ffta2_tool.cli backup path/to/save.sav

# Rename Unit 1 (Luso, freeform string), a generic unit (ROM character name/ID), or the clan
python3 -m ffta2_tool.cli rename path/to/save.sav --unit 1 --name "Ramza" --clan-name "Beoulve"
python3 -m ffta2_tool.cli rename path/to/save.sav --unit 2 --name "Frimelda"

# Inject a new recruit into the next empty clan slot (by build key, job name, or job ID)
python3 -m ffta2_tool.cli inject path/to/save.sav --job viera --level 50 --name "Frimelda" --master-abilities
python3 -m ffta2_tool.cli inject path/to/save.sav --job "Nu Mou Sage" --level 99

# Equip a single unit with a build from builds.toml
python3 -m ffta2_tool.cli equip-build path/to/save.sav --unit 2 --build nu_mou --master-abilities

# Patch the full 6-unit verified meta squad, clan perks, and difficulty
python3 -m ffta2_tool.cli patch-meta-squad path/to/save.sav --difficulty hard
python3 -m ffta2_tool.cli clan path/to/save.sav --all

# Verify save checksums and unit stability rules
python3 -m ffta2_tool.cli verify path/to/save.sav
python3 -m ffta2_tool.cli validate path/to/save.sav
```

Copy `config.example.toml` to `config.toml` (or `~/.config/ffta2-tool/config.toml`) or pass `--config path/to/config.toml` to customize save auto-detection paths, default slot (`1` or `2`), and `backup_dir`.

## Documentation

- [Save Architecture Reference](docs/save_architecture.md): Complete technical breakdown of save layout, cipher algorithms, and ARM9 disassembly offsets.
- [Meta Squad Strategy Specification](docs/meta_squad_strategy.md): Verified builds, legal proficiencies, and endgame gear.
- [MelonDS Headless Debugging](docs/melonds_headless_debugging.md): Automated emulation testing, headless Xvfb runner, load screen verification and battle driving rules.
- [MelonDS E2E Walkthrough](examples/melonds/e2e/WALKTHROUGH.md): Replayable in-game proofs of rename, inject, full roster, a won battle, the world map save and a cold reload.
- [Save Format Map](docs/save_format_map.md): Every verified address, including the in-battle RAM layout.
