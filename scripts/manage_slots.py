#!/usr/bin/env python3
"""FFTA2 Multi-Slot Save Management CLI Tool.

Enables inspecting, importing, exporting, and cloning save slots (Slot 1 and Slot 2)
in 512 KB FFTA2 EEPROM save files with automatic checksumming and dual-bank mirroring.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure package is importable relative to script directory
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from ffta2_tool.save import FFTA2Save, auto_detect_save
from ffta2_tool.slots import SlotManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage FFTA2 save slots (inspect, copy, import, mirror).")
    parser.add_argument(
        "--save",
        type=str,
        default=None,
        help="Path to 512 KB FFTA2 .sav file (auto-detected if omitted)",
    )

    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    # list
    subparsers.add_parser("list", help="List and verify all save slots in the file")

    # import
    p_import = subparsers.add_parser("import", help="Import a backup save into Slot 1 or Slot 2")
    p_import.add_argument("--slot", type=int, required=True, choices=[1, 2], help="Target slot (1 or 2)")
    p_import.add_argument("--from-file", type=str, required=True, help="Source .sav backup file to import")

    # copy
    p_copy = subparsers.add_parser("copy", help="Copy one slot to another slot inside the save")
    p_copy.add_argument("--src", type=int, required=True, choices=[1, 2], help="Source slot (1 or 2)")
    p_copy.add_argument("--dst", type=int, required=True, choices=[1, 2], help="Destination slot (1 or 2)")

    # mirror
    subparsers.add_parser("mirror", help="Mirror Bank 1 (0x00000) to Bank 2 (0x40000) for flashcart compatibility")

    # wipe-quicksave
    subparsers.add_parser("wipe-quicksave", help="Completely deactivate and wipe quicksave slot")

    # set-difficulty
    p_diff = subparsers.add_parser("set-difficulty", help="Set difficulty for a slot (hard or normal)")
    p_diff.add_argument("--slot", type=int, required=True, choices=[1, 2], help="Target slot (1 or 2)")
    p_diff.add_argument(
        "--difficulty",
        type=str,
        required=True,
        choices=["hard", "normal"],
        help="Difficulty setting (hard or normal)",
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

    sm = SlotManager(save_path.read_bytes())

    if args.action in (None, "list"):
        print(f"=== Save Slot Overview: {save_path} ===")
        for s in (0, 1):
            prev = sm.get_slot_preview(s)
            valid, stored, calc = sm.verify_slot(s)
            status = "VALID" if valid else "INVALID"
            print(f"[{status}] Slot {s + 1}:")
            print(f"       Leader:       {prev['leader_name']}")
            print(f"       Difficulty:   {prev.get('difficulty_label', 'Unknown')}")
            print(f"       Party Size:   {prev['member_count']} units")
            print(f"       Quests:       {prev['cleared_quests']}")
            print(f"       Play Time:    {prev['play_time_formatted']}")
            print(f"       Active Flag:  {prev['active']}")
            print(f"       Checksum:     Stored=0x{stored:08X}, Calc=0x{calc:08X}")
        is_mirrored = sm.raw[:0x40000] == sm.raw[0x40000:0x80000]
        print(f"Dual-Bank Mirror:    {'SYNCHRONIZED' if is_mirrored else 'OUT OF SYNC'}")
        return

    if args.action == "import":
        src_path = Path(args.from_file)
        if not src_path.is_file():
            print(f"Error: Source file does not exist: {src_path}", file=sys.stderr)
            sys.exit(1)

        src_save = FFTA2Save(src_path)
        payload = src_save.plaintext[0x01C0 : 0x01C0 + 0x3400]
        target_idx = args.slot - 1

        print(f"Importing {src_path} into Slot {args.slot}...")
        sm.put_slot_payload(slot_idx=target_idx, plaintext_payload=payload, seed=0x0031 if target_idx == 1 else 0x0027)
        sm.save_to_file(save_path)
        print(f"[SUCCESS] Slot {args.slot} imported and dual-bank mirrored into {save_path}!")
        return

    if args.action == "copy":
        src_idx = args.src - 1
        dst_idx = args.dst - 1
        _, seed, payload = sm.get_slot_payload(src_idx)

        print(f"Copying Slot {args.src} -> Slot {args.dst}...")
        sm.put_slot_payload(slot_idx=dst_idx, plaintext_payload=payload, seed=0x0031 if dst_idx == 1 else 0x0027)
        sm.save_to_file(save_path)
        print(f"[SUCCESS] Slot {args.src} copied to Slot {args.dst} and dual-bank mirrored!")
        return

    if args.action == "mirror":
        sm.raw[0x40000:0x80000] = sm.raw[:0x40000]
        sm.save_to_file(save_path)
        print(f"[SUCCESS] Bank 1 mirrored to Bank 2 in {save_path}!")
        return

    if args.action == "wipe-quicksave":
        sm.deactivate_quicksave()
        sm.save_to_file(save_path)
        print(f"[SUCCESS] Quicksave wiped and deactivated in {save_path}!")
        return

    if args.action == "set-difficulty":
        target_idx = args.slot - 1
        diff_val = 1 if args.difficulty.lower() == "hard" else 2
        sm.set_slot_difficulty(target_idx, diff_val)
        sm.save_to_file(save_path)
        diff_name = "Hard" if diff_val == 1 else "Normal"
        print(f"[SUCCESS] Slot {args.slot} difficulty set to {diff_name} and dual-bank mirrored!")
        return


if __name__ == "__main__":
    main()
