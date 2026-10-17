"""FFTA2 NDS ROM and NitroFS Archive extraction module."""

from __future__ import annotations

import os
import struct
from pathlib import Path
from typing import Any

from ffta2_tool.charset import decode_ffta2_string


def filename_crc(name: str) -> int:
    """Calculate 10-bit filename CRC used by FFTA2 master archive (pc.idx)."""
    b = name.encode("utf-8")
    crc = b[0]
    for x in b[1:]:
        crc = crc * 0x25 + x
    return crc & 0x3FF


def unpack_pak(idx_bytes: bytes, pak_bytes: bytes) -> list[bytes | None]:
    """Unpack an Idx/Pak pair into individual subfiles."""
    if len(idx_bytes) < 4:
        return []
    num_entries = (len(idx_bytes) - 4) // 6
    subfiles: list[bytes | None] = []

    for i in range(num_entries):
        a1 = struct.unpack_from("<I", idx_bytes, 4 + i * 6)[0]
        ab1 = ((a1 << 5) & 0xFFFFFFFF) // 0x100
        if (a1 & 7) != 0:
            if i != num_entries - 1:
                subfiles.append(None)
            continue
        if i + 1 < num_entries:
            a2 = struct.unpack_from("<I", idx_bytes, 4 + (i + 1) * 6)[0]
            ab2 = ((a2 << 5) & 0xFFFFFFFF) // 0x100
            sz = (ab2 - ab1) << 2
        else:
            sz = len(pak_bytes) - (ab1 << 2)
        offset = ab1 << 2
        subfiles.append(pak_bytes[offset : offset + sz])

    return subfiles


