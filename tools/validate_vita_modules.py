#!/usr/bin/env python3
"""Reject loader-visible divergence in the six Vita stack modules."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from inspect_vita_module import inspect_path
from unpack_fself import unpack_fself


ROOT = Path(__file__).resolve().parents[1]

PROFILES = {
    "adrbubblebooter": {
        "name": "/adrbubblebooter", "version": 0x0101, "nid": 0xBF7F98B3,
        "start": 0x8001, "stop": 0, "rw_vaddr": 0x20000,
        "auth_id": 0x2F00000000000001,
        "bss_size": 0x490,
        "segments": (
            (1, 0x00000, 0x00000, 0x00000, 0x09614, 0x09614, 5, 0x1000),
            (1, 0x10268, 0x20000, 0x20000, 0x00058, 0x004E8, 6, 0x1000),
            (0x60000000, 0x11DA0, 0, 0, 0x00738, 0, 0, 0x10),
        ),
        "process_version": 6, "process_firmware": 0x03570011,
        "tables": "8dd36554d6ab16e26fb882e8be48462f4d2b0477c4750f54c393286e0ef008b9",
    },
    "bootconv": {
        "name": "bootconv", "version": 0x0101, "nid": 0x147042CF,
        "start": 0x8019, "stop": 0, "rw_vaddr": 0x20000,
        "auth_id": 0x2F00000000000001,
        "bss_size": 0x3FC,
        "segments": (
            (1, 0x00000, 0x00000, 0x00000, 0x0963C, 0x0963C, 5, 0x1000),
            (1, 0x10274, 0x20000, 0x20000, 0x00058, 0x00454, 6, 0x1000),
            (0x60000000, 0x11F10, 0, 0, 0x006FC, 0, 0, 0x10),
        ),
        "process_version": 0, "process_firmware": 0,
        "tables": "6f988e71520e5d43dbf766ddffc09b111510b3877323c77873727f66f807ca21",
    },
    "ebooter": {
        "name": "ebooter", "version": 0x0101, "nid": 0x83317876,
        "start": 0x8221, "stop": 0, "rw_vaddr": 0x30000,
        "auth_id": 0x2800000000000001,
        "sha256": "6a0e6c192ea0071ddc3f661193a5b40f78ca2dc17283505ffbf500123cd97e93",
        "segments": (
            (1, 0x00000, 0x00000, 0x00000, 0x12D18, 0x12D18, 5, 0x1000),
            (1, 0x20450, 0x30000, 0x30000, 0x010DC, 0x45E08, 6, 0x1000),
            (0x60000000, 0x2B790, 0, 0, 0x4038, 0, 0, 0x10),
        ),
        "process_version": 0, "process_firmware": 0,
        "tables": "615a40e89a1bcdc5679f7d6a68d8a85e6072187739102c6017f5ac5f837d9bcf",
    },
    "kernel": {
        "name": "AdrenalineKernel", "version": 0x0100, "nid": 0x02C85BD5,
        "start": 0x83C5, "stop": 0x86C5, "rw_vaddr": 0x20000,
        "auth_id": 0x2F00000000000001,
        "process_version": 6, "process_firmware": 0x03570011,
        "tables": "5a88e4fbe683a3755fd3699e0c732852b7d6a33d212e4d12cb8ac29a3109fb81",
    },
    "user": {
        "name": "AdrenalineUser", "version": 0x0100, "nid": 0x532809F2,
        "start": 0x8AC5, "stop": 0x9E4D, "rw_vaddr": 0x50000,
        "auth_id": 0x2F00000000000001,
        "process_version": 6, "process_firmware": 0x03570011,
        "tables": "81c446b6c7170b40a1cf28cd4a4891f3507fcdfe3b3899fa7f039cf6053a49d5",
    },
    "vsh": {
        "name": "AdrenalineVsh", "version": 0x0100, "nid": 0xA260D147,
        "start": 0x8209, "stop": 0x82D1, "rw_vaddr": 0x20000,
        "auth_id": 0x2F00000000000001,
        "process_version": 0, "process_firmware": 0,
        "tables": "83e8e5b0d23aa0fc02ff6e58c8baa9e43c4205b109798179629f05a8a6c6a84b",
    },
}

EXPORT_FIELDS = (
    "size", "version", "flags", "function_count", "variable_count",
    "unknown_count", "library_nid", "name", "nids",
)
IMPORT_FIELDS = (
    "size", "version", "flags", "function_count", "variable_count",
    "unknown_count", "reserved1", "reserved2", "library_nid", "name",
    "function_nids", "variable_nids", "unknown_nids",
)
SHADER_ORDER = (
    "advanced_aa_f.gxp",
    "advanced_aa_v.gxp",
    "lcd3x_f.gxp",
    "lcd3x_v.gxp",
    "opaque_v.gxp",
    "sharp_bilinear_f.gxp",
    "sharp_bilinear_v.gxp",
    "texture_f.gxp",
    "sharp_bilinear_simple_v.gxp",
    "sharp_bilinear_simple_f.gxp",
)

# Bytes that differ here are only absolute pointers to equivalent, shifted
# constant pools.  After masking those relocation-backed words, these hashes
# cover the original closed modules' recovered machine code and initialized
# runtime data.  The bootconv main routine is excluded because GCC emitted an
# equivalent basic-block order for the reconstructed structured C; every
# helper, parser, runtime function, and import stub remains covered.
CLOSED_CODE_FINGERPRINTS = {
    "adrbubblebooter": {
        "ranges": ((0x8000, 0x9120),),
        "zero_words": (
            0x82D4, 0x82D8, 0x82DC, 0x82E0, 0x82E4, 0x82F8, 0x82FC,
            0x8538,
        ),
        "sha256": "6efa0c938bffe2d5595b3be273a5401ac6cd5583328a0a6ae468b9a3170d1074",
        "data_sha256": "35194dd3c53cff4def401548abd424b7337a7d77fef897e8478ba0cf035b3cc6",
    },
    "bootconv": {
        "ranges": ((0x8000, 0x8018), (0x8104, 0x9180)),
        "zero_words": (0x8010, 0x8014, 0x82B0, 0x82B8, 0x850C),
        "sha256": "ec03b27c29d60965303a2f261fad748f4ad428e9b9f199b9aaf97a4206e5b9ed",
        "data_sha256": "d02d3d0285618403c6d9ea4ba6c59753f2177ed19a0af65fb2e96a564027f23a",
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def table_digest(module: dict[str, Any]) -> str:
    structure = {
        "exports": [
            {field: entry[field] for field in EXPORT_FIELDS}
            for entry in module["exports"]
        ],
        "imports": [
            {field: entry[field] for field in IMPORT_FIELDS}
            for entry in module["imports"]
        ],
    }
    canonical = json.dumps(structure, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def validate_segments(
    label: str,
    inspected: dict[str, Any],
    profile: dict[str, Any],
) -> None:
    elf = inspected["elf"]
    expected_header = {
        "type": 0xFE04,
        "machine": 40,
        "version": 1,
        "program_header_offset": 52,
        "section_header_offset": 0,
        "flags": 0x05000400,
        "elf_header_size": 52,
        "program_header_size": 32,
        "program_header_count": 3,
        "section_header_size": 0,
        "section_header_count": 0,
        "section_name_index": 0,
    }
    for field, expected in expected_header.items():
        require(elf[field] == expected, f"{label}: ELF {field} changed")

    rx, rw, relocations = inspected["program_headers"]
    require(
        (rx["type"], rx["offset"], rx["vaddr"], rx["paddr"], rx["flags"], rx["align"])
        == (1, 0, 0, 0, 5, 0x1000),
        f"{label}: RX segment layout changed",
    )
    require(rx["filesz"] == rx["memsz"], f"{label}: RX filesz/memsz differs")
    require(
        (rw["type"], rw["vaddr"], rw["paddr"], rw["flags"], rw["align"])
        == (1, profile["rw_vaddr"], profile["rw_vaddr"], 6, 0x1000),
        f"{label}: RW segment layout changed",
    )
    require(rw["filesz"] <= rw["memsz"], f"{label}: invalid RW filesz/memsz")
    if "bss_size" in profile:
        require(
            rw["memsz"] - rw["filesz"] == profile["bss_size"],
            f"{label}: recovered BSS size changed",
        )
    require(
        (
            relocations["type"], relocations["vaddr"], relocations["paddr"],
            relocations["memsz"], relocations["flags"], relocations["align"],
        ) == (0x60000000, 0, 0, 0, 0, 0x10),
        f"{label}: relocation segment layout changed",
    )


def validate_fself(
    label: str,
    path: Path,
    inspected: dict[str, Any],
    profile: dict[str, Any],
) -> None:
    metadata = inspected["fself"]
    header = metadata["sce_header"]
    expected_header = {
        "version": 3,
        "sdk_type": 0xC0,
        "header_type": 1,
        "metadata_offset": 0x600,
        "header_length": 0x1000,
        "unknown": 0,
        "self_offset": 4,
        "appinfo_offset": 0x80,
        "elf_offset": 0xA0,
        "program_header_offset": 0xE0,
        "section_header_offset": 0,
        "section_info_offset": 0x140,
        "sce_version_offset": 0x1A0,
        "control_info_offset": 0x1B0,
        "control_info_size": 0x270,
        "padding": 0,
    }
    for field, expected in expected_header.items():
        require(header[field] == expected, f"{label}: SELF {field} changed")
    require(
        header["self_file_size"] == path.stat().st_size,
        f"{label}: SELF file-size field changed",
    )

    appinfo = metadata["appinfo"]
    require(appinfo["auth_id"] == profile["auth_id"], f"{label}: auth ID changed")
    require(appinfo["vendor_id"] == 0, f"{label}: vendor ID changed")
    require(appinfo["self_type"] == 8, f"{label}: SELF type changed")
    require(appinfo["version"] == 0x1000000000000, f"{label}: app version changed")
    require(appinfo["padding"] == 0, f"{label}: app-info padding changed")

    require(
        metadata["sce_version"] == {
            "unknown_1": 1,
            "unknown_2": 0,
            "unknown_3": 0x10,
            "unknown_4": 0,
        },
        f"{label}: SCE version structure changed",
    )
    controls = metadata["control_info"]
    require(len(controls) == 3, f"{label}: control-info count changed")
    expected_controls = (
        (5, 0x110, 1, 0, b"\0" * 0x100),
        (6, 0x110, 1, 0, b"\x01\0\0\0" + b"\0" * 0xFC),
        (7, 0x50, 0, 0, b"\0" * 0x40),
    )
    for record, expected in zip(controls, expected_controls):
        actual = (
            record["type"], record["size"], record["unknown"], record["padding"],
            bytes.fromhex(record["payload_hex"]),
        )
        require(actual == expected, f"{label}: control-info record changed")

    records = metadata["segments"]
    require(len(records) == 3, f"{label}: SELF segment-record count changed")
    next_offset = 0x420
    for index, record in enumerate(records):
        require(record["index"] == index, f"{label}: SELF segment order changed")
        require(
            record["stored_offset"] == next_offset,
            f"{label}: compact v276 segment storage changed",
        )
        require(record["compression"] == 2, f"{label}: segment compression changed")
        require(record["encryption"] == 2, f"{label}: segment encryption changed")
        next_offset += record["stored_size"]
    require(
        next_offset == path.stat().st_size,
        f"{label}: SELF contains unaccounted trailing bytes",
    )

    if "sha256" in profile:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        require(actual == profile["sha256"], f"{label}: exact binary hash changed ({actual})")
    if "segments" in profile:
        actual_segments = tuple(
            (
                segment["type"], segment["offset"], segment["vaddr"],
                segment["paddr"], segment["filesz"], segment["memsz"],
                segment["flags"], segment["align"],
            )
            for segment in inspected["program_headers"]
        )
        require(
            actual_segments == profile["segments"],
            f"{label}: exact program-header profile changed",
        )


def validate_identity(label: str, inspected: dict[str, Any], profile: dict[str, Any]) -> None:
    module = inspected["module"]
    require(module["attributes"] == 0, f"{label}: module attributes changed")
    require(module["version_raw"] == profile["version"], f"{label}: version changed")
    require(module["name"] == profile["name"], f"{label}: module name changed")
    expected_name = profile["name"].encode("ascii").ljust(27, b"\0").hex()
    require(module["name_raw_hex"] == expected_name, f"{label}: name padding changed")
    require(module["type"] == 6, f"{label}: module is no longer a PRX")
    require(module["library_nid"] == profile["nid"], f"{label}: module NID changed")
    require(module["module_start"] == profile["start"], f"{label}: start entry changed")
    require(module["module_stop"] == profile["stop"], f"{label}: stop entry changed")
    require(module["info_address"] == inspected["elf"]["entry"], f"{label}: bad module-info entry")
    for field in (
        "gp_value", "tls_start", "tls_filesz", "tls_memsz", "exidx_top",
        "exidx_end", "extab_top", "extab_end",
    ):
        require(module[field] == 0, f"{label}: {field} changed")

    process = module["process_param"]
    require(process["size"] == 0x34, f"{label}: process-param size changed")
    require(process["magic"] == 0x32505350, f"{label}: process-param magic changed")
    require(
        process["version"] == profile["process_version"],
        f"{label}: process-param version changed",
    )
    require(
        process["firmware_version"] == profile["process_firmware"],
        f"{label}: process-param firmware changed",
    )
    for field, value in process.items():
        if field not in ("size", "magic", "version", "firmware_version"):
            require(value == 0, f"{label}: process-param {field} changed")


def validate_shaders(path: Path) -> None:
    elf, _metadata, _segments = unpack_fself(path.read_bytes())
    offsets = []
    for filename in SHADER_ORDER:
        shader = (ROOT / "src/vita/shaders/gxp" / filename).read_bytes()
        require(elf.count(shader) == 1, f"user: {filename} is not embedded exactly once")
        offsets.append(elf.find(shader))
    require(offsets == sorted(offsets), "user: embedded GXP archive order changed")


def validate_closed_fingerprint(label: str, path: Path) -> None:
    profile = CLOSED_CODE_FINGERPRINTS[label]
    _elf, _metadata, segments = unpack_fself(path.read_bytes())
    require(len(segments) == 3, f"{label}: unexpected segment count")

    rx = bytearray(segments[0])
    for offset in profile["zero_words"]:
        require(offset + 4 <= len(rx), f"{label}: code mask is out of range")
        rx[offset:offset + 4] = b"\0" * 4
    payload = b"".join(rx[start:end] for start, end in profile["ranges"])
    actual = hashlib.sha256(payload).hexdigest()
    require(
        actual == profile["sha256"],
        f"{label}: recovered machine-code fingerprint changed ({actual})",
    )

    data = bytearray(segments[1])
    require(len(data) == 0x58, f"{label}: initialized-data size changed")
    for offset in range(0, 0x1C, 4):
        data[offset:offset + 4] = b"\0" * 4
    actual = hashlib.sha256(data).hexdigest()
    require(
        actual == profile["data_sha256"],
        f"{label}: initialized-runtime fingerprint changed ({actual})",
    )


def validate_module(label: str, path: Path) -> None:
    require(path.is_file(), f"{label}: missing module: {path}")
    profile = PROFILES[label]
    inspected = inspect_path(path)
    require(inspected["container"] == "FSELF", f"{label}: output is not an FSELF")
    validate_fself(label, path, inspected, profile)
    validate_segments(label, inspected, profile)
    validate_identity(label, inspected, profile)
    actual_digest = table_digest(inspected)
    require(
        actual_digest == profile["tables"],
        f"{label}: import/export structure changed ({actual_digest})",
    )
    if label == "user":
        validate_shaders(path)
    if label in CLOSED_CODE_FINGERPRINTS:
        validate_closed_fingerprint(label, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for label in PROFILES:
        parser.add_argument(f"--{label}", required=True, type=Path)
    arguments = parser.parse_args()
    for label in PROFILES:
        validate_module(label, getattr(arguments, label))
        print(f"{label}: loader structure verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
