# Blackbox reference

Facts for interpreting decoded Rotorflight logs (firmware 4.5-4.6). Sources: the Blackbox
Explorer's `flightlog_fielddefs.js` and `flightlog_fields_presenter.js`, and the firmware's
`src/main/blackbox/blackbox.c`. When in doubt, read those.

## Units of raw values

`bblog.UNITS` holds these; `lg.si(name)` applies them.

| Field | Raw unit | Note |
| --- | --- | --- |
| `gyroADC[0..2]`, `gyroRAW[0..2]`, `setpoint[0..2]`, `axisError[0..2]` | deg/s | roll, pitch, yaw |
| `setpoint[3]` | 0.012 deg | collective pitch |
| `attitude[0..2]` | 0.1 deg | |
| `rcCommand[0..3]` | 0.2 % | roll, pitch, yaw, collective |
| `rcCommand[4]`, `motor[n]`, `mixer[3]` | 0.1 % | throttle / motor output |
| `mixer[0..1]` | 0.012 deg | cyclic; `mixer[2]` yaw, 0.024 deg |
| `servo[n]` | us | |
| `axisP/I/D/F/O/B/Sum/PD[0..2]` | PID output units | Explorer shows them as % of the PID limit |
| `Vbat`, `Vbec`, `Vbus`, `EscV`, `BecV` | 0.01 V | |
| `Ibat`, `EscI`, `BecI` | 0.01 A | |
| `Tesc`, `Tmcu`, `Tbec` | deg C | |
| `headspeed`, `tailspeed` | rpm | `/60` for Hz |
| `altitude` | cm | |
| `vario` | cm/s | |
| `time` | us | since FC boot; `lg.t` is relative to the first frame |

`axisSum`, `axisPD` and `axisError` are computed by the parser, not logged.

## Header

- `header` is the parser's view (renamed and typed keys); `rawHeader` is every `H` line as the
  firmware wrote it. Look in both.
- `rollPID`, `pitchPID`, `yawPID`, rates and filters are those of the **profile active at log
  start**. The header does not say which profile that was. In-flight switches appear as
  `PROFILE_CHANGE` events.
