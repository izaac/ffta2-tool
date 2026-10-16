"""FFTA2 Command Line Interface."""

import argparse
import sys
from pathlib import Path

from ffta2_tool.crypto import verify_save_checksum
from ffta2_tool.save import FFTA2Save
from ffta2_tool.arm_tools import inspect_nds_rom, extract_arm9, extract_overlays
from ffta2_tool.patcher import apply_meta_squad, META_SQUAD_BUILDS


def cmd_patch_meta_squad(args: argparse.Namespace) -> int:
    save = FFTA2Save(args.save_file)
    apply_meta_squad(save, master_abilities=args.master_abilities)
    out_path = args.output if args.output else args.save_file
    save.save(out_path)
    print(f"[SUCCESS] Meta squad successfully applied to {out_path}!")
    for build in META_SQUAD_BUILDS:
        print(
            f"  Unit {build['slot']} ({build['name']}): "
            f"Job 0x{build['job_id']:02X}, Primary 0x{build['primary_set']:02X}, "
            f"Secondary 0x{build['secondary_set']:02X}, Weapon 0x{build['weapon_id']:04X}"
        )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    save_bytes = Path(args.save_file).read_bytes()
    is_valid, stored, calculated = verify_save_checksum(save_bytes)
    print(f"File:       {args.save_file}")
    print(f"Stored:     0x{stored:08X}")
    print(f"Calculated: 0x{calculated:08X}")
    if is_valid:
        print("[PASS] Checksum is VALID!")
        return 0
    else:
        print("[FAIL] Checksum MISMATCH (Save corrupted)!")
        return 1


def cmd_info(args: argparse.Namespace) -> int:
    save = FFTA2Save(args.save_file)
    print(f"=== FFTA2 Save: {args.save_file} ===")
    print(f"Slot 0 Leader Name: {save.slot_0_player_name}")

    is_valid, stored, calc = verify_save_checksum(save.raw_data)
    print(f"Checksum: 0x{stored:08X} ({'VALID' if is_valid else 'INVALID'})")

    print("\n--- Party Roster ---")
    for i in range(6):
        unit = save.get_unit(i)
        if unit and (unit.character_id != 0 or unit.job_id != 0):
            print(
                f"Unit {i:2d}: CharID=0x{unit.character_id:02X} JobID=0x{unit.job_id:02X} "
                f"Weapon=0x{unit.weapon_id:04X} Shield=0x{unit.shield_id:04X} Helm=0x{unit.helm_id:04X} Armor=0x{unit.armor_id:04X}"
            )
    return 0


def cmd_set_weapon(args: argparse.Namespace) -> int:
    save = FFTA2Save(args.save_file)
    unit = save.get_unit(args.unit)
    if not unit:
        print(f"Error: Invalid unit index {args.unit}")
        return 1

    old_weapon = unit.weapon_id
    unit.weapon_id = args.item_id
    out_path = args.output if args.output else args.save_file
    save.save(out_path)

    print(f"Unit {args.unit}: Weapon updated from 0x{old_weapon:02X} ({old_weapon}) to 0x{args.item_id:02X} ({args.item_id})")
    print(f"Saved and signed: {out_path}")
    return 0


def cmd_rom_inspect(args: argparse.Namespace) -> int:
    info = inspect_nds_rom(args.rom_file)
    print(f"=== NDS ROM: {args.rom_file} ===")
    for k, v in info.items():
        if isinstance(v, int):
            print(f"{k:<16}: 0x{v:X} ({v})")
        else:
            print(f"{k:<16}: {v}")
    return 0


def cmd_rom_extract(args: argparse.Namespace) -> int:
    out_arm9 = extract_arm9(args.rom_file, args.output)
    print(f"Extracted ARM9 binary to: {out_arm9}")
    if args.overlays_dir:
        ovs = extract_overlays(args.rom_file, args.overlays_dir)
        print(f"Extracted {len(ovs)} overlays to: {args.overlays_dir}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="FFTA2 Save and ARM Reverse Engineering CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # verify
    p_verify = subparsers.add_parser("verify", help="Verify save file checksum")
    p_verify.add_argument("save_file", help="Path to .sav file")
    p_verify.set_defaults(func=cmd_verify)

    # info
    p_info = subparsers.add_parser("info", help="Display save metadata and party info")
    p_info.add_argument("save_file", help="Path to .sav file")
    p_info.set_defaults(func=cmd_info)

    # set-weapon
    p_set = subparsers.add_parser("set-weapon", help="Change unit's equipped weapon and re-sign")
    p_set.add_argument("save_file", help="Path to .sav file")
    p_set.add_argument("--unit", type=int, default=0, help="Unit index (default: 0)")
    p_set.add_argument("--item-id", type=int, required=True, help="Item ID to equip")
    p_set.add_argument("--output", "-o", help="Output save path (overwrites if omitted)")
    p_set.set_defaults(func=cmd_set_weapon)

    # rom-info
    p_rom = subparsers.add_parser("rom-info", help="Inspect NDS ROM headers and offsets")
    p_rom.add_argument("rom_file", help="Path to .nds file")
    p_rom.set_defaults(func=cmd_rom_inspect)

    # rom-extract
    p_ext = subparsers.add_parser("rom-extract", help="Extract ARM9 and overlays from ROM")
    p_ext.add_argument("rom_file", help="Path to .nds file")
    p_ext.add_argument("--output", "-o", default="arm9.bin", help="ARM9 output file")
    p_ext.add_argument("--overlays-dir", help="Optional directory to extract overlays to")
    p_ext.set_defaults(func=cmd_rom_extract)

    # patch-meta-squad
    p_patch = subparsers.add_parser("patch-meta-squad", help="Apply verified meta squad builds to save")
    p_patch.add_argument("save_file", help="Path to .sav file")
    p_patch.add_argument("--output", "-o", help="Output save path (overwrites if omitted)")
    p_patch.add_argument("--master-abilities", action="store_true", help="Force master all abilities (may cause UI glitches)")
    p_patch.set_defaults(func=cmd_patch_meta_squad)


    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
