# -*- coding: utf-8 -*-
"""Sáng tác 10 bản nhạc nền nhẹ nhàng (không lời, bản quyền của Du Học Hải Dương) bằng tổng hợp âm thanh."""
import os, subprocess, sys
import numpy as np

SR = 44100
OUT = sys.argv[1] if len(sys.argv) > 1 else 'out'
FF = sys.argv[2] if len(sys.argv) > 2 else 'ffmpeg'
os.makedirs(OUT, exist_ok=True)

NOTE = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8,
        'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11}
MAJOR = [0, 2, 4, 5, 7, 9, 11]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def adsr(n, a=0.01, d=0.1, s=0.7, r=0.2):
    a, d, r = int(a * SR), int(d * SR), int(r * SR)
    env = np.full(n, s, dtype=np.float32)
    a = min(a, n); env[:a] = np.linspace(0, 1, a)
    d2 = min(d, max(0, n - a)); env[a:a + d2] = np.linspace(1, s, d2)
    r = min(r, n); env[n - r:] *= np.linspace(1, 0, r)
    return env


def epiano(f, dur, vel=0.5):
    n = int(dur * SR); t = np.arange(n) / SR
    dec = np.exp(-t * (2.2 + f / 900))
    x = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 6)
         + 0.12 * np.sin(2 * np.pi * 3 * f * t) * np.exp(-t * 9) + 0.08 * np.sin(2 * np.pi * 14 * f * t) * np.exp(-t * 40))
    return (x * dec * adsr(n, 0.004, 0.05, 1.0, 0.08) * vel).astype(np.float32)


def pluck(f, dur, vel=0.5, bright=0.5, rng=None):
    """Karplus-Strong (đàn guitar/harp)."""
    n = int(dur * SR); p = max(2, int(SR / f))
    rng = rng or np.random.default_rng(0)
    buf = rng.uniform(-1, 1, p).astype(np.float32)
    out = np.zeros(n, dtype=np.float32)
    k = 0.5 * (0.994 + 0.005 * bright)
    for i in range(0, n, p):
        seg = buf[: min(p, n - i)]
        out[i:i + len(seg)] = seg
        buf = k * (buf + np.roll(buf, 1)) * 0.998 + 0.002 * buf
    lp = np.convolve(out, np.ones(2) / 2, 'same')
    return (lp * vel * adsr(n, 0.001, 0.02, 1.0, 0.05)).astype(np.float32)


def bell(f, dur, vel=0.4):
    n = int(dur * SR); t = np.arange(n) / SR
    x = (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 3)
         + 0.25 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t * 6))
    return (x * np.exp(-t * 2.5) * vel * adsr(n, 0.002, 0.01, 1, 0.05)).astype(np.float32)


def marimba(f, dur, vel=0.5):
    n = int(dur * SR); t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * f * 4 * t) * np.exp(-t * 25)
    return (x * np.exp(-t * 7) * vel * adsr(n, 0.002, 0.01, 1, 0.03)).astype(np.float32)


def pad(freqs, dur, vel=0.25):
    n = int(dur * SR); t = np.arange(n) / SR
    x = np.zeros(n, dtype=np.float32)
    for f in freqs:
        for det in (-0.12, 0.0, 0.11):
            ff = f * 2 ** (det / 12)
            x += (np.sin(2 * np.pi * ff * t) + 0.3 * np.sin(2 * np.pi * 2 * ff * t) + 0.12 * np.sin(2 * np.pi * 3 * ff * t))
    x /= max(1, len(freqs) * 3)
    return (x * adsr(n, min(0.6, dur / 3), 0.2, 0.9, min(0.6, dur / 3)) * vel).astype(np.float32)


def bass(f, dur, vel=0.5):
    n = int(dur * SR); t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.2 * np.sin(2 * np.pi * 2 * f * t)
    return (x * adsr(n, 0.01, 0.15, 0.6, 0.08) * vel).astype(np.float32)


def kick(vel=0.6):
    n = int(0.35 * SR); t = np.arange(n) / SR
    f = 50 + 90 * np.exp(-t * 30)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9) * vel).astype(np.float32)


def hat(rng, vel=0.12, dur=0.05):
    n = int(dur * SR); x = rng.standard_normal(n).astype(np.float32)
    x = x - np.convolve(x, np.ones(3) / 3, 'same')
    return (x * np.exp(-np.arange(n) / SR * 60) * vel).astype(np.float32)


def shaker(rng, vel=0.08):
    n = int(0.09 * SR); x = rng.standard_normal(n).astype(np.float32)
    x = x - np.convolve(x, np.ones(5) / 5, 'same')
    env = np.sin(np.linspace(0, np.pi, n)) ** 2
    return (x * env * vel).astype(np.float32)


