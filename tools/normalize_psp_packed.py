#!/usr/bin/env python3
"""Make psp-packer's semantically unused random header fields reproducible."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


PSP_MAGIC = b"~PSP"

# psp-packer 0.1.3 calls its RNG exclusively for these three PspHeader
# members after compression parameters have already been selected. They are
# key_data0, key_data1, and key_data3 in the open packer source. The OE packed
# modules do not derive their compressed payload from these arbitrary bytes.
KEY_DATA_RANGES = (
    (0x080, 0x0B0),
    (0x0C0, 0x0D0),
    (0x134, 0x150),
)

DOMAIN = b"AdrBubbleBooter OSS deterministic psp-packer key data\0"


def normalized(data: bytes) -> bytes:
    if len(data) < KEY_DATA_RANGES[-1][1] or data[:4] != PSP_MAGIC:
        raise ValueError("input is not a complete packed ~PSP executable")

    output = bytearray(data)
    for start, end in KEY_DATA_RANGES:
        output[start:end] = b"\0" * (end - start)

    seed = hashlib.sha256(DOMAIN + output).digest()
    stream = b"".join(
        hashlib.sha256(seed + counter.to_bytes(4, "little")).digest()
        for counter in range(3)
    )
    cursor = 0
    for start, end in KEY_DATA_RANGES:
        size = end - start
        output[start:end] = stream[cursor:cursor + size]
        cursor += size
    return bytes(output)


def normalize(path: Path) -> None:
    data = path.read_bytes()
    result = normalized(data)
    if result != data:
        path.write_bytes(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args()
    for path in args.files:
        normalize(path)


if __name__ == "__main__":
    main()
