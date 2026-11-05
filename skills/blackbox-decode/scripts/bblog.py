"""Load and analyse Rotorflight blackbox logs decoded by bbl.js (or bbdecode_fallback.py).

    import sys; sys.path.insert(0, '<skill>/scripts')
    import bblog
    logs = bblog.decode('flight.bbl')            # runs bbl.js, returns one Log per log in the file
    lg = bblog.load('flight.0.npy')              # or load an earlier decode
    t = lg.t                                     # seconds since log start
    roll = lg['gyroADC[0]']                      # raw column; lg.si('Vbat') -> volts
    for seg in lg.profile_segments(): ...
    w = lg.window(30, 45)                        # a time slice as a new Log

Needs numpy; scipy for the filters.
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# Raw blackbox value -> SI-ish unit, from the Blackbox Explorer's field presenter (RF 4.x)
UNITS = {
    'Vbat': (0.01, 'V'), 'Vbec': (0.01, 'V'), 'Vbus': (0.01, 'V'), 'EscV': (0.01, 'V'), 'BecV': (0.01, 'V'),
    'Ibat': (0.01, 'A'), 'EscI': (0.01, 'A'), 'BecI': (0.01, 'A'),
    'Tesc': (1, 'degC'), 'Tmcu': (1, 'degC'), 'Tbec': (1, 'degC'),
    'altitude': (0.01, 'm'), 'headspeed': (1, 'rpm'), 'tailspeed': (1, 'rpm'),
    'attitude[0]': (0.1, 'deg'), 'attitude[1]': (0.1, 'deg'), 'attitude[2]': (0.1, 'deg'),
    'setpoint[3]': (0.012, 'deg'), 'mixer[0]': (0.012, 'deg'), 'mixer[1]': (0.012, 'deg'),
    'mixer[2]': (0.024, 'deg'), 'mixer[3]': (0.1, '%'),
    'rcCommand[0]': (0.2, '%'), 'rcCommand[1]': (0.2, '%'), 'rcCommand[2]': (0.2, '%'),
    'rcCommand[3]': (0.2, '%'), 'rcCommand[4]': (0.1, '%'),
    'motor[0]': (0.1, '%'), 'motor[1]': (0.1, '%'), 'motor[2]': (0.1, '%'), 'motor[3]': (0.1, '%'),
}
for _p in ('gyroADC', 'gyroRAW', 'axisError'):
    for _i in range(3):
        UNITS[f'{_p}[{_i}]'] = (1, 'deg/s')
for _i in range(3):
    UNITS[f'setpoint[{_i}]'] = (1, 'deg/s')
for _i in range(8):
    UNITS[f'servo[{_i}]'] = (1, 'us')


class Log:
    def __init__(self, data, names, meta, path=None):
        self.data = data
        self.names = list(names)
        self.meta = meta
        self.path = path
        self._ix = {n: i for i, n in enumerate(self.names)}

    # -- columns -------------------------------------------------------------------------------
    def __contains__(self, name):
        return name in self._ix

    def __getitem__(self, name):
        return self.data[:, self._ix[name]]

    def si(self, name):
        """Column converted with UNITS (raw values for fields without an entry)."""
        return self[name] * UNITS.get(name, (1, ''))[0]

    def find(self, pattern):
        """Column names containing pattern, e.g. lg.find('gov')."""
        return [n for n in self.names if pattern.lower() in n.lower()]

    @property
    def time_us(self):
        return self['time']

    @property
    def t(self):
        """Seconds since the log's first frame (the same zero as event_t)."""
        return (self['time'] - self.meta.get('start_us', self['time'][0])) / 1e6

    @property
    def rate_hz(self):
        return 1e6 / np.median(np.diff(self['time']))

    @property
    def header(self):
        return self.meta.get('header', {})

    @property
    def events(self):
        return self.meta.get('events', [])

    def event_t(self, ev):
        return None if ev.get('time') is None else (ev['time'] - self.meta['start_us']) / 1e6

    def events_named(self, *names):
        return [e for e in self.events if e['name'] in names]

    # -- slicing -------------------------------------------------------------------------------
    def window(self, t0, t1):
        """Rows with t0 <= t < t1 (seconds since log start), as a new Log sharing meta."""
        t = self.t
        return Log(self.data[(t >= t0) & (t < t1)], self.names, self.meta, self.path)

    def profile_segments(self, profile='pid_profile'):
        """[(t_start, t_end, index)] for each stretch flown on one profile.

        Indexes are the 1-based numbers of the PROFILE_CHANGE events. The header does not say
        which profile was active at log start, so the first segment is None unless a switch
        was logged before the first frame. The header PIDs belong to that first profile.
        """
        cur = None
        t_end = float(self.t[-1])
        segs, t_prev = [], 0.0
        for e in self.events_named('PROFILE_CHANGE'):
            if e['data'].get('profile') != profile:
                continue
            te = self.event_t(e)
            if te is None:
                continue
            if te <= 0:
                cur = e['data']['index']
                continue
            segs.append((t_prev, te, cur))
            t_prev, cur = te, e['data']['index']
        segs.append((t_prev, t_end, cur))
        return [s for s in segs if s[1] > s[0]]

    def summary(self):
        h = self.header
        return {
            'source': self.meta.get('source'), 'log': self.meta.get('log'),
            'firmware': h.get('Firmware revision'), 'board': h.get('Board information'),
            'craft': h.get('Craft name'), 'duration_s': round(float(self.t[-1]), 1),
            'rate_hz': round(float(self.rate_hz), 1), 'rows': len(self.data),
            'debug_mode': h.get('debugModeName'), 'events': len(self.events),
            'gaps': len(self.meta.get('gaps_us', [])),
        }


