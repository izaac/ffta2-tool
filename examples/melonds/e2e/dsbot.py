"""Pixel-guarded input and vision primitives for driving FFTA2 under melonDS.

Everything goes through mds.sh (keys, touch taps, raw frame grabs), so the same
session directory can be shared with the shell scenarios. Frames are raw RGB of
the two stacked DS screens (256x384), no imaging library needed.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

WIDTH, HEIGHT = 256, 384
HERE = Path(__file__).resolve().parent
MDS = os.environ.get("MDS", str(HERE / "mds.sh"))

Pixel = tuple[int, int, int]


class Frame:
    """One raw capture, addressed in stacked DS coordinates (bottom screen starts at y=192)."""

    def __init__(self, data: bytes):
        if len(data) != WIDTH * HEIGHT * 3:
            raise ValueError(f"bad frame size {len(data)}")
        self.data = data

    def px(self, x: int, y: int) -> Pixel:
        i = (y * WIDTH + x) * 3
        return self.data[i], self.data[i + 1], self.data[i + 2]

    def count(self, pred: Callable[[int, int, int], bool], x: int, y: int, w: int, h: int) -> int:
        n = 0
        for yy in range(y, y + h):
            i = (yy * WIDTH + x) * 3
            for _ in range(w):
                if pred(self.data[i], self.data[i + 1], self.data[i + 2]):
                    n += 1
                i += 3
        return n

    def find(self, pred: Callable[[int, int, int], bool], x: int, y: int, w: int, h: int) -> list[tuple[int, int]]:
        hits = []
        for yy in range(y, y + h):
            i = (yy * WIDTH + x) * 3
            for xx in range(x, x + w):
                if pred(self.data[i], self.data[i + 1], self.data[i + 2]):
                    hits.append((xx, yy))
                i += 3
        return hits


def _amber(r: int, g: int, b: int) -> bool:
    return (r, g, b) == (231, 166, 52)


def commands_visible(f: Frame) -> bool:
    """The top-level COMMANDS (Move/Action/Wait) menu is up.

    Keyed on the amber 'Config' button at the bottom right, which only exists on that menu. The panel
    header is not usable: a unit trait banner such as "Fleet of foot!" pushes it up by a row.
    """
    return f.count(_amber, 165, 352, 90, 15) >= 300


def bicon_visible(f: Frame) -> bool:
    """The round B (cancel) button of the move, target and facing selectors."""
    return f.count(_amber, 216, 190, 40, 28) >= 100


class Ds:
    """One running mds.sh session."""

    def __init__(self, sdir: str | Path):
        self.sdir = str(sdir)

    def _mds(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([MDS, *args], capture_output=True)

    def seq(self, keys: str) -> None:
        r = self._mds("seq", self.sdir, keys)
        if r.returncode != 0:
            raise RuntimeError(f"seq {keys!r} failed: {r.stderr.decode(errors='replace')}")

    def tap(self, btn: str, hold: float = 0.12, after: float = 0.7) -> None:
        self.seq(f"{btn}:{hold}:{after}")

    def touch(self, x: int, y: int, hold: float = 0.25, after: float = 0.8) -> None:
        self._mds("touch", self.sdir, str(x), str(y), str(hold))
        time.sleep(after)

    def frame(self) -> Frame:
        r = self._mds("raw", self.sdir)
        if r.returncode != 0:
            raise RuntimeError("frame grab failed: emulator or Xvfb dead?")
        return Frame(r.stdout)

    def shot(self, name: str, pct: int = 200) -> str:
        self._mds("shot", self.sdir, name, str(pct))
        return f"{self.sdir}/{name}.png"

    def wait_for(self, pred: Callable[[Frame], bool], timeout: float = 60.0, interval: float = 0.4) -> Frame | None:
        end = time.time() + timeout
        while time.time() < end:
            f = self.frame()
            if pred(f):
                return f
            time.sleep(interval)
        return None


def _foe_red(r: int, g: int, b: int) -> bool:
    return (r, g, b) == (142, 36, 44)


def _ally_blue(r: int, g: int, b: int) -> bool:
    return (r, g, b) == (20, 77, 125)


def hud(f: Frame) -> str:
    """Who the cursor is on, from the bottom-left name plate colour: foe, ally or none."""
    if f.count(_foe_red, 70, 340, 50, 8) > 150:
        return "foe"
    if f.count(_ally_blue, 70, 340, 50, 8) > 150:
        return "ally"
    return "none"


def _panel(r: int, g: int, b: int) -> bool:
    return (r, g, b) in ((142, 36, 44), (20, 77, 125))


def forecast_visible(f: Frame) -> bool:
    """Both name plates are up: the right-hand one only exists in the attack forecast."""
    return f.count(_panel, 160, 340, 50, 8) >= 120


def _orange(r: int, g: int, b: int) -> bool:
    return r > 200 and 60 < g < 200 and b < 90


def cmd_row(f: Frame) -> int | None:
    """Selected row of the COMMANDS menu: 0 Move, 1 Action, 2 Wait."""
    for row, y in enumerate((302, 318, 334)):
        if f.count(_orange, 184, y - 7, 14, 14) > 30:
            return row
    return None


def _main_menu_orange(r: int, g: int, b: int) -> bool:
    return (r, g, b) == (255, 150, 28)


def worldmap_visible(f: Frame) -> bool:
    """The orange 'X Main Menu' button of the world map, top right of the bottom screen."""
    return f.count(_main_menu_orange, 181, 194, 74, 15) >= 150


def _ring_orange(r: int, g: int, b: int) -> bool:
    return (r, g, b) == (255, 101, 0)


def slot_cursor(f: Frame) -> int | None:
    """Selected slot (1 or 2) of the save/load list, from the orange cursor dot at the card's left edge."""
    for slot, y in ((1, 232), (2, 299)):
        if f.count(_ring_orange, 3, y - 6, 14, 12) >= 12:
            return slot
    return None
