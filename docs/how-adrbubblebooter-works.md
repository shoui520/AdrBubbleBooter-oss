# How AdrBubbleBooter works

Adrenaline normally starts as one Vita application and then lets the user pick
a game inside its PSP environment. AdrBubbleBooter lets each game have its own
LiveArea bubble while still using that shared Adrenaline installation.

Adrenaline Bubble Manager creates a small Vita application for each game. The
application contains a per-bubble EBOOT and `data/boot.bin`, while the shared
runtime modules remain under `ux0:app/PSPEMUCFW/sce_module`. `boot.bin` is the
contract between the Vita and PSP sides: it stores the selected content path,
ISO driver, executable choice, save-state request, and per-bubble options in a
fixed 0x140-byte structure.

Launching a bubble follows this path:

```text
LiveArea bubble
  -> per-bubble EBOOT
  -> Adrenaline kernel and Vita user modules
  -> Sony PSP emulator
  -> flash0:/kd/booter.prx
  -> selected PSP, PS1, or ISO content
```

The per-bubble EBOOT checks that Adrenaline is installed, then loads
`adrenaline_kernel.skprx`. When the Sony PSP emulator process starts, the
kernel module loads the rest of the shared stack:

- `bootconv.suprx` converts the old `boot.inf` format into `boot.bin` for
  bubbles created by older versions.
- `adrbubblebooter.suprx` upgrades older `boot.bin` layouts, selects global or
  per-bubble settings, and keeps Adrenaline's memory-stick location consistent
  with the device containing the game.
- `adrenaline_user.suprx` applies the bubble settings, provides the modified
  PSP flash files, and asks the PSP custom firmware to restart through the
  booter.

On the PSP side, `booter.prx` reads the same `boot.bin`, converts the Vita path
to the emulated `ms0:` path, identifies ISO, PSP PBP, NPDRM PBP, or PS1 PBP
content, and starts it with the required driver, runlevel, and load-exec
parameters. The VSH module supplies the matching Adrenaline menu behavior.

These parts are one compatibility stack rather than interchangeable plugins.
The shared structure offsets, module identities, imports, exports, and PSP
runlevels must remain consistent across every layer. That is why the build
uses pinned toolchains and validates the completed modules before producing an
ABM package.
