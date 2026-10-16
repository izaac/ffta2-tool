"""FFTA2 Command Line Interface."""

import argparse
import sys
from pathlib import Path

from ffta2_tool.arm_tools import extract_arm9, extract_overlays, inspect_nds_rom
from ffta2_tool.crypto import verify_save_checksum
from ffta2_tool.mappings import (
    get_item_name,
    get_job_name,
    get_race_name,
)
from ffta2_tool.patcher import META_SQUAD_BUILDS, apply_meta_squad
from ffta2_tool.save import FFTA2Save, auto_detect_save
from ffta2_tool.validator import validate_save, validate_unit

SAVE_HELP = "Path to .sav file (auto-detected from FFTA2_Backups and mounted media if omitted)"

SAVE_COMMANDS = {"verify", "info", "inventory", "set-weapon", "patch-meta-squad", "validate", "topup-stats"}


def resolve_save_file(requested: str | None) -> str | None:
    """Resolves an explicit save path or auto-detects one; returns None if unresolved."""
    if requested:
        p = Path(requested).expanduser()
        if not p.is_file():
            print(f"Error: Save file not found: {p}", file=sys.stderr)
            sys.exit(1)
        return str(p)
    detected = auto_detect_save()
    if detected:
        print(f"[*] Auto-detected save: {detected}")
    return detected


def cmd_validate(args: argparse.Namespace) -> int:
    save = FFTA2Save(args.save_file)
    issues = validate_save(save)
    if not issues:
        print("[PASS] All clan units pass NDS engine stability validation!")
        return 0
    print(f"[FAIL] Found {len(issues)} stability issues:")
    for iss in issues:
        print(f"  [{iss.severity}] Unit {iss.unit_index} ({iss.field}): {iss.message}")
    return 1


def cmd_topup_stats(args: argparse.Namespace) -> int:
    save = FFTA2Save(args.save_file)
    from ffta2_tool.stats import topup_clan_stats

    results = topup_clan_stats(save, max_units=args.units)
    if not results:
        print("[*] All clan units already have stats equal to or exceeding 115% god roll maximums.")
        return 0

    out_path = args.output if args.output else args.save_file
    save.save(out_path, backup=not args.no_backup)
    print(f"[SUCCESS] 115% God Roll stats applied to {len(results)} clan units: {out_path}!")
    for res in results:
        u_idx = res["unit_index"]
        job_str = get_job_name(res["job_id"])
        summary = ", ".join(f"{stat}: {old}->{new}" for stat, (old, new) in res["changes"].items())
        print(f"  Unit {u_idx} ({job_str}): {summary}")
    return 0


