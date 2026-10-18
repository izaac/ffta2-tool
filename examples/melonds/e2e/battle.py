"""Live FFTA2 battle bot: RAM for state (roster, cursor), dsbot for the DS UI.

The in-battle RAM layout was found with melonDS savestates and cursor diffs (see
docs/save_format_map.md section 10):

* per-unit battle records, stride 0x48 from POS_TABLE: tile x/y at +0/+1; the preceding 0x24
  half holds a pointer to unit struct + 8.
* unit structs use the same 0x11C layout as the save (job +0x0E, status u16 +0x12, level +0x22,
  HP u16 pair +0x3C/+0x3E). Foes and guests live in FOE_TABLE (status bit 0 = hostile), our
  deployed units in the clan table.
* the map cursor tile is a u16 x/y pair at CURSOR+2/+4 and follows D-pad and touch input.
"""

from __future__ import annotations

import struct
import time
from collections.abc import Callable
from dataclasses import dataclass

from dsbot import Ds, bicon_visible, cmd_row, commands_visible, forecast_visible
from rsp import Rsp

POS_TABLE = 0x02129AAC
POS_STRIDE = 0x48
POS_COUNT = 14
CURSOR = 0x0212F018
FOE_TABLE = 0x02129FAC
CLAN_TABLE = 0x0212B118
UNIT_STRIDE = 0x11C
FOE_SLOTS = 16
CLAN_SLOTS = 24

ATTACK_TRY_DISTANCE = 6
MOVE_RADIUS = 4  # search radius only; the game enforces the unit's Move stat and refuses farther tiles
MOVE_CANDIDATES = 4


@dataclass
class Unit:
    x: int
    y: int
    side: str  # ours, guest, foe
    hp: int
    max_hp: int
    job: int
    level: int
    base: int

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def pos(self) -> tuple[int, int]:
        return self.x, self.y

    def dist(self, other: Unit | tuple[int, int]) -> int:
        ox, oy = other.pos if isinstance(other, Unit) else other
        return abs(self.x - ox) + abs(self.y - oy)

    def __str__(self) -> str:
        return f"{self.side}:job{self.job}@({self.x},{self.y}) {self.hp}/{self.max_hp}"


