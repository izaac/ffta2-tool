#!/usr/bin/env python3
"""FFTA2 Save Inspection Script.

Portable tool to inspect save states, story flags, active quests, and squad status.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

# Ensure package is importable relative to script directory
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from ffta2_tool.rom import FFTA2Rom
from ffta2_tool.save import FFTA2Save, auto_detect_save


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect FFTA2 save file progression, flags, and units.")
    parser.add_argument(
        "--save",
        type=str,
        default=None,
        help="Path to FFTA2 .sav file (defaults to auto-detection on removable media / backups)",
    )
    args = parser.parse_args()

    raw_path = args.save if args.save else auto_detect_save()
    if not raw_path:
        print("Error: No valid FFTA2 save file specified or found.", file=sys.stderr)
        sys.exit(1)

    save_path = Path(raw_path)
    if not save_path.is_file():
        print(f"Error: Save file does not exist: {save_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading save: {save_path}")
    save = FFTA2Save(save_path)
    pt = save.plaintext

    # Story progression word at 0x02834
    story_flag = struct.unpack_from("<H", pt, 0x02834)[0]

    # Active quest slot at 0x2962
    active_quest_id = struct.unpack_from("<H", pt, 0x2962)[0] if len(pt) > 0x2964 else 0

    print("=== Story Progression ===")
    print(f"Story Progress Flag (0x02834): 0x{story_flag:04X} ({story_flag})")
    print(f"Active Accepted Quest Slot:    ID {active_quest_id}")

    # Cross-reference with ROM if available
    try:
        rom = FFTA2Rom()
        quests = {q["id"]: q for q in rom.get_all_quests()}
        if active_quest_id in quests:
            aq = quests[active_quest_id]
            print(f'  -> Title:       "{aq["name"]}"')
            print(f"  -> Location:    [{aq['location_id']}] {aq['location_name']}")
            print(f"  -> Story Req:   0x{aq['story_req']:04X}")
    except Exception:
        pass

    print("\n=== Clan Squad Status ===")
    for i in range(6):
        u = save.get_unit(i)
        if u and (u.max_hp > 0 or u.character_id != 0):
            print(
                f"Unit {i}: CharID=0x{u.character_id:02X} JobID=0x{u.job_id:02X} Level={u.level:<2d} "
                f"HP={u.cur_hp:>3d}/{u.max_hp:<3d} MP={u.cur_mp:>2d}/{u.max_mp:<2d} "
                f"Atk={u.attack} Def={u.defense} Spd={u.speed}"
            )


if __name__ == "__main__":
    main()
