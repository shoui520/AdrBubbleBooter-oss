#!/usr/bin/env python3
"""Build and assemble the complete open AdrBubbleBooter/Adrenaline stack."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
import zlib
from pathlib import Path

from generate_data import generate as generate_data
from materialize_adrenaline import materialize as materialize_adrenaline
from materialize_vita2d import materialize as materialize_vita2d
from normalize_psp_packed import normalize as normalize_psp_packed
from validate_build import validate as validate_build
from validate_vita_modules import validate_module as validate_vita_module


ROOT = Path(__file__).resolve().parents[1]
REPRODUCIBLE_TIMESTAMP = 315532800  # 1980-01-01 00:00:00 UTC / DOS epoch


def run(
    arguments: list[str],
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> None:
    subprocess.run(arguments, cwd=cwd, check=True, env=env)


def sdk_environment(vitasdk: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["VITASDK"] = str(vitasdk)
    environment["PATH"] = os.pathsep.join((
        str(vitasdk / "bin"),
        environment.get("PATH", ""),
    ))
    return environment


def require_file_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"missing {label}: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError(f"wrong {label}: {path} has SHA-256 {actual}")


def require_environment(args: argparse.Namespace) -> None:
    pspdev = os.environ.get("PSPDEV")
    if not pspdev or not Path(pspdev).is_dir():
        raise RuntimeError("PSPDEV must name an installed SDK directory")
    for label, path in (
        ("historical PSPDEV", args.legacy_pspdev),
        ("April 2017 VitaSDK", args.legacy_vitasdk),
        ("August 2017 VitaSDK", args.closed_vitasdk),
        ("September 2020 VitaSDK", args.layout_vitasdk),
        ("taiHEN 0.6", args.legacy_taihen),
        ("Sony PSP2 shader tool directory", args.psp2_sdk_bin),
    ):
        if not path.is_dir():
            raise FileNotFoundError(f"missing {label}: {path}")

    locked = (
        (args.legacy_pspdev / "bin/psp-gcc", "b101331ce833b09922f8e12bb57636cc3d08ce8187ab3d97cd7616128c81e3b0", "historical PSP GCC 4.9.3"),
        (args.legacy_pspdev / "bin/psp-as", "a245993ebf7861afdda8e2fe4f01501a68a074d432fa36524267336df4b36f2c", "historical PSP assembler 2.22"),
        (args.legacy_pspdev / "bin/psp-ld", "33123e05e7921bab459ddc655dbbdcefe96941603d99db8f4197e953b696285f", "historical PSP linker 2.22"),
        (args.legacy_pspdev / "bin/psp-fixup-imports", "24ce8bde75406a6f943feb75e51cacef48d91960275e2865fc7dfbad7facba91", "historical psp-fixup-imports"),
        (args.legacy_pspdev / "bin/psp-prxgen", "81ee4b43b33697902a174fc14e25871d77efeefdcc9c4334c95453f0f2fc1c1f", "historical psp-prxgen"),
        (args.legacy_pspdev / "psp/sdk/lib/linkfile.prx", "279b81cbb90d6de3a96794d016ea765da787587d1a6c5fd5999a0447c2db6162", "historical PSP PRX linker script"),
        (args.psp_layout_ld, "d119ef5866b70ce46293b4ee7bb5ac356d44f93d802ca25580d3ad682b95937b", "PSP layout linker 2.44"),
        (args.legacy_vitasdk / "bin/arm-vita-eabi-gcc", "9102505975d92e24e4ac9f42a976808c0dfd74099bda13b703d7a619a50dcd3b", "legacy GCC"),
        (args.legacy_vitasdk / "bin/vita-elf-create", "66514c0233c053f484e7d766edf8f7b913d6e1aeccb42cd3b1ff29336cda8e9e", "legacy vita-elf-create"),
        (args.closed_vitasdk / "bin/arm-vita-eabi-gcc", "6bcb7bd71af67048b8d37291a0867b3c2000857f59f22be5e01498eec6557c12", "closed-module GCC 7.2"),
        (args.layout_vitasdk / "bin/arm-vita-eabi-gcc", "d42abf3e9a7f867d17f2e5f3e5a771cb3ceefe9bb2d63a6e96f5068b5a1c6713", "layout GCC"),
        (args.layout_vitasdk / "bin/vita-elf-create", "cd10247663f2942be2197491e89501ed31e42ae9a9f34c6e136474ce0b47a537", "layout vita-elf-create"),
        (args.legacy_make_fself, "1d81600aa41663c4290d9486d59b9da4f372f02eba43010f1b9c9b668e6e0601", "April 2017 fixed-identity vita-make-fself"),
        (args.legacy_taihen / "include/taihen.h", "87a8de9ebaf2ec079dfa0b4c50b8f397219a0b05513fe010252ce86d5e030c8b", "taiHEN 0.6 header"),
        (args.legacy_taihen / "lib/libtaihen_stub.a", "7d7c276dae5bc7cfd5d28fd5c82f893da8b9fa91c68782cdd494f7484a6e593d", "taiHEN 0.6 user stub"),
        (args.psp2_sdk_bin / "psp2cgc.exe", "dae6c92bb97b2b8adfa26a3f85589e80eacf4ba88d2d6189bff4eaa6c87a4e27", "Sony psp2cgc build 13276"),
        (args.psp2_sdk_bin / "psp2shaderperf.exe", "14b429ef05493b860d0eef8a8c0914f1722996b522b1fcadef64b5952a216c8b", "Sony psp2shaderperf"),
    )
    for path, expected, label in locked:
        require_file_hash(path, expected, label)


def clone(repository: str, destination: Path) -> None:
    run(["git", "clone", "--filter=blob:none", repository, str(destination)])


def source_or_clone(
    supplied: Path | None,
    integration: Path,
    temporary_root: Path,
    name: str,
) -> Path:
    if supplied is not None:
        return supplied.resolve()
    repository = (integration / "REPOSITORY").read_text(encoding="ascii").strip()
    destination = temporary_root / name
    clone(repository, destination)
    return destination


def configure(
    source: Path,
    build: Path,
    *definitions: str,
    env: dict[str, str] | None = None,
) -> None:
    run(
        [
            "cmake",
            "-S", str(source),
            "-B", str(build),
            "-DCMAKE_BUILD_TYPE=Release",
            *definitions,
        ],
        env=env,
    )


def copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def archive_checkout(source: Path, revision: str, output: Path) -> None:
    subprocess.run(
        ["git", "-C", str(source), "cat-file", "-e", f"{revision}^{{commit}}"],
        check=True,
    )
    archive = subprocess.run(
        ["git", "-C", str(source), "archive", "--format=tar", revision],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    output.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        bundle.extractall(output, filter="data")


def write_crc_file(modules: dict[str, Path], output: Path) -> None:
    names = {
        "adrbubblebooter.suprx": "CRCADRBOOTER",
        "adrenaline_kernel.skprx": "CRCKERNEL",
        "adrenaline_user.suprx": "CRCUSER",
        "adrenaline_vsh.suprx": "CRCVSH",
        "bootconv.suprx": "CRCBOOTCONV",
    }
    text = (ROOT / "integration/abm/crc.lua.in").read_text(encoding="utf-8")
    for filename, token in names.items():
        checksum = zlib.crc32(modules[filename].read_bytes()) & 0xFFFFFFFF
        placeholder = f"@{token}@"
        if text.count(placeholder) != 1:
            raise RuntimeError(f"unexpected ABM CRC template token: {placeholder}")
        text = text.replace(placeholder, f"0x{checksum:08X}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def write_module_zip(path: Path, root: Path, prefix: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    members = sorted(
        item for item in root.iterdir()
        if item.is_file() and item.resolve() != path.resolve()
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        if prefix:
            directory = zipfile.ZipInfo(prefix.rstrip("/") + "/")
            directory.date_time = (1980, 1, 1, 0, 0, 0)
            directory.external_attr = 0o40755 << 16
            archive.writestr(directory, b"")
        for source in members:
            name = f"{prefix.rstrip('/')}/{source.name}" if prefix else source.name
            info = zipfile.ZipInfo(name)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes())


def normalize_tree_timestamps(root: Path) -> None:
    timestamp = (REPRODUCIBLE_TIMESTAMP, REPRODUCIBLE_TIMESTAMP)
    for path in sorted(root.rglob("*"), reverse=True):
        os.utime(path, timestamp, follow_symlinks=False)
    os.utime(root, timestamp, follow_symlinks=False)


def package_abm(
    work: Path,
    distribution: Path,
    source: Path,
    env: dict[str, str],
) -> Path:
    revision = (ROOT / "integration/abm/BASE").read_text(encoding="ascii").strip()
    exported = work / "abm-source"
    archive_checkout(source, revision, exported)
    application = exported / "AdrenalineBubbleManager"
    require_files = (application / "script.lua", application / "sce_sys/param.sfo")
    if not all(path.is_file() for path in require_files):
        raise RuntimeError("pinned ABM tree has an unexpected layout")

    overlay = distribution / "abm-overlay"
    for source_file in sorted(item for item in overlay.rglob("*") if item.is_file()):
        copy(source_file, application / source_file.relative_to(overlay))

    write_module_zip(
        application / "sce_module/sce_module.zip",
        application / "sce_module",
    )
    write_module_zip(
        application / "bubbles/adrenaline/sce_module.zip",
        application / "bubbles/adrenaline/sce_module",
        "sce_module",
    )
    normalize_tree_timestamps(application)

    output = distribution / "abm/AdrenalineBubbleManager_6.21_AdrBubbleBooter-oss.vpk"
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "vita-pack-vpk",
        "-s", str(application / "sce_sys/param.sfo"),
        "-b", str(application / "eboot.bin"),
    ]
    for item in sorted(application.iterdir()):
        if item.name in ("eboot.bin", "sce_sys"):
            continue
        command.extend(("-a", f"{item}={item.name}"))
    for item in sorted((application / "sce_sys").iterdir()):
        if item.name == "param.sfo":
            continue
        command.extend(("-a", f"{item}=sce_sys/{item.name}"))
    command.append(str(output))
    run(command, env=env)
    return output


def tool_identity(
    name: str | Path,
    version_arguments: tuple[str, ...] = (),
) -> dict[str, object]:
    supplied = Path(name)
    if supplied.parent != Path("."):
        executable = supplied.resolve()
        if not executable.is_file():
            raise FileNotFoundError(f"required build tool does not exist: {executable}")
    else:
        located = shutil.which(str(name))
        if located is None:
            raise FileNotFoundError(f"required build tool is not on PATH: {name}")
        executable = Path(located).resolve()
    data = executable.read_bytes()
    identity: dict[str, object] = {
        "path": str(executable),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    if version_arguments:
        result = subprocess.run(
            [str(executable), *version_arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if lines:
            identity["version"] = lines[0]
    return identity


def toolchain_identity(args: argparse.Namespace) -> dict[str, object]:
    python = Path(sys.executable).resolve()
    python_data = python.read_bytes()
    return {
        "python3": {
            "version": sys.version.splitlines()[0],
            "size": len(python_data),
            "sha256": hashlib.sha256(python_data).hexdigest(),
        },
        "legacy-arm-vita-eabi-gcc": tool_identity(
            args.legacy_vitasdk / "bin/arm-vita-eabi-gcc", ("--version",)
        ),
        "legacy-vita-elf-create": tool_identity(
            args.legacy_vitasdk / "bin/vita-elf-create"
        ),
        "closed-arm-vita-eabi-gcc": tool_identity(
            args.closed_vitasdk / "bin/arm-vita-eabi-gcc", ("--version",)
        ),
        "layout-arm-vita-eabi-gcc": tool_identity(
            args.layout_vitasdk / "bin/arm-vita-eabi-gcc", ("--version",)
        ),
        "layout-vita-elf-create": tool_identity(
            args.layout_vitasdk / "bin/vita-elf-create"
        ),
        "legacy-fixed-vita-make-fself": tool_identity(args.legacy_make_fself),
        "sony-psp2cgc": tool_identity(
            args.psp2_sdk_bin / "psp2cgc.exe", ("-v",)
        ),
        "sony-psp2shaderperf": tool_identity(
            args.psp2_sdk_bin / "psp2shaderperf.exe"
        ),
        "historical-psp-gcc": tool_identity(
            args.legacy_pspdev / "bin/psp-gcc", ("--version",)
        ),
        "historical-psp-as": tool_identity(
            args.legacy_pspdev / "bin/psp-as", ("--version",)
        ),
        "historical-psp-ld": tool_identity(
            args.legacy_pspdev / "bin/psp-ld", ("--version",)
        ),
        "historical-psp-fixup-imports": tool_identity(
            args.legacy_pspdev / "bin/psp-fixup-imports"
        ),
        "historical-psp-prxgen": tool_identity(
            args.legacy_pspdev / "bin/psp-prxgen"
        ),
        "psp-layout-ld": tool_identity(args.psp_layout_ld, ("--version",)),
        "psp-gcc": tool_identity("psp-gcc", ("--version",)),
        "psp-packer": tool_identity("psp-packer", ("--version",)),
        "vita-pack-vpk": tool_identity(
            args.layout_vitasdk / "bin/vita-pack-vpk"
        ),
        "cmake": tool_identity("cmake", ("--version",)),
        "make": tool_identity("make", ("--version",)),
    }


def write_manifest(
    distribution: Path,
    variant: str,
    args: argparse.Namespace,
) -> None:
    manifest_path = distribution / "manifest.json"
    manifest: dict[str, object] = {
        "variant": variant,
        "booter_driver_menu_labels": (
            "original-leecherman"
            if args.original_leecherman_driver_labels
            else "corrected"
        ),
        "adrenaline_revision": (
            ROOT / "integration" /
            ("adrenaline-current" if variant == "current" else "adrenaline-v7") /
            "BASE"
        ).read_text(encoding="ascii").strip(),
        "abm_revision": (ROOT / "integration/abm/BASE").read_text(
            encoding="ascii"
        ).strip(),
        "libvita2d_revision": (
            ROOT / "integration/libvita2d-fbo/COMMIT"
        ).read_text(encoding="ascii").strip(),
        "libk_revision": (
            ROOT / "integration/libk/COMMIT"
        ).read_text(encoding="ascii").strip(),
        "toolchain": toolchain_identity(args),
        "files": {},
    }
    files = manifest["files"]
    assert isinstance(files, dict)
    for path in sorted(item for item in distribution.rglob("*") if item.is_file()):
        if path == manifest_path:
            continue
        relative = path.relative_to(distribution).as_posix()
        data = path.read_bytes()
        files[relative] = {
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def assemble(
    work: Path,
    closed_core: Path,
    ebooter_core: Path,
    adrenaline: Path,
    kernel_build: Path,
    user_build: Path,
    vsh_build: Path,
    variant: str,
) -> None:
    distribution = work / "dist"
    modules = {
        "adrbubblebooter.suprx":
            closed_core / "src/vita/adrbubblebooter/adrbubblebooter.suprx",
        "bootconv.suprx":
            closed_core / "src/vita/bootconv/bootconv.suprx",
        "adrenaline_kernel.skprx": kernel_build / "adrenaline_kernel.skprx",
        "adrenaline_user.suprx": user_build / "adrenaline_user.suprx",
        "adrenaline_vsh.suprx": vsh_build / "adrenaline_vsh.suprx",
    }
    for path in modules.values():
        if not path.is_file():
            raise FileNotFoundError(path)

    module_set = distribution / "sce_module"
    for filename, source in modules.items():
        copy(source, module_set / filename)

    overlay = distribution / "abm-overlay"
    for filename, source in modules.items():
        copy(source, overlay / "sce_module" / filename)
    for filename in (
        "adrenaline_kernel.skprx",
        "adrenaline_user.suprx",
        "adrenaline_vsh.suprx",
    ):
        copy(modules[filename], overlay / "bubbles/adrenaline/sce_module" / filename)

    copy(
        ebooter_core / "src/vita/ebooter/per-bubble-eboot.bin",
        overlay / "bubbles/pspemuxxx/eboot.bin",
    )
    generated = work / "generated-data"
    generate_data(generated)
    copy(generated / "boot.bin", overlay / "bubbles/pspemuxxx/data/boot.bin")
    copy(generated / "adrenaline.bin", overlay / "bubbles/adrenaline.bin")
    copy(generated / "menucolor.bin", overlay / "bubbles/menucolor.bin")
    write_crc_file(modules, overlay / "crc.lua")

    # Preserve the directly embedded PSP payloads as independently auditable
    # outputs in addition to the copies inside adrenaline_user.suprx.
    copy(
        adrenaline / "user/flash0/kd/booter.prx",
        distribution / "psp/flash0/kd/booter.prx",
    )
    copy(
        adrenaline / "user/flash0/kd/pspbtbnf.bin",
        distribution / "psp/flash0/kd/pspbtbnf.bin",
    )


def build(args: argparse.Namespace) -> None:
    require_environment(args)
    psp_env = os.environ.copy()
    psp_env["PSPDEV"] = str(args.legacy_pspdev)
    legacy_env = sdk_environment(args.legacy_vitasdk)
    closed_env = sdk_environment(args.closed_vitasdk)
    layout_env = sdk_environment(args.layout_vitasdk)
    work = args.work_dir.resolve()
    if work.exists():
        raise FileExistsError(f"refusing to overwrite existing work directory: {work}")
    work.mkdir(parents=True)

    jobs = str(args.jobs)
    with tempfile.TemporaryDirectory(prefix="adrbubble-sources-") as temporary:
        temporary_root = Path(temporary)
        integration = ROOT / "integration" / (
            "adrenaline-current" if args.variant == "current" else "adrenaline-v7"
        )
        adrenaline_source = source_or_clone(
            args.adrenaline_source,
            integration,
            temporary_root,
            "Adrenaline",
        )
        vita2d_source = source_or_clone(
            args.vita2d_source,
            ROOT / "integration/libvita2d-fbo",
            temporary_root,
            "vita2dlib",
        )
        libk_repository = source_or_clone(
            args.libk_source,
            ROOT / "integration/libk",
            temporary_root,
            "libk",
        )
        libk_revision = (ROOT / "integration/libk/COMMIT").read_text(
            encoding="ascii"
        ).strip()
        libk_source = work / "libk-source"
        archive_checkout(libk_repository, libk_revision, libk_source)
        abm_source = None
        if args.package_abm:
            abm_source = source_or_clone(
                args.abm_source,
                ROOT / "integration/abm",
                temporary_root,
                "AdrenalineBubbleManager",
            )

        run(
            [
                "make", "-B", "-C", str(ROOT / "src/psp/booter"),
                f"-j{jobs}",
                f"PSP_LAYOUT_LD={args.psp_layout_ld}",
                "PSP_HEADER_COMPAT_FLAGS=-D__INTPTR_TYPE__=int "
                "-D__INT32_TYPE__='long int'",
            ],
            env=psp_env,
        )
        btcnf = work / "pspbtbnf.bin"
        run([
            "python3", str(ROOT / "tools/btcnf.py"), "build",
            str(ROOT / "src/psp/btcnf/pspbtcnf.txt"), str(btcnf),
        ])

        core = work / "core"
        configure(
            ROOT,
            core,
            "-DCMAKE_MAKE_PROGRAM=/usr/bin/make",
            f"-DADRBUBBLE_MAKE_FSELF={args.legacy_make_fself}",
            f"-DADRBUBBLE_LEGACY_MAKE_FSELF={args.legacy_make_fself}",
            "-DADRBUBBLE_ELF_CREATE="
            f"{args.legacy_vitasdk / 'bin/vita-elf-create'}",
            "-DADRBUBBLE_ADR_ELF_CREATE="
            f"{args.layout_vitasdk / 'bin/vita-elf-create'}",
            f"-DADRBUBBLE_LIBK_SOURCE={libk_source}",
            f"-DCMAKE_C_FLAGS=-I{args.legacy_taihen / 'include'}",
            f"-DCMAKE_EXE_LINKER_FLAGS=-L{args.legacy_taihen / 'lib'}",
            env=closed_env,
        )
        run(
            [
                "cmake", "--build", str(core), "--parallel", jobs,
                "--target", "adrbubblebooter.suprx", "bootconv.suprx",
            ],
            env=closed_env,
        )

        ebooter_core = work / "ebooter-core"
        configure(
            ROOT,
            ebooter_core,
            "-DCMAKE_MAKE_PROGRAM=/usr/bin/make",
            f"-DADRBUBBLE_MAKE_FSELF={args.legacy_make_fself}",
            f"-DADRBUBBLE_LEGACY_MAKE_FSELF={args.legacy_make_fself}",
            "-DADRBUBBLE_ELF_CREATE="
            f"{args.legacy_vitasdk / 'bin/vita-elf-create'}",
            "-DADRBUBBLE_ADR_ELF_CREATE="
            f"{args.layout_vitasdk / 'bin/vita-elf-create'}",
            f"-DADRBUBBLE_LIBK_SOURCE={libk_source}",
            f"-DCMAKE_C_FLAGS=-I{args.legacy_taihen / 'include'}",
            f"-DCMAKE_EXE_LINKER_FLAGS=-L{args.legacy_taihen / 'lib'}",
            env=legacy_env,
        )
        run(
            [
                "cmake", "--build", str(ebooter_core), "--parallel", jobs,
                "--target", "per-bubble-eboot.bin",
            ],
            env=legacy_env,
        )

        run(
            [
                "make", "-C", str(ROOT / "src/vita/shaders"),
                f"-j{jobs}", "verify-gxp", f"PSP2_SDK_BIN={args.psp2_sdk_bin}",
            ],
            env=legacy_env,
        )
        run(
            [
                "make", "-B", "-C", str(ROOT / "src/vita/shaders"),
                f"-j{jobs}", "verify-archive",
            ],
            env=legacy_env,
        )
        vita2d = work / "vita2d"
        materialize_vita2d(vita2d_source, vita2d)
        run(
            ["make", "-C", str(vita2d / "libvita2d"), f"-j{jobs}"],
            env=layout_env,
        )

        adrenaline = work / "adrenaline"
        materialize_adrenaline(
            adrenaline_source,
            adrenaline,
            ROOT / "src/psp/booter/booter.prx",
            btcnf,
            variant=args.variant,
            modern_vitasdk=False,
            fix_booter_driver_labels=(
                not args.original_leecherman_driver_labels
            ),
        )
        run(["make", "-C", str(adrenaline / "cef"), f"-j{jobs}"])
        for relative in (
            "user/flash0/kd/popcorn.prx",
            "user/flash0/kd/systemctrl.prx",
            "user/flash0/kd/vshctrl.prx",
            "user/flash0/vsh/module/recovery.prx",
            "user/flash0/vsh/module/satelite.prx",
        ):
            normalize_psp_packed(adrenaline / relative)

        stage = work / "stage"
        kernel_build = work / "kernel-build"
        configure(
            adrenaline / "kernel",
            kernel_build,
            f"-DCMAKE_INSTALL_PREFIX={stage}",
            f"-DADRBUBBLE_MAKE_FSELF={args.legacy_make_fself}",
            "-DADRBUBBLE_ELF_CREATE="
            f"{args.layout_vitasdk / 'bin/vita-elf-create'}",
            env=layout_env,
        )
        run(
            ["cmake", "--build", str(kernel_build), "--parallel", jobs],
            env=layout_env,
        )
        run(
            ["cmake", "--install", str(kernel_build)],
            env=layout_env,
        )

        user_build = work / "user-build"
        user_include = vita2d / "libvita2d/include"
        user_link = " ".join((
            f"-L{stage / 'lib'}",
            f"-L{vita2d / 'libvita2d'}",
            f"-L{ROOT / 'src/vita/shaders'}",
        ))
        configure(
            adrenaline / "user",
            user_build,
            f"-DCMAKE_C_FLAGS=-I{user_include}",
            f"-DCMAKE_EXE_LINKER_FLAGS={user_link}",
            f"-DADRBUBBLE_MAKE_FSELF={args.legacy_make_fself}",
            "-DADRBUBBLE_ELF_CREATE="
            f"{args.layout_vitasdk / 'bin/vita-elf-create'}",
            env=layout_env,
        )
        run(
            ["cmake", "--build", str(user_build), "--parallel", jobs],
            env=layout_env,
        )

        vsh_build = work / "vsh-build"
        configure(
            adrenaline / "vsh",
            vsh_build,
            f"-DADRBUBBLE_MAKE_FSELF={args.legacy_make_fself}",
            "-DADRBUBBLE_ELF_CREATE="
            f"{args.legacy_vitasdk / 'bin/vita-elf-create'}",
            env=layout_env,
        )
        run(
            ["cmake", "--build", str(vsh_build), "--parallel", jobs],
            env=layout_env,
        )

        modules = {
            "adrbubblebooter":
                core / "src/vita/adrbubblebooter/adrbubblebooter.suprx",
            "bootconv": core / "src/vita/bootconv/bootconv.suprx",
            "ebooter":
                ebooter_core / "src/vita/ebooter/per-bubble-eboot.bin",
            "kernel": kernel_build / "adrenaline_kernel.skprx",
            "user": user_build / "adrenaline_user.suprx",
            "vsh": vsh_build / "adrenaline_vsh.suprx",
        }
        for label, path in modules.items():
            validate_vita_module(label, path)
            print(f"{label}: loader structure verified")

        assemble(
            work,
            core,
            ebooter_core,
            adrenaline,
            kernel_build,
            user_build,
            vsh_build,
            args.variant,
        )
        write_manifest(work / "dist", args.variant, args)
        validate_build(
            work,
            require_abm_vpk=False,
            legacy_elf_create=args.legacy_vitasdk / "bin/vita-elf-create",
            layout_elf_create=args.layout_vitasdk / "bin/vita-elf-create",
        )
        if args.package_abm:
            assert abm_source is not None
            package_abm(work, work / "dist", abm_source, layout_env)
            write_manifest(work / "dist", args.variant, args)
            validate_build(
                work,
                legacy_elf_create=args.legacy_vitasdk / "bin/vita-elf-create",
                layout_elf_create=args.layout_vitasdk / "bin/vita-elf-create",
            )
        print(f"complete validated stack: {work / 'dist'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adrenaline-source", type=Path)
    parser.add_argument("--vita2d-source", type=Path)
    parser.add_argument("--libk-source", type=Path)
    parser.add_argument("--abm-source", type=Path)
    parser.add_argument(
        "--legacy-pspdev",
        type=Path,
        default=os.environ.get("ADRBUBBLE_PSPDEV_2017"),
        help="GCC 4.9.3/binutils 2.22/2016 PSPSDK compatibility tree",
    )
    parser.add_argument(
        "--legacy-vitasdk",
        type=Path,
        default=os.environ.get("ADRBUBBLE_VITASDK_2017"),
        help="official April 2017 VitaSDK master-linux-v276 tree",
    )
    parser.add_argument(
        "--closed-vitasdk",
        type=Path,
        default=os.environ.get("ADRBUBBLE_VITASDK_2017_V481"),
        help="official August 2017 VitaSDK GCC 7.2 master-linux-v481 tree",
    )
    parser.add_argument(
        "--psp-layout-ld",
        type=Path,
        help="PSP binutils 2.44 linker used to preserve zero-size PRX sections",
    )
    parser.add_argument(
        "--layout-vitasdk",
        type=Path,
        default=os.environ.get("ADRBUBBLE_VITASDK_2020"),
        help="official September 2020 VitaSDK master-linux-v1224 tree",
    )
    parser.add_argument(
        "--legacy-taihen",
        type=Path,
        default=os.environ.get("ADRBUBBLE_TAIHEN_06"),
        help="taiHEN 0.6 install tree",
    )
    parser.add_argument(
        "--psp2-sdk-bin",
        type=Path,
        default=os.environ.get("PSP2_SDK_BIN"),
        help="Sony SDK directory containing psp2cgc build 13276",
    )
    parser.add_argument(
        "--legacy-make-fself",
        type=Path,
        help="patched April 2017 vita-make-fself used by all stack modules",
    )
    parser.add_argument(
        "--package-abm",
        action="store_true",
        help="create an ABM VPK only after all non-package validation passes",
    )
    parser.add_argument(
        "--original-leecherman-driver-labels",
        action="store_true",
        help=(
            "disable the default Booter driver-label correction and retain "
            "Leecherman's original INFERNO/MARCH33/NP9660 pointer order"
        ),
    )
    parser.add_argument(
        "--variant",
        choices=("current", "historical"),
        default="current",
    )
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--jobs", type=int, choices=(12,), default=12)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    for option, value in (
        ("--legacy-pspdev", args.legacy_pspdev),
        ("--legacy-vitasdk", args.legacy_vitasdk),
        ("--closed-vitasdk", args.closed_vitasdk),
        ("--layout-vitasdk", args.layout_vitasdk),
        ("--legacy-taihen", args.legacy_taihen),
        ("--psp2-sdk-bin", args.psp2_sdk_bin),
    ):
        if value is None:
            parser.error(f"{option} or its documented environment variable is required")
    args.legacy_pspdev = args.legacy_pspdev.resolve()
    if args.psp_layout_ld is None:
        args.psp_layout_ld = Path(os.environ["PSPDEV"]) / "bin/psp-ld"
    args.psp_layout_ld = args.psp_layout_ld.resolve()
    args.legacy_vitasdk = args.legacy_vitasdk.resolve()
    args.closed_vitasdk = args.closed_vitasdk.resolve()
    args.layout_vitasdk = args.layout_vitasdk.resolve()
    args.legacy_taihen = args.legacy_taihen.resolve()
    args.psp2_sdk_bin = args.psp2_sdk_bin.resolve()
    if args.legacy_make_fself is None:
        args.legacy_make_fself = (
            args.legacy_vitasdk / "bin/vita-make-fself-fixed"
        )
    args.legacy_make_fself = args.legacy_make_fself.resolve()
    if args.work_dir is None:
        args.work_dir = ROOT / f"build/full-{args.variant}"
    build(args)


if __name__ == "__main__":
    main()
