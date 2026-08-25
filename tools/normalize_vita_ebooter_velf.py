#!/usr/bin/env python3
"""Restore the pristine AdrBubbleBooter v1.3 ebooter VELF padding profile.

The reconstructed source and pinned Vita toolchain already reproduce every
loader-mapped byte.  The original converter placed the relocation segment 16
bytes later and left four additional zero bytes before the section table.
This transform is deliberately tied to the exact verified input profile and
rejects every other ELF instead of inferring a layout.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path


INPUT_SHA256 = "da0b6fbcf24c5eb7ccc61979c53df25311a9ff29eee3c348b1cddd9d7bdb704d"
INPUT_SIZE = 0x2FECA
OUTPUT_SIZE = 0x2FEDE
OLD_RELOCATION_OFFSET = 0x2B780
NEW_RELOCATION_OFFSET = 0x2B790
RELOCATION_SIZE = 0x4038
OLD_SECTION_TABLE_OFFSET = 0x2F7C2
NEW_SECTION_TABLE_OFFSET = 0x2F7D6
PROGRAM_HEADER_OFFSET = 0x34
PROGRAM_HEADER_SIZE = 0x20
PROGRAM_HEADER_COUNT = 3
SECTION_HEADER_SIZE = 0x28
SECTION_HEADER_COUNT = 45


class ProfileError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProfileError(message)


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def normalize(data: bytes) -> bytes:
    digest = hashlib.sha256(data).hexdigest()
    require(len(data) == INPUT_SIZE, f"input size is 0x{len(data):X}, expected 0x{INPUT_SIZE:X}")
    require(digest == INPUT_SHA256, f"input SHA-256 is {digest}, expected {INPUT_SHA256}")
    require(data[:7] == b"\x7fELF\x01\x01\x01", "input is not little-endian ELF32")
    require(u32(data, 0x1C) == PROGRAM_HEADER_OFFSET, "program-header offset changed")
    require(u32(data, 0x20) == OLD_SECTION_TABLE_OFFSET, "section-table offset changed")
    require(u16(data, 0x2A) == PROGRAM_HEADER_SIZE, "program-header size changed")
    require(u16(data, 0x2C) == PROGRAM_HEADER_COUNT, "program-header count changed")
    require(u16(data, 0x2E) == SECTION_HEADER_SIZE, "section-header size changed")
    require(u16(data, 0x30) == SECTION_HEADER_COUNT, "section-header count changed")

    relocation_phdr = PROGRAM_HEADER_OFFSET + 2 * PROGRAM_HEADER_SIZE
    require(u32(data, relocation_phdr) == 0x60000000, "third segment is not Vita relocations")
    require(u32(data, relocation_phdr + 4) == OLD_RELOCATION_OFFSET, "relocation offset changed")
    require(u32(data, relocation_phdr + 16) == RELOCATION_SIZE, "relocation size changed")
    require(
        data[OLD_RELOCATION_OFFSET + RELOCATION_SIZE:OLD_SECTION_TABLE_OFFSET] == b"\0" * 10,
        "unexpected bytes between relocation payload and section table",
    )
    require(
        OLD_SECTION_TABLE_OFFSET + SECTION_HEADER_COUNT * SECTION_HEADER_SIZE == len(data),
        "section table does not end at EOF",
    )

    output = bytearray()
    output += data[:OLD_RELOCATION_OFFSET]
    output += b"\0" * (NEW_RELOCATION_OFFSET - OLD_RELOCATION_OFFSET)
    output += data[OLD_RELOCATION_OFFSET:OLD_SECTION_TABLE_OFFSET]
    output += b"\0" * (
        NEW_SECTION_TABLE_OFFSET
        - (OLD_SECTION_TABLE_OFFSET + NEW_RELOCATION_OFFSET - OLD_RELOCATION_OFFSET)
    )
    output += data[OLD_SECTION_TABLE_OFFSET:]

    struct.pack_into("<I", output, 0x20, NEW_SECTION_TABLE_OFFSET)
    struct.pack_into("<I", output, relocation_phdr + 4, NEW_RELOCATION_OFFSET)

    for index in range(SECTION_HEADER_COUNT):
        old_header = OLD_SECTION_TABLE_OFFSET + index * SECTION_HEADER_SIZE
        new_header = NEW_SECTION_TABLE_OFFSET + index * SECTION_HEADER_SIZE
        section_offset = u32(data, old_header + 16)
        if section_offset >= OLD_SECTION_TABLE_OFFSET:
            section_offset += NEW_SECTION_TABLE_OFFSET - OLD_SECTION_TABLE_OFFSET
        elif section_offset >= OLD_RELOCATION_OFFSET:
            section_offset += NEW_RELOCATION_OFFSET - OLD_RELOCATION_OFFSET
        struct.pack_into("<I", output, new_header + 16, section_offset)

    require(len(output) == OUTPUT_SIZE, "normalized output size is incorrect")
    require(u32(output, 0x20) == NEW_SECTION_TABLE_OFFSET, "section-table rewrite failed")
    require(u32(output, relocation_phdr + 4) == NEW_RELOCATION_OFFSET, "relocation rewrite failed")
    return bytes(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        output = normalize(args.input.read_bytes())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(output)
    except (OSError, ProfileError) as error:
        print(f"normalize_vita_ebooter_velf: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
