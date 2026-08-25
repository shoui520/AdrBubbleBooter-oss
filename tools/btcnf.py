#!/usr/bin/env python3
"""Build or extract the plaintext PSP boot configuration format.

The layout is the decrypted 6.60/6.61 btcnf structure used by Adrenaline.
Unlike some historical tools, this implementation preserves entries with an
empty runlevel set; AdrBubbleBooter's pspbtbnf contains five such entries.
"""

from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from pathlib import Path


MAGIC = 0x0F803001
HEADER = struct.Struct("<16I")
MODE = struct.Struct("<HHII20x")
MODULE = struct.Struct("<IIII16x")

MODE_DEFINITIONS = (
    ("V", 0x01, 2),
    ("G", 0x02, 1),
    ("U", 0x04, 3),
    ("P", 0x08, 4),
    ("L", 0x10, 5),
    ("A", 0x20, 6),
    ("E", 0x40, 7),
    ("M", 0x80, 8),
)


@dataclass
class ModuleRecord:
    source_prefix: str
    path: str
    runlevels: int

    @property
    def flags(self) -> int:
        load_mode = {
            "": 1,
            "%": 2,
            "%%": 4,
            "$": 0x8001,
            "$%": 0x8002,
            "$%%": 0x8004,
        }[self.source_prefix]
        return (load_mode << 16) | self.runlevels


def split_module_token(token: str) -> tuple[str, str]:
    for prefix in ("$%%", "$%", "$", "%%", "%"):
        if token.startswith(prefix):
            return prefix, token[len(prefix):]
    return "", token


def parse_text(path: Path) -> tuple[int, list[ModuleRecord]]:
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)

    if not lines:
        raise ValueError("empty btcnf source")

    devkit = int(lines[0], 16)
    records = []
    for number, line in enumerate(lines[1:], 2):
        fields = line.split(None, 1)
        token = fields[0]
        mode_text = fields[1].upper() if len(fields) == 2 else ""
        prefix, module_path = split_module_token(token)
        if not module_path.startswith("/"):
            raise ValueError(f"line {number}: module path must begin with '/'")

        runlevels = 0
        for letter, flag, _index in MODE_DEFINITIONS:
            if letter in mode_text:
                runlevels |= flag
        unknown = set(mode_text) - {entry[0] for entry in MODE_DEFINITIONS}
        if unknown:
            raise ValueError(
                f"line {number}: unknown runlevel(s): {''.join(sorted(unknown))}"
            )
        records.append(ModuleRecord(prefix, module_path, runlevels))

    return devkit, records


def build(source: Path, output: Path) -> None:
    devkit, records = parse_text(source)
    used_modes = [
        (flag, index)
        for _letter, flag, index in MODE_DEFINITIONS
        if any(record.runlevels & flag for record in records)
    ]

    mode_start = HEADER.size
    module_start = mode_start + len(used_modes) * MODE.size
    name_start = module_start + len(records) * MODULE.size

    names = bytearray()
    offsets = []
    for record in records:
        # The historical compiler emitted one name for every record, including
        # duplicate paths. Preserve that quirk for byte-identical output.
        offsets.append(len(names))
        names.extend(record.path.encode("ascii"))
        names.append(0)
    name_end = name_start + len(names)

    data = bytearray()
    data.extend(HEADER.pack(
        MAGIC,
        devkit,
        0x6B8B4567,
        0x327B23C6,
        mode_start,
        len(used_modes),
        0x643C9869,
        0x66334873,
        module_start,
        len(records),
        0x74B0DC51,
        0x19495CFF,
        name_start,
        name_end,
        0x2AE8944A,
        0x625558EC,
    ))
    for flag, index in used_modes:
        data.extend(MODE.pack(len(records), 0, flag, index))
    # The Sony/historical compiler keeps the path strings in source order but
    # groups module records by load directive. This is observable in the first
    # dummy-anchor entry: its string precedes libatrac3plus while its record is
    # emitted after every $% record.
    directive_order = {
        "": 0,
        "$": 1,
        "%": 2,
        "$%": 3,
        "%%": 4,
        "$%%": 5,
    }
    module_entries = sorted(
        zip(records, offsets),
        key=lambda entry: directive_order[entry[0].source_prefix],
    )
    for record, offset in module_entries:
        data.extend(MODULE.pack(offset, 0, record.flags, 0))
    data.extend(names)
    output.write_bytes(data)


def prefix_from_flags(flags: int) -> str:
    load_mode = flags >> 16
    return {
        1: "",
        2: "%",
        4: "%%",
        0x8001: "$",
        0x8002: "$%",
        0x8004: "$%%",
    }.get(load_mode, f"!0x{load_mode:X}!")


def extract(source: Path, output: Path) -> None:
    data = source.read_bytes()
    if len(data) < HEADER.size:
        raise ValueError("truncated btcnf header")
    header = HEADER.unpack_from(data)
    if header[0] != MAGIC:
        raise ValueError("not a decrypted PSP btcnf file")

    module_start, module_count = header[8], header[9]
    name_start, name_end = header[12], header[13]
    if not (
        module_start <= len(data)
        and name_start <= name_end <= len(data)
        and module_start + module_count * MODULE.size <= len(data)
    ):
        raise ValueError("invalid btcnf offsets")

    lines = [f"0x{header[1]:08X}"]
    for index in range(module_count):
        offset, _unknown0, flags, _unknown1 = MODULE.unpack_from(
            data, module_start + index * MODULE.size
        )
        start = name_start + offset
        end = data.find(b"\0", start, name_end)
        if start < name_start or end < 0:
            raise ValueError(f"invalid module name at record {index}")
        module_path = data[start:end].decode("ascii")
        mode_text = "".join(
            letter for letter, flag, _index in MODE_DEFINITIONS if flags & flag
        )
        suffix = f" {mode_text}" if mode_text else ""
        lines.append(f"{prefix_from_flags(flags)}{module_path}{suffix}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "extract"))
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        build(args.input, args.output)
    else:
        extract(args.input, args.output)


if __name__ == "__main__":
    main()
