#!/usr/bin/env python3
"""FFTA2 ROM Inspection Script.

Portable tool to inspect internal files, quests, story requirements, and location data.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure package is importable relative to script directory
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from ffta2_tool.rom import FFTA2Rom


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect FFTA2 NDS ROM data, quests, and locations.")
    parser.add_argument(
        "--rom",
        type=str,
        default=None,
        help="Path to FFTA2 .nds ROM file (defaults to FFTA2_ROM_PATH or /tmp/ffta2_game.nds)",
    )
    parser.add_argument("--quests", action="store_true", help="List all quests with story/flag requirements")
    parser.add_argument("--locations", action="store_true", help="List all decoded world locations")
    parser.add_argument("--filter", type=str, default="", help="Filter quests by title keyword")
    parser.add_argument("--file", type=str, default=None, help="Inspect internal ROM file by archive path")

    args = parser.parse_args()

    try:
        rom = FFTA2Rom(args.rom)
    except FileNotFoundError as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    if args.file:
        data = rom.get_file(args.file)
        if data is None:
            print(f"File not found in ROM archive: {args.file}")
        else:
            print(f"File: {args.file} (size: {len(data)} bytes, hex preview: {data[:32].hex(' ')})")
        return

    if args.locations:
        locs = rom.get_locations()
        print(f"=== Decoded Locations ({len(locs)} total) ===")
        for idx, loc in enumerate(locs):
            print(f"[{idx:3d}] {loc}")
        return

    # Default to quests view if --quests or no other action specified
    quests = rom.get_all_quests()
    if args.filter:
        quests = [q for q in quests if args.filter.lower() in q["name"].lower()]

    print(f"=== FFTA2 Quests ({len(quests)} shown) ===")
    for q in quests:
        if q["id"] == 0 and not q["name"]:
            continue
        print(
            f"Quest {q['id']:3d} | Rank {q['rank']:2d} | StoryReq 0x{q['story_req']:04X} | "
            f"FlagReq 0x{q['flag_req']:04X} | Loc [{q['location_id']:2d}] {q['location_name']:<20} | {q['name']}"
        )


if __name__ == "__main__":
    main()