def cmd_patch_meta_squad(args: argparse.Namespace) -> int:
    save = FFTA2Save(args.save_file)

    # Pre-patch validation gate
    pre_issues = [i for i in validate_save(save) if i.severity == "ERROR"]
    if pre_issues:
        print(f"[WARNING] Save has {len(pre_issues)} pre-existing errors before patching:")
        for iss in pre_issues:
            print(f"  [{iss.severity}] Unit {iss.unit_index} ({iss.field}): {iss.message}")

    apply_meta_squad(
        save,
        inject_inventory=not args.no_inventory,
        inventory_count=args.count,
        master_abilities=not args.no_abilities,
        unlock_jobs=not args.no_jobs,
        topup_stats=not args.no_god_stats,
    )

    # Post-patch validation
    post_issues = [i for i in validate_save(save) if i.severity == "ERROR"]
    if post_issues:
        print(f"[ERROR] Post-patch validation failed with {len(post_issues)} errors! Aborting save.")
        for iss in post_issues:
            print(f"  [{iss.severity}] Unit {iss.unit_index} ({iss.field}): {iss.message}")
        return 1

    out_path = args.output if args.output else args.save_file
    save.save(out_path, backup=not args.no_backup)
    print(f"[SUCCESS] Meta squad successfully applied and verified: {out_path}!")
    for build in META_SQUAD_BUILDS:
        job_str = get_job_name(build["job_id"])
        w_str = get_item_name(build["weapon_id"])
        print(
            f"  Unit {build['slot']} ({build['name']}): "
            f"Job={job_str} (0x{build['job_id']:02X}), Weapon={w_str} (0x{build['weapon_id']:04X})"
        )

    if not args.no_inventory:
        print(
            f"  Clan Inventory: {args.count}x of all ability-learning weapons and endgame gear injected into clan bag."
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

    inv = save.get_inventory()
    print(f"Clan Inventory Items: {len(inv)} unique stacks registered")

    print("\n--- Party Roster ---")
    for i in range(6):
        unit = save.get_unit(i)
        if unit and (unit.character_id != 0 or unit.job_id != 0):
            job_str = get_job_name(unit.job_id)
            race_str = get_race_name(unit.race_id)
            w_str = get_item_name(unit.weapon_id)
            s_str = get_item_name(unit.shield_id)
            h_str = get_item_name(unit.helm_id)
            a_str = get_item_name(unit.armor_id)
            acc_str = get_item_name(unit.accessory_id)
            print(
                f"Unit {i:2d} ({race_str} {job_str}):\n"
                f"  Weapon: {w_str} (0x{unit.weapon_id:04X}) | Shield: {s_str} (0x{unit.shield_id:04X})\n"
                f"  Head:   {h_str} (0x{unit.helm_id:04X}) | Body:   {a_str} (0x{unit.armor_id:04X})\n"
                f"  Acc:    {acc_str} (0x{unit.accessory_id:04X})\n"
            )
    return 0


def cmd_inventory(args: argparse.Namespace) -> int:
    save = FFTA2Save(args.save_file)
    inv = save.get_inventory()
    print(f"=== Clan Inventory ({len(inv)} items) ===")
    for item_id, (total, eq) in sorted(inv.items()):
        name = get_item_name(item_id)
        print(f"  0x{item_id:04X}: {name:<24} Total={total:2d} (Equipped={eq:2d})")
    return 0


def cmd_set_weapon(args: argparse.Namespace) -> int:
    save = FFTA2Save(args.save_file)
    unit = save.get_unit(args.unit)
    if not unit:
        print(f"Error: Invalid unit index {args.unit}")
        return 1

    old_weapon = unit.weapon_id
    unit.weapon_id = args.item_id

    # Validation gate: protect against illegal item IDs or crash conditions
    issues = [i for i in validate_unit(unit) if i.severity == "ERROR"]
    if issues:
        print(f"[ERROR] Cannot equip item 0x{args.item_id:04X} on Unit {args.unit}:")
        for iss in issues:
            print(f"  [{iss.severity}] {iss.field}: {iss.message}")
        return 1

    save.sync_equipped_to_inventory()
    out_path = args.output if args.output else args.save_file
    save.save(out_path, backup=not args.no_backup)

    old_name = get_item_name(old_weapon)
    new_name = get_item_name(args.item_id)
    print(f"Unit {args.unit}: Weapon updated from {old_name} (0x{old_weapon:04X}) to {new_name} (0x{args.item_id:04X})")
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
    p_verify.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_verify.set_defaults(func=cmd_verify)

    # info
    p_info = subparsers.add_parser("info", help="Display save metadata, party info, and equipment")
    p_info.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_info.set_defaults(func=cmd_info)

    # inventory
    p_inv = subparsers.add_parser("inventory", help="List all items in the clan inventory bag")
    p_inv.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_inv.set_defaults(func=cmd_inventory)

    # set-weapon
    p_set = subparsers.add_parser("set-weapon", help="Change unit's equipped weapon and re-sign")
    p_set.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_set.add_argument("--unit", type=int, default=0, help="Unit index (default: 0)")
    p_set.add_argument("--item-id", type=int, required=True, help="Item ID to equip")
    p_set.add_argument("--output", "-o", help="Output save path (overwrites if omitted)")
    p_set.add_argument("--no-backup", action="store_true", help="Skip the pre-write timestamped backup snapshot")
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
    p_patch.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_patch.add_argument("--output", "-o", help="Output save path (overwrites if omitted)")
    p_patch.add_argument(
        "--count", "-c", type=int, default=50, help="Item quantity to inject into clan bag (default: 50)"
    )
    p_patch.add_argument(
        "--no-inventory", action="store_true", help="Skip injecting ability learning gear into clan inventory"
    )
    p_patch.add_argument("--no-abilities", action="store_true", help="Skip mastering all abilities for units")
    p_patch.add_argument("--no-jobs", action="store_true", help="Skip unlocking all jobs in clan data")
    p_patch.add_argument(
        "--no-god-stats", action="store_true", help="Skip topping up unit stats to 115%% god-roll maximums"
    )
    p_patch.add_argument("--no-backup", action="store_true", help="Skip the pre-write timestamped backup snapshot")
    p_patch.set_defaults(func=cmd_patch_meta_squad)

    # topup-stats
    p_topup = subparsers.add_parser("topup-stats", help="Top up clan units to 115%% god roll stats (non-destructive)")
    p_topup.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_topup.add_argument("--units", "-u", type=int, default=6, help="Number of clan unit slots to top up (default: 6)")
    p_topup.add_argument("--output", "-o", help="Output save path (overwrites if omitted)")
    p_topup.add_argument("--no-backup", action="store_true", help="Skip the pre-write timestamped backup snapshot")
    p_topup.set_defaults(func=cmd_topup_stats)

    # validate
    p_val = subparsers.add_parser("validate", help="Validate clan units against NDS UI crash conditions")
    p_val.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_val.set_defaults(func=cmd_validate)

    args = parser.parse_args()

    # Auto-detect the save file when a command needs one and none was supplied
    if args.command in SAVE_COMMANDS:
        args.save_file = resolve_save_file(args.save_file)
        if args.save_file is None:
            print(
                "Error: No save file specified and none found in ~/Documents/FFTA2_Backups, "
                "mounted media, or the current directory.",
                file=sys.stderr,
            )
            sys.exit(1)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
