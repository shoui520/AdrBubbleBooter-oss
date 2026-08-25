#!/usr/bin/env python3
"""Materialize the exact open AdrBubbleBooter Adrenaline source tree."""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / "integration" / "adrenaline-v7"
CURRENT = ROOT / "integration" / "adrenaline-current"
BOOTER_DRIVER_LABEL_PATCH = (
    ROOT / "integration" / "patches" / "booter-driver-menu-labels.patch"
)


def run_git(source: Path, *arguments: str, stdout=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(source), *arguments],
        check=True,
        stdout=stdout,
    )


def validate_checkout(source: Path, revision: str) -> None:
    if not (source / ".git").exists():
        raise ValueError(f"not a Git checkout: {source}")
    run_git(source, "cat-file", "-e", f"{revision}^{{commit}}")


def git_file(source: Path, revision: str, relative: Path) -> bytes | None:
    result = subprocess.run(
        ["git", "-C", str(source), "show", f"{revision}:{relative.as_posix()}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return result.stdout if result.returncode == 0 else None


def normalized(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def merge_current_overlay(source: Path, temporary: Path) -> None:
    ancestor = (CURRENT / "ANCESTOR").read_text(encoding="ascii").strip()
    current_revision = (CURRENT / "BASE").read_text(encoding="ascii").strip()
    overlay = HISTORICAL / "overlay"
    resolutions = {
        Path("cef/btcnf/pspbtcnf_recovery/pspbtcnf.txt"):
            overlay / "cef/btcnf/pspbtcnf_recovery/pspbtcnf.txt",
        Path("user/menu.c"): CURRENT / "resolutions/user/menu.c",
    }

    for other_file in sorted(path for path in overlay.rglob("*") if path.is_file()):
        relative = other_file.relative_to(overlay)
        destination = temporary / relative
        destination.parent.mkdir(parents=True, exist_ok=True)

        if relative in resolutions:
            shutil.copyfile(resolutions[relative], destination)
            continue

        base_data = git_file(source, ancestor, relative)
        current_data = git_file(source, current_revision, relative)
        other_data = normalized(other_file.read_bytes())
        if base_data is None:
            if current_data is not None:
                raise RuntimeError(
                    f"historically new file now collides with current source: {relative}"
                )
            destination.write_bytes(other_data)
            continue
        if current_data is None:
            raise RuntimeError(f"current source deleted an overlaid file: {relative}")

        with tempfile.TemporaryDirectory(prefix="merge-", dir=temporary) as merge_dir:
            merge_root = Path(merge_dir)
            current_path = merge_root / "current"
            base_path = merge_root / "ancestor"
            other_path = merge_root / "adrbubble"
            current_path.write_bytes(normalized(current_data))
            base_path.write_bytes(normalized(base_data))
            other_path.write_bytes(other_data)
            result = subprocess.run(
                [
                    "git", "merge-file",
                    "-L", "CURRENT",
                    "-L", "ANCESTOR",
                    "-L", "ADRBUBBLE",
                    "-p",
                    str(current_path),
                    str(base_path),
                    str(other_path),
                ],
                stdout=subprocess.PIPE,
            )
        if result.returncode != 0:
            raise RuntimeError(
                f"unresolved three-way merge for {relative}; add an explicit resolution"
            )
        destination.write_bytes(result.stdout)


def apply_modern_pspdev_compatibility(temporary: Path) -> None:
    """Preserve old GCC semantics explicitly under current PSPDEV.

    AdrBubbleBooter/Adrenaline was authored for pre-GCC-10 common symbols and
    pre-C23 empty parameter lists. These flags select those same semantics and
    prevent GCC's loop-to-libc recognition in the freestanding payloads.
    """
    extra = (
        " -std=gnu17 -fgnu89-inline -fcommon -fno-builtin"
        " -Wno-error=implicit-function-declaration"
        " -Wno-error=incompatible-pointer-types"
    )
    for makefile in sorted((temporary / "cef").rglob("Makefile")):
        text = normalized(makefile.read_bytes()).decode("utf-8")
        lines = text.splitlines()
        changed = False
        for index, line in enumerate(lines):
            if line.startswith("CFLAGS ="):
                if "-fcommon" not in line:
                    lines[index] = line + extra
                changed = True
                break
        if changed:
            makefile.write_text("\n".join(lines) + "\n", encoding="utf-8")

    recovery_main = temporary / "cef/recovery/main.c"
    recovery_text = normalized(recovery_main.read_bytes()).decode("utf-8")
    old_heap = "PSP_HEAP_SIZE_MAX();"
    if recovery_text.count(old_heap) != 1:
        raise RuntimeError("unexpected recovery heap declaration")
    recovery_main.write_text(
        recovery_text.replace(old_heap, "PSP_HEAP_SIZE_KB(-1);"),
        encoding="utf-8",
    )

    systemctrl_makefile = temporary / "cef/systemctrl/Makefile"
    systemctrl_text = systemctrl_makefile.read_text(encoding="utf-8")
    marker = "USE_KERNEL_LIBS = 1\n"
    if systemctrl_text.count(marker) != 1:
        raise RuntimeError("unexpected systemctrl Makefile")
    systemctrl_makefile.write_text(
        systemctrl_text.replace(
            marker,
            marker + "\nLIBDIR = ../lib\nLIBS = -lpspinit\n",
        ),
        encoding="utf-8",
    )


def apply_vitasdk_compatibility(temporary: Path, modern_vitasdk: bool) -> None:
    """Select the original C semantics and SDK-appropriate symbol names.

    GCC 15 defaults to C23, where an empty parameter list means ``(void)``;
    the archived Vita code predates that change.  Two kernel APIs were also
    renamed in vita-headers without changing their NIDs.  These materializer
    edits are therefore build compatibility, not runtime substitutions. The
    symbol substitutions and newlib teardown shim are deliberately excluded
    from the pinned 2020 SDK build, where the original names and runtime are
    present.
    """
    extra = (
        " -std=gnu17 -fcommon"
        " -Wno-error=implicit-function-declaration"
        " -Wno-error=int-conversion"
        " -Wno-error=incompatible-pointer-types"
    )
    for cmake_file in (
        temporary / "kernel/CMakeLists.txt",
        temporary / "user/CMakeLists.txt",
        temporary / "vsh/CMakeLists.txt",
    ):
        text = normalized(cmake_file.read_bytes()).decode("utf-8")
        marker = 'set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS}'
        if text.count(marker) != 1:
            raise RuntimeError(f"unexpected C flags declaration: {cmake_file}")
        text = text.replace(
            marker,
            f'set(CMAKE_C_FLAGS "${{CMAKE_C_FLAGS}}{extra}',
        )

        # Old CMake accepted this helper name; current CMake reserves ``all``.
        text = text.replace(
            "add_custom_target(all\n",
            "add_custom_target(archive_all\n",
        )
        # Current VitaSDK normalized the taiHEN user-stub archive's casing.
        text = text.replace("  taiHEN_stub\n", "  taihen_stub\n")
        cmake_file.write_text(text, encoding="utf-8")

    kernel_cmake = temporary / "kernel/CMakeLists.txt"
    text = kernel_cmake.read_text(encoding="utf-8")
    sysroot_kernel = "  SceSysrootForKernel_stub\n"
    sysroot_driver = "  SceSysrootForDriver_stub\n"
    if text.count(sysroot_kernel) != 1:
        raise RuntimeError("unexpected kernel sysroot link list")
    if sysroot_driver not in text:
        # This API belongs to SceSysrootForDriver in both pinned and current
        # NID databases; the archived CMake list omitted its stub archive.
        text = text.replace(
            sysroot_kernel,
            sysroot_kernel + sysroot_driver,
        )
    kernel_cmake.write_text(text, encoding="utf-8")

    if not modern_vitasdk:
        return

    kernel_main = temporary / "kernel/main.c"
    text = normalized(kernel_main.read_bytes()).decode("utf-8")
    cpu_old = "ksceKernelCpuDcacheWritebackRange"
    cpu_current = "ksceKernelDcacheCleanRangeForL1WBWA"
    if text.count(cpu_old) != 2:
        raise RuntimeError("unexpected legacy dcache API use")
    text = text.replace(cpu_old, cpu_current)

    include_marker = "#include <psp2kern/kernel/sysmem.h>\n"
    if text.count(include_marker) != 1:
        raise RuntimeError("unexpected kernel sysmem include")
    text = text.replace(
        include_marker,
        include_marker + "#include <psp2kern/kernel/sysroot.h>\n",
    )
    kernel_main.write_text(text, encoding="utf-8")

    # Newlib's modern _exit wrapper calls a teardown hook supplied by crt0.o.
    # These SUPRX projects intentionally use -nostartfiles, and the historical
    # newlib linked by Adrenaline had no such call.  A no-op hook therefore
    # preserves the old exit path without pulling in a conflicting Vita crt0.
    for component, target in (
        ("user", "adrenaline_user"),
        ("vsh", "adrenaline_vsh"),
    ):
        compat_source = temporary / component / "vitasdk_compat.c"
        compat_source.write_text(
            "void _free_vita_newlib(void) {\n"
            "}\n",
            encoding="ascii",
        )
        component_cmake = temporary / component / "CMakeLists.txt"
        text = component_cmake.read_text(encoding="utf-8")
        source_marker = f"add_executable({target}\n"
        if text.count(source_marker) != 1:
            raise RuntimeError(f"unexpected {target} source list")
        component_cmake.write_text(
            text.replace(
                source_marker,
                source_marker + "  vitasdk_compat.c\n",
            ),
            encoding="utf-8",
        )


def apply_booter_driver_label_patch(temporary: Path) -> None:
    """Match menu labels to the raw BootInfo driver values.

    Leecherman's source labels raw values 0, 1, 2 as INFERNO, MARCH33,
    NP9660. The PSP booter consumes those values as NP9660, INFERNO,
    MARCH33. shoui520's binary fix changed the pointer order accordingly;
    keep that correction as a separately selectable source patch.
    """
    if not BOOTER_DRIVER_LABEL_PATCH.is_file():
        raise FileNotFoundError(BOOTER_DRIVER_LABEL_PATCH)
    subprocess.run(
        [
            "patch", "--directory", str(temporary), "--strip=1",
            "--fuzz=0", "--no-backup-if-mismatch", "--dry-run", "--input",
            str(BOOTER_DRIVER_LABEL_PATCH),
        ],
        check=True,
    )
    subprocess.run(
        [
            "patch", "--directory", str(temporary), "--strip=1",
            "--fuzz=0", "--no-backup-if-mismatch", "--batch", "--input",
            str(BOOTER_DRIVER_LABEL_PATCH),
        ],
        check=True,
    )


def validate_booter_driver_label_source(temporary: Path, corrected: bool) -> None:
    order = (
        ("NP9660", "INFERNO", "MARCH33")
        if corrected
        else ("INFERNO", "MARCH33", "NP9660")
    )
    expected = (
        'static char *drivers_options[] = { "'
        + '", "'.join(order)
        + '" };'
    )
    menu = (temporary / "user/menu.c").read_text(encoding="utf-8")
    if menu.count(expected) != 1:
        mode = "corrected" if corrected else "original Leecherman"
        raise RuntimeError(
            f"materialized user/menu.c does not contain the {mode} driver order"
        )


def materialize(
    source: Path,
    output: Path,
    booter: Path | None,
    btcnf: Path | None,
    variant: str,
    modern_vitasdk: bool = False,
    fix_booter_driver_labels: bool = True,
) -> None:
    integration = CURRENT if variant == "current" else HISTORICAL
    revision = (integration / "BASE").read_text(encoding="ascii").strip()
    validate_checkout(source, revision)
    if output.exists():
        raise FileExistsError(
            f"refusing to overwrite existing materialization: {output}"
        )
    if booter is not None and not booter.is_file():
        raise FileNotFoundError(booter)
    if btcnf is not None and not btcnf.is_file():
        raise FileNotFoundError(btcnf)

    output_parent = output.parent.resolve()
    output_parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="adrenaline-v7-", dir=output_parent))
    try:
        archive = subprocess.run(
            ["git", "-C", str(source), "archive", revision],
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
            bundle.extractall(temporary, filter="data")

        if variant == "current":
            validate_checkout(
                source,
                (CURRENT / "ANCESTOR").read_text(encoding="ascii").strip(),
            )
            merge_current_overlay(source, temporary)
        else:
            overlay = HISTORICAL / "overlay"
            for source_file in sorted(
                path for path in overlay.rglob("*") if path.is_file()
            ):
                relative = source_file.relative_to(overlay)
                destination = temporary / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_file, destination)

        if fix_booter_driver_labels:
            apply_booter_driver_label_patch(temporary)

        menucolor = bytes.fromhex(
            (HISTORICAL / "menucolor.hex").read_text(encoding="ascii")
        )
        if len(menucolor) != 32:
            raise ValueError("menucolor.hex must decode to exactly 32 bytes")
        (temporary / "menucolor.bin").write_bytes(menucolor)

        if booter is not None:
            shutil.copyfile(booter, temporary / "user/flash0/kd/booter.prx")
        if btcnf is not None:
            shutil.copyfile(btcnf, temporary / "user/flash0/kd/pspbtbnf.bin")

        apply_modern_pspdev_compatibility(temporary)
        apply_vitasdk_compatibility(temporary, modern_vitasdk)
        validate_booter_driver_label_source(
            temporary, fix_booter_driver_labels
        )

        temporary.rename(output)
    except BaseException:
        shutil.rmtree(temporary)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--booter", type=Path)
    parser.add_argument("--btcnf", type=Path)
    parser.add_argument(
        "--variant",
        choices=("current", "historical"),
        default="current",
    )
    parser.add_argument(
        "--modern-vitasdk",
        action="store_true",
        help="apply compatibility substitutions for current VitaSDK",
    )
    parser.add_argument(
        "--original-leecherman-driver-labels",
        action="store_true",
        help=(
            "disable the default Booter driver-label correction and retain "
            "Leecherman's original INFERNO/MARCH33/NP9660 pointer order"
        ),
    )
    args = parser.parse_args()
    materialize(
        args.source.resolve(),
        args.output.resolve(),
        args.booter.resolve() if args.booter else None,
        args.btcnf.resolve() if args.btcnf else None,
        args.variant,
        args.modern_vitasdk,
        not args.original_leecherman_driver_labels,
    )


if __name__ == "__main__":
    main()
