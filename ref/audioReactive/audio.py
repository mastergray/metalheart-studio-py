"""
audio.py - turns a music file into per-video-frame control signals for metalheart.py.

Only needs numpy and the ffmpeg binary (any format ffmpeg can read works: mp3, wav,
flac, m4a, ogg, video files...).

What it measures, per video frame:
  bass / mid / high   loudness of 30-150 Hz, 150-2000 Hz, 2-10 kHz, normalised 0..1 for
                      this track, with fast attack and band-specific release
  onset               a spike on every detected hit (kick, snare, stab) that decays in ~0.15 s
  spectrum            24 log-spaced bands for the HUD bars
  energy              slow overall loudness, used to pick calm vs intense looks per section
Plus, for the whole track: tempo (BPM), a beat grid and the bar downbeats, so the
choreography can change looks exactly on phrase boundaries.
"""
import json
import subprocess
from dataclasses import dataclass, asdict

import numpy as np

SR = 22050
HOP = 256            # analysis hop (~11.6 ms) - finer than video frames so hits are timed well
NFFT = 2048


def load_audio(path, sr=SR, start=0.0, duration=None):
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start)]
    if duration:
        cmd += ["-t", str(duration)]
    cmd += ["-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    y = np.frombuffer(raw, np.float32).copy()
    if y.size == 0:
        raise ValueError(f"no audio decoded from {path}")
    return y


def _stft_mag(y):
    pad = NFFT // 2
    yp = np.pad(y, (pad, pad))
    n = 1 + (yp.size - NFFT) // HOP
    idx = np.arange(NFFT)[None, :] + HOP * np.arange(n)[:, None]
    win = np.hanning(NFFT).astype(np.float32)
    S = np.abs(np.fft.rfft(yp[idx] * win, axis=1)).astype(np.float32)
    freqs = np.fft.rfftfreq(NFFT, 1 / SR)
    return S, freqs


def _norm(x, lo=5, hi=98):
    a, b = np.percentile(x, lo), np.percentile(x, hi)
    return np.clip((x - a) / (b - a + 1e-9), 0, 1)


def _envelope(x, rate, attack, release):
    """Envelope follower: rises within `attack` s, falls within `release` s."""
    ka = 1 - np.exp(-1 / (rate * attack))
    kr = 1 - np.exp(-1 / (rate * release))
    out = np.empty_like(x)
    v = 0.0
    for i, s in enumerate(x):
        v += (s - v) * (ka if s > v else kr)
        out[i] = v
    return out


def _moving(x, w, fn):
    w = max(1, int(w))
    pad = np.pad(x, (w // 2, w - w // 2 - 1), mode="edge")
    view = np.lib.stride_tricks.sliding_window_view(pad, w)
    return fn(view, axis=1)


@dataclass
class Analysis:
    fps: float
    duration: float
    bpm: float
    beat_times: np.ndarray
    downbeat_times: np.ndarray
    bass: np.ndarray
    mid: np.ndarray
    high: np.ndarray
    onset: np.ndarray
    energy: np.ndarray
    spectrum: np.ndarray       # (frames, 24)

    @property
    def n_frames(self):
        return self.bass.size

    @property
    def bar(self):
        return 4 * 60.0 / self.bpm

    def summary(self):
        return dict(duration=round(self.duration, 2), bpm=round(self.bpm, 2), beats=int(self.beat_times.size),
                    first_downbeat=round(float(self.downbeat_times[0]), 3) if self.downbeat_times.size else None,
                    frames=int(self.n_frames), fps=self.fps)

    def save(self, path):
        np.savez_compressed(path, **{k: np.asarray(v) for k, v in asdict(self).items()})

    @classmethod
    def load(cls, path):
        z = np.load(path)
        return cls(**{k: (z[k].item() if z[k].ndim == 0 else z[k]) for k in z.files})


def _tempo(flux, rate, bpm_range=(70, 180), prior=120.0):
    f = flux - flux.mean()
    ac = np.correlate(f, f, mode="full")[f.size - 1:]
    lags = np.arange(ac.size)
    lo, hi = int(rate * 60 / bpm_range[1]), int(rate * 60 / bpm_range[0])
    bpms = 60 * rate / np.maximum(lags[lo:hi], 1)
    weight = np.exp(-0.5 * (np.log2(bpms / prior) / 0.9) ** 2)   # mild preference for ~120
    score = ac[lo:hi] * weight
    k = int(np.argmax(score)) + lo
    if 1 <= k < ac.size - 1:   # parabolic refinement of the peak lag
        a, b, c = ac[k - 1], ac[k], ac[k + 1]
        k = k + 0.5 * (a - c) / (a - 2 * b + c + 1e-12)
    return 60 * rate / k


def analyze(path, fps=24.0, start=0.0, duration=None, bpm_hint=None):
    y = load_audio(path, start=start, duration=duration)
    dur = y.size / SR
    S, freqs = _stft_mag(y)
    rate = SR / HOP
    P = S ** 2

    def band(lo, hi):
        m = (freqs >= lo) & (freqs < hi)
        return 10 * np.log10(P[:, m].sum(1) + 1e-10)

    raw = {"bass": band(30, 150), "mid": band(150, 2000), "high": band(2000, 10000)}
    rel = {"bass": 0.14, "mid": 0.22, "high": 0.09}
    env = {k: _envelope(_norm(v), rate, 0.008, rel[k]) for k, v in raw.items()}

    # onsets: positive spectral flux on log magnitude, low/mid weighted
    L = np.log1p(S * 10)
    w = np.where(freqs < 200, 1.6, np.where(freqs < 4000, 1.0, 0.5))[None, :]
    flux = np.r_[0, (np.maximum(np.diff(L, axis=0), 0) * w).sum(1)]
    flux = flux / (np.percentile(flux, 99) + 1e-9)
    thr = _moving(flux, rate * 0.4, np.median) + 0.12
    peaks = (flux > thr) & (flux >= _moving(flux, rate * 0.1, np.max))
    pk = np.nonzero(peaks)[0]
    keep, last = [], -1e9
    for p in pk:                      # minimum 90 ms between hits
        if p - last >= rate * 0.09:
            keep.append(p)
            last = p
    pk = np.array(keep, int)
    strength = np.clip((flux[pk] - thr[pk]) / 0.6, 0.25, 1.0) if pk.size else np.array([])
    tt = np.arange(flux.size) / rate
    onset = np.zeros_like(flux)
    for p, s in zip(pk, strength):
        seg = slice(p, min(flux.size, p + int(rate * 0.6)))
        onset[seg] = np.maximum(onset[seg], s * np.exp(-(tt[seg] - tt[p]) / 0.15))

    # tempo + beat grid
    bpm = float(bpm_hint) if bpm_hint else _tempo(flux, rate)
    period = 60 * rate / bpm
    # beat phase from low-end hits (kicks), so the grid doesn't lock onto offbeat bass or hats
    lowflux = np.r_[0, np.maximum(np.diff(L[:, freqs < 120], axis=0), 0).sum(1)]
    lowflux = lowflux / (np.percentile(lowflux, 99) + 1e-9)
    phases = np.arange(0, period, 0.5)
    comb = [lowflux[np.round(np.arange(ph, flux.size - 1, period)).astype(int)].sum() for ph in phases]
    ph0 = phases[int(np.argmax(comb))]
    beat_idx = np.arange(ph0, flux.size - 1, period)
    beat_times = beat_idx / rate
    # downbeat: the beat-in-bar position with the strongest low-end hits
    bi = np.round(beat_idx).astype(int)
    scores = [lowflux[bi[k::4]].mean() if bi[k::4].size else 0 for k in range(4)]
    downbeat_times = beat_times[int(np.argmax(scores))::4]

    # spectrum bars: 24 log bands
    edges = np.geomspace(40, 10000, 25)
    spec = np.stack([10 * np.log10(P[:, (freqs >= edges[i]) & (freqs < edges[i + 1])].sum(1) + 1e-10)
                     for i in range(24)], 1)
    spec = np.stack([_envelope(_norm(spec[:, i], 20, 99), rate, 0.005, 0.12) for i in range(24)], 1)

    # slow "intensity" for section decisions: sustained low end plus how busy the hits are
    energy = _moving(0.6 * env["bass"] + 0.4 * np.minimum(onset * 1.5, 1), rate * 2.0, np.mean)
    energy = energy / (np.percentile(energy, 98) + 1e-9)

    # resample everything to video frames (max over each frame's window keeps short hits)
    n = int(np.floor(dur * fps))
    ft = np.arange(n) / fps
    fi = np.clip(np.round(ft * rate).astype(int), 0, flux.size - 1)
    span = max(1, int(round(rate / fps)))

    def at_frames(x):
        return np.array([x[i:i + span].max() for i in fi], np.float32)

    return Analysis(
        fps=float(fps), duration=float(dur), bpm=float(bpm),
        beat_times=beat_times.astype(np.float32), downbeat_times=downbeat_times.astype(np.float32),
        bass=at_frames(env["bass"]), mid=at_frames(env["mid"]), high=at_frames(env["high"]),
        onset=at_frames(onset), energy=energy[fi].astype(np.float32),
        spectrum=np.stack([spec[fi, i] for i in range(24)], 1).astype(np.float32),
    )


def plan_looks(an: Analysis, calm, hot, bars_per_look=8, hot_threshold=0.6):
    """Split the track into phrases on the bar grid and pick a calm or intense look for each.

    Returns (sequence_of_looks, phrase_length_s, offset_s) for liquid3d.Choreo.
    """
    L = bars_per_look * an.bar
    first = float(an.downbeat_times[0]) if an.downbeat_times.size else 0.0
    offset = (first % L) - L if first % L > 1e-3 else 0.0
    n_seg = int(np.ceil((an.duration - offset) / L)) + 1
    seq, ci, hi = [], 0, 0
    for k in range(n_seg):
        a, b = offset + k * L, offset + (k + 1) * L
        fa, fb = max(0, int(a * an.fps)), min(an.n_frames, int(b * an.fps))
        e = float(an.energy[fa:fb].mean()) if fb > fa else 0.0
        if e > hot_threshold:
            seq.append(hot[hi % len(hot)])
            hi += 1
        else:
            seq.append(calm[ci % len(calm)])
            ci += 1
    return seq, L, offset


if __name__ == "__main__":
    import sys
    a = analyze(sys.argv[1])
    print(json.dumps(a.summary(), indent=2))
