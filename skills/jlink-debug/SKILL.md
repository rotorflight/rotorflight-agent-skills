---
name: jlink-debug
description: Debug Rotorflight firmware on a real flight controller over SWD with a SEGGER J-Link (J-Link GDB Server, arm-none-eabi-gdb, VS Code Cortex-Debug, RTT/SWO). Use when a bug only shows on hardware, for hard faults, lockups, boot loops, peripheral or DMA problems, or when asked to set breakpoints, inspect variables or flash with a J-Link.
---

# J-Link debugging

## Safety first

When the CPU halts, PWM and DShot outputs freeze or stop. **Remove the rotor blades and
disconnect the motor/ESC power** before debugging a board that is installed in a helicopter.
Servos can move to their limits on reset. Say this to the user before the first halt.

## Requirements

- SEGGER J-Link (any model, or an ST-Link reflashed to J-Link firmware) and the
  [J-Link Software Pack](https://www.segger.com/downloads/jlink/), which provides
  `JLinkGDBServer` (`JLinkGDBServerCL.exe` on Windows), `JLinkExe` and `JLinkRTTViewer`.
- `arm-none-eabi-gdb` from the firmware's own SDK (`tools/gcc-arm-none-eabi-9-2020-q2-update/bin`,
  see the firmware-toolchain skill).
- Wiring: SWDIO, SWCLK, GND, and VTref to the board's 3.3 V. Power the board from USB or the
  battery; the J-Link does not power it by default. Most Rotorflight boards bring SWD out on pads,
  not a header.

## Build for debugging

```sh
make STM32F7X2 DEBUG=GDB          # -Og, symbols: best for stepping
make STM32F7X2 DEBUG=INFO         # -O2 with symbols: when -Og changes timing or does not fit
```

The ELF is `obj/main/rotorflight_<TARGET>.elf`. Use the ELF that matches the flashed image;
symbols from another build are wrong without warning.

Optional flags: `DEBUG_HARDFAULTS=F7` (`G4`, `H7` for those MCUs; not available on F4) installs a fault handler that keeps registers
for inspection; `USE_PRINTF=ITM` sends `printf` output on SWO channel 0.

## Device names

| Target | J-Link `-device` (check the MCU marking on the board) |
| --- | --- |
| STM32F405 | `STM32F405RG` |
| STM32F411 | `STM32F411CE` |
| STM32F7X2 | `STM32F722RE` (or `STM32F722VE`, `STM32F722RC`) |
| STM32F745 | `STM32F745VG` |
| STM32G47X | `STM32G474CE` (or `STM32G474RE`) |
| STM32H743 | `STM32H743VI` |

## Command line

Terminal 1, the server:

```sh
JLinkGDBServer -device STM32F722RE -if SWD -speed 4000 -nogui -port 2331
```

Terminal 2, GDB:

```sh
arm-none-eabi-gdb obj/main/rotorflight_STM32F7X2.elf
(gdb) target remote :2331
(gdb) monitor reset
(gdb) load                 # flash this ELF; skip to debug what is already on the board
(gdb) monitor reset
(gdb) break pidController
(gdb) continue
```

Useful commands: `bt`, `info registers`, `p <variable>`, `x/16wx 0x20000000`,
`monitor halt`, `monitor go`, `watch <var>` (hardware watchpoints: 4 on Cortex-M4/M7).

To attach to a running board without resetting it, start the server with `-noreset` (newer
packs: `-nohalt`), connect, and do not `load`.

`load` programs only the firmware sections of the ELF. The configuration sector is normally kept,
but back up with `diff all` in the CLI first. A unified target flashed from an ELF without the
board configuration boots with defaults if the configuration is lost.

## VS Code (Cortex-Debug)

`.vscode/launch.json` in the firmware clone:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "J-Link STM32F7X2",
      "type": "cortex-debug",
      "request": "launch",
      "servertype": "jlink",
      "device": "STM32F722RE",
      "interface": "swd",
      "cwd": "${workspaceFolder}",
      "executable": "${workspaceFolder}/obj/main/rotorflight_STM32F7X2.elf",
      "armToolchainPath": "${workspaceFolder}/tools/gcc-arm-none-eabi-9-2020-q2-update/bin",
      "runToEntryPoint": "main",
      "svdFile": "${workspaceFolder}/STM32F722.svd"
    }
  ]
}
```

Use `"request": "attach"` to inspect a running board. The SVD file (register view) comes from
ST or the `cmsis-svd` collection; it is not in the repository.

## Hard faults and lockups

1. Attach without reset, `monitor halt`, `bt`.
2. In a fault handler: read `SCB->CFSR`, `SCB->HFSR`, `SCB->MMFAR`, `SCB->BFAR`
   (`p/x *(uint32_t*)0xE000ED28` for CFSR), and the stacked PC/LR from the exception frame
   (`x/8wx $sp`; PC is the 7th word).
3. `info symbol <pc>` or `arm-none-eabi-addr2line -e <elf> <pc>` names the faulting function.
4. Boot loops: break on `systemReset` and look at `bt` and its `reason` argument; the persistent
   objects in `drivers/persistent.c` survive the reset.

## Live data without halting

- **RTT:** `JLinkRTTViewer` or `JLinkRTTClient` with the server running. Needs a SEGGER RTT
  buffer in the firmware, which Rotorflight does not ship; add it only for a local experiment.
- **SWO/ITM:** build with `USE_PRINTF=ITM`, then `JLinkSWOViewer -device <device> -itmport 0`.
  The SWO pin (PB3) must be wired and not used by the board for something else.
- The firmware's own `debug_mode` plus blackbox is often the better choice for timing-sensitive
  problems; the debugger stops the loop.
