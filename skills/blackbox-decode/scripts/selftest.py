"""Cross-check bbl.js against bbdecode_fallback.py on real logs.

    python -I selftest.py <log.bbl> [<log.bbl> ...]

Decodes log 0 of each file with both decoders (two independent implementations of the
format) and requires every shared column to match exactly, except loopIteration, which the
fallback approximates. Also exercises --csv, --fields and --rate. Run it after updating the
vendored parser or changing either decoder. Exit code 1 on any mismatch.
"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bblog  # noqa: E402


def run(*cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def check(bbl, tmp):
    fails = []
    p = os.path.join(tmp, 'a')
    run('node', os.path.join(HERE, 'bbl.js'), 'decode', bbl, '-o', p, '--log', '0')
    run(sys.executable, '-I', os.path.join(HERE, 'bbdecode_fallback.py'), bbl, p + '.npz')
    a, b = bblog.load(p + '.0.npy'), bblog.load(p + '.npz')
    if len(a.data) != len(b.data):
        fails.append(f'rows {len(a.data)} != {len(b.data)}')
    else:
        for n in b.names:
            if n == 'loopIteration':
                continue
            if n not in a:
                fails.append(f'{n} missing in bbl.js output')
            elif not np.array_equal(a[n], b[n], equal_nan=True):
                fails.append(f'{n}: {int(np.sum(a[n] != b[n]))} values differ')

    run('node', os.path.join(HERE, 'bbl.js'), 'decode', bbl, '-o', p + 'c', '--log', '0', '--csv',
        '--fields', 'gyroADC[0],setpoint[0],nonexistent', '--rate', '50')
    c = bblog.load(p + 'c.0.csv')
    meta = json.load(open(p + 'c.0.json'))
    if c.names != ['time', 'gyroADC[0]', 'setpoint[0]'] or meta['missingFields'] != ['nonexistent']:
        fails.append(f'--fields gave {c.names}, missing {meta["missingFields"]}')
    if not (np.nanmax(c['gyroADC[0]']) == np.nanmax(a['gyroADC[0]']) and np.nanmin(c['gyroADC[0]']) == np.nanmin(a['gyroADC[0]'])):
        fails.append('--rate envelope lost the gyro extremes')
    return len(a.data), len(a.names), fails


def main():
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for bbl in sys.argv[1:]:
            rows, cols, fails = check(bbl, tmp)
            status = 'ok' if not fails else 'FAIL'
            print(f'{status}  {os.path.basename(bbl)}: {rows} rows x {cols} cols')
            for f in fails:
                print('      ', f)
            bad += bool(fails)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
