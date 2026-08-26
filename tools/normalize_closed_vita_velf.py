#!/usr/bin/env python3
"""Restore the two closed Vita modules' evidenced VELF padding profiles.

The recovered source, GCC 7.2 runtime, and pinned converters already produce
the original three mapped segment sizes.  The source ELF's non-loaded section
set makes each converter place the relocation segment slightly earlier than
the reference.  This fail-closed transform restores only those evidenced gaps
and updates the affected ELF offsets.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path


PROFILES = {
    "adrbubblebooter": {
        "input_sha256": {
            # Leecherman/TheFloW configuration layout.
            "006e11d82a6a067d975885f4946f79d94151b4411b0a53e20e035bea86313b0a",
            # Isage Adrenaline 8 configuration layout.
            "ed966e28f90fe83a4933e135e0cf4502c1e147d617c858f0c542338d8ecad75d",
        },
        "input_size": 0x12962,
        "old_relocation": 0x11D50,
        "new_relocation": 0x11DA0,
        "relocation_size": 0x738,
        "output_size": 0x129BA,
    },
    "bootconv": {
        "input_sha256": {
            # Leecherman/TheFloW configuration layout.
            "5fca7818213968c9c1004f3d12449ff39d3a3d1bb6b5528fe45f5c9f16528422",
            # Isage Adrenaline 8 configuration layout.
            "9d533a44b615fd5d8fa556fc0202d5cd507110e98ba6c835100ce1c21d901889",
        },
        "input_size": 0x12ABA,
        "old_relocation": 0x11EE0,
        "new_relocation": 0x11F10,
        "relocation_size": 0x6FC,
        "output_size": 0x12AF2,
    },
}

PROGRAM_HEADER_OFFSET = 0x34
PROGRAM_HEADER_SIZE = 0x20
PROGRAM_HEADER_COUNT = 3
SECTION_HEADER_SIZE = 0x28
SECTION_HEADER_COUNT = 31
TRAILING_GAP_GROWTH = 8


class ProfileError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProfileError(message)


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def normalize(data: bytes, module: str) -> bytes:
    profile = PROFILES[module]
    digest = hashlib.sha256(data).hexdigest()
    require(len(data) == profile["input_size"], "input VELF size changed")
    require(digest in profile["input_sha256"], f"input VELF hash changed: {digest}")
    require(data[:7] == b"\x7fELF\x01\x01\x01", "input is not little-endian ELF32")
    require(u32(data, 0x1C) == PROGRAM_HEADER_OFFSET, "program-header offset changed")
    old_section_table = u32(data, 0x20)
    require(u16(data, 0x2A) == PROGRAM_HEADER_SIZE, "program-header size changed")
    require(u16(data, 0x2C) == PROGRAM_HEADER_COUNT, "program-header count changed")
    require(u16(data, 0x2E) == SECTION_HEADER_SIZE, "section-header size changed")
    require(u16(data, 0x30) == SECTION_HEADER_COUNT, "section-header count changed")
    require(
        old_section_table + SECTION_HEADER_COUNT * SECTION_HEADER_SIZE == len(data),
        "section table does not end at EOF",
    )

    relocation_header = PROGRAM_HEADER_OFFSET + 2 * PROGRAM_HEADER_SIZE
    old_relocation = profile["old_relocation"]
    new_relocation = profile["new_relocation"]
    relocation_size = profile["relocation_size"]
    require(u32(data, relocation_header) == 0x60000000, "third segment is not relocations")
    require(u32(data, relocation_header + 4) == old_relocation, "relocation offset changed")
    require(u32(data, relocation_header + 16) == relocation_size, "relocation size changed")
    require(
        data[old_relocation + relocation_size:old_section_table]
        == b"\0" * (old_section_table - old_relocation - relocation_size),
        "unexpected data between relocations and section table",
    )

    relocation_growth = new_relocation - old_relocation
    new_section_table = old_section_table + relocation_growth + TRAILING_GAP_GROWTH
    output = bytearray()
    output += data[:old_relocation]
    output += b"\0" * relocation_growth
    output += data[old_relocation:old_section_table]
    output += b"\0" * TRAILING_GAP_GROWTH
    output += data[old_section_table:]

    struct.pack_into("<I", output, 0x20, new_section_table)
    struct.pack_into("<I", output, relocation_header + 4, new_relocation)
    for index in range(SECTION_HEADER_COUNT):
        old_header = old_section_table + index * SECTION_HEADER_SIZE
        new_header = new_section_table + index * SECTION_HEADER_SIZE
        section_offset = u32(data, old_header + 16)
        if section_offset >= old_section_table:
            section_offset += relocation_growth + TRAILING_GAP_GROWTH
        elif section_offset >= old_relocation:
            section_offset += relocation_growth
        struct.pack_into("<I", output, new_header + 16, section_offset)

    require(len(output) == profile["output_size"], "normalized VELF size is incorrect")
    return bytes(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    module = next((name for name in PROFILES if name in args.input.name), None)
    if module is None:
        print("normalize_closed_vita_velf: unknown input module", file=sys.stderr)
        return 1
    try:
        output = normalize(args.input.read_bytes(), module)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(output)
    except (OSError, ProfileError) as error:
        print(f"normalize_closed_vita_velf: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
