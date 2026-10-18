"""Offline tests for the melonDS battle bot: RAM decoding, pixel detectors and cursor walking.

The emulator is replaced by a fake gdb stub (plain bytes) and a fake DS that moves a fake cursor, so these
run without melonDS and guard the layout constants found in docs/save_format_map.md section 10.
"""

import struct
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples" / "melonds" / "e2e"))

import battle  # noqa: E402
from battle import Battle  # noqa: E402
from dsbot import HEIGHT, WIDTH, Frame, bicon_visible, commands_visible, forecast_visible, hud, worldmap_visible  # noqa: E402

RAM_BASE = 0x02000000


class FakeRsp:
    """Sparse main RAM behind the same read/paused surface as rsp.Rsp."""

    def __init__(self):
        self.ram = bytearray(0x400000)

    def put(self, addr: int, data: bytes) -> None:
        self.ram[addr - RAM_BASE : addr - RAM_BASE + len(data)] = data

    def read(self, addr: int, length: int) -> bytes:
        return bytes(self.ram[addr - RAM_BASE : addr - RAM_BASE + length])

    @contextmanager
    def paused(self):
        yield self


def put_unit(rsp: FakeRsp, base: int, job: int, status: int, level: int, hp: int, max_hp: int) -> None:
    rsp.put(base + 0x0E, bytes([job]))
    rsp.put(base + 0x12, struct.pack("<H", status))
    rsp.put(base + 0x22, bytes([level]))
    rsp.put(base + 0x3C, struct.pack("<HH", hp, max_hp))


def put_record(rsp: FakeRsp, index: int, x: int, y: int, unit_base: int) -> None:
    pos = battle.POS_TABLE + index * battle.POS_STRIDE
    rsp.put(pos, bytes([x, y]))
    rsp.put(pos - 8, struct.pack("<I", unit_base + 8))


def make_roster_rsp() -> FakeRsp:
    rsp = FakeRsp()
    foe0 = battle.FOE_TABLE
    foe1 = battle.FOE_TABLE + battle.UNIT_STRIDE
    foe2 = battle.FOE_TABLE + 2 * battle.UNIT_STRIDE
    guest = battle.FOE_TABLE + 3 * battle.UNIT_STRIDE
    ours = battle.CLAN_TABLE + 4 * battle.UNIT_STRIDE
    put_unit(rsp, foe0, 87, 0x0099, 8, 114, 114)
    put_unit(rsp, foe1, 88, 0x0099, 5, 0, 89)  # KO'd foe keeps its struct with 0 HP
    put_unit(rsp, foe2, 88, 0x0099, 5, 47, 89)
    put_unit(rsp, guest, 14, 0x009C, 8, 162, 165)
    put_unit(rsp, ours, 12, 0x2088, 5, 119, 119)
    put_record(rsp, 0, 3, 7, foe0)
    put_record(rsp, 1, 9, 5, foe1)
    put_record(rsp, 2, 9, 6, foe2)
    put_record(rsp, 3, 8, 5, guest)
    put_record(rsp, 4, 4, 2, ours)
    # placeholder record pointing outside both unit tables must be ignored
    put_record(rsp, 5, 11, 12, battle.FOE_TABLE - 0x1000)
    return rsp


def test_roster_decode():
    bot = Battle(None, make_roster_rsp(), log=lambda _m: None)
    units = bot.roster()
    by_pos = {u.pos: u for u in units}
    assert set(by_pos) == {(3, 7), (9, 5), (9, 6), (8, 5), (4, 2)}, sorted(by_pos)
    assert by_pos[(3, 7)].side == "foe" and by_pos[(3, 7)].alive
    assert by_pos[(9, 6)].side == "foe" and by_pos[(9, 6)].hp == 47 and by_pos[(9, 6)].max_hp == 89
    assert not by_pos[(9, 5)].alive, "HP 0 means KO'd"
    assert by_pos[(8, 5)].side == "guest"
    assert by_pos[(4, 2)].side == "ours" and by_pos[(4, 2)].job == 12
    assert sum(1 for u in units if u.side == "foe" and u.alive) == 2
    assert by_pos[(4, 2)].dist(by_pos[(3, 7)]) == 6
    print("[PASS] battle roster decoded from the position records and unit structs")