- `debug_mode` / `debugModeName`: what `debug[0..7]` holds. Names come from the parser's
  `DEBUG_MODE` table for the log's firmware version, corrected by `bbl.js` where that table is
  wrong (see [Debug modes](#debug-modes)). `lg.debug_mode` gives the name for both decoders.
- **Frame rate:** `nominalFrameRateHz = pidRateHz * frameIntervalPNum / frameIntervalPDenom`
  with `pidRateHz = 1e6 / (looptime * pid_process_denom)` and `looptime` the gyro period in us.
  Rotorflight writes `P interval:N`, a plain loop count (one main frame every N PID loops), and
  `P ratio` = I interval / N; the parser stores that as `frameIntervalPNum = 1`,
  `frameIntervalPDenom = N`. Older logs write `P interval:num/denom`. Reading a plain N as a
  numerator gives N squared times the real rate: `P interval:4` at a 2 kHz PID loop is 500 Hz,
  not 8000 Hz. The "loggingRate" some tools print (`1e6 / (looptime * frameIntervalI)`) is the
  I-frame rate, not the data rate. Always confirm with `lg.rate_hz`.
- Main frames start at the first valid I frame: `bbl.js` and the fallback give monotonic times
  from the first row. Other decoders (orangebox) can return a few start-of-log frames with
  near-zero or negative times before the clock jumps to the time since boot; drop them before
  computing a rate or a time axis.
- `Log start datetime` is the FC clock. A year 2000 date means the clock was never set. The
  `+00:00` offset is not reliable; it may be local time.
- `motor_poles` is not in the header; get it from the user's `diff all` if needed.
- `vbatref` (0.01 V) is the battery voltage when logging started. The Explorer estimates the
  cell count as the smallest n with `vbatref < n * vbatmaxcellvoltage` (n up to 13), so a freshly
  charged pack slightly above the maximum cell voltage counts as one cell more. Prefer the cell
  count the user states.

## Events

| Name | Code | `data` |
| --- | --- | --- |
| SYNC_BEEP | 0 | |
| PROFILE_CHANGE | 13, func 1-4, 82 | `profile` (`rate_profile`, `pid_profile`, `led_profile`, `osd_profile`, `battery_profile`), `index` (1-based) |
| INFLIGHT_ADJUSTMENT | 13, other funcs | `func`, `label`, `value` (an adjustment, e.g. a gain step) |
| LOGGING_RESUME | 14 | a gap in the data starts here |
| DISARM | 15 | `reason`, `label` |
| FLIGHT_MODE | 30 | `flags`, `lastFlags`, `on`, `off` (mode names) |
| GOVERNOR_STATE | 50 | `state`, `label` (see below) |
| RESCUE_STATE | 51 | `state`, `label` |
| AIRBORNE_STATE | 52 | `state`, `label` (TAKEOFF / LANDING) |
| CUSTOM_DATA / CUSTOM_STRING | 100 / 101 | with `esc_sensor_protocol = RECORD`, raw ESC telemetry bytes (nothing decoded) |
| LOG_END | 255 | time is `null` |

`FLIGHT_MODE` flags are the mode **switch** boxes (`rcModeActivationMask`, first 32 boxes),
not the modes actually engaged: a switched-on mode that cannot engage still shows as on. Logs
of the alt/pos-hold fork also carry the slow field `activeFlightModes`, see
[Position debug modes](#position-debug-modes-alt-pos-hold-fork-only).

A profile switch on a switch that changes both rate and PID profile shows as two events at the
same time. Adjustment function numbers are `ADJUSTMENT_*` in the firmware's
`src/main/fc/rc_adjustments.h`.

An event's time is that of the next main frame (the loop iteration it happened in).

### Governor states (`flight/governor.h`, 4.6)

| # | State | Meaning |
| --- | --- | --- |
| 0 | THROTTLE_OFF | |
| 1 | THROTTLE_IDLE | |
| 2 | SPOOLUP | |
| 3 | RECOVERY | fast re-spool out of FALLBACK or THROTTLE_HOLD; assumes the heli is airborne |
| 4 | ACTIVE | governing |
| 5 | THROTTLE_HOLD | |
| 6 | FALLBACK | RPM signal lost; `gov_fallback_drop` lowers throttle on purpose to warn the pilot, so the headspeed sag is the alarm, not a fault |
| 7 | AUTOROTATION | |
| 8 | BAILOUT | autorotation abandoned, ramped at `gov_recovery_time` |
| 9 | BYPASS | new in 4.6: no safeguards, no rate limiting |

The CRSF flight-mode strings (`telemetry/crsf.c`) use different names for 0, 5 and 6; the numbers
above are the authority.

## Telemetry sentinels

ESCs that do not report a value often log a constant such as 25500 (255.00 A or V), 65535 or 255.
`inventory.telemetry` in the `.json` classifies each telemetry column as `real`, `zero`,
`sentinel` or `empty`. Only analyse `real` ones. `Vbec`/`Vbus` are the FC's own ADC; `BecV`/`BecI`
come from the ESC.

Known placeholders: BEC temperature is a constant 255 when the ESC has no such sensor; BEC, bus
and MCU currents are usually exactly zero. `Tmcu` comes from the MCU's internal sensor through a
1 Hz task and an 8-sample average, so it lags ~8 s, and below 30 degC it reads about 1 degC high.

## Cell count

`battery_cell_count` (0-24) is usually set by the user; the firmware only auto-detects while it
is 0, and then takes the first matching voltage window, so overlapping windows can pick the wrong
count (e.g. 33.0-34.4 V detects as 8S). Get the real count from the user or their `diff all`.

## Firmware versions

The parser's field definitions branch on firmware version up to 4.6. A log from newer firmware
is decoded with the 4.6 definitions: new fields still decode (names come from the log header), but
enum names (debug modes, flight modes, governor states) can be wrong. Update the vendored parser
when a newer Blackbox Explorer release exists (see VENDOR.md).

## Debug modes

`debug_mode` is the index into `debugType_e` in the firmware's `src/main/build/debug.h`; modes are
only appended, so a number keeps its meaning within one line of firmware. The vendored parser's
4.6 table matches upstream for 0-80, then lists `USER1`-`USER4` (81-84), and names a few modes
differently (3 `GYRO` for `GYRO_FILTERED`, 8 `ANGLERATE` for `RC_SETPOINT`). `bbl.js` corrects
the numbers that matter:

| # | Upstream (rotorflight-firmware master) | Alt/pos-hold fork |
| --- | --- | --- |
| 14 | ALTITUDE | ALTITUDE (fields 0/1: the fork's altitude estimate) |
| 27 | RANGEFINDER (fields 1-3) | RANGEFINDER (fields 1-7) |
| 81 | GYRO_CALIBRATION (since 4.6.0; the parser says USER1) | GYRO_CALIBRATION |
| 82 | FBUS (4.7 development) | ALTHOLD |
| 83 | | POSHOLD |
| 84 | | HARDDECK |
| 85 | | OPTICAL_FLOW |
| 86 | | POS_EST_Z |
| 87 | | POS_EST_XY |
| 88 | | POS_EST_TERRAIN |

The fork is NightHawk32/rotorflight-firmware, branch `feature/microlink-alt-pos-hold` (altitude
and position hold with a MicroLink rangefinder/optical flow module, hard deck). Its modes from 82
on are not upstream, and 82 is FBUS upstream: `bbl.js` takes a log as the fork's when its header
has a `position_source` line, which upstream does not write. Do not describe 82-88 as upstream
modes.

## Position debug modes (alt/pos-hold fork only)

From the fork's `docs/Blackbox-Tuning-AltHold-PosHold.md`, section 4. Unless stated: altitudes
and positions in cm, velocities in cm/s, angles in centidegrees; altitude relative to the arm
point; horizontal values East/North (in the heading frame, see the pitfalls). The estimator runs
at 100 Hz and the flow module at 50 Hz, so 500 Hz logging loses nothing; the debug fields hold
their last value between updates.

**OPTICAL_FLOW** (85)

| Field | Value |
| --- | --- |
| 0, 1 | Flow X forward, Y left: module units "cm/s at 1 m", body frame after `optical_flow_align`, 50 Hz. Includes rotation: about 100 x the body rate in rad/s |
| 2 | Quality 0-255, not fused at 50 or below |
| 3 | Height used for scaling (AGL, cm) |
| 4 | Flow scale x100 (height / cos^2 tilt) |
| 5, 6 | Velocity forward, right (cm/s), last fused sample |
| 7 | Status of the latest sample, `bblog.FLOW_STATUS`: 0 fused, 1 disabled by `position_xy_source`, 2 no sensor / timeout, 3 no valid AGL, 4 quality too low, 5 tilt above 45 deg, 6 outlier (> 5 sigma) |

**RANGEFINDER** (27; fields 4-7 fork only): 1 raw distance (cm, median filtered), 2 tilt
compensated, 3 SNR (MicroLink: 255 - signal strength), 4 AGL (cm), 5 AGL vario (cm/s),
6 reliability (per mille, valid at 330 or more), 7 AGL valid (0/1).

**POS_EST_Z** (86, vertical Kalman filter)

| Field | Value |
| --- | --- |
| 0, 1 | Fused altitude, vertical velocity |
| 2 | Baro measurement before bias removal; the filter sees field 2 - field 5 |
| 3 | GPS altitude measurement (minus arm offset) |
| 4 | Rangefinder measurement, aligned to the arm frame (compare with field 0 - terrain) |
| 5 | Baro bias (downwash error) |
| 6 | Altitude 1 sigma |
| 7 | `flags * 1000 + disturbance * 100`, `bblog.pos_est_z_flags`. Flags: 1 anchor fresh, 2 inverted thrust bias, 4 baro sample rejected by the 5 sigma gate, 8 baro available |

**POS_EST_TERRAIN** (88): 0 rangefinder raw, 1 AGL (tilt compensated), 2 measurement as fused
(AGL - field 7), 3 innovation (measurement - (altitude - terrain)), 4 terrain offset under the
model, 5 terrain 1 sigma, 6 horizontal speed used (cm/s, 0 freezes the terrain), 7 alignment
offset, set on the first valid sample after arming.

**ALTHOLD** (82): 0 target altitude, 1 altitude used (AGL with flag 2, else fused), 2 vario
used, 3 climb-rate term x10 and 4 I term x10 (collective units 0-1000), 5 velocity command
(cm/s; the D term in logs before 2026-10-30), 6 output collective (pass-through when not
engaged), 7 flags: 1 engaged, 2 using AGL, 4 altitude source valid, 8 pilot moving the target,
16 yielding to rescue/failsafe, 32 switched off and fading out.

**POSHOLD** (83): 0/1 position error East/North (target - estimate), 2/3 estimated velocity
East/North, 4/5 wind trim (I) East/North in centidegrees of tilt, 6 roll command (+ right),
7 pitch command (+ forward), body frame, centidegrees. All 0 while not engaged.

**POS_EST_XY** (87, horizontal Kalman filters)

| Field | Value |
| --- | --- |
| 0, 1 | Position East, North from the arm point |
| 2, 3 | Velocity East, North |
| 4, 5 | Flow velocity East, North: the **last usable** flow sample, held |
| 6 | Position 1 sigma (both axes averaged) |
| 7 | Packed, `bblog.pos_est_xy_flags(v)`: bits 0-7 flags, bits 8-15 flow status (`FLOW_STATUS`), bits 16-24 heading offset in degrees (`(v >> 16) & 511`, heading frame to North, valid with flag 128) |

POS_EST_XY flags: 1 valid, 2 GPS position fused < 2 s ago, 4 flow fused < 500 ms ago,
8 dead-reckoning clamp, 16 GPS origin set, 32 GPS velocity fused alongside flow, 64 GPS held off
(heading not referenced to North), 128 heading aligned from flow vs GPS velocity.

**HARDDECK** (84): 0 state (0 off, 1 wait, 2 watch, 3 pull-up, 4 flip, 5 climb, 6 hold, 7 exit),
1 fused altitude, 2 altitude 1 sigma, 3 predicted minimum altitude, 4 recovery/hold target,
5 baro bias, 6 baro disturbance x100, 7 hard-deck collective output.

**Engaged modes.** `activeFlightModes` (slow field, fork only) holds `flightModeFlags_e`: bit 0
FAILSAFE, 1 ANGLE, 2 HORIZON, 3 TRAINER, 4 ALTHOLD, 5 RESCUE, 6 GPS_RESCUE, 7 POSHOLD,
8 HARDDECK; `lg.mode_active('POSHOLD')` gives the mask. A switched-on mode that is not engaged
(POSHOLD without ALTHOLD or a valid XY estimate) reads 0.

**Header lines** (fork only, comma-separated values in `rawHeader`): `althold_gain`,
`althold_limits`, `poshold_gain`, `poshold_limits`, `harddeck_altitude`, `harddeck_predict`,
`position_source` (alt source `DEFAULT`, `BARO_ONLY`, `GPS_ONLY`, `LIDAR_ONLY`; xy source `AUTO`,
`GPS_ONLY`, `FLOW_ONLY`), `position_lpf`, `position_gps_min_sats`, `position_est_q`,
`position_est_r`, `position_baro_downwash_comp`, `position_flow_gyro_comp`,
`position_flow_gyro_delay` (ms), `rangefinder_hardware`, `optical_flow_hardware`,
`optical_flow_align` (`CW0`, `CW90`, `CW180`, `CW270`, then the `FLIP` variants), `gps_provider`
(`NMEA`, `UBLOX`, `MSP`, `FBUS`, `CRSF`), `pid_rate_hz`. Section 5 of the fork's tuning doc lists
the members of each.

**Pitfalls**

- Stale flow: POS_EST_XY fields 4/5 and OPTICAL_FLOW fields 5/6 keep the last usable sample
  while new ones are rejected, and flag 4 stays set for 500 ms after the last fusion. Compare
  flow with the filter or GPS only on rows whose flow status (bits 8-15, or OPTICAL_FLOW
  field 7) is 0 (fused). Selecting on flag 4 counts the held values: on one hover log, flow - KF
  velocity was 173 cm/s rms that way and 59 cm/s on fused rows.
- Heading frame: the XY filters run in the IMU heading frame. Without a compass that frame is
  only tied to North once flow and GPS velocity are aligned (flag 128); bits 16-24 give the
  offset. Rotate GPS velocity into the filter frame before comparing,
  `(ge + 1j*gn) * np.exp(-1j * np.radians(offset))`, on rows with flag 128.
- New flow samples arrive at 50 Hz: count samples where fields 0-2 change, not rows, when
  fitting flow against gyro rates.

## GPS

The Explorer's parser reads GPS frames but its FlightLog drops them, so `bbl.js` runs the
unmodified parser once more over each log with GPS frames and writes `PREFIX.N.gps.npy` (or
`.gps.csv`), named in the log's `.json` under `gps`. One row per GPS frame (~10 Hz), `time` on
the main clock:

| Column | Unit | From the firmware's G frame |
| --- | --- | --- |
| `GPS_numSat` | | satellites |
| `GPS_north_m`, `GPS_east_m` | m | position from the GPS home (H frame), flat-earth |
| `GPS_altitude_m` | m | `altCm / 10` logged |
| `GPS_speed_mps` | m/s | ground speed, logged in cm/s (`gps.h` says 0.1 m/s; the positions' rate of change agrees with cm/s) |
| `GPS_course_deg` | deg | course over ground, logged in 0.1 deg |

Raw G frame fields, for other decoders: `GPS_coord[0..1]` latitude/longitude in 1e-7 deg as a
delta from the H frame's `GPS_home[0..1]`; `GPS_altitude` in dm (`altCm / 10`); `GPS_speed` in
cm/s; `GPS_ground_course` in 0.1 deg. Velocity components: `east = speed * sin(course)`,
`north = speed * cos(course)`. The course is the direction of travel, not the heading, and is
noise at low speed.

GPS frames come at ~10 Hz on their own times. To compare them with main-frame fields, put one on
the other's times with `bblog.hold(t_src, x, t)` (last sample held); do not interpolate flags or
status fields.

Frames before the GPS home is set are skipped (their coordinates are deltas from it).
Absolute latitude and longitude (`GPS_lat_deg`, `GPS_lon_deg`) only with `--gps-absolute`:
coordinates show where the pilot flies, so keep them out of shared files. `--no-gps` skips the
pass. In Python, `lg.gps` returns the GPS frames as a `Log` with the same time zero.
