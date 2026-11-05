#!/usr/bin/env python3
"""
Back up and restore the configuration of a Rotorflight flight controller over
the CLI on its USB serial port.

  backup  PORT LABEL [--out DIR]   read-only, ends with 'exit' (reboot, nothing saved)
  restore PORT FILE                replays a diff_all.txt and ends with 'save'

A backup writes DIR/<LABEL>_<YYYYmmdd_HHMMSS>/ (DIR defaults to ./backups):
  diff_all.txt   restore file: everything that differs from the board defaults
  dump_all.txt   every setting, defaults included (reference, diffing, fallback)
  info.txt       version, status, resource, dma, timer, gyroregisters, tasks
  transcript.txt the raw CLI output

Close the Configurator first: only one program can open the port.
Requires Python 3.8+ and pyserial.
"""

import argparse
import os
import sys
import time
from datetime import datetime

try:
    import serial
except ImportError:
    sys.exit("pyserial missing: pip install pyserial")

INFO_CMDS = ["version", "status", "resource show all", "dma show", "timer show",
             "gyroregisters", "tasks", "get gyro_", "get acc_", "get align"]

# 'gyroregisters' reads the gyro over SPI without checking that one was
# detected. With NOGYRO it hangs the FC until a USB replug, so skip it then.
SKIP_WITHOUT_GYRO = {"gyroregisters"}


def read_until_prompt(ser, timeout, idle=0.6):
    """Collect output until it ends with the '# ' prompt and the line goes quiet.
    The idle wait matters: dump output has '# ' comment lines of its own."""
    buf = bytearray()
    deadline = time.time() + timeout
    last = time.time()
    while time.time() < deadline:
        data = ser.read(max(1, ser.in_waiting))
        if data:
            buf.extend(data)
            last = time.time()
        elif buf.endswith(b"\n# ") and time.time() - last > idle:
            break
    return buf.decode(errors="replace")


def run(ser, cmd, timeout=60):
    ser.write(cmd.encode() + b"\r\n")
    return read_until_prompt(ser, timeout)


def strip_echo(text, cmd):
    lines = text.replace("\r", "").split("\n")
    if lines and lines[0].strip().endswith(cmd):
        lines = lines[1:]
    if lines and lines[-1].strip() == "#":
        lines = lines[:-1]
    return "\n".join(lines).strip() + "\n"


def enter_cli(ser):
    ser.reset_input_buffer()
    ser.write(b"#")
    banner = read_until_prompt(ser, 5)
    if not banner.rstrip().endswith("#"):
        raise RuntimeError("no CLI prompt: wrong port, or another program holds it")
    return banner


def leave_cli(ser, cmd):
    """'exit' and 'save' reboot the FC; the USB port disappears mid-read."""
    tail = ""
    try:
        ser.write(cmd.encode() + b"\r\n")
        time.sleep(1.0 if cmd == "save" else 0.3)
        tail = ser.read(4096).decode(errors="replace")
    except serial.SerialException:
        pass
    finally:
        try:
            ser.close()
        except serial.SerialException:
            pass
    return tail


def write(path, text):
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write(text)


def backup(port, label, out):
    outdir = os.path.abspath(os.path.join(out, f"{label}_{datetime.now():%Y%m%d_%H%M%S}"))
    os.makedirs(outdir, exist_ok=True)
    ser = serial.Serial(port, 115200, timeout=0.05)
    transcript, results = [], {}
    try:
        transcript.append(enter_cli(ser))
        no_gyro = False
        for cmd in ["status", "diff all", "dump all"] + [c for c in INFO_CMDS if c != "status"]:
            if no_gyro and cmd in SKIP_WITHOUT_GYRO:
                print(f"> {cmd}  (skipped: no gyro detected, it would hang the FC)", flush=True)
                results[cmd] = "skipped: no gyro detected (NOGYRO)\n"
                continue
            print(f"> {cmd}", flush=True)
            text = run(ser, cmd)
            transcript.append(text)
            results[cmd] = strip_echo(text, cmd)
            if cmd == "status" and ("NOGYRO" in text or "Gyros detected" not in text):
                no_gyro = True
                print("  WARNING: no gyro detected", flush=True)
    finally:
        transcript.append(leave_cli(ser, "exit"))
        write(os.path.join(outdir, "transcript.txt"), "".join(transcript).replace("\r", ""))

    if not results["diff all"].rstrip().endswith("save"):
        sys.exit(f"diff all looks truncated, see {outdir}/transcript.txt")
    write(os.path.join(outdir, "diff_all.txt"), results["diff all"])
    write(os.path.join(outdir, "dump_all.txt"), results["dump all"])
    write(os.path.join(outdir, "info.txt"),
          "".join(f"===== {c} =====\n{results[c]}\n" for c in INFO_CMDS))
    print(f"Backup written to {outdir}")
    for name in sorted(os.listdir(outdir)):
        print(f"  {name:16s} {os.path.getsize(os.path.join(outdir, name)):>8d} bytes")


def restore(port, path):
    with open(path, encoding="utf-8") as f:
        lines = [l.strip() for l in f]
    cmds = [l for l in lines if l and not l.startswith("#")]
    if not cmds or cmds[-1] != "save":
        sys.exit("file does not end with 'save': not a complete 'diff all'")
    ser = serial.Serial(port, 115200, timeout=0.05)
    errors = []
    try:
        enter_cli(ser)
        for cmd in cmds[:-1]:
            text = run(ser, cmd, timeout=10)
            if "###ERROR" in text:
                errors.append(f"{cmd}\n    {strip_echo(text, cmd).strip()}")
    except BaseException:
        leave_cli(ser, "exit")       # abort without saving
        raise
    if errors:
        leave_cli(ser, "exit")
        sys.exit("Nothing saved, the FC rejected these lines:\n" + "\n".join(errors))
    leave_cli(ser, "save")
    print(f"Restored {len(cmds) - 1} lines and saved. The FC reboots.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    b = sub.add_parser("backup")
    b.add_argument("port")
    b.add_argument("label")
    b.add_argument("--out", default="backups")
    r = sub.add_parser("restore")
    r.add_argument("port")
    r.add_argument("file")
    a = ap.parse_args()
    if a.mode == "backup":
        backup(a.port, a.label, a.out)
    else:
        restore(a.port, a.file)


if __name__ == "__main__":
    main()
