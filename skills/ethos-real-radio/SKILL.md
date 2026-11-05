---
name: ethos-real-radio
description: Drive a real FrSky Ethos radio over USB from an agent (keys, touch, screenshots, file transfer) with radio_remote.py from FrSkyRC/ethos-tools, to deploy and debug the Rotorflight Ethos suite on hardware. Use when a suite change must be checked on a physical radio, with a connected flight controller, or when a bug does not reproduce in the simulator.
---

# Ethos real radio

FrSky's documentation is the source of truth:
<https://ethos-lua-doc.frsky-rc.com/tools/ai-agents/#driving-a-real-radio>. The client is
`simulation/radio_remote.py` in [FrSkyRC/ethos-tools](https://github.com/FrSkyRC/ethos-tools);
its protocol is described in `radio_remote.md` next to it.

## Safety

- The radio may be bound to a powered helicopter. **Remove the blades or disconnect the motor**
  before driving a radio that talks to a live model. Never send stick, pot or switch commands:
  the protocol defines them but they are untested on real radios.
- Ask the user before writing or deleting files on the radio, and never touch anything outside
  `/scripts/rfsuite/` unless asked.

## Requirements

- Ethos 26 nightly from 2026-10-16 or later (earlier builds have no USB remote control).
- Python 3.8+ with `pip install pyserial hidapi` (`hidapi` only for the `mode` command).
- The radio in **Serial** USB mode (choose Serial when plugging in, or `mode serial`).

## Start

```sh
python radio_remote.py mode serial
python radio_remote.py --serve &      # port 8766; the simulator uses 8765
python radio_remote.py status
```

The server finds the radio by USB VID/PID and waits (60 s, `--accept-timeout`) for the
connection to be **accepted on the radio's screen**. The agent cannot do this: tell the user to
accept, then check `status`. Every new serial connection asks again, so keep one server running.

On Windows the port must be opened with overlapped I/O, as pyserial does; other serial libraries
get `HELLO` through and then time out.

## Commands

| Command | Effect |
| --- | --- |
| `screenshot [out.png] [main\|top\|glasses]` | Save a display as PNG |
| `press KEY [holdMs]` | `SYS` `MDL` `DISP` `PAGE` `RTN` `ENTER` `UP` `DOWN` `LEFT` `RIGHT`, trims `T1+` ... `T6-` |
| `tap X Y`, `longpress X Y`, `swipe X1 Y1 X2 Y2`, `wheel N` | Touch and rotary encoder |
| `ls PATH`, `read PATH [out]`, `write SRC PATH`, `rm PATH` | Radio storage, without switching to storage mode |
| `trims`, `load PATH`, `text STRING`, `fswitch I` | Trims, load a model, type text, function switch |
| `quit` | Stop the server |

## Deploy and test the suite

1. Back up what is on the radio: `ls /scripts/rfsuite` and `read` anything the user changed
   (for example preferences under the suite's user data).
2. Build the deployable tree with the suite's deploy script (see the ethos-simulator skill), then
   `write` the changed files to `/scripts/rfsuite/...`. Delete stale `*.luac` files for the
   changed modules with `rm`.
3. Scripts load at boot: ask the user to restart the radio, then reconnect (and accept again).
4. Open the app (`SYS`, `PAGE` to System page 2, **Rotorflight**) and screenshot each step.
5. With a flight controller connected, the pages show real MSP data instead of the simulator
   responses. Treat writes to the FC (save, ESC settings) as changes to the user's model and ask
   first.

## Not available on a real radio

Macros and model JSON are simulator-only. Lua errors are not readable over this protocol; look
at the screen, or reproduce in the simulator and use its `log`.
