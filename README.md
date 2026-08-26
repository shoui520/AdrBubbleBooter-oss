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

### Isage Adrenaline 8 integration

Isage Adrenaline 8 uses a different configuration layout and PSP boot-mode
numbering. Its modules cannot be mixed with the Leecherman/TheFloW modules.
The compatible Adrenaline source revision is pinned under
`integration/adrenaline-isage/`; check out that revision before building.
This path additionally requires a current PSPDEV and VitaSDK supported by
Isage's build system.

```sh
git clone https://github.com/shoui520/Adrenaline-isage.git \
  /path/to/Adrenaline-isage
git -C /path/to/Adrenaline-isage checkout \
  23a61f9af7b794f474b4351cef6edc3adf93b64f
```

Build the Isage PSP booter with the same locked PSP toolchains used above:

```sh
make -B -C src/psp/booter -j12 \
  PSPDEV="$ADRBUBBLE_PSPDEV_2017" \
  PSP_LAYOUT_LD="$PSPDEV/bin/psp-ld" \
  PSP_HEADER_COMPAT_FLAGS="-D__INTPTR_TYPE__=int -D__INT32_TYPE__='long int'" \
  ADRBUBBLE_PSP_CPPFLAGS=-DADRBUBBLE_ISAGE_CONFIG=1
```

Clone the pinned `libk` revision, then build the two Vita modules with the
Isage layout enabled:

```sh
git clone https://github.com/DaveeFTW/libk.git /path/to/libk
git -C /path/to/libk checkout 5aa300ce6c3c72c91fc417bd01df298ea6410044

env VITASDK="$ADRBUBBLE_VITASDK_2017_V481" cmake \
  -S . -B build/isage-modules \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_MAKE_PROGRAM=/usr/bin/make \
  -DADRBUBBLE_ISAGE_CONFIG=ON \
  -DADRBUBBLE_MAKE_FSELF=/path/to/vita-toolchain-25d343b-build/src/vita-make-fself \
  -DADRBUBBLE_LEGACY_MAKE_FSELF=/path/to/vita-toolchain-25d343b-build/src/vita-make-fself \
  -DADRBUBBLE_ELF_CREATE="$ADRBUBBLE_VITASDK_2017/bin/vita-elf-create" \
  -DADRBUBBLE_ADR_ELF_CREATE="$ADRBUBBLE_VITASDK_2020/bin/vita-elf-create" \
  -DADRBUBBLE_LIBK_SOURCE=/path/to/libk \
  -DCMAKE_C_FLAGS="-I$ADRBUBBLE_TAIHEN_06/include" \
  -DCMAKE_EXE_LINKER_FLAGS="-L$ADRBUBBLE_TAIHEN_06/lib"

env VITASDK="$ADRBUBBLE_VITASDK_2017_V481" cmake \
  --build build/isage-modules --parallel 12 \
  --target adrbubblebooter.suprx bootconv.suprx
```

Copy `src/psp/booter/booter.prx` into the pinned Isage checkout before its CEF
build. Configure that build through CMake so it fetches the exact
`psp-cfw-sdk` revision pinned by Isage; the legacy CEF Makefile uses whatever
headers happen to be installed globally and is not suitable for this build.
The CEF build generates its own `pspbtbnf.bin`; do not substitute the
Leecherman version. Then pass both Vita modules to the Isage Vita build:

```sh
mkdir -p /path/to/Adrenaline-isage/user/flash0/kd
cp src/psp/booter/booter.prx \
  /path/to/Adrenaline-isage/user/flash0/kd/booter.prx

cmake -S /path/to/Adrenaline-isage/cef \
  -B /path/to/Adrenaline-isage-cef-build \
  -DCMAKE_BUILD_TYPE=Release
cmake --build /path/to/Adrenaline-isage-cef-build --parallel 12

env VITASDK=/path/to/current-vitasdk cmake \
  -S /path/to/Adrenaline-isage -B /path/to/Adrenaline-isage-build \
  -DCMAKE_BUILD_TYPE=Release \
  -DADRBUBBLEBOOTER_MODULE="$PWD/build/isage-modules/src/vita/adrbubblebooter/adrbubblebooter.suprx" \
  -DBOOTCONV_MODULE="$PWD/build/isage-modules/src/vita/bootconv/bootconv.suprx"

env VITASDK=/path/to/current-vitasdk cmake \
  --build /path/to/Adrenaline-isage-build --parallel 12
```

The resulting Isage VPK is
`/path/to/Adrenaline-isage-build/bubble/Adrenaline.vpk`. Omitting
`ADRBUBBLE_ISAGE_CONFIG` keeps the original Leecherman/TheFloW ABI; the
aggregate `build_stack.py` commands above deliberately use that default.

All distributable modules and generated data are placed under the selected
work directory's `dist/` directory. `dist/manifest.json` records the size and
SHA-256 identity of every output and every tool used for the build.
