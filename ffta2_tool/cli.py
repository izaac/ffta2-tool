"""FFTA2 Command Line Interface."""

import argparse
import sys
from pathlib import Path

from ffta2_tool.arm_tools import extract_arm9, extract_overlays, inspect_nds_rom
from ffta2_tool.mappings import (
    get_item_name,
    get_job_name,
    get_race_name,
)
from ffta2_tool.patcher import META_SQUAD_BUILDS, apply_meta_squad
from ffta2_tool.save import FFTA2Save, auto_detect_save
from ffta2_tool.slots import SlotManager
from ffta2_tool.validator import validate_save, validate_unit

SAVE_HELP = "Path to .sav file (auto-detected from FFTA2_Backups and mounted media if omitted)"

SAVE_COMMANDS = {
    "verify",
    "info",
    "inventory",
    "set-weapon",
    "patch-meta-squad",
    "validate",
    "topup-stats",
    "set-difficulty",
    "master-abilities",
    "clan",
}


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


def cmd_set_difficulty(args: argparse.Namespace) -> int:
    slot_idx = getattr(args, "slot", 1) - 1
    save = FFTA2Save(args.save_file, slot=slot_idx)
    target = 1 if args.difficulty == "hard" else 2
    save.difficulty = target
    out_path = args.output if args.output else args.save_file
    save.save(out_path, backup=not args.no_backup)
    print(f"[SUCCESS] Slot {slot_idx + 1} difficulty set to {args.difficulty.capitalize()} and signed: {out_path}!")
    return 0


def cmd_master_abilities(args: argparse.Namespace) -> int:
    slot_idx = getattr(args, "slot", 1) - 1
    save = FFTA2Save(args.save_file, slot=slot_idx)
    target_unit = getattr(args, "unit", None)
    unit_idx = target_unit - 1 if target_unit is not None else None

    count = save.master_all_unit_abilities(unit_idx)
    target_desc = f"Unit {target_unit}" if target_unit is not None else f"all {count} recruited clan units"

    out_path = args.output if args.output else args.save_file
    save.save(out_path, backup=not args.no_backup)
    print(f"[SUCCESS] Mastered abilities for {target_desc} in Slot {slot_idx + 1}: {out_path}!")
    return 0


def cmd_clan(args: argparse.Namespace) -> int:
    slot_idx = getattr(args, "slot", 1) - 1
    save = FFTA2Save(args.save_file, slot=slot_idx)

    actions = []
    if args.all or args.gil is not None:
        val = 99999999 if args.all or args.gil is None else args.gil
        save.gil = val
        actions.append(f"Gil={save.gil:,}")

    if args.all or args.cp is not None:
        val = 9999 if args.all or args.cp is None else args.cp
        save.clan_points = val
        actions.append(f"CP={save.clan_points}")

    if args.all or args.talents:
        save.clan_talents = (99, 99, 99, 99)
        actions.append("Talents=99/99/99/99")

    if args.all or args.privileges:
        save.unlock_clan_privileges()
        actions.append("64 Clan Privileges unlocked")

    if not actions:
        print("No clan options specified. Use --all, --gil, --cp, --privileges, or --talents.", file=sys.stderr)
        return 1

    out_path = args.output if args.output else args.save_file
    save.save(out_path, backup=not args.no_backup)
    print(f"[SUCCESS] Slot {slot_idx + 1} clan updated ({', '.join(actions)}): {out_path}!")
    return 0


