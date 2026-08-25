#!/usr/bin/env python3
"""Generate the exact small data templates used by ABM and the booter stack."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def boot_template() -> bytes:
    data = bytearray(0x140)
    struct.pack_into("<I", data, 0x00, 0x00424241)  # ABB\0
    struct.pack_into("<I", data, 0x04, 1)           # MARCH33
    struct.pack_into("<I", data, 0x0C, 1)           # customized
    struct.pack_into("<I", data, 0x2C, 0x31444242)  # BBD1 marker
    return bytes(data)


def adrenaline_config() -> bytes:
    # Historical ABM stores the 64-byte pre-suspend_threads layout. The user
    # module zeroes its 68-byte structure before reading this file.
    fields: list[int | float] = [
        0x31483943,
        0x334F4E33,
        0, 0, 0, 0, 0, 0, 0, 0,
        2.0, 2.0, 1.0, 1.0,
        0, 0,
    ]
    return struct.pack("<10I4f2I", *fields)


def menu_color() -> bytes:
    encoded = (ROOT / "integration/adrenaline-v7/menucolor.hex").read_text(
        encoding="ascii"
    )
    data = bytes.fromhex(encoded)
    if len(data) != 32:
        raise ValueError("menucolor.hex must decode to 32 bytes")
    return data


def generate(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "boot.bin").write_bytes(boot_template())
    (output / "adrenaline.bin").write_bytes(adrenaline_config())
    (output / "menucolor.bin").write_bytes(menu_color())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    generate(args.output.resolve())


if __name__ == "__main__":
    main()