def blank_frame() -> bytearray:
    return bytearray(WIDTH * HEIGHT * 3)


def paint(data: bytearray, color: tuple[int, int, int], x: int, y: int, w: int, h: int) -> None:
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            i = (yy * WIDTH + xx) * 3
            data[i : i + 3] = bytes(color)


def test_frame_detectors():
    f = Frame(bytes(blank_frame()))
    assert not commands_visible(f) and not bicon_visible(f) and not worldmap_visible(f)
    assert hud(f) == "none" and not forecast_visible(f)

    d = blank_frame()
    paint(d, (231, 166, 52), 165, 352, 90, 15)  # amber Config button, the COMMANDS menu only
    assert commands_visible(Frame(bytes(d)))

    d = blank_frame()
    paint(d, (231, 166, 52), 216, 190, 40, 28)
    assert bicon_visible(Frame(bytes(d)))

    d = blank_frame()
    paint(d, (255, 150, 28), 181, 194, 74, 15)
    assert worldmap_visible(Frame(bytes(d)))

    d = blank_frame()
    paint(d, (142, 36, 44), 70, 340, 50, 8)
    assert hud(Frame(bytes(d))) == "foe"
    paint(d, (20, 77, 125), 160, 340, 50, 8)
    assert forecast_visible(Frame(bytes(d)))
    d = blank_frame()
    paint(d, (20, 77, 125), 70, 340, 50, 8)
    assert hud(Frame(bytes(d))) == "ally" and not forecast_visible(Frame(bytes(d)))
    print("[PASS] pixel detectors fire on their signatures and stay quiet on a blank frame")


class FakeCursorWorld:
    """Fake DS: taps move the cursor stored in the fake RAM, with a configurable key mapping."""

    def __init__(self, rsp: FakeRsp, mapping: dict[str, tuple[int, int]], blocked: set[tuple[int, int]] | None = None):
        self.rsp, self.mapping, self.blocked = rsp, mapping, blocked or set()
        self.x, self.y = 4, 4
        self.taps = 0
        self.sync()

    def sync(self) -> None:
        self.rsp.put(battle.CURSOR + 2, struct.pack("<HH", self.x, self.y))

    def tap(self, key: str, _hold: float = 0.12, _after: float = 0.7) -> None:
        self.taps += 1
        dx, dy = self.mapping[key]
        nx, ny = self.x + dx, self.y + dy
        if (nx, ny) not in self.blocked:
            self.x, self.y = nx, ny
        self.sync()


def test_goto_tile_learns_rotated_keys():
    rsp = FakeRsp()
    rotated = {"right": (0, 1), "left": (0, -1), "down": (-1, 0), "up": (1, 0)}
    world = FakeCursorWorld(rsp, rotated)
    bot = Battle(world, rsp, log=lambda _m: None)
    assert bot.goto_tile(7, 2)
    assert (world.x, world.y) == (7, 2)
    assert world.taps <= 8, f"learned the rotation quickly (took {world.taps} taps)"
    print("[PASS] goto_tile reaches its tile even with rotated D-pad directions")


def test_goto_tile_gives_up_on_void_tiles():
    rsp = FakeRsp()
    plain = {"right": (1, 0), "left": (-1, 0), "down": (0, 1), "up": (0, -1)}
    world = FakeCursorWorld(rsp, plain, blocked={(5, 4), (4, 5), (3, 4), (4, 3)})
    bot = Battle(world, rsp, log=lambda _m: None)
    assert not bot.goto_tile(9, 9)
    assert world.taps <= 4, f"stall detection should stop after a few dead taps (took {world.taps})"
    print("[PASS] goto_tile gives up quickly when the cursor cannot move")


if __name__ == "__main__":
    test_roster_decode()
    test_frame_detectors()
    test_goto_tile_learns_rotated_keys()
    test_goto_tile_gives_up_on_void_tiles()