# -- loading -----------------------------------------------------------------------------------
def load(path):
    """Load PREFIX.N.npy / .csv (+ .json) from bbl.js, or an .npz from bbdecode_fallback.py."""
    if path.endswith('.npz'):
        z = np.load(path)
        names = [str(n) for n in z['names']]
        data = z['data'].astype(float)
        hdr = dict(h.split(':', 1) for h in z['hdr'] if ':' in h)
        start = float(data[0, names.index('time')])
        events = []
        for raw in z['events']:
            tm, typ, d = _literal(raw)
            events.append(_fallback_event(tm, typ, d))
        return Log(data, names, {'header': hdr, 'events': events, 'start_us': start,
                                 'source': os.path.basename(path), 'tool': 'bbdecode_fallback'}, path)
    base = path[:-4] if path.endswith(('.npy', '.csv', '.json')) else path
    with open(base + '.json', encoding='utf-8') as f:
        meta = json.load(f)
    if os.path.exists(base + '.npy'):
        data = np.load(base + '.npy')
    else:
        data = np.genfromtxt(base + '.csv', delimiter=',', skip_header=1)
    return Log(data, meta['names'], meta, path)


def decode(bbl, out=None, log='all', node=None, extra=()):
    """Run bbl.js on a .bbl file and return the list of Logs it wrote."""
    node = node or shutil.which('node')
    if not node:
        raise RuntimeError('node not found; install Node.js 16+ or use bbdecode_fallback.py')
    prefix = out or os.path.splitext(bbl)[0]
    cmd = [node, os.path.join(HERE, 'bbl.js'), 'decode', bbl, '-o', prefix, '--log', str(log), *extra]
    subprocess.run(cmd, check=True)
    info = json.loads(subprocess.run([node, os.path.join(HERE, 'bbl.js'), 'info', bbl],
                                     check=True, capture_output=True, text=True).stdout)
    idx = [l['log'] for l in info['logs'] if 'error' not in l] if log == 'all' else [int(log)]
    return [load(f'{prefix}.{i}.npy') for i in idx if os.path.exists(f'{prefix}.{i}.json')]


def _literal(s):
    import ast
    return ast.literal_eval(str(s))


