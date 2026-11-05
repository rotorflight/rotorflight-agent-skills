---
name: fc-config-backup
description: Back up and restore the configuration of a real Rotorflight flight controller over the CLI on its USB serial port (diff all, dump all, status, resources, gyro registers), with scripts/fc_config.py. Use before flashing firmware, before a full chip erase or DFU flash, before swapping hardware on a board, when asked to save or restore an FC's settings, or to snapshot a board's state for a hardware test.
---

# Flight controller config backup

The CLI is the source of truth: `diff all` prints every setting that differs from the board
defaults as a replayable script, and `dump all` prints every setting. Both are implemented in
`src/main/cli/cli.c` of rotorflight-firmware. This skill adds a script that captures them
reliably and replays a diff with error checking.

## Requirements

- Python 3.8+ and `pyserial`.
- The FC on USB. Its port is the STM32 virtual COM port (USB `0483:5740`): `COMx` on Windows,
  `/dev/ttyACMx` on Linux, `/dev/cu.usbmodem*` on macOS.
- **Close the Rotorflight Configurator** (or disconnect it). Only one program can hold the port,
  and a connected Configurator also answers MSP on it.

## Back up

```sh
python scripts/fc_config.py backup <PORT> <LABEL> [--out <DIR>]
```

Read-only. It enters the CLI, runs the commands, and leaves with `exit`, which reboots the FC
without saving. It writes `<DIR>/<LABEL>_<timestamp>/` (default `DIR` is `./backups`):

| File | Content |
| --- | --- |
| `diff_all.txt` | Restore file. Ends with `save`. |
| `dump_all.txt` | Every setting, defaults included. Use it to compare two boards or firmware versions, and as a fallback when a diff no longer applies. |
| `info.txt` | `version`, `status`, `resource show all`, `dma show`, `timer show`, `gyroregisters`, `tasks`, `get gyro_`/`acc_`/`align`. |
| `transcript.txt` | The raw CLI output. Check it first when a file looks short. |

Check afterwards: `diff_all.txt` starts with `# version` and ends with `save` (the script refuses
otherwise), and the `version` and `status` in `info.txt` name the board and firmware you expect.
Keep the firmware version from `# version` with the backup: a diff is restored onto the same
major version.

The files contain the board's `mcu_id`. Do not commit them to a public repository.

## Restore

```sh
python scripts/fc_config.py restore <PORT> <DIR>/<LABEL>_<timestamp>/diff_all.txt
```

It replays the diff line by line. If the FC answers any line with `###ERROR`, it leaves with
`exit`, saves nothing, and lists the rejected lines. Otherwise it sends `save` and the FC
reboots. Run a fresh `backup` afterwards and compare its `diff_all.txt` with the original.

`defaults nosave` at the top of a diff resets the config in RAM to the board defaults; it
does not reboot.

## Pitfalls

- **Board config first.** `diff all` only holds what differs from the board's defaults, so a
  board running its factory config has almost nothing in it: no `resource` lines, no gyro bus.
  The pin map comes from `configs/<MANUFACTURER>-<BOARD>.config` in
  [rotorflight-targets](https://github.com/rotorflight/rotorflight-targets). When a flash
  leaves it out (a DFU flash of a bare `.hex`, a local `.hex` in the Configurator), the
  arming disable flags in `status` include `NOGYRO`. Apply the board config with
  `restore`: append a `save` line to a copy of the `.config` file first.
- **`defaults nosave` removes a CLI-applied board config.** A diff begins with it. If the board
  config was applied in the CLI rather than as custom defaults, replaying a diff that has
  no `resource` lines leaves the board without a pin map again. Then apply the board config
  first and replay only the `set` lines and other settings from the diff, without
  `defaults nosave`.
- **`gyroregisters` hangs the FC when no gyro was detected:** it reads over an unconfigured SPI
  device. The FC stops answering until a USB replug. The script runs `status` first and skips
  `gyroregisters` on `NOGYRO`. When typing commands by hand, check `status` first.
- **Restoring onto another firmware version.** Renamed or removed settings show up as
  `###ERROR IN set: INVALID NAME`. Edit those lines in a copy of the diff, using `dump_all.txt`
  of the new firmware to find the new names, and restore the copy.
- **Restoring onto another board.** `board_name`, `mcu_id` and `signature` in the diff belong
  to the original board. Remove them from a copy before restoring it to another board.
- **The port disappears.** `exit` and `save` reboot the FC; the USB port drops and comes back
  after about 2 s. The script expects this. Wait for the port before the next command.
- **No prompt.** `no CLI prompt` means a wrong port, the Configurator still connected, or the FC
  still booting.
- **Flash and SD card.** Blackbox logs on onboard flash or SD card are not part of the config.
  Download them in the Configurator before a full chip erase.
