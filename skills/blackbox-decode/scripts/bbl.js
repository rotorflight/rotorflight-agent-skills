#!/usr/bin/env node
/*
 * bbl.js - decode Rotorflight blackbox logs with the Blackbox Explorer's own parser.
 *
 *   node bbl.js info   <log.bbl>                     list the logs in the file, as JSON
 *   node bbl.js decode <log.bbl> [options]           write each log as .npy/.csv + .json
 *
 * decode options:
 *   -o, --out PREFIX     output prefix (default: the log path without extension)
 *   --log N|all          which log in the file (default: all)
 *   --fields a,b,...     only these columns (time is always included)
 *   --rate HZ            downsample to about HZ rows per second (default: every frame)
 *   --mode envelope|skip downsampling: keep each column's min and max per bucket (envelope,
 *                        default) or one frame per bucket (skip)
 *   --csv                write CSV instead of .npy
 *
 * Output per log N: PREFIX.N.npy (float64, one row per main frame, NaN where a value is
 * missing) or PREFIX.N.csv, and PREFIX.N.json (column names, header, events, gaps, stats,
 * sensor inventory). Load them with bblog.py.
 *
 * Needs only Node.js 16+. The parser in vendor/rotorflight-blackbox is used unmodified.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const TOOL_VERSION = '1.0.0';
const VENDOR_DIR = path.join(__dirname, 'vendor', 'rotorflight-blackbox');
const VENDOR_TAG = 'rotorflight-blackbox release/2.3.0';
const SCRIPTS = [
    'tools.js', 'cache.js', 'datastream.js', 'decoders.js', 'flightlog_fielddefs.js',
    'flightlog_fields_presenter.js', 'flightlog_parser.js', 'flightlog_index.js', 'flightlog.js',
];

// ---------------------------------------------------------------------------------------------
// Load the browser parser into a VM context with the few browser globals it touches.

function semverParts(v) {
    const m = String(v || '0.0.0').match(/(\d+)(?:\.(\d+))?(?:\.(\d+))?/);
    return m ? [+m[1], +(m[2] || 0), +(m[3] || 0)] : [0, 0, 0];
}
function semverCmp(a, b) {
    const x = semverParts(a), y = semverParts(b);
    for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] < y[i] ? -1 : 1;
    return 0;
}
const semver = {
    gte: (a, b) => semverCmp(a, b) >= 0, gt: (a, b) => semverCmp(a, b) > 0,
    lte: (a, b) => semverCmp(a, b) <= 0, lt: (a, b) => semverCmp(a, b) < 0,
    eq: (a, b) => semverCmp(a, b) === 0, valid: (a) => (/^\d+\.\d+\.\d+/.test(String(a)) ? String(a) : null),
};

function jqueryExtend() {
    let target = arguments[0] || {}, i = 1, deep = false;
    if (typeof target === 'boolean') { deep = target; target = arguments[1] || {}; i = 2; }
    for (; i < arguments.length; i++) {
        const src = arguments[i];
        if (src == null) continue;
        for (const k of Object.keys(src)) {
            const v = src[k];
            if (v === target) continue;
            if (deep && v && typeof v === 'object') {
                target[k] = jqueryExtend(true, target[k] || (Array.isArray(v) ? [] : {}), v);
            } else if (v !== undefined) {
                target[k] = v;
            }
        }
    }
    return target;
}

function makeContext(verbose) {
    const quiet = () => {};
    const jq = () => new Proxy({}, { get: () => () => jq() });   // $(...).anything() is a no-op
    jq.extend = jqueryExtend;
    const element = () => ({ style: {}, setAttribute: quiet, appendChild: quiet });
    const ctx = vm.createContext({
        console: {
            log: verbose ? console.error : quiet, info: quiet, debug: quiet, trace: quiet,
            warn: (...a) => console.error('[parser]', ...a), error: (...a) => console.error('[parser]', ...a),
        },
        semver, $: jq, jQuery: jq,
        navigator: { userAgent: 'node' },
        document: { body: { style: {} }, createElement: element, getElementsByTagName: () => [], querySelector: () => null },
        setTimeout, clearTimeout,
    });
    vm.runInContext('this.window = this; this.self = this;', ctx);
    for (const s of SCRIPTS) {
        vm.runInContext(fs.readFileSync(path.join(VENDOR_DIR, s), 'utf8'), ctx, { filename: s });
    }
    return ctx;
}

// ---------------------------------------------------------------------------------------------
// Events

const PROFILE_FUNCS = { 1: 'rate_profile', 2: 'pid_profile', 3: 'led_profile', 4: 'osd_profile', 82: 'battery_profile' };

function eventNames(ctx) {
    const E = vm.runInContext('FlightLogEvent', ctx);
    const byNum = {};
    for (const [k, v] of Object.entries(E)) byNum[v] = k;
    return byNum;
}

function lookup(ctx, table, i) {
    try {
        const arr = vm.runInContext(table, ctx);
        return arr && arr[i] !== undefined ? arr[i] : null;
    } catch (e) { return null; }
}

function flagNames(ctx, flags) {
    const names = vm.runInContext('FLIGHT_LOG_FLIGHT_MODE_NAME', ctx) || [];
    const out = [];
    for (let i = 0; i < names.length; i++) if (flags & (1 << i)) out.push(names[i]);
    return out;
}

function describeEvent(ctx, names, ev) {
    const d = ev.data || {};
    const out = { time: ev.time ?? null, type: ev.event, name: names[ev.event] || `UNKNOWN_${ev.event}`, data: d };
    switch (ev.event) {
        case 13:
            if (PROFILE_FUNCS[d.func]) {
                out.name = 'PROFILE_CHANGE';
                out.data = { profile: PROFILE_FUNCS[d.func], index: d.value, func: d.func, label: d.name };
            } else {
                out.data = { func: d.func, label: d.name, value: d.value };
            }
            break;
        case 15: out.data = { reason: d.reason, label: lookup(ctx, 'FLIGHT_LOG_DISARM_REASON', d.reason) }; break;
        case 30: out.data = { flags: d.newFlags, lastFlags: d.lastFlags,
                              on: flagNames(ctx, d.newFlags & ~d.lastFlags), off: flagNames(ctx, d.lastFlags & ~d.newFlags) }; break;
        case 50: out.data = { state: d.govState, label: lookup(ctx, 'FLIGHT_LOG_GOVSTATES', d.govState) }; break;
        case 51: out.data = { state: d.rescueState, label: lookup(ctx, 'FLIGHT_LOG_RESCUE_STATES', d.rescueState) }; break;
        case 52: out.data = { state: d.airborneState, label: lookup(ctx, 'FLIGHT_LOG_AIRBORNE_STATES', d.airborneState) }; break;
    }
    return out;
}

// ---------------------------------------------------------------------------------------------
// Header extras that analyses keep needing

function headerExtras(ctx, sys) {
    const looptime = +sys.looptime || 0;               // gyro sample period, us
    const pidDenom = +sys.pid_process_denom || 1;
    const pNum = +sys.frameIntervalPNum || 1, pDenom = +sys.frameIntervalPDenom || 1;
    return {
        firmwareTypeName: { 1: 'Baseflight', 2: 'Cleanflight', 3: 'Betaflight', 4: 'INAV', 5: 'Rotorflight' }[sys.firmwareType] || 'Unknown',
        debugModeName: lookup(ctx, 'DEBUG_MODE', +sys.debug_mode),
        // nominal main-frame rate; check it against the decoded time column
        nominalFrameRateHz: looptime ? 1e6 / (looptime * pidDenom) * pNum / pDenom : null,
    };
}

// Telemetry fields that ESCs fill with a sentinel when they do not report the value
const SENTINELS = [25500, 65535, 255];

function inventory(names, cols) {
    const has = (n) => names.includes(n);
    const range = (n) => {
        const c = cols[names.indexOf(n)];
        let lo = Infinity, hi = -Infinity, nonzero = false;
        for (const v of c) { if (v == null || Number.isNaN(v)) continue; if (v < lo) lo = v; if (v > hi) hi = v; if (v) nonzero = true; }
        if (lo === Infinity) return { status: 'empty' };
        if (!nonzero) return { status: 'zero', min: lo, max: hi };
        if (lo === hi && SENTINELS.includes(lo)) return { status: 'sentinel', min: lo, max: hi };
        return { status: 'real', min: lo, max: hi };
    };
    const telemetry = {};
    for (const n of ['Vbat', 'Ibat', 'Vbec', 'Vbus', 'headspeed', 'tailspeed', 'Tesc', 'Tmcu', 'EscV', 'EscI', 'EscRPM', 'BecV', 'BecI', 'altitude'])
        if (has(n)) telemetry[n] = range(n);
    const group = (re) => names.filter((n) => re.test(n));
    return {
        gyro: group(/^gyroADC\[/).length > 0, gyroRaw: group(/^gyroRAW\[/).length > 0,
        acc: group(/^accSmooth\[|^accADC\[/).length > 0, attitude: group(/^attitude\[/).length > 0,
        setpoint: group(/^setpoint\[/).length > 0, pid: group(/^axisP\[/).length > 0,
        governor: has('govTarget'), motors: group(/^motor\[/).length, servos: group(/^servo\[/).length,
        debug: group(/^debug\[/).length, telemetry,
    };
}

// ---------------------------------------------------------------------------------------------
// Decoding

function openFile(ctx, file) {
    const buf = fs.readFileSync(file);
    const data = new (vm.runInContext('Uint8Array', ctx))(buf.buffer, buf.byteOffset, buf.byteLength);
    const FlightLog = vm.runInContext('FlightLog', ctx);
    const fl = new FlightLog(data);
    fl.rawBuffer = buf;
    return fl;
}

// Every "H key:value" line of log i as written by the firmware. The parser renames or drops
// some (field definitions, settings it does not know), so keep the original as well.
function rawHeader(buf, i) {
    const marker = Buffer.from('H Product:Blackbox flight data recorder by Nicholas Sherlock\n', 'latin1');
    let pos = -1;
    for (let k = 0; k <= i; k++) { pos = buf.indexOf(marker, pos + 1); if (pos < 0) return {}; }
    const out = {};
    while (pos < buf.length && buf[pos] === 0x48 && buf[pos + 1] === 0x20) {   // "H "
        const nl = buf.indexOf(0x0a, pos);
        if (nl < 0) break;
        const line = buf.toString('latin1', pos + 2, nl);
        const c = line.indexOf(':');
        if (c > 0) out[line.slice(0, c)] = line.slice(c + 1);
        pos = nl + 1;
    }
    return out;
}

function logSummary(ctx, fl, i) {
    const err = fl.getLogError(i);
    if (err) return { log: i, error: String(err) };
    fl.openLog(i);
    const sys = fl.getSysConfig();
    const t0 = fl.getMinTime(), t1 = fl.getMaxTime();
    return {
        log: i, start_us: t0, end_us: t1, duration_s: (t1 - t0) / 1e6,
        craft: sys['Craft name'] || null, firmware: sys['Firmware revision'] || null,
        board: sys['Board information'] || null, logStart: sys['Log start datetime'] || null,
        fields: fl.getMainFieldNames().length, ...headerExtras(ctx, sys),
    };
}

function decodeLog(ctx, fl, i, opt) {
    if (!fl.openLog(i)) throw new Error(`log ${i}: ${fl.getLogError(i) || 'cannot open'}`);
    const names = fl.getMainFieldNames().slice();
    const tIdx = names.indexOf('time');
    const evNames = eventNames(ctx);
    const t0 = fl.getMinTime(), t1 = fl.getMaxTime();

    // Walk the log in windows so the chunk cache stays small; chunks overlap at window edges,
    // so keep only frames strictly after the last time taken.
    const all = names.map(() => new Column());
    const events = [], gaps = [], seenEv = new Set();
    let last = -Infinity;
    const WINDOW = 5e6;
    for (let a = t0; a <= t1; a += WINDOW) {
        for (const chunk of fl.getChunksInTimeRange(a, Math.min(a + WINDOW, t1))) {
            chunk.frames.forEach((f, k) => {
                const t = f[tIdx];
                if (t <= last) return;
                last = t;
                for (let c = 0; c < all.length; c++) { const v = f[c]; all[c].push(v == null ? NaN : v); }
                if (chunk.gapStartsHere[k]) gaps.push(t);
            });
            for (const ev of chunk.events) {
                const key = `${ev.time}|${ev.event}|${JSON.stringify(ev.data || null)}`;
                if (seenEv.has(key)) continue;
                seenEv.add(key);
                events.push(describeEvent(ctx, evNames, ev));
            }
        }
    }
    events.sort((x, y) => (x.time ?? Infinity) - (y.time ?? Infinity));

    // Column selection
    let keep = names.map((_, k) => k);
    const missing = [];
    if (opt.fields) {
        keep = [tIdx];
        for (const f of opt.fields) {
            const k = names.indexOf(f);
            if (k < 0) missing.push(f); else if (k !== tIdx) keep.push(k);
        }
    }
    const full = all.map((c) => c.done());
    const nRows = full.length ? full[0].length : 0;
    const cols = keep.map((k) => full[k]);
    const outNames = keep.map((k) => names[k]);

    // Downsampling
    let sel = null;   // null = every row
    if (opt.rate && nRows) {
        const bucket = 1e6 / opt.rate, tcol = cols[0];
        const picked = new Set();
        let start = 0;
        while (start < nRows) {
            let end = start;
            const edge = tcol[start] + bucket;
            while (end + 1 < nRows && tcol[end + 1] < edge) end++;
            picked.add(start);
            if (opt.mode !== 'skip') {
                for (let c = 1; c < cols.length; c++) {
                    let lo = start, hi = start;
                    for (let r = start + 1; r <= end; r++) {
                        if (cols[c][r] < cols[c][lo]) lo = r;
                        if (cols[c][r] > cols[c][hi]) hi = r;
                    }
                    picked.add(lo); picked.add(hi);
                }
            }
            start = end + 1;
        }
        sel = [...picked].sort((x, y) => x - y);
    }

    const sys = fl.getSysConfig();
    const meta = {
        tool: `bbl.js ${TOOL_VERSION}`, parser: VENDOR_TAG, source: path.basename(opt.file), log: i,
        logCount: fl.getLogCount(), names: outNames, rows: sel ? sel.length : nRows, framesDecoded: nRows,
        downsample: opt.rate ? { rateHz: opt.rate, mode: opt.mode || 'envelope' } : null,
        start_us: t0, end_us: t1, missingFields: missing,
        header: { ...sys, ...headerExtras(ctx, sys) },
        rawHeader: rawHeader(fl.rawBuffer, i),
        stats: compactStats(fl.getStats()),
        events, gaps_us: gaps,
        inventory: inventory(names, full),
    };
    return { meta, cols, sel };
}

// Growable float64 column
class Column {
    constructor() { this.a = new Float64Array(65536); this.n = 0; }
    push(v) {
        if (this.n === this.a.length) { const b = new Float64Array(this.a.length * 2); b.set(this.a); this.a = b; }
        this.a[this.n++] = v;
    }
    done() { return this.a.subarray(0, this.n); }
}

function compactStats(s) {
    if (!s || !s.frame) return s;
    const out = { totalBytes: s.totalBytes, totalCorruptFrames: s.totalCorruptFrames, intentionallyAbsentIterations: s.intentionallyAbsentIterations, frame: {} };
    for (const [type, f] of Object.entries(s.frame)) {
        out.frame[type] = { validCount: f.validCount, corruptCount: f.corruptCount, desyncCount: f.desyncCount, bytes: f.bytes };
    }
    return out;
}

function writeNpy(file, cols, sel) {
    const nr = sel ? sel.length : (cols.length ? cols[0].length : 0), nc = cols.length;
    let header = `{'descr': '<f8', 'fortran_order': False, 'shape': (${nr}, ${nc}), }`;
    const total = 10 + header.length + 1;
    header += ' '.repeat((64 - (total % 64)) % 64) + '\n';
    const pre = Buffer.alloc(10);
    pre.write('\x93NUMPY', 0, 'latin1'); pre[6] = 1; pre[7] = 0; pre.writeUInt16LE(header.length, 8);
    const fd = fs.openSync(file, 'w');
    fs.writeSync(fd, Buffer.concat([pre, Buffer.from(header, 'latin1')]));
    const BLOCK = 8192;
    const body = new Float64Array(BLOCK * nc);
    for (let r0 = 0; r0 < nr; r0 += BLOCK) {
        const n = Math.min(BLOCK, nr - r0);
        for (let r = 0; r < n; r++) {
            const src = sel ? sel[r0 + r] : r0 + r;
            for (let c = 0; c < nc; c++) body[r * nc + c] = cols[c][src];
        }
        fs.writeSync(fd, new Uint8Array(body.buffer, 0, n * nc * 8));
    }
    fs.closeSync(fd);
}

function writeCsv(file, names, cols, sel) {
    const fd = fs.openSync(file, 'w');
    fs.writeSync(fd, names.map((n) => `"${n}"`).join(',') + '\n');
    let buf = [];
    const n = sel ? sel.length : (cols.length ? cols[0].length : 0);
    for (let i = 0; i < n; i++) {
        const r = sel ? sel[i] : i;
        buf.push(cols.map((c) => (Number.isNaN(c[r]) ? '' : c[r])).join(','));
        if (buf.length >= 10000) { fs.writeSync(fd, buf.join('\n') + '\n'); buf = []; }
    }
    if (buf.length) fs.writeSync(fd, buf.join('\n') + '\n');
    fs.closeSync(fd);
}

// ---------------------------------------------------------------------------------------------

function parseArgs(argv) {
    const opt = { cmd: argv[0], file: argv[1], log: 'all' };
    for (let i = 2; i < argv.length; i++) {
        const a = argv[i], v = () => argv[++i];
        if (a === '-o' || a === '--out') opt.out = v();
        else if (a === '--log') opt.log = v();
        else if (a === '--fields') opt.fields = v().split(',').map((s) => s.trim()).filter(Boolean);
        else if (a === '--rate') opt.rate = +v();
        else if (a === '--mode') opt.mode = v();
        else if (a === '--csv') opt.csv = true;
        else if (a === '-v' || a === '--verbose') opt.verbose = true;
        else throw new Error(`unknown option ${a}`);
    }
    if (!['info', 'decode'].includes(opt.cmd) || !opt.file) {
        throw new Error('usage: node bbl.js info|decode <log.bbl> [options]  (see the header of bbl.js)');
    }
    return opt;
}

function main() {
    const opt = parseArgs(process.argv.slice(2));
    const ctx = makeContext(opt.verbose);
    const fl = openFile(ctx, opt.file);
    const count = fl.getLogCount();

    if (opt.cmd === 'info') {
        const logs = [];
        for (let i = 0; i < count; i++) logs.push(logSummary(ctx, fl, i));
        process.stdout.write(JSON.stringify({ file: path.basename(opt.file), parser: VENDOR_TAG, logCount: count, logs }, null, 2) + '\n');
        return;
    }

    const prefix = opt.out || opt.file.replace(/\.[^./\\]+$/, '');
    const which = opt.log === 'all' ? [...Array(count).keys()] : [+opt.log];
    let failed = 0;
    for (const i of which) {
        if (fl.getLogError(i)) { console.error(`log ${i}: skipped, ${fl.getLogError(i)}`); failed++; continue; }
        const { meta, cols, sel } = decodeLog(ctx, fl, i, opt);
        const base = `${prefix}.${i}`;
        if (opt.csv) writeCsv(`${base}.csv`, meta.names, cols, sel); else writeNpy(`${base}.npy`, cols, sel);
        fs.writeFileSync(`${base}.json`, JSON.stringify(meta, null, 1));
        const st = meta.stats || {};
        console.error(`log ${i}: ${meta.rows} rows x ${meta.names.length} cols, ${((meta.end_us - meta.start_us) / 1e6).toFixed(1)} s, ` +
            `${meta.events.length} events, ${meta.gaps_us.length} gaps, corrupt frames ${st.totalCorruptFrames ?? '?'} -> ${base}.${opt.csv ? 'csv' : 'npy'}`);
        if (meta.missingFields.length) console.error(`log ${i}: not in this log: ${meta.missingFields.join(', ')}`);
    }
    process.exitCode = failed && failed === which.length ? 1 : 0;
}

try { main(); } catch (e) { console.error(e.message); process.exitCode = 2; }
