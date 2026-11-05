---
name: blackbox-decode
description: Decode and analyse Rotorflight blackbox logs (.bbl/.BBL) in Python with the bundled decoder. Use when a user shares a blackbox log and asks to evaluate a flight, find oscillations or tail wag, check governor or headspeed behaviour, compare PID profiles, or confirm a firmware issue from flight data.
---

# Rotorflight blackbox decoder

[scripts/bbdecode.py](scripts/bbdecode.py) decodes Rotorflight blackbox logs that use
**data version 2** into a numpy `.npz` file. It needs only numpy; use scipy and matplotlib for the
analysis.

## Decode

```sh
python -I scripts/bbdecode.py <log.bbl> <out.npz>
```

- Run it with `-I`: the log is untrusted input.
- About 1 minute per 13 MB of log.
- It prints `frames N bad M events K`. A bad count well above 0 means a corrupt stream or a format
  gap (see Limitations).
- A file with several flights holds several logs; only the first is decoded. Split the file on the
  `H Product:` header lines to decode the others.

The `.npz` contains:

| Key | Content |
| --- | --- |
| `data` | int64 array, one row per I/P frame: all `Field I name` fields, then the latest S-frame fields (`flightModeFlags`, `stateFlags`, ...). |
| `names` | Column names in the same order. |
| `hdr` | All `H key:value` header lines: PIDs of the profile active at log start, rates, filters, `debug_mode`. |
| `events` | `repr((time_us, type, data))` for each event frame. |

```python
import numpy as np
z = np.load('out.npz'); a = z['data']; N = list(z['names'])
c = lambda n: a[:, N.index(n)].astype(float)
t = (c('time') - c('time')[0]) / 1e6          # seconds since log start
hdr = dict(h.split(':', 1) for h in z['hdr'])
events = [eval(e) for e in z['events']]        # trusted: written by bbdecode.py
```

Event time relative to the log: `(ev[0] - c('time')[0]) / 1e6`.

## Fields

The set depends on `fields_mask` and the firmware version; always check `names`.

- `setpoint[0..3]`: roll, pitch, yaw in deg/s, and collective.
- `gyroADC[0..2]`: filtered gyro in deg/s. `gyroRAW[0..2]`: unfiltered.
- `axisP/I/D/F/O[0..2]`: PID terms. `mixer[0..3]`: mixer input; yaw saturates near +-1000.
- `rcCommand[0..4]`: roll, pitch, yaw, collective, throttle.
- `headspeed`, `govTarget`, `govRequest`, `govP/I/D/F/Sum`, `motor[0]`: governor and main motor.
- `servo[n]`, `Vbat`, `Ibat`, `Vbec`, `Tesc`, `debug[n]` (if logged).

## Events

| Type | Meaning | Data |
| --- | --- | --- |
| 0 | sync beep | time |
| 13 | in-flight adjustment | `[function, value]`; function 1 = rate profile, 2 = PID profile, so a profile switch shows as two type-13 events |
| 14 | logging resume | `[iteration, time]` |
| 15 | disarm | reason |
| 30 | flight mode change | `[flags, lastFlags]` |
| 50 | governor state | state |
| 51 | rescue state | state |
| 52 | airborne state | 0/1 |
| 100/101 | custom data / string | bytes |
| 255 | end of log | - |

## Analysis recipes

- **Effective P gain per profile:** fit `axisP[k]` against `setpoint[k] - gyroADC[k]` over a window
  (`np.dot(e,p)/np.dot(e,e)`) and check the correlation. The header holds only the starting
  profile's gains; the fit compares profiles within one log.
- **Oscillation search:** band-pass the gyro (scipy `butter` + `sosfiltfilt`, e.g. 8-18 Hz for tail
  wag), smooth the Hilbert envelope and threshold it to list bursts. Band-pass the setpoint the same
  way so pilot input is not mistaken for oscillation.
- **Frequency:** FFT of the burst with a Hann window, or zero-crossing spacing.
- **Governor:** headspeed against `govTarget` and `motor[0]`; collective and cyclic show the load.
- **Data rate:** `np.median(np.diff(t))`.
- **Plots:** save PNGs and look at them before drawing conclusions.

Put each analysis in its own folder with the plots and a short README that states the log, the
question, the method and the result.

## Limitations

- GPS frames (G/H) are not decoded.
- P-frame `loopIteration` is approximated as previous + 1; use `time` for the time axis.
- Encoding `TAG2_3SVARIABLE` (10) is not implemented: the frame counts as bad and the decoder
  resyncs on the next `I` frame.
- A corrupt frame triggers a resync to the next `I` byte and resets predictor history.

Format reference: `rotorflight-firmware/src/main/blackbox/blackbox.c` (`writeIntraframe`,
`writeInterframe`, `blackboxWriteEvent`) and `blackbox_fielddefs.h`. For interactive viewing use
[rotorflight-blackbox](https://github.com/rotorflight/rotorflight-blackbox).