def snap(rng, vel=0.18):
    n = int(0.18 * SR); t = np.arange(n) / SR
    x = rng.standard_normal(n).astype(np.float32)
    x = np.convolve(x, np.ones(3) / 3, 'same') - np.convolve(x, np.ones(25) / 25, 'same')
    return (x * np.exp(-t * 28) * vel).astype(np.float32)


def add(buf, x, at, pan=0.0):
    i = int(at * SR)
    if i >= buf.shape[0]:
        return
    j = min(buf.shape[0], i + len(x))
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buf[i:j, 0] += x[:j - i] * l * 1.41
    buf[i:j, 1] += x[:j - i] * r * 1.41


def reverb(buf, wet=0.25, rt=1.6, seed=3):
    rng = np.random.default_rng(seed)
    n = int(rt * SR); t = np.arange(n) / SR
    out = np.empty_like(buf)
    L = buf.shape[0] + n
    nfft = 1 << (L - 1).bit_length()
    for c in range(2):
        ir = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 6.9 / rt)
        ir = np.convolve(ir, np.ones(8) / 8, 'same'); ir[:int(0.012 * SR)] = 0
        ir /= np.sqrt((ir ** 2).sum()) + 1e-9
        y = np.fft.irfft(np.fft.rfft(buf[:, c], nfft) * np.fft.rfft(ir, nfft), nfft)[:buf.shape[0]]
        out[:, c] = buf[:, c] + wet * y.astype(np.float32)
    return out