def cmd_patch_meta_squad(args: argparse.Namespace) -> int:
    save = FFTA2Save(args.save_file)

    # Pre-patch validation gate
    pre_issues = [i for i in validate_save(save) if i.severity == "ERROR"]
    if pre_issues:
        print(f"[WARNING] Save has {len(pre_issues)} pre-existing errors before patching:")
        for iss in pre_issues:
            print(f"  [{iss.severity}] Unit {iss.unit_index} ({iss.field}): {iss.message}")

    if getattr(args, "difficulty", None):
        save.difficulty = 1 if args.difficulty == "hard" else 2

    apply_meta_squad(
        save,
        inject_inventory=not args.no_inventory,
        inventory_count=args.count,
        master_abilities=args.master_abilities,
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
    # Verify the records the game actually loads for each slot (they move on every save)
    sm = SlotManager(Path(args.save_file).read_bytes())
    print(f"File:       {args.save_file}")
    all_valid = True
    found = False
    for slot in (0, 1):
        if not sm.has_data(slot):
            print(f"Slot {slot + 1}:     No data")
            continue
        found = True
        is_valid, stored, calculated = sm.verify_slot(slot)
        all_valid = all_valid and is_valid
        print(
            f"Slot {slot + 1}:     record 0x{sm.record_offset(slot):04X} "
            f"stored=0x{stored:08X} calculated=0x{calculated:08X} {'VALID' if is_valid else 'MISMATCH'}"
        )
    if found and all_valid:
        print("[PASS] Checksum is VALID!")
        return 0
    print("[FAIL] Checksum MISMATCH (Save corrupted)!" if found else "[FAIL] No save data in either slot!")
    return 1


def cmd_info(args: argparse.Namespace) -> int:
    save = FFTA2Save(args.save_file)
    print(f"=== FFTA2 Save: {args.save_file} ===")
    print(f"Slot 0 Leader Name: {save.slot_0_player_name}")
    diff_val = save.difficulty
    diff_str = "Hard" if diff_val == 1 else ("Normal" if diff_val == 2 else f"Unknown ({diff_val})")
    print(f"Difficulty:         {diff_str}")

    is_valid, stored, calc = SlotManager(save.raw_data).verify_slot(save.slot)
    print(f"Checksum: 0x{stored:08X} ({'VALID' if is_valid else 'INVALID'}) at record 0x{save.record_base:04X}")

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
    p_patch.add_argument(
        "--master-abilities",
        action="store_true",
        help="Fill unit ability array with 0xFF (also masters other races' and '???' jobs; off by default)",
    )
    p_patch.add_argument("--no-jobs", action="store_true", help="Skip unlocking all jobs in clan data")
    p_patch.add_argument(
        "--no-god-stats", action="store_true", help="Skip topping up unit stats to 115%% god-roll maximums"
    )
    p_patch.add_argument(
        "--difficulty",
        "-d",
        choices=["hard", "normal"],
        help="Override difficulty setting (hard or normal; keeps current if omitted)",
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

    # set-difficulty
    p_diff = subparsers.add_parser("set-difficulty", help="Set difficulty setting for a save slot")
    p_diff.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_diff.add_argument(
        "--difficulty",
        "-d",
        choices=["hard", "normal"],
        required=True,
        help="Difficulty level to set (hard or normal)",
    )
    p_diff.add_argument(
        "--slot",
        type=int,
        choices=[1, 2],
        default=1,
        help="Slot index to modify (1 or 2, default: 1)",
    )
    p_diff.add_argument("--output", "-o", help="Output save path (overwrites if omitted)")
    p_diff.add_argument("--no-backup", action="store_true", help="Skip the pre-write timestamped backup snapshot")
    p_diff.set_defaults(func=cmd_set_difficulty)

    # validate
    p_val = subparsers.add_parser("validate", help="Validate clan units against NDS UI crash conditions")
    p_val.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_val.set_defaults(func=cmd_validate)

    # master-abilities
    p_mab = subparsers.add_parser("master-abilities", help="Master all job abilities (AP max) for units on demand")
    p_mab.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_mab.add_argument(
        "--unit",
        "-u",
        type=int,
        choices=range(1, 25),
        default=None,
        help="Specific unit index to master (1..24; masters all recruited units if omitted)",
    )
    p_mab.add_argument(
        "--slot",
        type=int,
        choices=[1, 2],
        default=1,
        help="Slot index to modify (1 or 2, default: 1)",
    )
    p_mab.add_argument("--output", "-o", help="Output save path (overwrites if omitted)")
    p_mab.add_argument("--no-backup", action="store_true", help="Skip the pre-write timestamped backup snapshot")
    p_mab.set_defaults(func=cmd_master_abilities)

    # clan
    p_clan = subparsers.add_parser("clan", help="Manage clan perks: max Gil, CP, talents, and Clan Privileges")
    p_clan.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_clan.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Max out Gil (99,999,999), CP (9999), Talents (99), and unlock all 64 Clan Privileges",
    )
    p_clan.add_argument(
        "--gil",
        "-g",
        type=int,
        nargs="?",
        const=99999999,
        default=None,
        help="Set Gil balance (default if flag passed without value: 99,999,999)",
    )
    p_clan.add_argument(
        "--cp",
        type=int,
        nargs="?",
        const=9999,
        default=None,
        help="Set Clan Points (default if flag passed without value: 9999)",
    )
    p_clan.add_argument(
        "--privileges",
        "-p",
        action="store_true",
        help="Unlock all 64 Clan Privileges in the Judge menu",
    )
    p_clan.add_argument(
        "--talents",
        "-t",
        action="store_true",
        help="Set all four Clan Talents (Negotiation, Aptitude, Teamwork, Adaptability) to 99",
    )
    p_clan.add_argument(
        "--slot",
        type=int,
        choices=[1, 2],
        default=1,
        help="Slot index to modify (1 or 2, default: 1)",
    )
    p_clan.add_argument("--output", "-o", help="Output save path (overwrites if omitted)")
    p_clan.add_argument("--no-backup", action="store_true", help="Skip the pre-write timestamped backup snapshot")
    p_clan.set_defaults(func=cmd_clan)

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