_FALLBACK_NAMES = {0: 'SYNC_BEEP', 13: 'INFLIGHT_ADJUSTMENT', 14: 'LOGGING_RESUME', 15: 'DISARM',
                   30: 'FLIGHT_MODE', 50: 'GOVERNOR_STATE', 51: 'RESCUE_STATE', 52: 'AIRBORNE_STATE',
                   100: 'CUSTOM_DATA', 101: 'CUSTOM_STRING', 255: 'LOG_END'}
_PROFILE = {1: 'rate_profile', 2: 'pid_profile', 3: 'led_profile', 4: 'osd_profile', 82: 'battery_profile'}


def _fallback_event(tm, typ, d):
    name = _FALLBACK_NAMES.get(typ, f'UNKNOWN_{typ}')
    data = {'raw': d}
    if typ == 13 and d and d[0] in _PROFILE:
        name, data = 'PROFILE_CHANGE', {'profile': _PROFILE[d[0]], 'index': d[1], 'func': d[0]}
    elif typ in (50, 51, 52, 15) and d:
        data = {'state' if typ != 15 else 'reason': d[0]}
    elif typ == 30 and d:
        data = {'flags': d[0], 'lastFlags': d[1]}
    return {'time': tm or None, 'type': typ, 'name': name, 'data': data}


# -- analysis helpers ----------------------------------------------------------------------------
def bandpass(x, lo, hi, fs, order=4):
    from scipy.signal import butter, sosfiltfilt
    sos = butter(order, [lo, hi], btype='band', fs=fs, output='sos')
    return sosfiltfilt(sos, np.nan_to_num(x))


def envelope(x, fs, smooth_s=0.2):
    from scipy.signal import hilbert
    e = np.abs(hilbert(x))
    n = max(1, int(smooth_s * fs))
    return np.convolve(e, np.ones(n) / n, mode='same')


def bursts(mask, t, min_s=0.2):
    """[(t0, t1)] for runs where mask is true for at least min_s seconds."""
    d = np.diff(np.r_[0, mask.astype(int), 0])
    starts, ends = np.where(d == 1)[0], np.where(d == -1)[0] - 1
    return [(float(t[a]), float(t[b])) for a, b in zip(starts, ends) if t[b] - t[a] >= min_s]


def oscillation_bursts(lg, axis, lo, hi, threshold, min_s=0.2):
    """Bursts where the gyro band [lo, hi] Hz envelope exceeds threshold (deg/s) and the
    setpoint in the same band stays below half of it (so stick input is not counted)."""
    fs = lg.rate_hz
    g = envelope(bandpass(lg[f'gyroADC[{axis}]'], lo, hi, fs), fs)
    s = envelope(bandpass(lg[f'setpoint[{axis}]'], lo, hi, fs), fs)
    return bursts((g > threshold) & (s < threshold / 2), lg.t, min_s)


def dominant_freq(x, fs, fmin=1.0, fmax=None):
    x = np.nan_to_num(x - np.nanmean(x)) * np.hanning(len(x))
    f = np.fft.rfftfreq(len(x), 1 / fs)
    p = np.abs(np.fft.rfft(x))
    sel = (f >= fmin) & (f <= (fmax or fs / 2))
    return float(f[sel][np.argmax(p[sel])])


def effective_gain(lg, term, axis):
    """Least-squares gain of axis<term>[axis] against axisError (setpoint - gyro), with the
    correlation coefficient. Compare it between profile segments of one log."""
    err = lg[f'axisError[{axis}]'] if f'axisError[{axis}]' in lg else lg[f'setpoint[{axis}]'] - lg[f'gyroADC[{axis}]']
    y = lg[f'axis{term}[{axis}]']
    ok = np.isfinite(err) & np.isfinite(y)
    e, y = err[ok], y[ok]
    k = float(np.dot(e, y) / np.dot(e, e)) if np.dot(e, e) else float('nan')
    with np.errstate(invalid='ignore', divide='ignore'):
        r = float(np.corrcoef(e, y)[0, 1]) if len(e) > 2 else float('nan')
    return k, r


if __name__ == '__main__':
    for p in sys.argv[1:]:
        print(json.dumps(load(p).summary(), indent=1))
