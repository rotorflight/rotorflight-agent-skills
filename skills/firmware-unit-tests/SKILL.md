---
name: firmware-unit-tests
description: Build and run the rotorflight-firmware unit tests (googletest under src/test, `make test`). Use when adding or changing a unit test, when a firmware change touches code that has tests, or when `make test` fails to compile because of the compiler version or a missing BlocksRuntime.
---

# Rotorflight firmware unit tests

The tests are googletest programs in `src/test/unit/*_unittest.cc`, each linked against a few
firmware sources listed in `src/test/Makefile`. They run on the host, not on a flight controller.

## Requirements

- **clang 7 to 18** (`CC_VERSION_CHECK_MIN/MAX` in `src/test/Makefile`). Newer clang is
  refused, and gcc does not work because the makefile passes clang-only flags.
- **BlocksRuntime** (`libblocksruntime-dev` on Debian/Ubuntu).
- Linux, macOS or WSL. Native Windows is not supported.

On Ubuntu 22.04: `sudo apt install clang-14 libblocksruntime-dev`, then pass
`CC=clang-14 CXX=clang++-14` or put `/usr/lib/llvm-14/bin` first on `PATH`.

### Without root

`apt-get download` the packages and unpack them with `dpkg -x` into a private root:

```sh
mkdir -p ~/clang-local && cd ~/clang-local
apt-get download clang-14 libclang-common-14-dev libclang-cpp14 libllvm14 llvm-14-linker-tools \
    libblocksruntime-dev libblocksruntime0 libgc1 libobjc4 libobjc-11-dev libstdc++-11-dev
for f in *.deb; do dpkg -x "$f" root; done

R=~/clang-local/root
export PATH=$R/usr/lib/llvm-14/bin:$PATH
export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu:$R/usr/lib/llvm-14/lib
export LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu
export CPATH=$R/usr/include
```

## Run

From the repository root:

```sh
make test                      # all tests, expanded tests for one target
make test-all                  # all tests, expanded tests for every target
make test_help                 # list the tests
make test_pid_unittest         # one test
make test_clean                # after changing compilers or flags
```

`-k` keeps going after a failing test, so one run reports all failures:
`make -k test CC=clang CXX=clang++`.

From `src/test` you can also run a built test binary directly, for example to shuffle:
`obj/test/pid_unittest/pid_unittest --gtest_shuffle --gtest_repeat=30`. Tests must pass in any
order.

## Writing a test

- Add the test file to `src/test/unit/` and a `<name>_unittest_SRC` entry (plus `_DEFINES` if
  needed) to `src/test/Makefile`.
- Stub what the code under test calls but the test does not link, in an `extern "C"` block in the
  test file. Keep stubs minimal and deterministic.
- Rotorflight has replaced or rewritten many Betaflight modules. A test copied from Betaflight
  usually needs rewriting against the Rotorflight code, not just new stubs.
- CI for pull requests may not run the unit tests. Run them yourself and say in the pull request
  which tests you ran.
