#!/usr/bin/env python3
"""E6: win the live quicksave battle with real attacks, save on the world map, reload, verify.

Input is the E5 quicksave (run_e5_full.sh leaves $OUT_DIR/e2e/e5_final_saved.sav). The bot reads the
battle roster and the map cursor from RAM through the melonDS gdb stub and plays our units with the
DS buttons (Move, Action > Attack, Wait). No HP or position is forged. After the VICTORY sequence it
saves to slot 1 from the world map, stops melonDS to flush, then proves the result three ways:
checksums and validator on the file, a field diff against the pre-battle slot, and a fresh boot where
the game's in-RAM clan table must equal the decrypted save byte for byte.

Exit 0 only if every gate passes. Screenshots land next to the artifacts as e6_NN_*.png.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
E2E = HERE.parent
REPO = E2E.parents[2]
sys.path.insert(0, str(E2E))
sys.path.insert(0, str(REPO))

from battle import CLAN_TABLE, UNIT_STRIDE, Battle  # noqa: E402
from dsbot import (  # noqa: E402
    MDS,
    Ds,
    commands_visible,
    slot_cursor,
    worldmap_visible,
)
from rsp import Rsp  # noqa: E402

from ffta2_tool.save import UNIT_TABLE_BASE, FFTA2Save  # noqa: E402
from ffta2_tool.slots import SlotManager  # noqa: E402
from ffta2_tool.validator import validate_save  # noqa: E402

T0 = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


class Gate(Exception):
    """A proof gate failed."""


def mds(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([MDS, *args], capture_output=True, text=True)


def boot(sdir: Path, sav: Path, port: int) -> tuple[Ds, Rsp]:
    shutil.rmtree(sdir, ignore_errors=True)
    r = mds("start", str(sdir), str(sav), str(port))
    if r.returncode != 0:
        raise Gate(f"mds start failed: {r.stderr or r.stdout}")
    rsp = None
    for _ in range(30):
        try:
            rsp = Rsp(port)
            break
        except (ConnectionRefusedError, OSError):
            time.sleep(1)
    if rsp is None:
        raise Gate(f"melonDS gdb stub on {port} never accepted a connection")
    rsp.resume()
    time.sleep(24)  # title screen
    return Ds(sdir), rsp


def keep(ds: Ds, out: Path, name: str) -> None:
    shutil.copy(ds.shot(name), out / f"{name}.png")


def resume_quicksave(ds: Ds) -> None:
    ds.seq("a:0.4:2.5 up:0.15:1 a:0.4:7")  # Continue, answer the "deleted after load" prompt with Continue
    for _ in range(10):
        if commands_visible(ds.frame()):
            return
        ds.tap("a", 0.3, 2.5)  # objective, law and privilege banners
    if not ds.wait_for(commands_visible, timeout=20):
        raise Gate("battle never showed the COMMANDS menu after resuming the quicksave")


def aftermath(ds: Ds, out: Path) -> None:
    """Mash A through the VICTORY sequence, results and quest report until the world map is back."""
    end = time.time() + 420
    presses = 0
    while time.time() < end:
        if worldmap_visible(ds.frame()):
            time.sleep(1.5)
            if worldmap_visible(ds.frame()):
                if presses:
                    shutil.copy(ds.sdir + "/aftermath_prev.png", out / "e6_04_quest_report.png")
                log(f"world map after {presses} presses")
                return
        ds.tap("a", 0.2, 1.8)
        presses += 1
        shutil.copy(ds.shot("aftermath_cur"), ds.sdir + "/aftermath_prev.png")
        if presses == 4:
            keep(ds, out, "e6_03_victory_dialogue")
    raise Gate("world map never came back after the victory sequence")


def ingame_save(ds: Ds, out: Path) -> None:
    ds.tap("x", 0.25, 2.5)  # Main Menu
    ds.seq("down:0.12:0.8 down:0.12:0.8 a:0.25:2.0")  # System Menu
    ds.tap("a", 0.25, 2.0)  # Save
    if slot_cursor(ds.frame()) == 2:
        ds.tap("up", 0.12, 0.8)
    ds.tap("a", 0.25, 2.0)  # "Overwrite data in Slot 1?"
    ds.seq("up:0.12:0.8 a:0.25:5.0")  # Overwrite and save
    keep(ds, out, "e6_06_saved")
    ds.tap("a", 0.25, 2.0)
    for _ in range(6):
        if worldmap_visible(ds.frame()):
            break
        ds.tap("b", 0.2, 1.5)
    time.sleep(10)  # let melonDS flush the NVRAM


def unit_bytes(save: FFTA2Save, idx: int) -> bytes:
    off = UNIT_TABLE_BASE + idx * UNIT_STRIDE
    return bytes(save.plaintext[off : off + UNIT_STRIDE])


def report(pre_path: Path | None, post_path: Path, out: Path) -> list[str]:
    """Checksums, validator, preview and field diff of the post-battle slot 1. Returns gate failures."""
    fails: list[str] = []
    lines: list[str] = []
    post = FFTA2Save(post_path, slot=0)
    sm = SlotManager(bytearray(post_path.read_bytes()))
    for slot in (0, 1):
        valid, stored, calc = sm.verify_slot(slot)
        lines.append(
            f"slot {slot + 1} checksum: stored {stored:#010x} calculated {calc:#010x} {'VALID' if valid else 'INVALID'}"
        )
        if not valid:
            fails.append(f"slot {slot + 1} checksum invalid")
    prev = sm.get_slot_preview(0)
    lines.append(
        f"preview: {prev['member_count']} members, {prev['cleared_quests']} quests, "
        f"{prev['play_time_formatted']}, {prev['difficulty_label']}"
    )
    post_issues = validate_save(post)
    errors = [i for i in post_issues if i.severity == "ERROR"]
    lines.append(f"validator: {len(errors)} errors, {len(post_issues) - len(errors)} warnings")
    if errors:
        fails.append(f"validator errors: {[str(e) for e in errors]}")
    if pre_path and pre_path.exists():
        pre = FFTA2Save(pre_path, slot=0)
        pre_keys = {(i.unit_index, i.field) for i in validate_save(pre)}
        new = [(i.unit_index, i.field) for i in post_issues if (i.unit_index, i.field) not in pre_keys]
        lines.append(f"validator issues new since the pre-battle slot: {new or 'none'}")
        if new:
            fails.append(f"battle introduced validator issues: {new}")
        lines.append(f"gil {pre.gil} -> {post.gil}, clan points {pre.clan_points} -> {post.clan_points}")
        for idx in range(24):
            a, b = pre.get_unit(idx), post.get_unit(idx)
            if not (a and b and a.is_recruited):
                continue
            ch = [
                f"{n} {getattr(a, n)}->{getattr(b, n)}"
                for n in ("level", "exp", "max_hp", "max_mp", "attack", "defense", "matk", "mdef", "speed")
                if getattr(a, n) != getattr(b, n)
            ]
            if ch:
                lines.append(f"unit {idx + 1} {b.name}: " + ", ".join(ch))
        if post.gil <= pre.gil and post.clan_points <= pre.clan_points:
            fails.append("neither gil nor clan points moved: the battle rewards never landed")
    (out / "e6_report.txt").write_text("\n".join(lines) + "\n")
    for ln in lines:
        log("  " + ln)
    return fails


def reload_check(sdir: Path, sav: Path, port: int, out: Path, unit_index: int) -> list[str]:
    """Fresh boot, load slot 1: the game's clan table in RAM must equal the decrypted save."""
    ds, rsp = boot(sdir, sav, port)
    fails: list[str] = []
    try:
        ds.tap("a", 0.4, 2.5)  # title: Load
        keep(ds, out, "e6_07_reloaded_loadscreen")
        ds.tap("a", 0.3, 1.8)  # slot 1
        ds.seq("up:0.12:0.8 a:0.3:3.0")  # Load
        ds.tap("a", 0.3, 2.0)  # "Slot 1 data loaded."
        if not ds.wait_for(worldmap_visible, timeout=40, interval=1.0):
            raise Gate("reloaded slot 1 never reached the world map")
        time.sleep(2)
        keep(ds, out, "e6_08_reloaded_worldmap")
        save = FFTA2Save(sav, slot=0)
        count = sum(1 for i in range(24) if (u := save.get_unit(i)) and u.is_recruited)
        with rsp.paused():
            ram = rsp.read(CLAN_TABLE, count * UNIT_STRIDE)
        for i in range(count):
            if ram[i * UNIT_STRIDE : (i + 1) * UNIT_STRIDE] != unit_bytes(save, i):
                fails.append(f"unit {i + 1}: RAM clan table differs from the decrypted save")
        log(f"RAM clan table == save for {count - len(fails)}/{count} units")
        ds.tap("x", 0.25, 2.2)
        ds.tap("a", 0.25, 3.0)  # Unit Info
        keep(ds, out, "e6_09_reloaded_roster")
        row, col = divmod(unit_index - 1, 6)
        for _ in range(row):
            ds.tap("down", 0.12, 1.5)
        for _ in range(col):
            ds.tap("right", 0.12, 1.5)
        ds.tap("a", 0.25, 3.0)
        keep(ds, out, "e6_10_unit_status")
    finally:
        mds("stop", str(sdir))
    return fails