class Battle:
    def __init__(
        self,
        ds: Ds,
        rsp: Rsp,
        log: Callable[[str], None] = print,
        passive_jobs: frozenset[int] = frozenset(),
        on_event: Callable[[str], None] | None = None,
    ):
        self.ds = ds
        self.rsp = rsp
        self._log = log
        self.t0 = time.time()
        self.passive_jobs = passive_jobs
        self.on_event = on_event
        self.stats = {"turns": 0, "attacks": 0, "moves": 0}
        self.dirs = {"right": (1, 0), "left": (-1, 0), "down": (0, 1), "up": (0, -1)}
        self.learned: set[str] = set()

    def log(self, msg: str) -> None:
        self._log(f"[{time.time() - self.t0:6.1f}s] {msg}")

    def event(self, name: str) -> None:
        if self.on_event:
            self.on_event(name)

    # ---- RAM ----------------------------------------------------------------------------

    def cursor(self) -> tuple[int, int]:
        with self.rsp.paused():
            data = self.rsp.read(CURSOR, 8)
        x, y = struct.unpack_from("<HH", data, 2)
        return x, y

    def roster(self) -> list[Unit]:
        first = POS_TABLE - 8
        units: list[Unit] = []
        with self.rsp.paused():
            raw = self.rsp.read(first, POS_COUNT * POS_STRIDE)
            for i in range(POS_COUNT):
                off = 8 + i * POS_STRIDE
                x, y = raw[off], raw[off + 1]
                (ptr,) = struct.unpack_from("<I", raw, off - 8)
                base = ptr - 8
                in_foe = FOE_TABLE <= base < FOE_TABLE + FOE_SLOTS * UNIT_STRIDE
                in_clan = CLAN_TABLE <= base < CLAN_TABLE + CLAN_SLOTS * UNIT_STRIDE
                if not (in_foe or in_clan):
                    continue
                if (base - (CLAN_TABLE if in_clan else FOE_TABLE)) % UNIT_STRIDE:
                    continue
                d = self.rsp.read(base + 0x0E, 0x32)
                job, level = d[0], d[0x14]
                (status,) = struct.unpack_from("<H", d, 4)
                hp, max_hp = struct.unpack_from("<HH", d, 0x2E)
                if level == 0 or max_hp == 0:
                    continue
                side = "ours" if in_clan else ("foe" if status & 1 else "guest")
                units.append(Unit(x, y, side, hp, max_hp, job, level, base))
        return units

    # ---- UI primitives --------------------------------------------------------------------

    def backout(self, tries: int = 6) -> bool:
        """B until the COMMANDS menu is back."""
        for _ in range(tries):
            if commands_visible(self.ds.frame()):
                return True
            self.ds.tap("b", 0.2, 0.9)
        return commands_visible(self.ds.frame())

    def goto_tile(self, tx: int, ty: int, max_steps: int = 40) -> bool:
        """Walk the map cursor onto a tile with D-pad taps, learning what each key really does.

        Keys start with the default camera mapping (right = x+1, down = y+1). A key whose real effect
        is unknown gets probed once when no known key makes progress. Gives up after three taps in a
        row that leave the cursor where it was (void or off-map tile).
        """
        cx, cy = self.cursor()
        stalled = 0
        tried_here: set[str] = set()  # keys that did nothing at the current tile
        for _ in range(max_steps):
            if (cx, cy) == (tx, ty):
                return True
            best_key, best_gain = None, 0
            for known in (True, False):
                for key, (dx, dy) in self.dirs.items():
                    if key in tried_here or (key in self.learned) != known:
                        continue
                    gain = (abs(tx - cx) + abs(ty - cy)) - (abs(tx - (cx + dx)) + abs(ty - (cy + dy)))
                    if gain > best_gain:
                        best_key, best_gain = key, gain
                if best_key is not None:
                    break
            if best_key is None:
                unknown = [k for k in self.dirs if k not in self.learned and k not in tried_here]
                if not unknown:
                    return False
                best_key = unknown[0]
            self.ds.tap(best_key, 0.12, 0.3)
            nx, ny = self.cursor()
            delta = (nx - cx, ny - cy)
            if abs(delta[0]) + abs(delta[1]) == 1:
                self.dirs[best_key] = delta
                self.learned.add(best_key)
            if (nx, ny) == (cx, cy):
                stalled += 1
                tried_here.add(best_key)
                if stalled >= 3:
                    return False
            else:
                tried_here.clear()
            cx, cy = nx, ny
        return (cx, cy) == (tx, ty)

    # ---- actions ----------------------------------------------------------------------------

    def attack(self, foe: Unit) -> bool:
        """From the COMMANDS menu: Action > Attack > foe tile > confirm. False if out of reach."""
        ds = self.ds
        row = cmd_row(ds.frame())
        for _ in range(1 - (row if row is not None else 0)):
            ds.tap("down", 0.12, 0.6)
        ds.tap("a", 0.25, 1.0)  # Action list, cursor on Attack
        ds.tap("a", 0.25, 1.4)  # target mode
        if not bicon_visible(ds.frame()):
            self.log("  attack: no target mode")
            self.backout()
            return False
        if not self.goto_tile(foe.x, foe.y):
            self.log("  attack: cursor could not reach the foe tile")
            self.backout()
            return False
        ds.tap("a", 0.25, 1.6)
        if not forecast_visible(ds.frame()):
            self.log(f"  attack: no forecast on {foe.pos}, out of reach")
            self.backout()
            return False
        self.event("forecast")
        ds.tap("a", 0.25, 1.0)
        self.stats["attacks"] += 1
        return True

    def move_to(self, me: Unit, tiles: list[tuple[int, int]]) -> tuple[int, int] | None:
        """From the COMMANDS menu: Move, then try the candidate tiles in order."""
        ds = self.ds
        row = cmd_row(ds.frame())
        for _ in range(row if row is not None else 0):
            ds.tap("up", 0.12, 0.5)
        ds.tap("a", 0.25, 1.2)
        if not bicon_visible(ds.frame()):
            self.backout()
            return None
        for tx, ty in tiles:
            if not self.goto_tile(tx, ty):
                self.log(f"  move: cursor could not reach {(tx, ty)}")
                continue
            ds.tap("a", 0.25, 2.5)
            if commands_visible(ds.frame()):
                self.stats["moves"] += 1
                return tx, ty
            self.log(f"  move: {(tx, ty)} rejected")
        self.backout()
        return None

    def wait_turn(self) -> None:
        ds = self.ds
        f = ds.frame()
        row = cmd_row(f)
        for _ in range(2 - (row if row is not None else 0)):
            ds.tap("down", 0.12, 0.6)
        ds.tap("a", 0.25, 1.2)  # Wait: facing prompt
        ds.tap("a", 0.25, 1.0)  # keep facing
        end = time.time() + 12
        while time.time() < end and commands_visible(ds.frame()):
            time.sleep(0.5)
        self.log("  turn ended")

    # ---- policy ---------------------------------------------------------------------------------

    def foes_alive(self) -> int:
        return sum(1 for u in self.roster() if u.side == "foe" and u.alive)

    def wait_commands(self, timeout: float = 120.0) -> str:
        """Block until one of our units has the COMMANDS menu ("commands"), the last foe is down
        ("victory") or time runs out ("timeout"). Stuck dialogs are nudged along with A."""
        end = time.time() + timeout
        quiet_since = time.time()
        last_check = time.time()
        while time.time() < end:
            f = self.ds.frame()
            if commands_visible(f):
                time.sleep(0.6)
                if commands_visible(self.ds.frame()):
                    return "commands"
                continue
            if bicon_visible(f):
                # facing prompt left over after an action: keep the facing
                self.ds.tap("a", 0.25, 1.0)
                quiet_since = time.time()
                continue
            if time.time() - last_check > 5:
                last_check = time.time()
                if self.foes_alive() == 0:
                    time.sleep(2.5)
                    if self.foes_alive() == 0:
                        return "victory"
            if time.time() - quiet_since > 6:
                self.ds.tap("a", 0.2, 0.5)
                quiet_since = time.time() - 3
            time.sleep(0.5)
        return "timeout"

    def play_turn(self) -> str:
        ds = self.ds
        roster = self.roster()
        cx, cy = self.cursor()
        me = next((u for u in roster if u.side == "ours" and u.pos == (cx, cy)), None)
        foes = sorted((u for u in roster if u.side == "foe" and u.alive), key=lambda u: me.dist(u) if me else 0)
        if me is None:
            self.log(f"  cursor ({cx},{cy}) is not on one of ours: {[str(u) for u in roster]}")
            self.wait_turn()
            return "unknown-unit"
        self.log(f"  {me} foes: {[str(f) for f in foes]}")
        if not foes:
            return "victory-pending"
        occupied = {u.pos for u in roster if u.alive}
        result = "wait"
        if me.job in self.passive_jobs:
            foes = [f for f in foes if me.dist(f) <= 2]  # keep the healer back unless a foe is on top of it
        near = [f for f in foes if me.dist(f) <= ATTACK_TRY_DISTANCE]
        for foe in near[:2]:
            if self.attack(foe):
                self.log(f"  attacked {foe}")
                result = "attacked"
                break
        if result != "attacked" and foes:
            target = foes[0]
            tiles = sorted(
                (
                    (me.x + dx, me.y + dy)
                    for dx in range(-MOVE_RADIUS, MOVE_RADIUS + 1)
                    for dy in range(-MOVE_RADIUS, MOVE_RADIUS + 1)
                    if 0 < abs(dx) + abs(dy) <= MOVE_RADIUS and (me.x + dx, me.y + dy) not in occupied
                ),
                key=lambda t: (target.dist(t), me.dist(t)),
            )[:MOVE_CANDIDATES]
            dest = self.move_to(me, tiles)
            self.log(f"  move toward {target.pos}: {dest}")
            if dest is not None:
                result = "moved"
                if target.dist(dest) <= ATTACK_TRY_DISTANCE and self.attack(target):
                    self.log(f"  attacked {target} after moving")
                    result = "moved+attacked"
        if result in ("attacked", "moved+attacked"):
            time.sleep(3.0)
            if self.foes_alive() == 0:
                return "victory-pending"
        if not commands_visible(ds.frame()):
            status = self.wait_commands(timeout=40)
            if status == "victory":
                return "victory-pending"
        self.wait_turn()
        return result

    def run(self, max_turns: int = 80, deadline: float | None = None) -> str:
        """Play our turns until the last foe is down. Returns victory, stuck, timeout or max-turns."""
        for turn in range(1, max_turns + 1):
            remaining = 120.0 if deadline is None else min(120.0, deadline - time.time())
            if remaining <= 0:
                return "timeout"
            status = self.wait_commands(timeout=remaining)
            if status == "victory":
                return "victory"
            if status != "commands":
                self.log("no COMMANDS menu for 120 s")
                return "stuck"
            self.stats["turns"] = turn
            self.log(f"turn {turn}")
            if turn == 1:
                self.event("first-turn")
            if self.play_turn() == "victory-pending":
                return "victory"
        return "max-turns"
