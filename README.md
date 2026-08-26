# AdrBubbleBooter OSS

AdrBubbleBooter OSS is an open-source implementation of the complete
AdrBubbleBooter stack used by Adrenaline Bubble Manager to launch PSP and PS1
games directly from Vita LiveArea bubbles. It builds the shared Vita modules,
the per-bubble EBOOT, the PSP-side booter, and the required Adrenaline modules.

By default, the build process will include my menu driver label fix, which was a genuine problem in LMAN's original AdrBubbleBooter. 

## Build instructions

Build on x86-64 Linux or WSL with Git, Python 3, CMake 3.10 or newer, GNU Make,
GNU Patch, a host C compiler, and network access for the pinned source
checkouts. The build uses `-j12` throughout.

The complete stack depends on several specific SDK generations. Extract or
install each one into a separate directory:

| Environment variable | Required contents |
| --- | --- |
| `PSPDEV` | A current PSPDEV installation containing `psp-packer`; its binutils 2.44 `psp-ld` is used for final PRX layout. |
| `ADRBUBBLE_PSPDEV_2017` | PSP GCC 4.9.3, binutils 2.22 assembler, and `psp-fixup-imports`/`psp-prxgen` from PSPSDK commit `024abb63f27d5a9edd3b7a3187529a4b9c97bd96`. Its PSP headers and libraries may point to the current PSPDEV tree. |
| `ADRBUBBLE_VITASDK_2017` | VitaSDK `master-linux-v276`, GCC 6.2.0. The archive `vitasdk-x86_64-linux-gnu-2017-04-09_17-29-08.tar.bz2` has SHA-256 `ed294afa52e4931324ae46ccfea09b8f216208bd1f16bbd4dd889f9b99c7b3cc`. |
| `ADRBUBBLE_VITASDK_2017_V481` | VitaSDK `master-linux-v481`, GCC 7.2.0. The archive `vitasdk-x86_64-linux-gnu-2017-09-10_21-50-27.tar.bz2` has SHA-256 `819b8e28b099337b171847adeb556c88031c4341c1ce062f30d55065d5222460`. |
| `ADRBUBBLE_VITASDK_2020` | VitaSDK `master-linux-v1224`, GCC 10.1.0. The archive `vitasdk-x86_64-linux-gnu-2020-09-22_14-38-25.tar.bz2` has SHA-256 `348faa185fe37a6d87cfd08fc8cca5d4a18f51ecb6a11ab06ee97c39e7b077b6`. |
| `ADRBUBBLE_TAIHEN_06` | taiHEN 0.6 with `include/taihen.h` and `lib/libtaihen_stub.a`. The release archive has SHA-256 `ceae5ae46244cb5adb37c68a140f5f7b15383705e3f366437e5f24efda9f4bc5`. |
| `PSP2_SDK_BIN` | Sony PSP2 SDK 3.5.0 host tools containing `psp2cgc.exe` build 13276 and the matching `psp2shaderperf.exe`. Build 13284 is not byte-identical and is rejected. |

The builder checks the SHA-256 identity of every loader-sensitive compiler,
linker, converter, packer, taiHEN input, and shader tool before creating the
work directory. A mismatch stops the build and reports the expected file.

The Vita modules also require a patched April 2017 `vita-make-fself`. Build it
from the exact historical source as follows, replacing `/path/to` with local
paths:

```sh
git clone https://github.com/vitasdk/vita-toolchain.git /path/to/vita-toolchain-25d343b
git -C /path/to/vita-toolchain-25d343b checkout 25d343b448d4d4f9883b6f38e44a4e0ac8355865
git -C /path/to/vita-toolchain-25d343b apply /path/to/AdrBubbleBooter-oss/toolchain/patches/vita-toolchain-25d343b-explicit-module-nid.patch
cmake -S /path/to/vita-toolchain-25d343b -B /path/to/vita-toolchain-25d343b-build -DCMAKE_BUILD_TYPE=Release
cmake --build /path/to/vita-toolchain-25d343b-build --target vita-make-fself --parallel 12
sha256sum /path/to/vita-toolchain-25d343b-build/src/vita-make-fself
```

The resulting executable must have SHA-256
`1d81600aa41663c4290d9486d59b9da4f372f02eba43010f1b9c9b668e6e0601`.

Set the SDK paths, add current PSPDEV to `PATH`, then run the aggregate build
from the repository root:

```sh
export PSPDEV=/path/to/current-pspdev
export PATH="$PSPDEV/bin:$PATH"
export ADRBUBBLE_PSPDEV_2017=/path/to/pspdev-2017-compat
export ADRBUBBLE_VITASDK_2017=/path/to/vitasdk-v276
export ADRBUBBLE_VITASDK_2017_V481=/path/to/vitasdk-v481
export ADRBUBBLE_VITASDK_2020=/path/to/vitasdk-v1224
export ADRBUBBLE_TAIHEN_06=/path/to/taihen-0.6
export PSP2_SDK_BIN="/path/to/PSVITA/sdk/host_tools/bin"

python3 tools/build_stack.py \
  --variant current \
  --legacy-make-fself /path/to/vita-toolchain-25d343b-build/src/vita-make-fself \
  --work-dir build/full-current \
  --jobs 12
```

The work directory must not already exist. If source paths are omitted, the
builder clones and exports the revisions pinned under `integration/`; it never
builds from an uncommitted working tree. An offline build can supply the local
Git checkouts explicitly:

```sh
python3 tools/build_stack.py \
  --variant current \
  --adrenaline-source /path/to/Adrenaline \
  --vita2d-source /path/to/vita2dlib \
  --libk-source /path/to/libk \
  --legacy-make-fself /path/to/vita-toolchain-25d343b-build/src/vita-make-fself \
  --work-dir build/full-current \
  --jobs 12
```

Both commands build and validate the complete stack. Add `--package-abm` to
also clone the pinned ABM source and create an installable VPK. For an offline
package build, additionally pass `--abm-source /path/to/AdrenalineBubbleManager`.
The package is written to:

```text
build/full-current/dist/abm/AdrenalineBubbleManager_6.21_AdrBubbleBooter-oss.vpk
```

Use `--variant historical` to build the original Adrenaline v7 integration.
The corrected `NP9660`, `INFERNO`, `MARCH33` driver-label order is enabled by
default in both variants; add `--original-leecherman-driver-labels` to reproduce
the original Leecherman label order instead.

All distributable modules and generated data are placed under the selected
work directory's `dist/` directory. `dist/manifest.json` records the size and
SHA-256 identity of every output and every tool used for the build.