class FFTA2Rom:
    """Interface to parse and query FFTA2 NDS ROM archives."""

    def __init__(self, rom_path: str | Path | None = None, rom_bytes: bytes | None = None):
        if rom_bytes is not None:
            self._rom = rom_bytes
        elif rom_path is not None:
            self._rom = Path(rom_path).read_bytes()
        else:
            detected = self.auto_detect_rom()
            if not detected:
                raise FileNotFoundError(
                    "ROM path not provided and no FFTA2 NDS ROM found in environment or standard paths."
                )
            self._rom = detected.read_bytes()

        self._fat: list[tuple[int, int]] = []
        self._files: list[Any] = []
        self._parse_fat()
        self._parse_nitro_archive()

    @staticmethod
    def auto_detect_rom() -> Path | None:
        """Find FFTA2 ROM via environment variable or standard relative/system locations."""
        env_path = os.environ.get("FFTA2_ROM_PATH")
        if env_path and Path(env_path).is_file():
            return Path(env_path)

        candidates = [
            Path("/tmp/ffta2_game.nds"),
            Path("ffta2.nds"),
        ]
        for c in candidates:
            if c.is_file():
                return c
        return None

    def _parse_fat(self) -> None:
        fat_off, fat_sz = struct.unpack_from("<II", self._rom, 0x48)
        num_files = fat_sz // 8
        for i in range(num_files):
            start, end = struct.unpack_from("<II", self._rom, fat_off + i * 8)
            self._fat.append((start, end))

    def _parse_nitro_archive(self) -> None:
        # File 19 = pc.bin, File 20 = pc.idx in standard FFTA2 US/EU releases
        pc_bin_s, pc_bin_e = self._fat[19]
        pc_idx_s, pc_idx_e = self._fat[20]

        pc_bin = self._rom[pc_bin_s:pc_bin_e]
        pc_idx = self._rom[pc_idx_s:pc_idx_e]

        num_ids = struct.unpack_from("<I", pc_idx, 0)[0]
        table_by_ids: list[tuple[int, int]] = []
        pos = 8
        for _ in range(num_ids):
            a, b = struct.unpack_from("<II", pc_idx, pos)
            table_by_ids.append((a, b))
            pos += 9

        extra_start = pos
        extra = pc_idx[extra_start:]

        bottom_table: dict[int, list[tuple[int, int, int, int]]] = {}
        epos = 0
        while epos < len(extra):
            start_offset = epos
            num_entries = extra[epos]
            epos += 1
            if num_entries == 0:
                break
            lf = []
            for i in range(num_entries):
                offset = struct.unpack_from("<I", extra, epos)[0]
                epos += 4
                if i == 0:
                    size = 0
                else:
                    size = struct.unpack_from("<I", extra, epos)[0]
                    epos += 8
                chr_val = extra[epos]
                chr_pos = extra[epos + 1]
                epos += 3
                lf.append((offset * 4, size * 4, chr_val, chr_pos))
            bottom_table[start_offset] = lf

        self._files = []
        for a, b in table_by_ids:
            if a == 0 and b == 0:
                self._files.append(None)
                continue
            of = (a & 0x3FFFFFF) * 2
            sz = ((a >> 26) + (b & 0xFFFF) * 64) * 4
            if a % 2 == 1:
                idx = (of // 4) - extra_start
                entries = bottom_table.get(idx, [])
                flist = []
                for extra_data in entries:
                    new_size = sz if extra_data[1] == 0 else extra_data[1]
                    flist.append((extra_data[2], extra_data[3], pc_bin[extra_data[0] : extra_data[0] + new_size]))
                self._files.append(("list", flist))
            else:
                self._files.append(("single", pc_bin[of : of + sz]))

    def get_file(self, name: str) -> bytes | None:
        """Lookup and retrieve an internal file from the ROM archive by path."""
        fid = filename_crc(name)
        if fid >= len(self._files) or self._files[fid] is None:
            return None
        entry = self._files[fid]
        if entry[0] == "single":
            return entry[1]
        for chr_val, chr_pos, data in entry[1]:
            if chr_pos < len(name) and ord(name[chr_pos]) == chr_val:
                return data
        return None

    def get_locations(self) -> list[str]:
        """Decode and return the full location names table from JD_message."""
        jd_idx = self.get_file("system/rom/JD_message_rom_0.idx")
        jd_pak = self.get_file("system/rom/JD_message_0.pak")
        if not jd_idx or not jd_pak:
            return []
        sub = unpack_pak(jd_idx, jd_pak)
        if len(sub) <= 5 or sub[5] is None:
            return []
        loc_table = sub[5]
        num_entries = struct.unpack_from("<H", loc_table, 0)[0]
        locations: list[str] = []
        pos = 2
        for _ in range(num_entries):
            string_len, offset, _ = struct.unpack_from("<IIH", loc_table, pos)
            pos += 10
            locations.append(decode_ffta2_string(loc_table[offset : offset + string_len], string_len))
        return locations

    def get_all_quests(self) -> list[dict[str, Any]]:
        """Extract and parse all quests, including story requirements, locations, and names."""
        sys_idx = self.get_file("system/rom/sysdata_rom.idx")
        sys_pak = self.get_file("system/rom/sysdata.pak")
        if not sys_idx or not sys_pak:
            return []
        sys_sub = unpack_pak(sys_idx, sys_pak)
        if len(sys_sub) <= 11 or sys_sub[11] is None:
            return []
        quest_data = sys_sub[11]

        qtext_idx = self.get_file("system/rom/JH_questtext_rom_0.idx")
        qtext_pak = self.get_file("system/rom/JH_questtext_0.pak")
        qtext_sub = unpack_pak(qtext_idx, qtext_pak) if qtext_idx and qtext_pak else []

        locations = self.get_locations()
        num_quests = len(quest_data) // 100
        quests: list[dict[str, Any]] = []

        for qid in range(num_quests):
            q = quest_data[qid * 100 : (qid + 1) * 100]
            qtype = q[0]
            qgroup = q[1]
            qrank = q[2]
            qregion = q[3]
            story_req, flag_req, unk_idx = struct.unpack_from("<HHH", q, 4)
            loc_id = q[0x21]
            battlefield = struct.unpack_from("<H", q, 0x22)[0]

            name = ""
            if qid < len(qtext_sub) and qtext_sub[qid] and len(qtext_sub[qid]) > 0x0E:
                name = decode_ffta2_string(qtext_sub[qid][0x0E:], 48)

            loc_name = locations[loc_id] if loc_id < len(locations) else f"Unknown ({loc_id})"

            quests.append(
                {
                    "id": qid,
                    "name": name,
                    "type": qtype,
                    "group": qgroup,
                    "rank": qrank,
                    "region": qregion,
                    "story_req": story_req,
                    "flag_req": flag_req,
                    "location_id": loc_id,
                    "location_name": loc_name,
                    "battlefield": battlefield,
                }
            )

        return quests
