#!/usr/bin/env python3
"""Rebuild and verify the exact GXP programs used by Adrenaline.

The reference collection contains programs produced by two Sony compiler
generations.  SDK 3.570's psp2cgc build 13276 emits identical executable
programs and symbol tables, but writes newer provenance fields into the GXP
header.  Those known header fields are restored to their reference values;
all other bytes must already match.  psp2shaderperf is then used to prove that
the raw compiler output and the exact reconstructed GXP have identical
disassembly, symbols, statistics, and estimated cost.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


PROGRAMS = {
    "advanced_aa_f": "60d608705edddea9cfbd0d1c13ff5580afbdb90f6eb1f7041cc5dad1f8629a3d",
    "advanced_aa_v": "4246ac0139944ad46a6c3e2b01bc428c9c2f39d9406e8f4caa72f9d31fa9ffcf",
    "lcd3x_f": "9447f4fa152cf9f93f602f4100f53a485e18dca8d0e7eb9e61d35c0244ef35ef",
    "lcd3x_v": "cbbd4f2fc0dc80e261785ae0e46a415a14c7b71677983c8befc032577e331a45",
    "opaque_v": "33438e5f6fc58e843d1192a60c01625653173aae559a26f169d40d1185dc6c4b",
    "sharp_bilinear_f": "392e71d2f33f8cc06b555eefad6d0c2bffa96b3e769ff50728d16cd68a0ee5cf",
    "sharp_bilinear_v": "ddd7d98ed5b6f14ee03c1329f384a4fa081dbde8ee0bf31edbea415058ffdbe1",
    "sharp_bilinear_simple_f": "dacb36f737dcec8ca1056cabc497b0eab74f130cc2ae5af5ec86df798c30e9b7",
    "sharp_bilinear_simple_v": "74de9d3072b219ba625ef804bbeec4ff735055901905e82b3d10858811fd00a5",
    "texture_f": "3eb9950d367d4489cb29b221c9a54dab8e54e362194ab781352c4ced99669337",
}

COLLECTION_PROGRAMS = {
    "advanced_aa_f",
    "advanced_aa_v",
    "lcd3x_f",
    "lcd3x_v",
    "opaque_v",
    "sharp_bilinear_f",
    "sharp_bilinear_v",
    "texture_f",
}

# Zero-based offsets.  These are compiler/provenance header fields only.  Any
# executable, parameter, or symbol-table difference remains a hard failure.
COLLECTION_HEADER = {
    0x06: 0x10,
    0x0C: 0x00,
    0x0D: 0x00,
    0x0E: 0x00,
    0x0F: 0x00,
    0x10: 0x00,
    0x11: 0x00,
    0x12: 0x00,
    0x13: 0x00,
    0x6D: 0x3C,
}

SIMPLE_HEADER = {
    "sharp_bilinear_simple_f": {
        0x10: 0xB9,
        0x11: 0x87,
        0x12: 0x7A,
        0x13: 0xC8,
    },
    "sharp_bilinear_simple_v": {
        0x10: 0x24,
        0x11: 0xC4,
        0x12: 0xC2,
        0x13: 0x83,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sdk-bin",
        type=Path,
        default=os.environ.get("PSP2_SDK_BIN"),
        help="directory containing psp2cgc and psp2shaderperf",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("build/gxp"),
        help="output directory for reconstructed GXPs",
    )
    parser.add_argument(
        "--reference-dir",
        type=Path,
        help="optional directory of known-working GXPs for byte comparison",
    )
    return parser.parse_args()


def find_tool(sdk_bin: Path, name: str) -> Path:
    for candidate in (sdk_bin / f"{name}.exe", sdk_bin / name):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{name} was not found under {sdk_bin}")


def run(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized_report(shaderperf: Path, path: Path) -> bytes:
    return run(
        [str(shaderperf), "-disasm", "-symbols", "-stats", str(path)]
    ).stdout.replace(b"\r\n", b"\n")


def main() -> int:
    args = parse_args()
    if args.sdk_bin is None:
        raise SystemExit("--sdk-bin or PSP2_SDK_BIN is required")

    root = Path(__file__).resolve().parent
    source_dir = root / "cg"
    sdk_bin = args.sdk_bin.resolve()
    cgc = find_tool(sdk_bin, "psp2cgc")
    shaderperf = find_tool(sdk_bin, "psp2shaderperf")

    version = run([str(cgc), "-v"]).stdout.decode(errors="replace")
    if "build 13276" not in version:
        raise SystemExit(
            "exact reconstruction requires psp2cgc SDK 3.5.0 build 13276; "
            f"got: {version.strip()}"
        )

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    reference_dir = args.reference_dir.resolve() if args.reference_dir else None

    with tempfile.TemporaryDirectory(prefix="gxp-", dir=out_dir.parent) as temp:
        temp_dir = Path(temp)
        for name, expected_hash in PROGRAMS.items():
            source = source_dir / f"{name}.cg"
            raw_path = temp_dir / f"{name}.raw.gxp"
            exact_path = temp_dir / f"{name}.gxp"
            profile = "sce_vp_psp2" if name.endswith("_v") else "sce_fp_psp2"

            run(
                [
                    str(cgc),
                    "-profile",
                    profile,
                    "-O3",
                    "-o",
                    str(raw_path),
                    str(source),
                ]
            )

            raw = raw_path.read_bytes()
            exact = bytearray(raw)
            header = COLLECTION_HEADER if name in COLLECTION_PROGRAMS else SIMPLE_HEADER[name]
            for offset, value in header.items():
                exact[offset] = value
            exact_path.write_bytes(exact)

            changed = {index for index, (before, after) in enumerate(zip(raw, exact)) if before != after}
            if changed != set(header):
                raise SystemExit(
                    f"{name}: unexpected compiler header state; changed offsets "
                    f"{sorted(changed)}, expected {sorted(header)}"
                )
            if digest(exact) != expected_hash:
                raise SystemExit(
                    f"{name}: exact hash mismatch: {digest(exact)} != {expected_hash}"
                )
            if normalized_report(shaderperf, raw_path) != normalized_report(shaderperf, exact_path):
                raise SystemExit(f"{name}: header normalization changed shader analysis")

            if reference_dir is not None:
                reference = (reference_dir / f"{name}.gxp").read_bytes()
                if bytes(exact) != reference:
                    raise SystemExit(f"{name}: reconstructed GXP differs from reference")

            shutil.copyfile(exact_path, out_dir / f"{name}.gxp")
            print(f"{name}.gxp: {expected_hash}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
