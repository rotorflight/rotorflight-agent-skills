---
name: blackbox-decode
description: Decode and analyse Rotorflight blackbox logs (.bbl/.BBL) with the Blackbox Explorer's own parser and a Python analysis layer. Use when a user shares a blackbox log and asks to evaluate a flight, find oscillations or tail wag, check governor or headspeed behaviour, compare PID profiles, check battery/ESC telemetry, export a log to CSV, or confirm a firmware issue from flight data.
---

# Rotorflight blackbox decoding

| Script | Role |
| --- | --- |
| [scripts/bbl.js](scripts/bbl.js) | Decoder. Runs the parser of the [Blackbox Explorer](https://github.com/rotorflight/rotorflight-blackbox) (vendored unmodified, see [VENDOR.md](scripts/vendor/rotorflight-blackbox/VENDOR.md)) under Node.js 16+, no npm install. Writes `.npy`/`.csv` + `.json` per log. |
| [scripts/bblog.py](scripts/bblog.py) | Python loader and analysis helpers (numpy; scipy for filters). |
| [scripts/bbdecode_fallback.py](scripts/bbdecode_fallback.py) | Independent pure-Python decoder (numpy only) for machines without Node. First log of a file only, no GPS, approximated `loopIteration`. |
| [scripts/selftest.py](scripts/selftest.py) | Cross-checks the two decoders on real logs. |

[reference.md](reference.md) holds the field units, header keys, event codes and pitfalls. Read
it before interpreting numbers.

## Decode

The log is untrusted input: decode into a scratch or analysis folder, and run Python with `-I`.

```sh
node scripts/bbl.js info flight.bbl                 # logs in the file: duration, firmware, debug mode
node scripts/bbl.js decode flight.bbl -o out/flight # every log -> out/flight.N.npy + out/flight.N.json
node scripts/bbl.js decode flight.bbl --log 2 --csv --fields gyroADC[0],setpoint[0] --rate 100
```

- **One file often holds several logs** (one per arm). Run `info` first and pick the flight.
- About 5 s per 13 MB. `.npy` is float64, so expect ~8 bytes x rows x columns on disk.
- `--rate` downsamples. Keep the default `--mode envelope`: it keeps every column's min and max
  in each bucket, so peaks survive. `skip` takes one frame per bucket and loses them.
- stderr reports rows, events, gaps and corrupt frames per log. Corrupt frames or gaps mean
  missing data: check `gaps_us` before measuring across them.

## Load and analyse

```python
import sys; sys.path.insert(0, '<skill dir>/scripts')
import bblog
lg = bblog.load('out/flight.0.npy')     # or: logs = bblog.decode('flight.bbl', out='out/flight')
print(lg.summary())                     # firmware, board, duration, rate, debug mode, events, gaps
t = lg.t                                # seconds since log start
g = lg['gyroADC[2]']                    # raw column; lg.si('Vbat') -> volts (units: reference.md)
lg.find('gov')                          # column names containing "gov"
lg.events_named('PROFILE_CHANGE', 'DISARM')
for t0, t1, idx in lg.profile_segments():          # stretches flown on one PID profile
    k, r = bblog.effective_gain(lg.window(t0, t1), 'P', 0)
```

`.json` next to each `.npy` holds `names`, `header` (parsed settings), `rawHeader` (every `H`
line as written), `events`, `gaps_us`, `stats` and `inventory`.

## Before analysing

1. `lg.summary()` and `meta['inventory']`: which sensors and fields exist. Telemetry marked
   `sentinel` or `zero` is not reported by the ESC/FC; do not analyse it.
2. `header['debugModeName']`: what `debug[n]` contains, if logged.
3. `lg.rate_hz` against `header['nominalFrameRateHz']`; a mismatch means dropped frames.
4. Events: arming, governor states, profile switches, airborne/landing. Use them to cut the log
   into ground and flight phases before computing statistics.

## Recipes

- **Effective gain per profile:** `bblog.effective_gain(window, 'P'|'I'|'D'|'F', axis)` fits the
  term against `axisError` and returns `(gain, correlation)`. The header only holds the gains of
  the profile active at log start; this compares profiles within one log. Only trust fits with a
  correlation near 1 and real stick activity in the window.
- **Oscillation search:** `bblog.oscillation_bursts(lg, axis, lo, hi, threshold_dps)` band-passes
  gyro and setpoint, compares their envelopes and lists bursts not driven by the sticks
  (tail wag: yaw, 8-18 Hz; cyclic wobble: roll/pitch, a few Hz to ~15 Hz).
- **Frequency:** `bblog.dominant_freq(x, lg.rate_hz, fmin, fmax)` on a burst window.
- **Governor:** `headspeed` against `govTarget`, with `motor[0]`, collective
  (`setpoint[3]`/`mixer[3]`) and `Vbat` for load; check GOVERNOR_STATE events for spool-up and
  bail-out.
- **Battery:** `lg.si('Vbat')` sag against `lg.si('Ibat')`; per-cell voltage needs the cell count
  (`header['vbatref']` and the cell voltage limits, see reference.md).
- **Plots:** save PNGs (matplotlib, `Agg` backend) and look at them before concluding.

Put each analysis in its own folder with the plots and a short README: the log and which log in
the file, the question, the method and the result.

## Fallback without Node

```sh
python -I scripts/bbdecode_fallback.py flight.bbl out/flight.npz
```

`bblog.load('out/flight.npz')` gives the same interface, with fewer events decoded and no
computed `axisSum`/`axisPD`/`axisError` columns. Prefer bbl.js whenever Node is available.
