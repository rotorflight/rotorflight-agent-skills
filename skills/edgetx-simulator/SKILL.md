---
name: edgetx-simulator
description: Run the Rotorflight EdgeTX Lua suite (rotorflight-lua-edgetx-suite) in the EdgeTX Companion simulator, feed it simulated telemetry and take screenshots. Use when checking a UI, dashboard, theme or telemetry change in the EdgeTX suite, or when a pull request needs simulator screenshots.
---

# EdgeTX simulator

The suite's `DEVELOPMENT.md` is the source of truth ("The `simulator/` folder", "Running it",
"Sensor tool"). Read it first; this skill adds the steps an agent needs to do the same without
VS Code.

## Setup

1. Install [EdgeTX Companion](https://github.com/EdgeTX/edgetx/releases) (2.11 or later). The
   simulator is `simulator.exe` in Companion's `bin` folder on Windows, and the `simulator` binary
   beside Companion on Linux and macOS. Companion's installer accepts `/S` for a silent install.
2. The simulator needs a Companion profile. Start Companion once and create a radio profile
   for the target radio, or on Windows write it directly:
   `HKCU\Software\EdgeTX\Companion <version>\Profiles\profile0` with `Name`,
   `fwType` (for example `edgetx-tx16smk3-en`) and `sdPath`.
3. In VS Code, set `rfsuite.simulatorPath` in the user settings to the simulator executable
   (`DEVELOPMENT.md`, "Simulator path").

## Deploy and start

The checked-in `simulator/` folder is a complete SD card root (radio settings and one model).
Deploying copies `src/` into it as `SCRIPTS/`, `WIDGETS/` and `SOUNDS/`.

- VS Code: run `RFSuite: Deploy + Run Simulator (TX16S MK3)` (or the TX16S or TX15 variant).
- Without VS Code (Windows), deploy and start the simulator the way the tasks do:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .vscode\scripts\deploy-rfsuite-demo.ps1
& <simulator> --radio edgetx-tx16smk3 --start-with sd --sd-path <suite>\simulator
```

Radio targets: `edgetx-tx16smk3`, `edgetx-tx16s`, `edgetx-tx15`. Check the screen at the
smallest resolution you support, not only on the TX16S.

Screenshots: the simulator has a screenshot button, and the window can be captured with the OS
screenshot tools. Add them to the pull request for any visible change.

## Telemetry without a flight controller

`bin/sensors/` is a GUI that writes per-sensor Lua files into the simulator target (fixed values,
sliders, random variance). Start it with the `Sensors: Run Tool` task. For scripted tests, write
the sensor files yourself in the same format.

- The simulator's `model1.yml` defines some sensors (current, capacity, battery %) that override
  the simulated sensor files.
- The suite reads the sensor files once per tick, so a sensor read late can show a stale value.

## Lua checks without the simulator

The `bin/` harnesses run with plain `lua5.3`, as in CI (`.github/workflows/`).
`bin/accounting/` gates every pull request on instruction counts
(`lua5.3 bin/accounting/measure.lua --check`); see its README. On Windows,
`io.popen("ls")`, `mkdir -p` and `os.rename` behave differently, so a few harnesses need a shim
or WSL; compare a failing harness against `master` before blaming your change.

## Afterwards

The simulator writes to `simulator/MODELS` and `simulator/RADIO` (and `radio.yml` carries a
checksum: set `manuallyEdited: 1` if you edit it by hand). Restore them with
`git checkout -- simulator/MODELS simulator/RADIO` before committing.
