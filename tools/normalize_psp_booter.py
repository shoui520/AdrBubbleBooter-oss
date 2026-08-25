#!/usr/bin/env python3
"""Restore historical PRX relocation flags after the layout-only link."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


ELF_HEADER = struct.Struct("<16sHHIIIIIHHHHHH")
PROGRAM_HEADER = struct.Struct("<IIIIIIII")
SECTION_HEADER = struct.Struct("<IIIIIIIIII")
SHF_INFO_LINK = 0x40

# Complete section-header profile recovered from the pristine embedded
# booter.prx. Only SHF_INFO_LINK is permitted as a pre-normalization delta.
REFERENCE_SECTIONS = (
    (0x00, 0x00000000, 0x00000000, 0x000, 0x0000, 0x000, 0, 0x00, 0x00, 0x0),
    (0x01, 0x00000001, 0x00000006, 0x000, 0x0060, 0x564, 0, 0x00, 0x04, 0x0),
    (0x07, 0x700000A0, 0x00000000, 0x000, 0x0D3C, 0x398, 0, 0x01, 0x04, 0x8),
    (0x11, 0x00000001, 0x00000006, 0x564, 0x05C4, 0x0A8, 0, 0x00, 0x04, 0x0),
    (0x1F, 0x00000001, 0x00000002, 0x60C, 0x066C, 0x004, 0, 0x00, 0x04, 0x0),
    (0x2C, 0x00000001, 0x00000002, 0x610, 0x0670, 0x004, 0, 0x00, 0x04, 0x0),
    (0x39, 0x00000001, 0x00000002, 0x614, 0x0674, 0x004, 0, 0x00, 0x04, 0x0),
    (0x47, 0x00000001, 0x00000002, 0x618, 0x0678, 0x08C, 0, 0x00, 0x04, 0x0),
    (0x51, 0x700000A0, 0x00000000, 0x000, 0x10D4, 0x0A8, 0, 0x07, 0x04, 0x8),
    (0x5F, 0x00000001, 0x00000002, 0x6A4, 0x0704, 0x004, 0, 0x00, 0x04, 0x0),
    (0x6D, 0x00000001, 0x00000002, 0x6B0, 0x0710, 0x040, 0, 0x00, 0x10, 0x0),
    (0x83, 0x700000A0, 0x00000000, 0x000, 0x117C, 0x028, 0, 0x0A, 0x04, 0x8),
    (0x9D, 0x00000001, 0x00000002, 0x6F0, 0x0750, 0x0A0, 0, 0x00, 0x04, 0x0),
    (0xB1, 0x00000001, 0x00000002, 0x790, 0x07F0, 0x054, 0, 0x00, 0x04, 0x0),
    (0xC0, 0x00000001, 0x00000002, 0x7E4, 0x0844, 0x100, 0, 0x00, 0x04, 0x0),
    (0xC8, 0x00000001, 0x00000003, 0x9E4, 0x0A44, 0x000, 0, 0x00, 0x01, 0x0),
    (0xCE, 0x00000008, 0x10000003, 0x9E4, 0x0A44, 0x000, 0, 0x00, 0x01, 0x0),
    (0xD4, 0x00000008, 0x00000003, 0x9E4, 0x0A44, 0x150, 0, 0x00, 0x04, 0x0),
    (0xD9, 0x00000003, 0x00000000, 0x000, 0x11A4, 0x0E6, 0, 0x00, 0x01, 0x0),
)
RELOCATION_SECTIONS = (2, 8, 11)
REFERENCE_SHSTRTAB = (
    b"\0.text\0.rel.text\0.sceStub.text\0.lib.ent.top\0.lib.ent.btm\0"
    b".lib.stub.top\0.lib.stub\0.rel.lib.stub\0.lib.stub.btm\0"
    b".rodata.sceModuleInfo\0.rel.rodata.sceModuleInfo\0"
    b".rodata.sceResident\0.rodata.sceNid\0.rodata\0.data\0.sbss\0"
    b".bss\0.shstrtab\0\0\0\0"
)


def validate_profile(data: bytes | bytearray, allow_info_link: bool = False) -> None:
    if len(data) != 0x128A:
        raise RuntimeError(f"unexpected PSP booter size: 0x{len(data):X}")

    header = ELF_HEADER.unpack_from(data)
    identity = header[0]
    if identity != b"\x7fELF\x01\x01\x01" + bytes(9):
        raise RuntimeError("PSP booter is not ELF32 little-endian")
    expected_header = (
        0xFFA0, 8, 1, 8, 0x34, 0xA44, 0x10A23001,
        0x34, 0x20, 1, 0x28, 19, 18,
    )
    if header[1:] != expected_header:
        raise RuntimeError("PSP booter ELF header differs from the reference profile")
    if PROGRAM_HEADER.unpack_from(data, 0x34) != (
        1, 0x60, 0, 0x80000710, 0x9E4, 0xB34, 5, 0x10,
    ):
        raise RuntimeError("PSP booter load segment differs from the reference profile")

    section_table = 0xA44
    for index, expected in enumerate(REFERENCE_SECTIONS):
        offset = section_table + index * SECTION_HEADER.size
        actual = SECTION_HEADER.unpack_from(data, offset)
        allowed_flags = (expected[2],)
        if allow_info_link and index in RELOCATION_SECTIONS:
            allowed_flags += (expected[2] | SHF_INFO_LINK,)
        if actual[2] not in allowed_flags:
            raise RuntimeError(f"unexpected flags in PSP booter section {index}")
        comparable = actual[:2] + (expected[2],) + actual[3:]
        if comparable != expected:
            raise RuntimeError(f"PSP booter section {index} differs from the reference profile")

    if data[0x11A4:0x128A] != REFERENCE_SHSTRTAB:
        raise RuntimeError("PSP booter section-name table differs from the reference profile")


def normalize(path: Path) -> None:
    data = bytearray(path.read_bytes())
    validate_profile(data, allow_info_link=True)
    section_table = 0xA44
    for index in RELOCATION_SECTIONS:
        offset = section_table + index * SECTION_HEADER.size
        expected = REFERENCE_SECTIONS[index]
        struct.pack_into("<I", data, offset + 8, expected[2])

    path.write_bytes(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prx", type=Path)
    args = parser.parse_args()
    normalize(args.prx)


if __name__ == "__main__":
    main()
