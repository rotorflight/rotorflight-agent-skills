---
name: firmware-sitl
description: Build and run Rotorflight firmware as a host process (SITL, TARGET=SITL) and talk to it over MSP, the CLI, CRSF or UDP. Use when a firmware change needs testing without a flight controller, when reproducing a bug in the PID, governor, mixer or MSP code on a PC, or when connecting the Configurator or a flight dynamics model to a simulated FC.
---

# Rotorflight SITL

`TARGET=SITL` builds the firmware above the hardware drivers (scheduler, filters, PID,
governor, mixer, rescue, MSP, CLI) as a host executable. A flight dynamics model (FDM) replaces
the sensors and outputs.

> Full heli SITL support (Windows build, lockstep, CRSF, ESC telemetry, file-backed blackbox,
> smoke test) is in [rotorflight-firmware#596](https://github.com/rotorflight/rotorflight-firmware/pull/596).
> Until it merges, `master` has only the older Betaflight SITL, and the reference is
> `src/main/target/SITL/README.md` **on the branch you build**. Read it first; it is the source
> of truth for ports, packet layouts and options.

## Build and run

```sh
make arm_sdk_install       # once: the makefile checks for the Arm SDK even for SITL
make TARGET=SITL           # -> obj/main/rotorflight_SITL.elf
./obj/main/rotorflight_SITL.elf   # first start writes eeprom.bin with defaults and exits
./obj/main/rotorflight_SITL.elf   # second start stays up
```

- Linux or WSL: needs gcc and make. Native Windows (#596): `make mingw_sdk_install` once, then
  `make TARGET=SITL` from an MSYS2 shell. The output keeps the `.elf` name but is a Windows
  executable; start it from Python `subprocess` (PowerShell `Start-Process` refuses `.elf`), or
  copy it to `.exe`.
- The configuration lives in `eeprom.bin` in the working directory. A CLI `save` ends the process;
  start it again. Use a separate working directory per experiment.

## Interfaces

| Direction | Address | Content |
| --- | --- | --- |
| FDM -> FC | `udp://127.0.0.1:9003` | `fdm_packet` (gyro, accel, attitude, ...) |
| FC -> FDM | `udp://127.0.0.1:9002` | `servo_packet` (motors, servos) |
| UARTn | `tcp://127.0.0.1:576n` | one client per port; UART1/UART2 carry MSP and the CLI |

The packet structs are in `src/main/target/SITL/target.h`. Point the Configurator at
`tcp://127.0.0.1:5761` (or 5762). Without an FDM feeding packets the gyro reads zero and the FC
will not arm.

## Checking a change

- `python3 src/utils/sitl-smoke-test.py obj/main/rotorflight_SITL.elf` (#596) checks first
  start, MSP identity, CLI save, arming, motor output and disarm. Run it after any SITL change.
- For a scripted test, drive MSP over TCP: send `MSP_SET_RAW_RC` for sticks, read state with
  `MSP_STATUS`, `MSP_MOTOR`, `MSP_SERVO`. Send FDM packets faster than 50 Hz from one sender.
- The governor is feature-gated: `feature GOVERNOR` as well as a `gov_mode`.
- Blackbox (#596) writes to the simulated flash chip `blackbox_flash.bin`. Download the log with
  the Configurator's Blackbox tab, then decode it with the blackbox-decode skill.

## Pitfalls

- WSL1 sleeps are coarse (~0.7 ms): run with `SITL_LOOP_SLEEP_US=0`.
- Windows `nanosleep` below 1 ms returns at once; short delays are spun, so expect one busy core.
- A store written by a different build is replaced with defaults on start.
