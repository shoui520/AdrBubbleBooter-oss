#!/usr/bin/env python3
"""Inspect the loader-visible structure of an unencrypted Vita SELF or VELF.

This deliberately implements only the historical ELF32/Vita structures used
by AdrBubbleBooter.  Unknown layouts are rejected instead of being guessed.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Any

from unpack_fself import unpack_fself


ELF_HEADER = struct.Struct("<16sHHIIIIIHHHHHH")
PROGRAM_HEADER = struct.Struct("<IIIIIIII")
MODULE_INFO_SIZE = 0x5C
PROCESS_PARAM_SIZE = 0x34


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_u16(data: bytes, offset: int) -> int:
    require(0 <= offset <= len(data) - 2, f"u16 outside ELF at 0x{offset:X}")
    return struct.unpack_from("<H", data, offset)[0]


def read_u32(data: bytes, offset: int) -> int:
    require(0 <= offset <= len(data) - 4, f"u32 outside ELF at 0x{offset:X}")
    return struct.unpack_from("<I", data, offset)[0]


def read_c_string(data: bytes, offset: int, limit: int = 0x1000) -> str:
    require(0 <= offset < len(data), f"string outside ELF at 0x{offset:X}")
    end = data.find(b"\0", offset, min(len(data), offset + limit))
    require(end >= 0, f"unterminated string at 0x{offset:X}")
    return data[offset:end].decode("ascii")


def parse_elf(data: bytes) -> tuple[dict[str, Any], list[dict[str, int]]]:
    require(len(data) >= ELF_HEADER.size, "truncated ELF header")
    fields = ELF_HEADER.unpack_from(data)
    ident = fields[0]
    require(ident[:7] == b"\x7fELF\x01\x01\x01", "not a little-endian ELF32")
    header = {
        "type": fields[1],
        "machine": fields[2],
        "version": fields[3],
        "entry": fields[4],
        "program_header_offset": fields[5],
        "section_header_offset": fields[6],
        "flags": fields[7],
        "elf_header_size": fields[8],
        "program_header_size": fields[9],
        "program_header_count": fields[10],
        "section_header_size": fields[11],
        "section_header_count": fields[12],
        "section_name_index": fields[13],
    }
    require(header["elf_header_size"] == ELF_HEADER.size, "unexpected ELF header size")
    require(header["program_header_size"] == PROGRAM_HEADER.size, "unexpected program-header size")
    program_headers = []
    for index in range(header["program_header_count"]):
        offset = header["program_header_offset"] + index * PROGRAM_HEADER.size
        require(offset <= len(data) - PROGRAM_HEADER.size, "truncated program-header table")
        values = PROGRAM_HEADER.unpack_from(data, offset)
        program_headers.append(
            dict(
                index=index,
                type=values[0],
                offset=values[1],
                vaddr=values[2],
                paddr=values[3],
                filesz=values[4],
                memsz=values[5],
                flags=values[6],
                align=values[7],
            )
        )
    return header, program_headers


def address_to_offset(program_headers: list[dict[str, int]], address: int, size: int = 1) -> int:
    for segment in program_headers:
        if segment["type"] != 1:
            continue
        start = segment["vaddr"]
        end = start + segment["filesz"]
        if start <= address and address + size <= end:
            return segment["offset"] + address - start
    raise ValueError(f"address range 0x{address:X}..0x{address + size:X} is not file-backed")


def read_address_u32s(
    data: bytes,
    program_headers: list[dict[str, int]],
    address: int,
    count: int,
) -> list[int]:
    if count == 0:
        require(address == 0, "non-null address for an empty table")
        return []
    offset = address_to_offset(program_headers, address, count * 4)
    return list(struct.unpack_from(f"<{count}I", data, offset))


def read_address_string(
    data: bytes,
    program_headers: list[dict[str, int]],
    address: int,
) -> str | None:
    if address == 0:
        return None
    return read_c_string(data, address_to_offset(program_headers, address))


def parse_exports(
    data: bytes,
    program_headers: list[dict[str, int]],
    start: int,
    end: int,
) -> list[dict[str, Any]]:
    require(start <= end, "reversed export-table range")
    exports = []
    address = start
    while address < end:
        offset = address_to_offset(program_headers, address, 2)
        size = read_u16(data, offset)
        require(size == 0x20, f"unsupported export structure size 0x{size:X}")
        require(address + size <= end, "export extends past table end")
        version, flags, functions = struct.unpack_from("<HHH", data, offset + 2)
        variables = read_u32(data, offset + 8)
        unknown = read_u32(data, offset + 12)
        library_nid = read_u32(data, offset + 16)
        name_address = read_u32(data, offset + 20)
        nid_address = read_u32(data, offset + 24)
        entry_address = read_u32(data, offset + 28)
        count = functions + variables + unknown
        exports.append(
            {
                "address": address,
                "size": size,
                "version": version,
                "flags": flags,
                "function_count": functions,
                "variable_count": variables,
                "unknown_count": unknown,
                "library_nid": library_nid,
                "name": read_address_string(data, program_headers, name_address),
                "nids": read_address_u32s(data, program_headers, nid_address, count),
                "entries": read_address_u32s(data, program_headers, entry_address, count),
            }
        )
        address += size
    require(address == end, "export table is not an exact sequence of entries")
    return exports


def parse_imports(
    data: bytes,
    program_headers: list[dict[str, int]],
    start: int,
    end: int,
) -> list[dict[str, Any]]:
    require(start <= end, "reversed import-table range")
    imports = []
    address = start
    while address < end:
        offset = address_to_offset(program_headers, address, 2)
        size = read_u16(data, offset)
        require(size in (0x24, 0x34), f"unsupported import structure size 0x{size:X}")
        require(address + size <= end, "import extends past table end")
        version, flags, functions, variables, unknown = struct.unpack_from("<HHHHH", data, offset + 2)
        if size == 0x34:
            reserved1 = read_u32(data, offset + 12)
            library_nid = read_u32(data, offset + 16)
            name_address = read_u32(data, offset + 20)
            reserved2 = read_u32(data, offset + 24)
            table_addresses = struct.unpack_from("<IIIIII", data, offset + 28)
        else:
            reserved1 = 0
            library_nid = read_u32(data, offset + 12)
            name_address = read_u32(data, offset + 16)
            reserved2 = 0
            short_addresses = struct.unpack_from("<IIII", data, offset + 20)
            table_addresses = (*short_addresses, 0, 0)
            require(unknown == 0, "short import has unsupported unknown symbols")
        function_nids, function_entries, variable_nids, variable_entries, unknown_nids, unknown_entries = table_addresses
        imports.append(
            {
                "address": address,
                "size": size,
                "version": version,
                "flags": flags,
                "function_count": functions,
                "variable_count": variables,
                "unknown_count": unknown,
                "reserved1": reserved1,
                "reserved2": reserved2,
                "library_nid": library_nid,
                "name": read_address_string(data, program_headers, name_address),
                "function_nids": read_address_u32s(data, program_headers, function_nids, functions),
                "function_entries": read_address_u32s(data, program_headers, function_entries, functions),
                "variable_nids": read_address_u32s(data, program_headers, variable_nids, variables),
                "variable_entries": read_address_u32s(data, program_headers, variable_entries, variables),
                "unknown_nids": read_address_u32s(data, program_headers, unknown_nids, unknown),
                "unknown_entries": read_address_u32s(data, program_headers, unknown_entries, unknown),
            }
        )
        address += size
    require(address == end, "import table is not an exact sequence of entries")
    return imports


def inspect_elf(data: bytes) -> dict[str, Any]:
    header, program_headers = parse_elf(data)
    require(header["type"] == 0xFE04, f"unexpected Vita ELF type 0x{header['type']:X}")
    require(header["machine"] == 40, f"unexpected ELF machine {header['machine']}")
    info_address = header["entry"]
    info_offset = address_to_offset(program_headers, info_address, MODULE_INFO_SIZE + PROCESS_PARAM_SIZE)
    attributes, raw_version = struct.unpack_from("<HH", data, info_offset)
    raw_name = data[info_offset + 4:info_offset + 31]
    name = raw_name.split(b"\0", 1)[0].decode("ascii")
    module_type = data[info_offset + 31]
    values = struct.unpack_from("<15I", data, info_offset + 32)
    (
        gp_value,
        export_top,
        export_end,
        import_top,
        import_end,
        library_nid,
        tls_start,
        tls_filesz,
        tls_memsz,
        module_start,
        module_stop,
        exidx_top,
        exidx_end,
        extab_top,
        extab_end,
    ) = values
    process_values = struct.unpack_from("<13I", data, info_offset + MODULE_INFO_SIZE)
    module = {
        "info_address": info_address,
        "attributes": attributes,
        "version_raw": raw_version,
        "version_major": raw_version >> 8,
        "version_minor": raw_version & 0xFF,
        "name": name,
        "name_raw_hex": raw_name.hex(),
        "type": module_type,
        "gp_value": gp_value,
        "export_top": export_top,
        "export_end": export_end,
        "import_top": import_top,
        "import_end": import_end,
        "library_nid": library_nid,
        "tls_start": tls_start,
        "tls_filesz": tls_filesz,
        "tls_memsz": tls_memsz,
        "module_start": module_start,
        "module_stop": module_stop,
        "exidx_top": exidx_top,
        "exidx_end": exidx_end,
        "extab_top": extab_top,
        "extab_end": extab_end,
        "process_param": {
            "size": process_values[0],
            "magic": process_values[1],
            "version": process_values[2],
            "firmware_version": process_values[3],
            "main_thread_name": process_values[4],
            "main_thread_priority": process_values[5],
            "main_thread_stacksize": process_values[6],
            "main_thread_attribute": process_values[7],
            "process_name": process_values[8],
            "process_preload_disabled": process_values[9],
            "main_thread_cpu_affinity_mask": process_values[10],
            "sce_libc_param": process_values[11],
            "unknown": process_values[12],
        },
    }
    return {
        "elf": header,
        "program_headers": program_headers,
        "module": module,
        "exports": parse_exports(data, program_headers, export_top, export_end),
        "imports": parse_imports(data, program_headers, import_top, import_end),
    }


def inspect_path(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if data.startswith(b"\x7fELF"):
        elf = data
        container = "ELF"
        metadata = None
    else:
        elf, metadata, _segments = unpack_fself(data)
        container = "FSELF"
    result = inspect_elf(elf)
    result["path"] = str(path)
    result["container"] = container
    if metadata is not None:
        result["fself"] = metadata
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, help="write JSON to this path")
    arguments = parser.parse_args()
    result = inspect_path(arguments.input)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