def chord_notes(root_midi, degree, ext=False):
    """Hợp âm thuận (bậc 1..7) trong giọng trưởng; trả về list midi."""
    idx = [(degree - 1 + k) % 7 for k in (0, 2, 4)] + ([(degree - 1 + 6) % 7] if ext else [])
    notes = []
    for j, k in enumerate(idx):
        m = root_midi + MAJOR[k] + 12 * ((degree - 1 + 2 * j) // 7)
        notes.append(m)
    return notes


def song(name, key, bpm, prog, lead, bars=32, seed=1, drums='soft', pad_on=True, ext=False, swing=0.0,
         lead_oct=0, arp='up', density=0.7):
    rng = np.random.default_rng(seed)
    beat = 60 / bpm
    bar = 4 * beat
    total = bars * bar + 3.0
    buf = np.zeros((int(total * SR), 2), dtype=np.float32)
    root = 48 + NOTE[key]                      # C3..B3
    scale = [root + 12 + MAJOR[i % 7] + 12 * (i // 7) for i in range(14)]
    inst = {'epiano': epiano, 'pluck': lambda f, d, v: pluck(f, d, v, 0.5, rng), 'bell': bell, 'marimba': marimba}[lead]
    mel_prev = 4
    for b in range(bars):
        deg = prog[b % len(prog)]
        t0 = b * bar
        cn = chord_notes(root, deg, ext)
        section = 0 if b < 4 else (1 if b < bars - 4 else 2)    # mở đầu / thân / kết
        if pad_on:
            add(buf, pad([hz(m) for m in cn], bar + 0.3, 0.16 if section != 1 else 0.13), t0, 0.0)
        # bass
        if section >= 1 or b >= 2:
            add(buf, bass(hz(cn[0] - 12), beat * 1.8, 0.42), t0)
            add(buf, bass(hz(cn[0] - 12 + (7 if b % 2 else 0)), beat * 1.6, 0.32), t0 + 2 * beat)
        # arpeggio
        pat = {'up': [0, 1, 2, 3, 2, 1, 0, 1], 'wave': [0, 2, 1, 3, 2, 1, 3, 1], 'pop': [0, 2, 3, 2, 1, 2, 3, 2]}[arp]
        arpn = cn + [cn[0] + 12]
        for k in range(8):
            if section == 0 and k % 2:
                continue
            tt = t0 + k * beat / 2 + (swing * beat / 2 if k % 2 else 0)
            m = arpn[pat[k]] + 12 * lead_oct
            add(buf, inst(hz(m), beat * 1.4, 0.22), tt, -0.35 if k % 2 else 0.35)
        # giai điệu đơn giản (thân bài)
        if section == 1:
            for k in range(4):
                if rng.random() > density:
                    continue
                step = int(rng.choice([-2, -1, -1, 0, 1, 1, 2]))
                mel_prev = int(np.clip(mel_prev + step, 2, 11))
                # rơi vào nốt hợp âm ở phách 1
                if k == 0:
                    cands = [i for i in range(14) if (scale[i] - cn[0]) % 12 in [(x - cn[0]) % 12 for x in cn]]
                    mel_prev = min(cands, key=lambda i: abs(i - mel_prev))
                m = scale[mel_prev] + 12 * lead_oct
                add(buf, inst(hz(m), beat * 1.6, 0.30), t0 + k * beat, 0.1)
        # trống
        if drums != 'none' and 2 <= b < bars - 1:
            for k in range(4):
                tt = t0 + k * beat
                if drums in ('soft', 'pop') and k in (0, 2):
                    add(buf, kick(0.55 if drums == 'pop' else 0.42), tt)
                if drums == 'pop' and k in (1, 3):
                    add(buf, snap(rng, 0.16), tt, 0.1)
                if drums == 'lofi' and k in (0,):
                    add(buf, kick(0.4), tt)
                if drums == 'lofi' and k in (2,):
                    add(buf, snap(rng, 0.12), tt)
                for h in range(2):
                    th = tt + h * beat / 2 + (swing * beat / 2 if h else 0)
                    add(buf, hat(rng, 0.07 if h else 0.05) if drums != 'shaker' else shaker(rng, 0.06), th,
                        0.4 if h else -0.4)
    # kết: hợp âm chủ ngân
    add(buf, pad([hz(m) for m in chord_notes(root, 1)], 3.0, 0.18), bars * bar, 0.0)
    add(buf, inst(hz(root + 12), 2.5, 0.25), bars * bar, 0.0)
    buf = reverb(buf, 0.22, 1.8, seed)
    # chuẩn hoá + fade
    peak = np.abs(buf).max() + 1e-9
    buf = buf / peak * 0.89
    fi, fo = int(1.0 * SR), int(2.5 * SR)
    buf[:fi] *= np.linspace(0, 1, fi)[:, None]
    buf[-fo:] *= np.linspace(1, 0, fo)[:, None]
    wav = os.path.join(OUT, name + '.wav')
    import wave
    with wave.open(wav, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(buf, -1, 1) * 32767).astype(np.int16).tobytes())
    mp3 = os.path.join(OUT, name + '.mp3')
    subprocess.run([FF, '-y', '-loglevel', 'error', '-i', wav, '-c:a', 'libmp3lame', '-b:a', '128k', mp3], check=True)
    os.remove(wav)
    print(name, '%.0fs' % total)


SONGS = [
    # tên file                  giọng  bpm  vòng hợp âm        nhạc cụ   ...
    ('nhe_nhang_piano',          'C',  84, [1, 5, 6, 4],      'epiano',  dict(drums='none', arp='up', seed=11)),
    ('tuoi_sang_buoi_sang',      'G',  104, [1, 5, 6, 4],     'pluck',   dict(drums='soft', arp='pop', seed=12)),
    ('hy_vong_tuong_lai',        'D',  92, [6, 4, 1, 5],      'epiano',  dict(drums='soft', arp='wave', seed=13, ext=True)),
    ('chuyen_bay_uoc_mo',        'A',  100, [1, 6, 4, 5],     'bell',    dict(drums='shaker', arp='up', seed=14)),
    ('lofi_hoc_bai',             'F',  78, [2, 5, 1, 6],      'epiano',  dict(drums='lofi', arp='wave', seed=15, ext=True, swing=0.18)),
    ('vui_tuoi_marimba',         'C',  110, [1, 4, 5, 4],     'marimba', dict(drums='pop', arp='pop', seed=16, lead_oct=1)),
    ('am_ap_gia_dinh',           'Eb', 80, [1, 6, 2, 5],      'pluck',   dict(drums='none', arp='wave', seed=17, ext=True)),
    ('tu_tin_buoc_toi',          'E',  108, [1, 5, 4, 5],     'pluck',   dict(drums='pop', arp='up', seed=18)),
    ('bau_troi_dai_loan',        'Bb', 90, [4, 5, 3, 6],      'bell',    dict(drums='shaker', arp='wave', seed=19)),
    ('thanh_cong_ruc_ro',        'D',  112, [1, 5, 6, 3, 4, 1, 4, 5], 'marimba', dict(drums='pop', arp='pop', seed=20, lead_oct=1)),
    ('chill_cuoi_tuan',          'G',  82, [1, 3, 4, 5],      'pluck',   dict(drums='lofi', arp='wave', seed=21, swing=0.15)),
    ('khoi_dau_moi',             'F',  96, [4, 1, 5, 6],      'epiano',  dict(drums='soft', arp='pop', seed=22)),
]

if __name__ == '__main__':
    only = os.environ.get('ONLY')
    for name, key, bpm, prog, lead, kw in SONGS:
        if only and only != name:
            continue
        song(name, key, bpm, prog, lead, **kw)
