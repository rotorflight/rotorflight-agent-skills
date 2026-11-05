---
name: firmware-toolchain
description: Install the Arm GCC toolchain for rotorflight-firmware with its makefile and build a flight controller target. Use when a firmware build fails with "arm-none-eabi-gcc not in the PATH" or a wrong GCC version, when setting up a fresh clone, or when asked to build or flash firmware on Linux, macOS, WSL or Windows.
---

# Rotorflight firmware toolchain

The firmware makefile installs and checks its own compiler. Do not install a distribution
`gcc-arm-none-eabi`: the build requires the exact version in `make/tools.mk`
(`GCC_REQUIRED_VERSION`, currently 9.3.1 from `gcc-arm-none-eabi-9-2020-q2-update`) and
stops with an error on any other version.

## Install

From the root of a `rotorflight-firmware` clone:

```sh
make arm_sdk_install      # downloads to downloads/, extracts to tools/
make arm_sdk_version      # prints the compiler version
```

- Needs GNU make, curl, and `tar`/`bzip2` (Linux, macOS) or `unzip` (Windows).
- The SDK lands in `tools/gcc-arm-none-eabi-9-2020-q2-update` inside the clone. Each clone and
  each git worktree has its own `tools/`. To share one install, pass
  `ARM_SDK_DIR=<absolute path to an existing SDK>` to every `make` call, or set it in
  `make/local.mk` (git-ignored).
- `make help` lists the other targets. `make arm_sdk_clean` removes the SDK.
- The SDK is per host OS: a Windows SDK in `tools/` does not run in WSL, and the reverse.
  In WSL install a second one outside the Windows clone and point `ARM_SDK_DIR` at it.

## Build

```sh
make STM32F7X2            # one unified target: STM32F405, STM32F411, STM32F7X2, STM32F745, STM32G47X, STM32H743
make targets              # list all valid targets
make STM32F7X2 DEBUG=GDB  # -Og with debug symbols, for a debugger (see the jlink-debug skill)
make STM32F7X2 DEBUG=INFO # normal optimisation, with debug symbols
```

Output: `obj/rotorflight_<version>_<TARGET>.hex` and `.bin`; the ELF with symbols is
`obj/main/rotorflight_<TARGET>.elf`.

The unified targets carry no board configuration. A board's pin map and defaults come from
[rotorflight-targets](https://github.com/rotorflight/rotorflight-targets) and are applied by
the Configurator when flashing, or by pasting the board config into the CLI.

Before pushing, `make pre-push` cleans and builds a few representative targets with `-Werror`.

## Platform notes

| Platform | Notes |
| --- | --- |
| Linux, macOS | Works as documented. |
| WSL2 | Works as on Linux. Keep the clone on the Linux file system for speed. |
| WSL1 | Works, but slowly on `/mnt/c`. |
| Windows (Git Bash, MSYS2) | Works with GNU make on the path. If the build fails in `ccache` because `USERPROFILE` is not set, pass `CCACHE=`. Pass an absolute `ARM_SDK_DIR` when building from a worktree. |

When an agent calls `wsl` from Git Bash, set `MSYS_NO_PATHCONV=1` and put the commands in a
script file: Git Bash rewrites `/mnt/...` arguments and mangles inline quoting. Output from
`wsl` can arrive interleaved; redirect it to a file and read the file.

## Flash

- **Configurator:** load the `.hex` with "Load firmware [Local]". This also applies the board
  configuration. Prefer this for a user's board.
- **DFU:** `make dfu_flash TARGET=STM32F7X2` (needs `dfu-util` and the board in DFU mode, for
  example after the `bl` CLI command). `make dfu_erase_and_flash TARGET=...` mass-erases first,
  which also wipes the configuration: back it up with `diff all` in the CLI before.
- **Debugger:** see the jlink-debug skill.
