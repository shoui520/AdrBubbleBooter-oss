#!/usr/bin/env python3
"""Reconstruct the plain ELF payload carried by an unencrypted Vita FSELF.

The parser follows the structures and write order used by VitaSDK's
vita-make-fself. It deliberately rejects encrypted segments and unknown
compression modes instead of guessing.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import zlib
from pathlib import Path


SCE_MAGIC = b"SCE\0"
ELF32_HEADER_SIZE = 0x34
ELF32_PROGRAM_HEADER_SIZE = 0x20
SEGMENT_INFO_SIZE = 0x20


class FselfError(ValueError):
    pass


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def checked_slice(data: bytes, offset: int, size: int, description: str) -> bytes:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise FselfError(
            f"{description} exceeds input: offset=0x{offset:X}, size=0x{size:X}"
        )
    return data[offset : offset + size]


def unpack_fself(data: bytes) -> tuple[bytes, dict[str, object], list[bytes]]:
    if len(data) < 0x80 or data[:4] != SCE_MAGIC:
        raise FselfError("input is not a Vita SCE/FSELF container")

    header = {
        "version": u32(data, 0x04),
        "sdk_type": u16(data, 0x08),
        "header_type": u16(data, 0x0A),
        "metadata_offset": u32(data, 0x0C),
        "header_length": u64(data, 0x10),
        "elf_file_size": u64(data, 0x18),
        "self_file_size": u64(data, 0x20),
        "unknown": u64(data, 0x28),
        "self_offset": u64(data, 0x30),
        "appinfo_offset": u64(data, 0x38),
        "elf_offset": u64(data, 0x40),
        "program_header_offset": u64(data, 0x48),
        "section_header_offset": u64(data, 0x50),
        "section_info_offset": u64(data, 0x58),
        "sce_version_offset": u64(data, 0x60),
        "control_info_offset": u64(data, 0x68),
        "control_info_size": u64(data, 0x70),
        "padding": u64(data, 0x78),
    }

    appinfo_offset = int(header["appinfo_offset"])
    appinfo_data = checked_slice(data, appinfo_offset, 0x20, "SELF app info")
    auth_id, vendor_id, self_type, app_version, app_padding = struct.unpack(
        "<QIIQQ", appinfo_data
    )
    appinfo = {
        "auth_id": auth_id,
        "vendor_id": vendor_id,
        "self_type": self_type,
        "version": app_version,
        "padding": app_padding,
    }

    sce_version_offset = int(header["sce_version_offset"])
    sce_version_data = checked_slice(data, sce_version_offset, 0x10, "SCE version")
    version_fields = struct.unpack("<IIII", sce_version_data)
    sce_version = {
        "unknown_1": version_fields[0],
        "unknown_2": version_fields[1],
        "unknown_3": version_fields[2],
        "unknown_4": version_fields[3],
    }

    control_offset = int(header["control_info_offset"])
    control_end = control_offset + int(header["control_info_size"])
    checked_slice(data, control_offset, control_end - control_offset, "control info")
    control_info: list[dict[str, object]] = []
    cursor = control_offset
    while cursor < control_end:
        record_header = checked_slice(data, cursor, 0x10, "control-info header")
        record_type, record_size, unknown, padding = struct.unpack(
            "<IIII", record_header
        )
        if record_size < 0x10 or cursor + record_size > control_end:
            raise FselfError(
                f"invalid control-info record size 0x{record_size:X} at 0x{cursor:X}"
            )
        payload = checked_slice(
            data, cursor + 0x10, record_size - 0x10, "control-info payload"
        )
        control_info.append(
            {
                "type": record_type,
                "size": record_size,
                "unknown": unknown,
                "padding": padding,
                "payload_hex": payload.hex(),
            }
        )
        cursor += record_size
    if cursor != control_end:
        raise FselfError("control-info records do not exactly fill the table")

    elf_offset = int(header["elf_offset"])
    embedded_header = checked_slice(data, elf_offset, ELF32_HEADER_SIZE, "ELF header")
    if embedded_header[:4] != b"\x7fELF" or embedded_header[4:6] != b"\x01\x01":
        raise FselfError("container does not carry a little-endian ELF32 header")

    elf_phoff = u32(embedded_header, 0x1C)
    original_section_header_offset = u32(embedded_header, 0x20)
    elf_phentsize = u16(embedded_header, 0x2A)
    elf_phnum = u16(embedded_header, 0x2C)
    original_section_header_size = u16(embedded_header, 0x2E)
    original_section_header_count = u16(embedded_header, 0x30)
    original_section_name_index = u16(embedded_header, 0x32)
    if elf_phentsize != ELF32_PROGRAM_HEADER_SIZE:
        raise FselfError(f"unsupported ELF program-header size: 0x{elf_phentsize:X}")

    self_phoff = int(header["program_header_offset"])
    section_info_offset = int(header["section_info_offset"])
    program_headers = checked_slice(
        data,
        self_phoff,
        elf_phnum * elf_phentsize,
        "SELF program-header table",
    )

    elf_size = int(header["elf_file_size"])
    if elf_size < ELF32_HEADER_SIZE:
        raise FselfError(f"invalid reconstructed ELF size: 0x{elf_size:X}")
    output = bytearray(elf_size)
    output[:ELF32_HEADER_SIZE] = embedded_header
    output[elf_phoff : elf_phoff + len(program_headers)] = program_headers

    segment_records: list[dict[str, int]] = []
    segment_payloads: list[bytes] = []
    for index in range(elf_phnum):
        phdr_offset = index * elf_phentsize
        p_offset = u32(program_headers, phdr_offset + 0x04)
        p_filesz = u32(program_headers, phdr_offset + 0x10)

        info_offset = section_info_offset + index * SEGMENT_INFO_SIZE
        info = checked_slice(data, info_offset, SEGMENT_INFO_SIZE, "segment info")
        stored_offset, stored_size, compression, encryption = struct.unpack(
            "<QQQQ", info
        )
        if encryption != 2:
            raise FselfError(
                f"segment {index} is encrypted or has unknown encryption mode {encryption}"
            )

        stored = checked_slice(data, stored_offset, stored_size, f"segment {index}")
        if compression == 1:
            payload = stored
        elif compression == 2:
            try:
                payload = zlib.decompress(stored)
            except zlib.error as error:
                raise FselfError(f"segment {index} zlib failure: {error}") from error
        else:
            raise FselfError(
                f"segment {index} has unknown compression mode {compression}"
            )

        if len(payload) != p_filesz:
            raise FselfError(
                f"segment {index} expands to 0x{len(payload):X}, expected 0x{p_filesz:X}"
            )
        if p_offset + p_filesz > len(output):
            raise FselfError(f"segment {index} exceeds reconstructed ELF size")

        output[p_offset : p_offset + p_filesz] = payload
        segment_payloads.append(payload)
        segment_records.append(
            {
                "index": index,
                "elf_offset": p_offset,
                "file_size": p_filesz,
                "stored_offset": stored_offset,
                "stored_size": stored_size,
                "compression": compression,
                "encryption": encryption,
            }
        )

    # Segment zero contains the original VELF header and overwrites the
    # container's synthetic header copied above. vita-make-fself records the
    # input VELF's section-table fields but does not carry the section table
    # itself. Advertising the absent table makes ordinary ELF tools parse
    # zero-filled bytes as corrupt section headers. Keep the original values
    # in metadata and mark the reconstructed ELF as sectionless after all
    # segments have been restored.
    struct.pack_into("<I", output, 0x20, 0)
    struct.pack_into("<HHH", output, 0x2E, 0, 0, 0)

    metadata: dict[str, object] = {
        "sce_header": header,
        "appinfo": appinfo,
        "sce_version": sce_version,
        "control_info": control_info,
        "elf": {
            "program_header_offset": elf_phoff,
            "program_header_size": elf_phentsize,
            "program_header_count": elf_phnum,
            "original_section_header_offset": original_section_header_offset,
            "original_section_header_size": original_section_header_size,
            "original_section_header_count": original_section_header_count,
            "original_section_name_index": original_section_name_index,
        },
        "segments": segment_records,
    }
    return bytes(output), metadata, segment_payloads


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="input Vita FSELF/SUPRX/SKPRX")
    parser.add_argument("output", type=Path, help="output reconstructed ELF")
    parser.add_argument("--metadata", type=Path, help="write parsed metadata as JSON")
    parser.add_argument(
        "--segments-dir", type=Path, help="also write each decompressed segment"
    )
    args = parser.parse_args()

    try:
        reconstructed, metadata, segments = unpack_fself(args.input.read_bytes())
    except (OSError, FselfError) as error:
        print(f"unpack_fself: {error}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(reconstructed)

    if args.metadata:
        args.metadata.parent.mkdir(parents=True, exist_ok=True)
        args.metadata.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    if args.segments_dir:
        args.segments_dir.mkdir(parents=True, exist_ok=True)
        for index, payload in enumerate(segments):
            (args.segments_dir / f"segment-{index}.bin").write_bytes(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