def main() -> int:
    out_root = Path(os.environ.get("OUT_DIR", "/tmp")) / "e2e"
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sav", type=Path, default=out_root / "e5_final_saved.sav", help="E5 quicksave to resume")
    ap.add_argument("--ref", type=Path, default=out_root / "e5_final.sav", help="pre-battle save for the field diff")
    ap.add_argument("--out", type=Path, default=out_root)
    ap.add_argument("--port", type=int, default=3800, help="gdb port of the battle session (reload uses +20)")
    ap.add_argument("--passive-job", type=int, default=35, help="job id kept out of melee (injected White Mage)")
    ap.add_argument("--unit-index", type=int, default=7, help="1-based roster slot to open after the reload")
    ap.add_argument("--max-minutes", type=float, default=45.0)
    args = ap.parse_args()

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    sdir = out / "e6_session"
    post_sav = out / "e6_aftermath.sav"
    failures: list[str] = []

    log(f"booting {args.sav}")
    ds, rsp = boot(sdir, args.sav, args.port)
    stopped = False
    try:
        resume_quicksave(ds)
        keep(ds, out, "e6_01_battle_start")
        battle_log = (out / "e6_battle.log").open("w")

        def blog(msg: str) -> None:
            print(msg, file=battle_log, flush=True)
            log(msg.strip())

        def on_event(name: str) -> None:
            if name == "forecast" and not (out / "e6_02_first_attack.png").exists():
                keep(ds, out, "e6_02_first_attack")

        bot = Battle(ds, rsp, blog, frozenset({args.passive_job}), on_event)
        result = bot.run(deadline=time.time() + args.max_minutes * 60)
        log(f"battle: {result} after {bot.stats}")
        if result != "victory":
            keep(ds, out, "e6_fail_battle")
            raise Gate(f"battle did not end in victory: {result}")
        aftermath(ds, out)
        keep(ds, out, "e6_05_worldmap_after")
        ingame_save(ds, out)
        rc = mds("stop", str(sdir), str(post_sav), str(args.sav)).returncode
        stopped = True
    finally:
        if not stopped:
            mds("stop", str(sdir))
    if rc == 3:
        raise Gate("game.sav is byte-identical to the quicksave: the in-game save never flushed")
    log(f"post-battle save: {post_sav}")

    failures += report(args.ref, post_sav, out)
    failures += reload_check(out / "e6_reload_session", post_sav, args.port + 20, out, args.unit_index)
    if failures:
        for f in failures:
            log(f"GATE FAILED: {f}")
        return 1
    log("E6 PASS: real victory, post-battle save valid, reload matches the save byte for byte")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Gate as exc:
        log(f"GATE FAILED: {exc}")
        sys.exit(1)
