"""Minimal Rotorflight blackbox (data version 2) decoder -> npz."""
import sys, struct
import numpy as np

def sx(v, bits):
    m = 1 << (bits - 1)
    v &= (1 << bits) - 1
    return (v ^ m) - m

class R:
    def __init__(s, d, p): s.d = d; s.p = p
    def b(s):
        v = s.d[s.p]; s.p += 1; return v
    def uvb(s):
        r = 0; sh = 0
        for _ in range(5):
            c = s.d[s.p]; s.p += 1
            r |= (c & 0x7F) << sh
            if c < 128: return r
            sh += 7
        raise ValueError('uvb')
    def svb(s):
        u = s.uvb(); return (u >> 1) ^ -(u & 1)

def tag8_4s16(r):
    sel = r.b(); out = []; ni = 0; buf = 0
    for _ in range(4):
        t = sel & 3
        if t == 0: v = 0
        elif t == 1:
            if ni == 0: buf = r.b(); v = sx(buf >> 4, 4); ni = 1
            else: v = sx(buf & 0xF, 4); ni = 0
        elif t == 2:
            if ni == 0: v = sx(r.b(), 8)
            else:
                c1 = (buf << 4) & 0xFF; buf = r.b(); c1 |= buf >> 4; v = sx(c1, 8)
        else:
            if ni == 0:
                c1 = r.b(); c2 = r.b(); v = sx((c1 << 8) | c2, 16)
            else:
                c1 = (buf << 4) & 0xFF; buf = r.b(); c1 |= buf >> 4
                c2 = (buf << 4) & 0xFF; buf = r.b(); c2 |= buf >> 4
                v = sx((c1 << 8) | c2, 16)
        out.append(v); sel >>= 2
    return out

def tag2_3s32(r):
    lead = r.b(); s = lead >> 6
    if s == 0:
        return [sx(lead >> 4, 2), sx(lead >> 2, 2), sx(lead, 2)]
    if s == 1:
        b = r.b(); return [sx(lead, 4), sx(b >> 4, 4), sx(b, 4)]
    if s == 2:
        return [sx(lead, 6), sx(r.b(), 6), sx(r.b(), 6)]
    out = []; sel = lead
    for _ in range(3):
        t = sel & 3
        if t == 0: v = sx(r.b(), 8)
        elif t == 1: b1 = r.b(); b2 = r.b(); v = sx(b1 | b2 << 8, 16)
        elif t == 2: b1 = r.b(); b2 = r.b(); b3 = r.b(); v = sx(b1 | b2 << 8 | b3 << 16, 24)
        else: b1 = r.b(); b2 = r.b(); b3 = r.b(); b4 = r.b(); v = sx(b1 | b2 << 8 | b3 << 16 | b4 << 24, 32)
        out.append(v); sel >>= 2
    return out

def tag8_8svb(r, n):
    if n == 1: return [r.svb()]
    h = r.b(); out = []
    for i in range(n):
        out.append(r.svb() if h & (1 << i) else 0)
    return out

def read_fields(r, enc):
    vals = []; i = 0; n = len(enc)
    while i < n:
        e = enc[i]
        if e == 0: vals.append(r.svb()); i += 1
        elif e == 1: vals.append(r.uvb()); i += 1
        elif e == 3: vals.append(-sx(r.uvb(), 14)); i += 1
        elif e == 9: vals.append(0); i += 1
        elif e == 8:
            g = tag8_4s16(r); k = min(4, n - i); vals += g[:k]; i += k
        elif e == 7:
            g = tag2_3s32(r); k = min(3, n - i); vals += g[:k]; i += k
        elif e == 6:
            k = 1
            while i + k < n and enc[i + k] == 6 and k < 8: k += 1
            vals += tag8_8svb(r, k); i += k
        else: raise ValueError('enc %d' % e)
    return vals

def main(path, out):
    d = open(path, 'rb').read()
    hdr = {}; p = 0
    while d[p:p+2] == b'H ':
        e = d.index(b'\n', p); line = d[p+2:e].decode('latin1'); p = e + 1
        k, _, v = line.partition(':'); hdr[k] = v
    names = hdr['Field I name'].split(',')
    ints = lambda k: [int(x) for x in hdr[k].split(',')]
    Ienc, Ipred = ints('Field I encoding'), ints('Field I predictor')
    Penc, Ppred = ints('Field P encoding'), ints('Field P predictor')
    Snames = hdr['Field S name'].split(','); Senc = ints('Field S encoding')
    vbatref = int(hdr['vbatref'])
    n = len(names)
    rows = []; srows = []; events = []
    prev = prev2 = None; lastS = [0]*len(Snames)
    r = R(d, p); bad = 0
    valid = b'IPSE'
    while r.p < len(d):
        start = r.p; ft = d[r.p]; r.p += 1
        try:
            if ft == ord('I'):
                raw = read_fields(r, Ienc); v = []
                for i in range(n):
                    x = raw[i]; pr = Ipred[i]
                    if pr == 8: x += 1500
                    elif pr == 9: x += vbatref
                    v.append(x)
                fr = ('I', v)
            elif ft == ord('P'):
                if prev is None: raise ValueError('P without I')
                raw = read_fields(r, Penc); v = []
                for i in range(n):
                    x = raw[i]; pr = Ppred[i]
                    if pr == 1: x += prev[i]
                    elif pr == 2: x += 2*prev[i] - prev2[i]
                    elif pr == 3: x += int((prev[i] + prev2[i]) / 2)
                    elif pr == 6: x = prev[i] + 1
                    v.append(x)
                fr = ('P', v)
            elif ft == ord('S'):
                fr = ('S', read_fields(r, Senc))
            elif ft == ord('E'):
                t = r.b()
                if t in (0, 15, 50, 51, 52): data = [r.uvb()]
                elif t in (14, 30): data = [r.uvb(), r.uvb()]
                elif t == 13:
                    f = r.b()
                    if f & 128: data = [f & 127, struct.unpack('<f', d[r.p:r.p+4])[0]]; r.p += 4
                    else: data = [f, r.svb()]
                elif t in (100, 101):
                    L = r.b(); data = [d[r.p:r.p+L]]; r.p += L
                elif t == 255:
                    events.append((rows[-1][1] if rows else 0, 255, [])); break
                else: raise ValueError('event %d' % t)
                fr = ('E', (t, data))
            else:
                raise ValueError('frame %r' % ft)
            if r.p < len(d) and d[r.p] not in valid: raise ValueError('nextbad')
        except (ValueError, IndexError):
            bad += 1; prev = None
            nx = d.find(b'I', start + 1)
            if nx < 0: break
            r.p = nx; continue
        k, v = fr
        if k in 'IP':
            prev2 = prev if (k == 'P') else v
            prev = v
            if k == 'I': prev2 = v
            rows.append(v + lastS)
        elif k == 'S': lastS = v; srows.append(v)
        else: events.append((rows[-1][1] if rows else 0, v[0], v[1]))
    a = np.array(rows, dtype=np.int64)
    np.savez(out, data=a, names=np.array(names + Snames), hdr=np.array([f'{k}:{v}' for k, v in hdr.items()]),
             events=np.array([repr(e) for e in events]))
    print('frames', len(a), 'bad', bad, 'events', len(events))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
