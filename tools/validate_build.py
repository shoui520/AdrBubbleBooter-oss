#!/usr/bin/env python3
"""Run static equivalence checks against a complete stack build."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
import zlib
from pathlib import Path

from normalize_psp_packed import normalized as normalized_packed_psp
from normalize_psp_booter import REFERENCE_SECTIONS, validate_profile
from unpack_fself import unpack_fself


ROOT = Path(__file__).resolve().parents[1]

ABM_VPK = "AdrenalineBubbleManager_6.21_AdrBubbleBooter-oss.vpk"

STACK_MODULES = (
    "adrbubblebooter.suprx",
    "adrenaline_kernel.skprx",
    "adrenaline_user.suprx",
    "adrenaline_vsh.suprx",
    "bootconv.suprx",
)

ADRENALINE_MODULES = (
    "adrenaline_kernel.skprx",
    "adrenaline_user.suprx",
    "adrenaline_vsh.suprx",
)

SHADER_HASHES = {
    "advanced_aa_f.gxp": "60d608705edddea9cfbd0d1c13ff5580afbdb90f6eb1f7041cc5dad1f8629a3d",
    "advanced_aa_v.gxp": "4246ac0139944ad46a6c3e2b01bc428c9c2f39d9406e8f4caa72f9d31fa9ffcf",
    "lcd3x_f.gxp": "9447f4fa152cf9f93f602f4100f53a485e18dca8d0e7eb9e61d35c0244ef35ef",
    "lcd3x_v.gxp": "cbbd4f2fc0dc80e261785ae0e46a415a14c7b71677983c8befc032577e331a45",
    "opaque_v.gxp": "33438e5f6fc58e843d1192a60c01625653173aae559a26f169d40d1185dc6c4b",
    "sharp_bilinear_f.gxp": "392e71d2f33f8cc06b555eefad6d0c2bffa96b3e769ff50728d16cd68a0ee5cf",
    "sharp_bilinear_simple_f.gxp": "dacb36f737dcec8ca1056cabc497b0eab74f130cc2ae5af5ec86df798c30e9b7",
    "sharp_bilinear_simple_v.gxp": "74de9d3072b219ba625ef804bbeec4ff735055901905e82b3d10858811fd00a5",
    "sharp_bilinear_v.gxp": "ddd7d98ed5b6f14ee03c1329f384a4fa081dbde8ee0bf31edbea415058ffdbe1",
    "texture_f.gxp": "3eb9950d367d4489cb29b221c9a54dab8e54e362194ab781352c4ced99669337",
}

TEMPLATE_HASHES = {
    "bubbles/adrenaline.bin": "f5c70268bfae1208274b6b541c4b40a5248bf93fb5eb46b5288b522c19465eb3",
    "bubbles/menucolor.bin": "60216c700f462a978abb59515a9bb33b58d7e7e8a1a2c9cb96725717e6773b7b",
    "bubbles/pspemuxxx/data/boot.bin": "f6901fabc6bddf9acae609c5170740f3b9ad4036b90811c75901a2df13a57d3c",
}

PER_BUBBLE_EBOOT_SHA256 = (
    "6a0e6c192ea0071ddc3f661193a5b40f78ca2dc17283505ffbf500123cd97e93"
)

PSP_BOOTER_NIDS = (
    0xF91FE6AA, 0x2D10FB28, 0x85B520C6, 0x31C6160D, 0xB64186D0,
    0x5CB025F0, 0xD8779AC6, 0x810C4BC3, 0x109F50BC, 0x6A638D83,
    0x27EB27B8, 0xACE946E8, 0x79D1C3FA, 0x446D8DE6, 0xF475845D,
    0x4C0E0274, 0xB49A7697, 0x52DF196C, 0x10F3BB61, 0x81D0D1F7,
    0x7661E728,
)

PSP_BOOTER_SECTION_HASHES = {
    3: "738bca0875f394b8d8892544b3054795aac957e139607840d30749d7b934d7f3",
    4: "df3f619804a92fdb4057192dc43dd748ea778adc52bc498ce80524c014b81119",
    5: "df3f619804a92fdb4057192dc43dd748ea778adc52bc498ce80524c014b81119",
    6: "df3f619804a92fdb4057192dc43dd748ea778adc52bc498ce80524c014b81119",
    7: "ca69b9927184eec9af432998a8a5c20eec6bf58ea82a38d27be86b9758b723d1",
    8: "8f67880977cc4aa0b651a8b06f68641d8374017be4d353d4bca9e64d68deed87",
    9: "df3f619804a92fdb4057192dc43dd748ea778adc52bc498ce80524c014b81119",
    10: "170f8b1b84132f4142b0a1764185c4d48dd84c05687b74dde9c859204481e0cb",
    11: "fa4feb7ad776acdc70ba3320bdc06557937cca89369dd6f70bcbb7ade225839f",
    12: "12ab96dc688bc7fb48299141af728b2f6d887fa0d489c846d03fbbf760f22200",
    13: "7ece85c7bc23a366435521487d005b2f585045d7ea05bb3776f9df456b9a63e6",
    14: "eb4d9eeb82f3b78a49c35dbcec2c1e63fbfb7ffaceb63059edcf7e6fd37ac98b",
    18: "c80d197ed6f0a2d7214ead63ed8e767b4649e4d9a77f8a56bad0ace44f9b242c",
}

COMMON_VITA_IMPORTS = {
    (0x203D1A28, 0xA5899384),  # taiGetModuleInfo
    (0xA6605D6F, 0xF4D6AE3A),  # sceAppMgrGetNameById
    (0xF2FF276E, 0xC70B8886),  # sceIoClose
    (0xF2FF276E, 0xFDB32293),  # sceIoRead
    (0xF2FF276E, 0x34EFD876),  # sceIoWrite
    (0x859A24B1, 0x9DCB4B7A),  # sceKernelGetProcessId
    (0xCAE9ACE6, 0xBCA5B623),  # sceIoGetstat
    (0xCAE9ACE6, 0x99BA173E),  # sceIoLseek
    (0xCAE9ACE6, 0x6C60AC61),  # sceIoOpen
    (0xCAE9ACE6, 0x7595D9AA),  # sceKernelExitProcess
}

CLOSED_VITA_BSS = {
    "adrbubblebooter/adrbubblebooter": {
        "device_name": (0x20058, 0x100),
        "_PDCLIB_errno": (0x20158, 0x4),
        "adrenaline_config_path": (0x2015C, 0x40),
        "legacy_boot_info": (0x2019C, 0x120),
        "app_title_id": (0x202BC, 0xC),
        "bubble_config_path": (0x202C8, 0x40),
        "config": (0x20308, 0x60),
        "boot_info": (0x20368, 0x140),
        "bubble_boot_path": (0x204A8, 0x40),
    },
    "bootconv/bootconv": {
        "device_name": (0x20058, 0x100),
        "ini_value": (0x20158, 0x100),
        "_PDCLIB_errno": (0x20258, 0x4),
        "adrenaline_config": (0x2025C, 0xB8),
        "boot_info": (0x20314, 0x140),
    },
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def check_hash(path: Path, expected: str) -> None:
    require(path.is_file(), f"missing file: {path}")
    actual = digest(path.read_bytes())
    require(actual == expected, f"SHA-256 mismatch for {path}: {actual}")


def vita_imports(
    executable: Path,
    exports: Path,
    elf_create: Path | str = "vita-elf-create",
) -> set[tuple[int, int]]:
    with tempfile.TemporaryDirectory(prefix="adrbubble-velf-") as temporary:
        output = Path(temporary) / "module.velf"
        result = subprocess.run(
            [
                str(elf_create), "-vv", "-e", str(exports),
                str(executable), str(output),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=True,
        )
    hexadecimal = re.compile(
        r"library_nid=0x([0-9A-Fa-f]+).*target_nid=0x([0-9A-Fa-f]+)"
    )
    imports = {
        (int(match.group(1), 16), int(match.group(2), 16))
        for match in hexadecimal.finditer(result.stdout)
    }
    decimal = re.compile(
        r"^\s*Library:\s+(\d+).*?^\s*NID\s*:\s+(\d+)",
        re.MULTILINE | re.DOTALL,
    )
    imports.update(
        (int(match.group(1)), int(match.group(2)))
        for match in decimal.finditer(result.stdout)
    )
    return imports


def check_closed_vita_imports(
    work: Path,
    legacy_elf_create: Path | str,
    layout_elf_create: Path | str,
) -> None:
    core = work / "core/src/vita"
    adrbubble = vita_imports(
        core / "adrbubblebooter/adrbubblebooter",
        ROOT / "src/vita/adrbubblebooter/exports.yml",
        layout_elf_create,
    )
    require(adrbubble == COMMON_VITA_IMPORTS, "adrbubblebooter import set changed")

    bootconv = vita_imports(
        core / "bootconv/bootconv",
        ROOT / "src/vita/bootconv/exports.yml",
        legacy_elf_create,
    )
    expected = COMMON_VITA_IMPORTS | {(0xCAE9ACE6, 0xE20ED0F3)}
    require(bootconv == expected, "bootconv import set changed")


def elf32_symbols(path: Path) -> dict[str, tuple[int, int]]:
    data = path.read_bytes()
    require(data[:7] == b"\x7fELF\x01\x01\x01", f"not ELF32: {path}")
    section_offset = struct.unpack_from("<I", data, 0x20)[0]
    section_size, section_count = struct.unpack_from("<HH", data, 0x2E)
    require(section_size == 0x28, f"unexpected ELF section size: {path}")
    sections = [
        struct.unpack_from("<10I", data, section_offset + index * section_size)
        for index in range(section_count)
    ]
    symbols: dict[str, tuple[int, int]] = {}
    for section in sections:
        if section[1] != 2:
            continue
        offset, size, string_index, entry_size = (
            section[4], section[5], section[6], section[9]
        )
        require(entry_size == 0x10, f"unexpected ELF symbol size: {path}")
        strings = sections[string_index]
        string_data = data[strings[4]:strings[4] + strings[5]]
        for entry in range(offset, offset + size, entry_size):
            name_offset, value, symbol_size = struct.unpack_from("<III", data, entry)
            if name_offset == 0:
                continue
            end = string_data.find(b"\0", name_offset)
            require(end >= 0, f"unterminated ELF symbol name: {path}")
            name = string_data[name_offset:end].decode("ascii")
            symbols[name] = (value, symbol_size)
    return symbols


def check_closed_vita_bss_layout(work: Path) -> None:
    core = work / "core/src/vita"
    for relative, expected in CLOSED_VITA_BSS.items():
        path = core / relative
        symbols = elf32_symbols(path)
        for name, placement in expected.items():
            require(name in symbols, f"{relative}: missing BSS symbol {name}")
            require(
                symbols[name] == placement,
                f"{relative}: {name} layout changed: {symbols[name]} != {placement}",
            )


def check_psp_booter(work: Path) -> None:
    booter = work / "dist/psp/flash0/kd/booter.prx"
    require(booter.is_file(), f"missing PSP booter: {booter}")
    booter_data = booter.read_bytes()
    validate_profile(booter_data)
    require(b"Booter\0" in booter_data, "PSP module name is not Booter")
    require(
        struct.unpack_from("<I", booter_data, 0x18)[0] == 0x8,
        "PSP booter module entrypoint is not the original 0x8",
    )
    with tempfile.TemporaryDirectory(prefix="adrbubble-nids-") as temporary:
        temporary_booter = Path(temporary) / "booter.prx"
        shutil.copyfile(booter, temporary_booter)
        nids = Path(temporary) / "nids.bin"
        subprocess.run(
            [
                "psp-objcopy",
                f"--dump-section=.rodata.sceNid={nids}",
                str(temporary_booter),
            ],
            check=True,
        )
        raw = nids.read_bytes()
    actual = struct.unpack(f"<{len(raw) // 4}I", raw)
    require(actual == PSP_BOOTER_NIDS, "PSP booter import NID order changed")

    for index, expected_hash in PSP_BOOTER_SECTION_HASHES.items():
        section = REFERENCE_SECTIONS[index]
        payload = booter_data[section[4]:section[4] + section[5]]
        require(
            digest(payload) == expected_hash,
            f"PSP booter reference section {index} content changed",
        )

    rel_text = REFERENCE_SECTIONS[2]
    relocations = booter_data[rel_text[4]:rel_text[4] + rel_text[5]]
    relocation_types: dict[int, int] = {}
    for offset in range(0, len(relocations), 8):
        _address, info = struct.unpack_from("<II", relocations, offset)
        relocation_type = info & 0xFF
        relocation_types[relocation_type] = relocation_types.get(relocation_type, 0) + 1
    require(
        relocation_types == {4: 52, 5: 30, 6: 33},
        "PSP booter .rel.text relocation profile changed",
    )

    symbols = subprocess.run(
        ["psp-nm", "-n", str(ROOT / "src/psp/booter/booter.elf")],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    expected_symbols = {
        "reference_entry_prefix": 0x000,
        "module_start": 0x008,
        "launch_content": 0x070,
        "read_file": 0x264,
        "path_after_pspemu_device": 0x2D0,
        "check_file": 0x304,
        "flush_caches": 0x340,
        "detect_content_type": 0x35C,
        "booter_thread": 0x4A0,
        "pspSdkSetK1": 0x550,
        "pspSdkGetK1": 0x55C,
        "sceKernelSetParamSfo": 0x564,
        "sctrlKernelLoadExecVSHWithApitype": 0x56C,
        "sctrlSEMountUmdFromFile": 0x574,
        "sctrlSESetDiscType": 0x57C,
        "SetUmdFile": 0x584,
        "sctrlSESetBootConfFileIndex": 0x58C,
        "sceKernelIcacheClearAll": 0x594,
        "sceIoClose": 0x59C,
        "sceIoOpen": 0x5A4,
        "sceIoRead": 0x5AC,
        "sceIoLseek": 0x5B4,
        "sceIoGetstat": 0x5BC,
        "sceKernelDcacheWritebackAll": 0x5C4,
        "sceKernelCreateThread": 0x5CC,
        "sceKernelStartThread": 0x5D4,
        "strrchr": 0x5DC,
        "strncpy": 0x5E4,
        "strlen": 0x5EC,
        "memset": 0x5F4,
        "memcmp": 0x5FC,
        "sprintf": 0x604,
        "module_info": 0x6B0,
        "reference_bss_word": 0x9E4,
        "boot_info": 0x9E8,
        "ps1_title_id": 0xB28,
    }
    symbol_addresses: dict[str, int] = {}
    for line in symbols.splitlines():
        fields = line.split()
        if len(fields) == 3:
            try:
                symbol_addresses[fields[2]] = int(fields[0], 16)
            except ValueError:
                pass
    for name, exact_address in expected_symbols.items():
        require(name in symbol_addresses, f"PSP booter is missing {name}")
        address = symbol_addresses[name]
        require(
            address == exact_address,
            f"PSP booter {name} moved: 0x{address:X} != 0x{exact_address:X}",
        )


def check_embedded_payloads(work: Path) -> None:
    self_data = (work / "user-build/adrenaline_user.suprx").read_bytes()
    elf, _metadata, _segments = unpack_fself(self_data)
    for name in SHADER_HASHES:
        payload = (ROOT / "src/vita/shaders/gxp" / name).read_bytes()
        require(elf.count(payload) == 1, f"{name} is not embedded exactly once")
    for path in (
        work / "dist/psp/flash0/kd/booter.prx",
        work / "dist/psp/flash0/kd/pspbtbnf.bin",
    ):
        payload = path.read_bytes()
        require(elf.count(payload) == 1, f"{path.name} is not embedded exactly once")


def check_packed_psp_reproducibility(work: Path) -> None:
    for relative in (
        "user/flash0/kd/popcorn.prx",
        "user/flash0/kd/systemctrl.prx",
        "user/flash0/kd/vshctrl.prx",
        "user/flash0/vsh/module/recovery.prx",
        "user/flash0/vsh/module/satelite.prx",
    ):
        path = work / "adrenaline" / relative
        data = path.read_bytes()
        require(
            data == normalized_packed_psp(data),
            f"random psp-packer header data was not normalized: {relative}",
        )


def check_iftu_integration(work: Path, elf_create: Path | str) -> None:
    kernel_source = (work / "adrenaline/kernel/main.c").read_text(encoding="utf-8")
    require("ksceIftuSetInputFrameBufferPatched" in kernel_source, "IFTU hook missing")
    require("0xCAFCFE50, 0x7CE0C4DA" in kernel_source, "IFTU import NIDs changed")
    menu_source = (work / "adrenaline/user/menu.c").read_text(encoding="utf-8")
    require("kuSetPspemuDirectSharpScale" in menu_source, "user IFTU control missing")
    require("<<<<<<<" not in menu_source, "unresolved menu merge marker")

    imports = vita_imports(
        work / "user-build/adrenaline_user",
        work / "adrenaline/user/exports.yml",
        elf_create,
    )
    require(
        (0xDD6CB853, 0x36B0C051) in imports,
        "user module does not import kuSetPspemuDirectSharpScale",
    )


def check_booter_driver_menu_labels(work: Path) -> None:
    manifest = json.loads(
        (work / "dist/manifest.json").read_text(encoding="utf-8")
    )
    mode = manifest.get("booter_driver_menu_labels")
    orders = {
        "corrected": (b"NP9660", b"INFERNO", b"MARCH33"),
        "original-leecherman": (b"INFERNO", b"MARCH33", b"NP9660"),
    }
    require(mode in orders, f"unknown Booter driver-label mode: {mode!r}")

    expected_source = (
        'static char *drivers_options[] = { "'
        + '", "'.join(label.decode("ascii") for label in orders[mode])
        + '" };'
    )
    menu_source = (work / "adrenaline/user/menu.c").read_text(encoding="utf-8")
    require(
        menu_source.count(expected_source) == 1,
        f"materialized source does not select {mode} Booter driver labels",
    )

    self_data = (work / "user-build/adrenaline_user.suprx").read_bytes()
    elf, _metadata, segments = unpack_fself(self_data)
    require(len(segments) >= 2, "adrenaline_user.suprx has no data segment")
    program_header_offset = struct.unpack_from("<I", elf, 0x1C)[0]
    code_virtual_address = struct.unpack_from(
        "<I", elf, program_header_offset + 0x08
    )[0]
    addresses: dict[bytes, int] = {}
    for label in (b"INFERNO", b"MARCH33", b"NP9660"):
        needle = label + b"\0"
        offset = segments[0].find(needle)
        require(offset >= 0, f"adrenaline_user.suprx is missing {label!r}")
        require(
            segments[0].find(needle, offset + 1) < 0,
            f"adrenaline_user.suprx contains ambiguous {label!r} strings",
        )
        addresses[label] = code_virtual_address + offset

    expected_table = struct.pack(
        "<III", *(addresses[label] for label in orders[mode])
    )
    require(
        segments[1].count(expected_table) == 1,
        f"compiled Booter driver pointer order does not match {mode}",
    )
    other_mode = next(candidate for candidate in orders if candidate != mode)
    other_table = struct.pack(
        "<III", *(addresses[label] for label in orders[other_mode])
    )
    require(
        other_table not in segments[1],
        f"compiled module still contains {other_mode} Booter driver pointer order",
    )


def expected_crc_lua(work: Path) -> bytes:
    names = {
        "adrbubblebooter.suprx": "CRCADRBOOTER",
        "adrenaline_kernel.skprx": "CRCKERNEL",
        "adrenaline_user.suprx": "CRCUSER",
        "adrenaline_vsh.suprx": "CRCVSH",
        "bootconv.suprx": "CRCBOOTCONV",
    }
    text = (ROOT / "integration/abm/crc.lua.in").read_text(encoding="utf-8")
    for filename, token in names.items():
        placeholder = f"@{token}@"
        require(text.count(placeholder) == 1, f"bad CRC template: {placeholder}")
        data = (work / "dist/sce_module" / filename).read_bytes()
        text = text.replace(
            placeholder,
            f"0x{zlib.crc32(data) & 0xFFFFFFFF:08X}",
        )
    return text.encode("utf-8")


def check_abm_overlay(work: Path) -> None:
    distribution = work / "dist"
    overlay = distribution / "abm-overlay"
    require(
        (overlay / "crc.lua").read_bytes() == expected_crc_lua(work),
        "generated crc.lua does not preserve the complete ABM template",
    )
    for name in STACK_MODULES:
        require(
            (overlay / "sce_module" / name).read_bytes()
            == (distribution / "sce_module" / name).read_bytes(),
            f"ABM top-level module differs from build output: {name}",
        )
    for name in ADRENALINE_MODULES:
        require(
            (overlay / "bubbles/adrenaline/sce_module" / name).read_bytes()
            == (distribution / "sce_module" / name).read_bytes(),
            f"ABM Adrenaline template module differs from build output: {name}",
        )


def check_zip_members(
    archive_data: bytes,
    expected_names: list[str],
    expected_data: dict[str, bytes],
    label: str,
) -> None:
    with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        require(len(names) == len(set(names)), f"duplicate member in {label}")
        require(names == expected_names, f"unexpected member layout in {label}: {names}")
        for info in infos:
            require(
                info.date_time == (1980, 1, 1, 0, 0, 0),
                f"non-reproducible timestamp in {label}: {info.filename}",
            )
            if info.is_dir():
                require(archive.read(info) == b"", f"non-empty directory in {label}")
            else:
                require(
                    archive.read(info) == expected_data[info.filename],
                    f"member differs from installed module in {label}: {info.filename}",
                )


def check_abm_vpk(work: Path) -> None:
    application = work / "abm-source/AdrenalineBubbleManager"
    require(application.is_dir(), "missing pinned ABM package source tree")
    vpk_path = work / "dist/abm" / ABM_VPK
    require(vpk_path.is_file(), f"missing ABM VPK: {vpk_path}")

    expected_files = {
        path.relative_to(application).as_posix(): path.read_bytes()
        for path in application.rglob("*")
        if path.is_file()
    }
    with zipfile.ZipFile(vpk_path) as vpk:
        infos = vpk.infolist()
        names = [info.filename for info in infos if not info.is_dir()]
        require(len(names) == len(set(names)), "duplicate file in ABM VPK")
        for info in infos:
            require(
                info.date_time == (1980, 1, 1, 0, 0, 0),
                f"non-reproducible VPK timestamp: {info.filename}",
            )
        require(
            set(names) == set(expected_files),
            "ABM VPK file set differs from the pinned-and-overlaid source tree",
        )
        for name in names:
            require(
                vpk.read(name) == expected_files[name],
                f"ABM VPK member differs from package source: {name}",
            )

        main_names = [*STACK_MODULES, "usbdevice.skprx"]
        main_names.sort()
        main_data = {
            name: vpk.read(f"sce_module/{name}") for name in main_names
        }
        check_zip_members(
            vpk.read("sce_module/sce_module.zip"),
            main_names,
            main_data,
            "sce_module/sce_module.zip",
        )

        bubble_files = [*ADRENALINE_MODULES, "usbdevice.skprx"]
        bubble_files.sort()
        bubble_names = ["sce_module/"] + [
            f"sce_module/{name}" for name in bubble_files
        ]
        bubble_data = {
            f"sce_module/{name}": vpk.read(
                f"bubbles/adrenaline/sce_module/{name}"
            )
            for name in bubble_files
        }
        check_zip_members(
            vpk.read("bubbles/adrenaline/sce_module.zip"),
            bubble_names,
            bubble_data,
            "bubbles/adrenaline/sce_module.zip",
        )

        for relative in (
            "crc.lua",
            "bubbles/adrenaline.bin",
            "bubbles/menucolor.bin",
            "bubbles/pspemuxxx/data/boot.bin",
            "bubbles/pspemuxxx/eboot.bin",
        ):
            require(
                vpk.read(relative)
                == (work / "dist/abm-overlay" / relative).read_bytes(),
                f"ABM VPK payload differs from generated overlay: {relative}",
            )


def check_manifest(work: Path) -> None:
    distribution = work / "dist"
    manifest = json.loads((distribution / "manifest.json").read_text(encoding="utf-8"))
    variant = manifest["variant"]
    integration = ROOT / "integration" / (
        "adrenaline-current" if variant == "current" else "adrenaline-v7"
    )
    require(
        manifest["adrenaline_revision"]
        == (integration / "BASE").read_text(encoding="ascii").strip(),
        "manifest Adrenaline revision is not the pinned revision",
    )
    require(
        manifest["abm_revision"]
        == (ROOT / "integration/abm/BASE").read_text(encoding="ascii").strip(),
        "manifest ABM revision is not the pinned revision",
    )
    require(
        manifest["libvita2d_revision"]
        == (ROOT / "integration/libvita2d-fbo/COMMIT").read_text(
            encoding="ascii"
        ).strip(),
        "manifest libvita2d revision is not the pinned revision",
    )
    require(bool(manifest.get("toolchain")), "manifest has no toolchain identity")
    actual_files = {
        path.relative_to(distribution).as_posix()
        for path in distribution.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    require(
        set(manifest["files"]) == actual_files,
        "manifest file set differs from the distribution",
    )
    for relative, record in manifest["files"].items():
        path = distribution / relative
        data = path.read_bytes()
        require(len(data) == record["size"], f"manifest size mismatch: {relative}")
        require(digest(data) == record["sha256"], f"manifest hash mismatch: {relative}")


def validate(
    work: Path,
    *,
    require_abm_vpk: bool = True,
    legacy_elf_create: Path | str = "vita-elf-create",
    layout_elf_create: Path | str = "vita-elf-create",
) -> None:
    require(work.is_dir(), f"not a build directory: {work}")
    check_hash(
        work / "dist/psp/flash0/kd/pspbtbnf.bin",
        "e02ac316056c66eb1264b84147888d9facfc4865819b88e67b0f74eac02c036f",
    )
    for relative, expected in TEMPLATE_HASHES.items():
        check_hash(work / "dist/abm-overlay" / relative, expected)
    check_hash(
        work / "dist/abm-overlay/bubbles/pspemuxxx/eboot.bin",
        PER_BUBBLE_EBOOT_SHA256,
    )
    for name, expected in SHADER_HASHES.items():
        check_hash(ROOT / "src/vita/shaders/gxp" / name, expected)
    check_closed_vita_imports(work, legacy_elf_create, layout_elf_create)
    check_closed_vita_bss_layout(work)
    check_psp_booter(work)
    check_embedded_payloads(work)
    check_packed_psp_reproducibility(work)
    check_iftu_integration(work, layout_elf_create)
    check_booter_driver_menu_labels(work)
    check_abm_overlay(work)
    if require_abm_vpk:
        check_abm_vpk(work)
    check_manifest(work)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", type=Path)
    args = parser.parse_args()
    validate(args.work_dir.resolve())
    print("all static equivalence checks passed")


if __name__ == "__main__":
    main()
