#!/usr/bin/env python3
"""Verify the shader archive's member order and raw2c object layout."""

from __future__ import annotations

import argparse
from pathlib import Path
import struct
import subprocess
import tempfile


PROGRAMS = (
    "advanced_aa_f",
    "advanced_aa_v",
    "lcd3x_f",
    "lcd3x_v",
    "opaque_v",
    "sharp_bilinear_f",
    "sharp_bilinear_v",
    "texture_f",
    "sharp_bilinear_simple_v",
    "sharp_bilinear_simple_f",
)


def run(command: list[str], *, text: bool = False) -> bytes | str:
    return subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=text,
    ).stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--gxp-dir", type=Path, default=Path("gxp"))
    parser.add_argument("--prefix", default="arm-vita-eabi")
    args = parser.parse_args()

    expected_members = [f"{name}.o" for name in PROGRAMS]
    members = str(run([f"{args.prefix}-ar", "t", str(args.archive)], text=True)).splitlines()
    if members != expected_members:
        raise SystemExit(f"archive member order differs: {members!r} != {expected_members!r}")

    with tempfile.TemporaryDirectory(prefix="vitashaders-") as temporary:
        temporary_dir = Path(temporary)
        for name in PROGRAMS:
            member = f"{name}.o"
            object_path = temporary_dir / member
            object_path.write_bytes(bytes(run([f"{args.prefix}-ar", "p", str(args.archive), member])))

            rodata_path = temporary_dir / f"{name}.rodata"
            run(
                [
                    f"{args.prefix}-objcopy",
                    "-O",
                    "binary",
                    "--only-section=.rodata",
                    str(object_path),
                    str(rodata_path),
                ]
            )

            gxp = (args.gxp_dir / f"{name}.gxp").read_bytes()
            expected_rodata = struct.pack("<I", len(gxp)) + bytes(4) + gxp
            if rodata_path.read_bytes() != expected_rodata:
                raise SystemExit(f"{member}: .rodata is not exact raw2c layout")

            symbols = str(
                run(
                    [f"{args.prefix}-nm", "-n", "--print-size", str(object_path)],
                    text=True,
                )
            ).splitlines()
            expected_symbols = [
                f"00000000 00000004 R {name}_size",
                f"00000008 {len(gxp):08x} R {name}",
            ]
            if symbols != expected_symbols:
                raise SystemExit(f"{member}: symbol layout differs: {symbols!r}")

            sections = str(
                run([f"{args.prefix}-readelf", "-SW", str(object_path)], text=True)
            )
            rodata_line = next(
                (line for line in sections.splitlines() if "] .rodata " in line),
                "",
            )
            if not rodata_line.endswith(" 8"):
                raise SystemExit(f"{member}: .rodata is not aligned to 8: {rodata_line}")

    print("shader archive member order, symbols, alignment, and bytes match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
