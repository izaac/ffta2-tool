"""FFTA2 Command Line Interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ffta2_tool.arm_tools import extract_arm9, extract_overlays, inspect_nds_rom
from ffta2_tool.config import load_config
from ffta2_tool.mappings import (
    get_item_name,
    get_job_name,
    get_race_name,
)
from ffta2_tool.patcher import META_SQUAD_BUILDS, apply_meta_squad, equip_unit_build
from ffta2_tool.save import MAX_UNITS, FFTA2Save, auto_detect_save, create_backup_snapshot
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
    "rename",
    "inject",
    "equip-build",
    "backup",
}


def resolve_save_file(requested: str | None, cfg: dict[str, Any] | None = None) -> str | None:
    """Resolves an explicit save path, config.toml default, or auto-detects one; returns None if unresolved."""
    if requested:
        p = Path(requested).expanduser()
        if not p.is_file():
            print(f"Error: Save file not found: {p}", file=sys.stderr)
            sys.exit(1)
        return str(p)

    paths_cfg = (cfg or {}).get("paths", {})
    cfg_save = paths_cfg.get("save_file")
    if cfg_save:
        p = Path(str(cfg_save)).expanduser()
        if p.is_file():
            print(f"[*] Using configured save: {p}")
            return str(p)

    search_paths = paths_cfg.get("search_paths") or paths_cfg.get("save_search_paths")
    if not isinstance(search_paths, list):
        search_paths = None
    detected = auto_detect_save(search_paths=search_paths)
    if detected:
        print(f"[*] Auto-detected save: {detected}")
    return detected


def _add_slot_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--slot",
        type=int,
        choices=[1, 2],
        default=None,
        help="Slot index to inspect or modify (1 or 2, default: 1 or config.toml default)",
    )


def _add_common_write_args(parser: argparse.ArgumentParser) -> None:
    _add_slot_arg(parser)
    parser.add_argument("--output", "-o", help="Output save path (overwrites if omitted)")
    parser.add_argument("--no-backup", action="store_true", help="Skip the pre-write timestamped backup snapshot")
    parser.add_argument("--config", help="Path to user config.toml")


def _slot_idx(args: argparse.Namespace) -> int:
    slot = getattr(args, "slot", None)
    if slot in (1, 2):
        return slot - 1
    cfg = getattr(args, "_cfg", None) or {}
    cfg_slot = cfg.get("defaults", {}).get("slot", 1)
    return 1 if cfg_slot == 2 else 0


def _save_with_args(save: FFTA2Save, args: argparse.Namespace) -> Path:
    out_path = getattr(args, "output", None) or args.save_file
    cfg = getattr(args, "_cfg", None) or {}
    cfg_backup = cfg.get("defaults", {}).get("backup", True)
    do_backup = bool(cfg_backup) and not getattr(args, "no_backup", False)
    backup_dir = cfg.get("paths", {}).get("backup_dir")
    return save.save(out_path, backup=do_backup, backup_dir=backup_dir)


def cmd_backup(args: argparse.Namespace) -> int:
    cfg = getattr(args, "_cfg", None) or {}
    backup_dir = getattr(args, "backup_dir", None) or cfg.get("paths", {}).get("backup_dir")
    snap = create_backup_snapshot(args.save_file, backup_dir=backup_dir)
    print(f"[SUCCESS] Backup snapshot created: {snap}")
    return 0


def _format_issue_target(unit_index: int) -> str:
    return "Save" if unit_index < 0 else f"Unit {unit_index + 1}"


def _run_pre_write_gate(save: FFTA2Save, context: str) -> bool:
    """Run validate_save before writing; print errors and return False if any ERROR is found."""
    errors = [i for i in validate_save(save) if i.severity == "ERROR"]
    if errors:
        print(f"[ERROR] {context} failed validation with {len(errors)} errors! Aborting save.", file=sys.stderr)
        for iss in errors:
            print(
                f"  [{iss.severity}] {_format_issue_target(iss.unit_index)} ({iss.field}): {iss.message}",
                file=sys.stderr,
            )
        return False
    return True


def cmd_rename(args: argparse.Namespace) -> int:
    import warnings

    slot_idx = _slot_idx(args)
    save = FFTA2Save(args.save_file, slot=slot_idx)
    changes: list[str] = []
    force = bool(getattr(args, "force", False))

    if getattr(args, "name", None) is not None:
        unit_idx = args.unit - 1
        old_name = save.get_unit_name(unit_idx)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", UserWarning)
            new_name = save.rename_unit(unit_idx, args.name, force=force)
        for w in caught:
            print(f"[WARNING] {w.message}")
        changes.append(f"Unit {args.unit}: '{old_name}' -> '{new_name}'")

    if getattr(args, "clan_name", None) is not None:
        old_clan = save.clan_name
        save.clan_name = args.clan_name
        changes.append(f"Clan: '{old_clan}' -> '{save.clan_name}'")

    if not changes:
        print("Error: Specify --name/-n to rename a unit or --clan-name to rename the clan.", file=sys.stderr)
        return 1

    if not _run_pre_write_gate(save, "Rename"):
        return 1

    out_path = _save_with_args(save, args)
    print(f"[SUCCESS] Slot {slot_idx + 1} renamed ({', '.join(changes)}): {out_path}!")
    return 0


def cmd_inject(args: argparse.Namespace) -> int:
    import warnings

    slot_idx = _slot_idx(args)
    save = FFTA2Save(args.save_file, slot=slot_idx)
    target_unit = getattr(args, "unit", None)
    unit_idx = target_unit - 1 if target_unit is not None else None
    force = bool(getattr(args, "force", False))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        injected_idx, unit = save.inject_unit(
            args.job,
            level=args.level,
            name=args.name,
            unit_index=unit_idx,
            master_abilities=args.master_abilities,
            force=force,
        )
    for w in caught:
        print(f"[WARNING] {w.message}")

    if not _run_pre_write_gate(save, f"Injected Unit {injected_idx + 1}"):
        return 1

    out_path = _save_with_args(save, args)
    u_name = save.get_unit_name(injected_idx)
    r_name = get_race_name(unit.race_id)
    j_name = get_job_name(unit.job_id)
    print(
        f"[SUCCESS] Injected Unit {injected_idx + 1} [{u_name}] "
        f"({r_name} {j_name} Lv.{unit.level}) into Slot {slot_idx + 1}: {out_path}!"
    )
    return 0


def cmd_equip_build(args: argparse.Namespace) -> int:
    slot_idx = _slot_idx(args)
    save = FFTA2Save(args.save_file, slot=slot_idx)
    unit_idx = args.unit - 1

    build = equip_unit_build(
        save,
        unit_idx,
        args.build,
        master_abilities=args.master_abilities,
        topup_stats=not args.no_god_stats,
    )
    unit = save.get_unit(unit_idx)
    if unit is None:
        sys.stderr.write(f"Error: Unit {args.unit} not found\n")
        return 1

    if not _run_pre_write_gate(save, f"Build '{args.build}' on Unit {args.unit}"):
        return 1

    out_path = _save_with_args(save, args)
    u_name = save.get_unit_name(unit_idx)
    j_name = get_job_name(unit.job_id)
    w_name = get_item_name(unit.weapon_id)
    print(
        f"[SUCCESS] Equipped build '{build.get('key', build['name'])}' on Slot {slot_idx + 1} "
        f"Unit {args.unit} [{u_name}] (Job={j_name}, Weapon={w_name}): {out_path}!"
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    slot_idx = _slot_idx(args)
    save = FFTA2Save(args.save_file, slot=slot_idx)
    issues = validate_save(save)
    if not issues:
        print(f"[PASS] All clan units in Slot {slot_idx + 1} pass NDS engine stability validation!")
        return 0
    print(f"[FAIL] Found {len(issues)} stability issues in Slot {slot_idx + 1}:")
    for iss in issues:
        print(f"  [{iss.severity}] {_format_issue_target(iss.unit_index)} ({iss.field}): {iss.message}")
    return 1


def cmd_topup_stats(args: argparse.Namespace) -> int:
    slot_idx = _slot_idx(args)
    save = FFTA2Save(args.save_file, slot=slot_idx)
    from ffta2_tool.stats import topup_clan_stats

    results = topup_clan_stats(save, max_units=args.units)
    if not results:
        print(
            f"[*] All clan units in Slot {slot_idx + 1} already have stats "
            "equal to or exceeding 115% god roll maximums."
        )
        return 0

    out_path = _save_with_args(save, args)
    print(f"[SUCCESS] 115% God Roll stats applied to {len(results)} clan units in Slot {slot_idx + 1}: {out_path}!")
    for res in results:
        u_idx = res["unit_index"]
        job_str = get_job_name(res["job_id"])
        summary = ", ".join(f"{stat}: {old}->{new}" for stat, (old, new) in res["changes"].items())
        print(f"  Unit {u_idx + 1} ({job_str}): {summary}")
    return 0


def cmd_set_difficulty(args: argparse.Namespace) -> int:
    slot_idx = _slot_idx(args)
    save = FFTA2Save(args.save_file, slot=slot_idx)
    target = 1 if args.difficulty == "hard" else 2
    save.difficulty = target
    out_path = _save_with_args(save, args)
    print(f"[SUCCESS] Slot {slot_idx + 1} difficulty set to {args.difficulty.capitalize()} and signed: {out_path}!")
    return 0


def cmd_master_abilities(args: argparse.Namespace) -> int:
    slot_idx = _slot_idx(args)
    save = FFTA2Save(args.save_file, slot=slot_idx)
    target_unit = getattr(args, "unit", None)
    unit_idx = target_unit - 1 if target_unit is not None else None

    count = save.master_all_unit_abilities(unit_idx)
    target_desc = f"Unit {target_unit}" if target_unit is not None else f"all {count} recruited clan units"

    out_path = _save_with_args(save, args)
    print(f"[SUCCESS] Mastered abilities for {target_desc} in Slot {slot_idx + 1}: {out_path}!")
    return 0


def cmd_clan(args: argparse.Namespace) -> int:
    slot_idx = _slot_idx(args)
    save = FFTA2Save(args.save_file, slot=slot_idx)

    actions = []
    if getattr(args, "clan_name", None) is not None:
        save.clan_name = args.clan_name
        actions.append(f"Name='{save.clan_name}'")

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
        actions.append("all Clan Privileges unlocked")

    if not actions:
        print(
            "No clan options specified. Use --all, --gil, --cp, --privileges, --talents, or --clan-name.",
            file=sys.stderr,
        )
        return 1

    if not _run_pre_write_gate(save, "Clan update"):
        return 1

    out_path = _save_with_args(save, args)
    print(f"[SUCCESS] Slot {slot_idx + 1} clan updated ({', '.join(actions)}): {out_path}!")
    return 0


def cmd_patch_meta_squad(args: argparse.Namespace) -> int:
    slot_idx = _slot_idx(args)
    save = FFTA2Save(args.save_file, slot=slot_idx)

    # Pre-patch validation gate
    pre_issues = [i for i in validate_save(save) if i.severity == "ERROR"]
    if pre_issues:
        print(f"[WARNING] Save has {len(pre_issues)} pre-existing errors before patching:")
        for iss in pre_issues:
            print(f"  [{iss.severity}] Unit {iss.unit_index + 1} ({iss.field}): {iss.message}")

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
            print(f"  [{iss.severity}] Unit {iss.unit_index + 1} ({iss.field}): {iss.message}")
        return 1

    out_path = _save_with_args(save, args)
    print(f"[SUCCESS] Meta squad successfully applied to Slot {slot_idx + 1} and verified: {out_path}!")
    for build in META_SQUAD_BUILDS:
        job_str = get_job_name(build["job_id"])
        w_str = get_item_name(build["weapon_id"])
        print(
            f"  Unit {build['slot'] + 1} ({build['name']}): "
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
    slot_idx = _slot_idx(args)
    save = FFTA2Save(args.save_file, slot=slot_idx)
    print(f"=== FFTA2 Save: {args.save_file} (Slot {slot_idx + 1}) ===")
    print(f"Slot {slot_idx + 1} Leader Name: {save.slot_player_name}")
    print(f"Clan Name:          {save.clan_name}")
    diff_val = save.difficulty
    diff_str = "Hard" if diff_val == 1 else ("Normal" if diff_val == 2 else f"Unknown ({diff_val})")
    print(f"Difficulty:         {diff_str}")

    is_valid, stored, _calc = SlotManager(save.raw_data).verify_slot(save.slot)
    print(f"Checksum: 0x{stored:08X} ({'VALID' if is_valid else 'INVALID'}) at record 0x{save.record_base:04X}")

    inv = save.get_inventory()
    print(f"Clan Inventory Items: {len(inv)} unique stacks registered")

    print("\n--- Party Roster ---")
    for i in range(MAX_UNITS):
        unit = save.get_unit(i)
        if unit and unit.is_recruited:
            u_name = save.get_unit_name(i)
            job_str = get_job_name(unit.job_id)
            race_str = get_race_name(unit.race_id)
            w_str = get_item_name(unit.weapon_id)
            s_str = get_item_name(unit.shield_id)
            h_str = get_item_name(unit.helm_id)
            a_str = get_item_name(unit.armor_id)
            acc_str = get_item_name(unit.accessory_id)
            print(
                f"Unit {i + 1:2d} [{u_name}] ({race_str} {job_str} Lv.{unit.level}):\n"
                f"  Weapon: {w_str} (0x{unit.weapon_id:04X}) | Shield: {s_str} (0x{unit.shield_id:04X})\n"
                f"  Head:   {h_str} (0x{unit.helm_id:04X}) | Body:   {a_str} (0x{unit.armor_id:04X})\n"
                f"  Acc:    {acc_str} (0x{unit.accessory_id:04X})\n"
            )
    return 0


def cmd_inventory(args: argparse.Namespace) -> int:
    slot_idx = _slot_idx(args)
    save = FFTA2Save(args.save_file, slot=slot_idx)
    inv = save.get_inventory()
    print(f"=== Slot {slot_idx + 1} Clan Inventory ({len(inv)} items) ===")
    for item_id, (total, eq) in sorted(inv.items()):
        name = get_item_name(item_id)
        print(f"  0x{item_id:04X}: {name:<24} Total={total:2d} (Equipped={eq:2d})")
    return 0


def cmd_set_weapon(args: argparse.Namespace) -> int:
    slot_idx = _slot_idx(args)
    save = FFTA2Save(args.save_file, slot=slot_idx)
    unit_idx = args.unit - 1
    unit = save.get_unit(unit_idx)
    if not unit:
        print(f"Error: Invalid unit number {args.unit} (must be 1..24)", file=sys.stderr)
        return 1
    if not unit.is_recruited:
        raise ValueError(f"Unit slot {args.unit} is empty (no recruited clan member)")

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
    out_path = _save_with_args(save, args)

    old_name = get_item_name(old_weapon)
    new_name = get_item_name(args.item_id)
    print(
        f"Slot {slot_idx + 1} Unit {args.unit}: "
        f"Weapon updated from {old_name} (0x{old_weapon:04X}) to {new_name} (0x{args.item_id:04X})"
    )
    print(f"Saved and signed: {out_path}")
    return 0


def cmd_rom_inspect(args: argparse.Namespace) -> int:
    try:
        info = inspect_nds_rom(args.rom_file)
    except ValueError as e:
        sys.stderr.write(f"Error inspecting ROM: {e}\n")
        return 1
    print(f"=== NDS ROM: {args.rom_file} ===")
    for k, v in info.items():
        if isinstance(v, int):
            print(f"{k:<16}: 0x{v:X} ({v})")
        else:
            print(f"{k:<16}: {v}")
    return 0


def cmd_rom_extract(args: argparse.Namespace) -> int:
    try:
        out_arm9 = extract_arm9(args.rom_file, args.output)
        print(f"Extracted ARM9 binary to: {out_arm9}")
        if args.overlays_dir:
            ovs = extract_overlays(args.rom_file, args.overlays_dir)
            print(f"Extracted {len(ovs)} overlays to: {args.overlays_dir}")
    except ValueError as e:
        sys.stderr.write(f"Error extracting ROM: {e}\n")
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="FFTA2 Save and ARM Reverse Engineering CLI")
    parser.add_argument("--config", help="Path to user config.toml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # verify
    p_verify = subparsers.add_parser("verify", help="Verify save file checksum")
    p_verify.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_verify.add_argument("--config", help="Path to user config.toml")
    p_verify.set_defaults(func=cmd_verify)

    # info
    p_info = subparsers.add_parser("info", help="Display save metadata, party info, and equipment")
    p_info.add_argument("save_file", nargs="?", help=SAVE_HELP)
    _add_slot_arg(p_info)
    p_info.add_argument("--config", help="Path to user config.toml")
    p_info.set_defaults(func=cmd_info)

    # inventory
    p_inv = subparsers.add_parser("inventory", help="List all items in the clan inventory bag")
    p_inv.add_argument("save_file", nargs="?", help=SAVE_HELP)
    _add_slot_arg(p_inv)
    p_inv.add_argument("--config", help="Path to user config.toml")
    p_inv.set_defaults(func=cmd_inventory)

    # backup
    p_bak = subparsers.add_parser("backup", help="Create a standalone timestamped backup snapshot in backup_dir")
    p_bak.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_bak.add_argument("--backup-dir", "-d", help="Override backup directory (default: ~/Documents/FFTA2_Backups)")
    p_bak.add_argument("--config", help="Path to user config.toml")
    p_bak.set_defaults(func=cmd_backup)

    # rename
    p_ren = subparsers.add_parser("rename", help="Rename a clan unit (1..24) or the clan itself")
    p_ren.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_ren.add_argument(
        "--unit",
        "-u",
        type=int,
        choices=range(1, 25),
        default=1,
        help="Unit number to rename (1..24, default: 1)",
    )
    p_ren.add_argument(
        "--name",
        "-n",
        help=(
            "New unit name (freeform string up to 9 chars for Unit 1; "
            "race-pool ROM name, ID, or 'random' for Units 2..24)"
        ),
    )
    p_ren.add_argument("--clan-name", help="New custom clan name (up to 9 characters)")
    p_ren.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Allow story or cross-race ROM names on generic units (2..24)",
    )
    _add_common_write_args(p_ren)
    p_ren.set_defaults(func=cmd_rename)

    # inject
    p_inj = subparsers.add_parser("inject", help="Inject a new recruit into the clan roster")
    p_inj.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_inj.add_argument(
        "--job",
        "-j",
        required=True,
        help="Build key (e.g. 'viera', 'nu_mou'), job name (e.g. 'Parivir', 'Nu Mou Sage'), or job ID",
    )
    p_inj.add_argument(
        "--level",
        "-l",
        type=int,
        default=50,
        help="Recruit level (1..99, default: 50)",
    )
    p_inj.add_argument(
        "--name",
        "-n",
        default=None,
        help="Recruit name (ROM character name, ID, or 'random'; auto-assigned by race if omitted)",
    )
    p_inj.add_argument(
        "--unit",
        "-u",
        type=int,
        choices=range(1, 25),
        default=None,
        help="Target unit slot (2..24; uses first empty slot if omitted)",
    )
    p_inj.add_argument(
        "--master-abilities",
        action="store_true",
        help="Master all abilities on the injected recruit",
    )
    p_inj.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Allow overwriting an occupied non-Luso unit slot or using a story/cross-race ROM name",
    )
    _add_common_write_args(p_inj)
    p_inj.set_defaults(func=cmd_inject)

    # equip-build
    p_eqb = subparsers.add_parser("equip-build", help="Equip a single unit with a build from builds.toml")
    p_eqb.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_eqb.add_argument(
        "--unit",
        "-u",
        type=int,
        choices=range(1, 25),
        default=1,
        help="Unit number to equip (1..24, default: 1)",
    )
    p_eqb.add_argument(
        "--build",
        "-b",
        required=True,
        help="Build key or job name from builds.toml (e.g. 'luso', 'nu_mou', 'viera', 'bangaa', 'hume', 'moogle')",
    )
    p_eqb.add_argument(
        "--master-abilities",
        action="store_true",
        help="Master all abilities on the unit",
    )
    p_eqb.add_argument(
        "--no-god-stats",
        action="store_true",
        help="Skip topping up unit stats to 115%% god-roll maximums",
    )
    _add_common_write_args(p_eqb)
    p_eqb.set_defaults(func=cmd_equip_build)

    # set-weapon
    p_set = subparsers.add_parser("set-weapon", help="Change unit's equipped weapon and re-sign")
    p_set.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_set.add_argument(
        "--unit",
        "-u",
        type=int,
        choices=range(1, 25),
        default=1,
        help="Unit number to equip (1..24, default: 1)",
    )
    p_set.add_argument("--item-id", type=int, required=True, help="Item ID to equip")
    _add_common_write_args(p_set)
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
    _add_common_write_args(p_patch)
    p_patch.set_defaults(func=cmd_patch_meta_squad)

    # topup-stats
    p_topup = subparsers.add_parser("topup-stats", help="Top up clan units to 115%% god roll stats (non-destructive)")
    p_topup.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_topup.add_argument("--units", "-u", type=int, default=6, help="Number of clan unit slots to top up (default: 6)")
    _add_common_write_args(p_topup)
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
    _add_common_write_args(p_diff)
    p_diff.set_defaults(func=cmd_set_difficulty)

    # validate
    p_val = subparsers.add_parser("validate", help="Validate clan units against NDS UI crash conditions")
    p_val.add_argument("save_file", nargs="?", help=SAVE_HELP)
    _add_slot_arg(p_val)
    p_val.add_argument("--config", help="Path to user config.toml")
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
    _add_common_write_args(p_mab)
    p_mab.set_defaults(func=cmd_master_abilities)

    # clan
    p_clan = subparsers.add_parser("clan", help="Manage clan perks: max Gil, CP, talents, and Clan Privileges")
    p_clan.add_argument("save_file", nargs="?", help=SAVE_HELP)
    p_clan.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Max out Gil (99,999,999), CP (9999), Talents (99), and unlock all Clan Privileges",
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
        help="Unlock all Clan Privileges in the Judge menu (other flag bits are preserved)",
    )
    p_clan.add_argument(
        "--talents",
        "-t",
        action="store_true",
        help="Set all four Clan Talents (Negotiation, Aptitude, Teamwork, Adaptability) to 99",
    )
    p_clan.add_argument("--clan-name", help="Set custom clan name (up to 15 characters)")
    _add_common_write_args(p_clan)
    p_clan.set_defaults(func=cmd_clan)

    args = parser.parse_args()
    cfg = load_config(getattr(args, "config", None))
    args._cfg = cfg

    # Auto-detect the save file when a command needs one and none was supplied
    if args.command in SAVE_COMMANDS:
        args.save_file = resolve_save_file(args.save_file, cfg=cfg)
        if args.save_file is None:
            print(
                "Error: No save file specified and none found in ~/Documents/FFTA2_Backups, "
                "mounted media, or the current directory.",
                file=sys.stderr,
            )
            sys.exit(1)

    try:
        sys.exit(args.func(args))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
