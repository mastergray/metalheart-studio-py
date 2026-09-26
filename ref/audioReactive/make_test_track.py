"""Synthesises a 30 s, 128 BPM techno test track (intro / breakdown / drop) as WAV."""
import subprocess
import sys

import numpy as np

SR = 44100
BPM = 128.0
BEAT = 60 / BPM
LEAD_IN = 0.25          # first downbeat lands here, to test downbeat detection
BARS = 16
rng = np.random.default_rng(7)
N = int((LEAD_IN + BARS * 4 * BEAT + 1.0) * SR)
out = np.zeros(N, np.float32)


def at(t):
    return int((LEAD_IN + t) * SR)


def add(sig, t, gain=1.0):
    i = at(t)
    j = min(N, i + sig.size)
    out[i:j] += sig[: j - i] * gain


def env(n, attack, decay):
    t = np.arange(n) / SR
    return np.minimum(t / max(attack, 1e-4), 1) * np.exp(-t / decay)


def kick():
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 48 + 110 * np.exp(-t / 0.035)
    return np.tanh(2.2 * np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.001, 0.16)).astype(np.float32)


def noise_hit(dur, decay, hp=True):
    n = int(dur * SR)
    x = rng.standard_normal(n).astype(np.float32)
    if hp:
        x = np.diff(np.r_[0, x])
    return x * env(n, 0.0005, decay)


def clap():
    x = noise_hit(0.3, 0.09)
    x = np.convolve(x, np.ones(8) / 8, "same")          # crude band-limit
    return x * 1.8


def tone(freq, dur, decay, shape="saw"):
    n = int(dur * SR)
    t = np.arange(n) / SR
    ph = (freq * t) % 1
    w = 2 * ph - 1 if shape == "saw" else np.sin(2 * np.pi * freq * t)
    return (w * env(n, 0.003, decay)).astype(np.float32)


def lowpass(x, a):
    y = np.empty_like(x)
    v = 0.0
    for i, s in enumerate(x):
        v += a * (s - v)
        y[i] = v
    return y


bass_notes = [36, 36, 39, 36, 34, 36, 41, 39]
hz = lambda m: 440 * 2 ** ((m - 69) / 12)  # noqa: E731

for bar in range(BARS):
    intro, breakdown, drop = bar < 4, 4 <= bar < 8, bar >= 8
    for b in range(4):
        t = (bar * 4 + b) * BEAT
        if not breakdown:
            add(kick(), t, 0.9)
        if drop and b in (1, 3):
            add(clap(), t, 0.35)
        for s in range(4):   # 16th hats
            ts = t + s * BEAT / 4
            if s == 2:
                add(noise_hit(0.2, 0.06 if drop else 0.03), ts, 0.16 if drop else 0.1)
            elif not breakdown:
                add(noise_hit(0.05, 0.012), ts, 0.07)
        if not breakdown:    # offbeat rolling bass
            note = bass_notes[(bar * 4 + b) % len(bass_notes)]
            add(lowpass(tone(hz(note), BEAT * 0.45, 0.12), 0.08 if intro else 0.14), t + BEAT / 2, 0.55)
        if drop and b == 0 and bar % 2 == 0:   # chord stab
            for m in (60, 63, 67):
                add(lowpass(tone(hz(m), 0.4, 0.15), 0.25), t, 0.12)
    if breakdown:            # sustained pad + rising noise
        t0 = bar * 4 * BEAT
        n = int(4 * BEAT * SR)
        tt = np.arange(n) / SR
        pad = sum(np.sin(2 * np.pi * hz(m) * tt + np.sin(2 * np.pi * 0.3 * tt)) for m in (48, 55, 60, 63)) * 0.05
        rise = (bar - 4 + tt / (4 * BEAT)) / 4
        noise = lowpass(rng.standard_normal(n).astype(np.float32), 0.05 + 0.4 * rise.mean()) * rise * 0.5
        add((pad * np.minimum(tt / 0.5, 1)).astype(np.float32) + noise, t0)

out = np.tanh(out * 1.3) * 0.8
path = sys.argv[1] if len(sys.argv) > 1 else "test_track.wav"
raw = (np.clip(out, -1, 1) * 32767).astype(np.int16).tobytes()
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "-", path],
               input=raw, check=True)
print(f"wrote {path}: {N / SR:.1f}s, {BPM} BPM, first downbeat at {LEAD_IN}s, drop at bar 9 "
      f"({LEAD_IN + 8 * 4 * BEAT:.2f}s)")
