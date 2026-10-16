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
# Verify save file checksum
python3 -m ffta2_tool.cli verify path/to/save.sav

# Inspect save metadata and party roster
python3 -m ffta2_tool.cli info path/to/save.sav

# Equip weapon on a unit (e.g. Unit 0 with Chirijiraden, ID 24)
python3 -m ffta2_tool.cli set-weapon path/to/save.sav --unit 0 --item-id 24

# Inspect ROM headers
python3 -m ffta2_tool.cli rom-info path/to/game.nds

# Extract ARM9 binary from ROM
python3 -m ffta2_tool.cli rom-extract path/to/game.nds -o arm9.bin
```

## Documentation
- [Save Architecture Reference](docs/save_architecture.md): Complete technical breakdown of save layout, cipher algorithms, and ARM9 disassembly offsets.
