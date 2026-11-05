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
| `time` | us | since FC boot; `lg.t` is relative to the first frame |

`axisSum`, `axisPD` and `axisError` are computed by the parser, not logged.

## Header

- `header` is the parser's view (renamed and typed keys); `rawHeader` is every `H` line as the
  firmware wrote it. Look in both.
- `rollPID`, `pitchPID`, `yawPID`, rates and filters are those of the **profile active at log
  start**. The header does not say which profile that was. In-flight switches appear as
  `PROFILE_CHANGE` events.
- `debug_mode` / `debugModeName`: what `debug[0..7]` holds. Names come from the parser's
  `DEBUG_MODE` table for the log's firmware version.
- **Frame rate:** `nominalFrameRateHz = 1e6 / (looptime * pid_process_denom) * frameIntervalPNum / frameIntervalPDenom`
  with `looptime` the gyro period in us. The "loggingRate" some tools print
  (`1e6 / (looptime * frameIntervalI)`) is the I-frame rate, not the data rate. Always confirm with
  `lg.rate_hz`.
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
| GOVERNOR_STATE | 50 | `state`, `label` (THROTTLE_OFF, THROTTLE_IDLE, SPOOLUP, RECOVERY, ACTIVE, ...) |
| RESCUE_STATE | 51 | `state`, `label` |
| AIRBORNE_STATE | 52 | `state`, `label` (TAKEOFF / LANDING) |
| CUSTOM_DATA / CUSTOM_STRING | 100 / 101 | |
| LOG_END | 255 | time is `null` |

A profile switch on a switch that changes both rate and PID profile shows as two events at the
same time. Adjustment function numbers are `ADJUSTMENT_*` in the firmware's
`src/main/fc/rc_adjustments.h`.

An event's time is that of the next main frame (the loop iteration it happened in).

## Telemetry sentinels

ESCs that do not report a value often log a constant such as 25500 (255.00 A or V), 65535 or 255.
`inventory.telemetry` in the `.json` classifies each telemetry column as `real`, `zero`,
`sentinel` or `empty`. Only analyse `real` ones. `Vbec`/`Vbus` are the FC's own ADC; `BecV`/`BecI`
come from the ESC.

## Firmware versions

The parser's field definitions branch on firmware version up to 4.6. A log from newer firmware
is decoded with the 4.6 definitions: new fields still decode (names come from the log header), but
enum names (debug modes, flight modes, governor states) can be wrong. Update the vendored parser
when a newer Blackbox Explorer release exists (see VENDOR.md).

GPS frames are read but not exported (the Explorer's parser does not use them either).
