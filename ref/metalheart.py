#!/usr/bin/env python3
"""
metalheart.py - CPU-only renderer for Metalheart / Depthcore-style frames (c. 1998-2004).

Layers, back to front:
  1. Dark radial background, faint nebula noise, dot grid
  2. Blurred "ghost" copies of the foreground (fake depth of field)
  3. Drop shadows
  4. Foreground chrome: twisted ribbons, machined plates, liquid blob
     (height fields shaded with a procedural chrome matcap - no 3D, no GPU)
  5. HUD: brackets, reticle, rulers, tech readouts, barcode, spectrum bars
  6. Post: bloom, anamorphic streaks, chromatic offset, grain, vignette

Every frame is a pure function of (t, Params), so an audio analyser can drive
it later by filling in Params each frame.

Usage:
  python metalheart.py still -o frame.png --preset steel --seed 3 --t 2.0
  python metalheart.py clip  -o test.mp4  --seconds 8 --fps 24 --size 1280x720
"""
import argparse
import math
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter

import liquid3d

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

# ----------------------------------------------------------------------------- palettes
# RGB floats. sky/ground define the chrome reflection environment.
PRESETS = {
    "steel": dict(
        sky_top=(0.06, 0.16, 0.36), sky_hor=(0.80, 0.90, 1.00),
        ground_hor=(0.03, 0.035, 0.05), ground_low=(0.26, 0.29, 0.34),
        key=(1.0, 1.0, 1.0), rim=(0.30, 0.70, 1.00),
        accent=(1.00, 0.52, 0.08), hud=(0.72, 0.88, 1.00),
        bg_center=(0.055, 0.10, 0.15), bg_edge=(0.0, 0.0, 0.008),
    ),
    "acid": dict(
        sky_top=(0.03, 0.14, 0.09), sky_hor=(0.82, 1.00, 0.86),
        ground_hor=(0.02, 0.03, 0.025), ground_low=(0.20, 0.25, 0.22),
        key=(0.95, 1.0, 0.95), rim=(0.45, 1.00, 0.30),
        accent=(0.80, 1.00, 0.05), hud=(0.68, 1.00, 0.74),
        bg_center=(0.035, 0.09, 0.06), bg_edge=(0.0, 0.004, 0.0),
    ),
    "ember": dict(
        sky_top=(0.30, 0.10, 0.03), sky_hor=(1.00, 0.90, 0.76),
        ground_hor=(0.05, 0.035, 0.03), ground_low=(0.30, 0.27, 0.25),
        key=(1.0, 0.97, 0.92), rim=(1.00, 0.48, 0.12),
        accent=(1.00, 0.30, 0.04), hud=(1.00, 0.86, 0.70),
        bg_center=(0.11, 0.055, 0.03), bg_edge=(0.008, 0.0, 0.0),
    ),
}


@dataclass
class Params:
    """Per-frame control signals, 0..1. Audio analysis will fill these later."""
    bass: float = 0.3
    mid: float = 0.3
    high: float = 0.3
    onset: float = 0.0
    spectrum: Optional[np.ndarray] = None  # optional N-band magnitudes for HUD bars


# ----------------------------------------------------------------------------- helpers
def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def rgb(c):
    return np.asarray(c, np.float32)


class Noise:
    """Tileable smooth-noise textures sampled with cv2.remap (fast, sub-pixel smooth)."""

    def __init__(self, rng, size=512, sigmas=(40, 18, 7, 2.5)):
        self.size = size
        self.tex = []
        for s in sigmas:
            n = rng.standard_normal((size, size)).astype(np.float32)
            n = gaussian_filter(n, s, mode="wrap")
            n = (n - n.mean()) / (n.std() + 1e-8)
            self.tex.append(n.astype(np.float32))

    def sample(self, i, X, Y):
        s = self.size
        return cv2.remap(self.tex[i], np.mod(X, s).astype(np.float32), np.mod(Y, s).astype(np.float32),
                         cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)


def environment(rx, up, rz, pal, bands=1.0):
    """Procedural studio environment seen in chrome: sky, hard horizon, ground, softboxes."""
    sky_t = np.clip(up, 0, 1) ** 0.55
    sky = rgb(pal["sky_hor"]) * (1 - sky_t)[..., None] + rgb(pal["sky_top"]) * sky_t[..., None]
    g_t = np.clip(-up, 0, 1) ** 0.5
    ground = rgb(pal["ground_hor"]) * (1 - g_t)[..., None] + rgb(pal["ground_low"]) * g_t[..., None]
    # contour bands in the reflected floor + thin lines in the sky: the stripey Depthcore chrome look
    band = smoothstep(0.55, 0.75, np.sin(-up * 38.0 + np.sin(rx * 3.0) * 0.8)) * np.clip(-up * 3, 0, 1)
    ground = ground + band[..., None] * rgb(pal["sky_hor"]) * 0.22 * bands
    lines = smoothstep(0.92, 0.98, np.sin(up * 55.0)) * np.clip(up * 4, 0, 1)
    sky = sky + lines[..., None] * rgb(pal["key"]) * 0.35 * bands
    m = smoothstep(-0.015, 0.015, up)[..., None]
    img = ground * (1 - m) + sky * m
    # bright line right above the horizon, dark band right below: the classic chrome look
    img = img + (np.exp(-((up - 0.035) / 0.02) ** 2) * 1.1)[..., None] * rgb(pal["sky_hor"])
    img = img * (1 - 0.85 * np.exp(-((up + 0.06) / 0.05) ** 2))[..., None]

    def lobe(L, lo, hi):
        L = np.asarray(L, np.float32)
        L = L / np.linalg.norm(L)
        return smoothstep(lo, hi, rx * L[0] + up * L[1] + rz * L[2])

    key = rgb(pal["key"])
    img = img + lobe((-0.55, 0.55, 0.62), 0.955, 0.972)[..., None] * key * 2.2   # hard key softbox
    img = img + lobe((-0.55, 0.55, 0.62), 0.70, 1.0)[..., None] * key * 0.35     # its falloff
    # vertical strip light on the right
    strip = smoothstep(0.07, 0.03, np.abs(rx - 0.62)) * smoothstep(-0.3, 0.1, up) * (rz > -0.2)
    img = img + strip[..., None] * key * 1.4
    # coloured rim fill from behind
    img = img + lobe((0.0, -0.2, -1.0), 0.75, 1.0)[..., None] * rgb(pal["rim"]) * 0.45
    return img.astype(np.float32)


def build_matcap(pal, size=512):
    c = (size - 1) / 2.0
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    nx, ny = (xx - c) / c, (yy - c) / c
    d = np.sqrt(nx * nx + ny * ny)
    scale = 1.0 / np.maximum(d, 1.0)  # clamp outside disk to the silhouette normal
    nx, ny = nx * scale, ny * scale
    nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))
    rx, ry, rz = 2 * nz * nx, 2 * nz * ny, 2 * nz * nz - 1  # reflect eye vector (0,0,1)
    up = -ry * 0.92 - rz * 0.38  # tilt env: surfaces facing camera reflect the dark ground
    return environment(rx, up, rz, pal)


# ----------------------------------------------------------------------------- renderer
class MetalheartRenderer:
    def __init__(self, width=1280, height=720, seed=1, preset="steel", scanlines=True,
                 core="3d", looks=("mercury",), cams=("orbit",), look_len=6.0, cam_len=9.0,
                 core_scale=0.5, decor=True, aa=True):
        self.W, self.H = W, H = width, height
        self.seed = seed
        self.pal = PRESETS[preset]
        self.scanlines = scanlines
        self.core_mode, self.decor, self.aa = core, decor, aa
        self.pan = (0.0, 0.0)
        self.hud_mode = "LEGACY.2D"
        if core == "3d":
            self.core3d = liquid3d.CoreRenderer(W, H, environment, self.pal, seed=seed, scale=core_scale, decor=decor)
            self.choreo = liquid3d.Choreo(looks, cams, look_len, cam_len)
        rng = np.random.default_rng(seed)
        self.noise = Noise(np.random.default_rng(seed + 7919))
        self.matcap = build_matcap(self.pal)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.u = (xx - W / 2) / H  # normalized coords, v in [-0.5, 0.5]
        self.v = (yy - H / 2) / H

        # metaballs for the liquid core
        side = rng.choice([-1, 1])
        self.core = np.array([side * rng.uniform(0.12, 0.28), rng.uniform(-0.06, 0.04)], np.float32)
        self.balls = []
        for i in range(6):
            self.balls.append(dict(
                x=rng.uniform(-0.13, 0.13), y=rng.uniform(-0.10, 0.10),
                ax=rng.uniform(0.03, 0.09), ay=rng.uniform(0.03, 0.08),
                wx=rng.uniform(0.3, 0.9) * rng.choice([-1, 1]), wy=rng.uniform(0.3, 0.9),
                px=rng.uniform(0, 6.28), py=rng.uniform(0, 6.28),
                r=rng.uniform(0.045, 0.085) if i else 0.10, react=rng.uniform(0.4, 1.0)))

        # twisted ribbons / blades. dof>0 = out-of-focus foreground element
        self.ribbons = []
        specs = [("back", 0.0), ("front", 0.0), ("front", 0.0), ("front", 1.0)]
        for i, (layer, dof) in enumerate(specs):
            big = dof > 0
            self.ribbons.append(dict(
                layer=layer, dof=dof,
                cx=rng.uniform(-0.3, 0.3) if not big else -side * 0.55,
                cy=rng.uniform(-0.2, 0.2) if not big else rng.uniform(0.25, 0.4),
                angle=rng.uniform(-0.5, 0.5) + (0 if i % 2 == 0 else math.pi / 2 * 0.3),
                amp=rng.uniform(0.03, 0.09), freq=rng.uniform(3, 7), speed=rng.uniform(0.3, 0.8),
                ph=rng.uniform(0, 6.28), ph2=rng.uniform(0, 6.28),
                twist=rng.uniform(4, 10), tspeed=rng.uniform(0.4, 1.0) * rng.choice([-1, 1]),
                w=rng.uniform(0.012, 0.028) * (3.5 if big else 1.0),
                length=rng.uniform(0.45, 0.8) * (1.3 if big else 1.0)))

        # machined plates: chamfered polygons with slots, drawn as masks
        self.plates = []
        for i in range(3):
            w, h = rng.uniform(0.24, 0.46), rng.uniform(0.05, 0.11)
            c = min(w, h) * rng.uniform(0.25, 0.5)
            kind = rng.choice(["chamfer", "blade"])
            if kind == "chamfer":
                poly = [(-w / 2 + c, -h / 2), (w / 2 - c, -h / 2), (w / 2, -h / 2 + c), (w / 2, h / 2 - c),
                        (w / 2 - c, h / 2), (-w / 2 + c, h / 2), (-w / 2, h / 2 - c), (-w / 2, -h / 2 + c)]
            else:
                poly = [(-w / 2, -h / 2), (w / 2 - h, -h / 2), (w / 2, 0), (w / 2 - h, h / 2), (-w / 2 + h * 0.6, h / 2)]
            self.plates.append(dict(
                poly=np.array(poly, np.float32), w=w, h=h,
                x=rng.uniform(-0.55, 0.55), y=rng.uniform(-0.32, 0.32),
                ang=rng.uniform(-0.6, 0.6), drift=rng.uniform(-0.02, 0.02, 2), spin=rng.uniform(-0.05, 0.05),
                tilt=rng.uniform(-0.8, 0.8, 2), slots=int(rng.integers(1, 4)), holes=int(rng.integers(0, 4)),
                seed=int(rng.integers(0, 1 << 30))))

        # HUD: fonts, fixed layout choices, dot grid
        self.font = ImageFont.truetype(FONT_PATH, max(9, int(H * 0.0165)))
        self.font_small = ImageFont.truetype(FONT_PATH, max(8, int(H * 0.0125)))
        self.font_big = ImageFont.truetype(FONT_BOLD, max(12, int(H * 0.034)))
        self.font_tag = ImageFont.truetype(FONT_BOLD, max(9, int(H * 0.018)))
        self.hud_rng_seed = seed
        self.barcode = rng.integers(1, 4, 44)
        self.markers = [(rng.uniform(0.08, 0.92), rng.uniform(0.1, 0.9)) for _ in range(9)]
        self.hline_y = rng.uniform(0.18, 0.3)
        dots = np.zeros((H, W), np.float32)
        step = max(8, int(H / 30))
        dots[step // 2::step, step // 2::step] = 1.0
        self.dots = cv2.GaussianBlur(dots, (0, 0), 0.6) * 3.0

    # ------------------------------------------------------------------ shading
    def shade(self, hp):
        """Height field (pixel units) -> chrome colour via matcap lookup, plus facing ratio."""
        gx = cv2.Sobel(hp, cv2.CV_32F, 1, 0, ksize=3) / 8.0
        gy = cv2.Sobel(hp, cv2.CV_32F, 0, 1, ksize=3) / 8.0
        inv = 1.0 / np.sqrt(gx * gx + gy * gy + 1.0)
        nx, ny, nz = -gx * inv, -gy * inv, inv
        c = (self.matcap.shape[0] - 1) / 2.0
        col = cv2.remap(self.matcap, (nx * c + c).astype(np.float32), (ny * c + c).astype(np.float32),
                        cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        rim = ((1 - nz) ** 4)[..., None] * rgb(self.pal["rim"]) * 0.35
        return col + rim

    # ------------------------------------------------------------------ elements
    def warp(self, t, P):
        a = 0.035 + 0.06 * P.bass
        wu = self.u + a * self.noise.sample(0, self.u * 260 + t * 14, self.v * 260 + 50)
        wv = self.v + a * self.noise.sample(0, self.u * 260 + 311, self.v * 260 - t * 14)
        return wu, wv

    def blob(self, t, P, wu, wv):
        H = self.H
        f = np.zeros_like(wu)
        cx0, cy0 = self.core
        for b in self.balls:
            cx = cx0 + b["x"] + b["ax"] * math.sin(b["wx"] * t + b["px"])
            cy = cy0 + b["y"] + b["ay"] * math.cos(b["wy"] * t + b["py"])
            r = b["r"] * (1 + 0.45 * P.bass * b["react"])
            f += (r * r) / ((wu - cx) ** 2 + (wv - cy) ** 2 + 1e-5)
        f *= 1 + 0.18 * self.noise.sample(1, wu * 500 + t * 20, wv * 500)
        alpha = smoothstep(0.97, 1.03, f)
        h = np.minimum(np.sqrt(np.maximum(np.log(np.maximum(f, 1e-3)), 0)) * 0.7, 1.6)  # one dome per metaball
        ridge = 1 - np.abs(self.noise.sample(1, wu * 420 - t * 25, wv * 420 + t * 10))
        swell = self.noise.sample(0, wu * 600 + t * 12, wv * 600 - t * 8)
        hp = h * H * 0.24 + swell * H * 0.05 * h + (ridge ** 4) * H * 0.035 * h
        return hp.astype(np.float32), alpha.astype(np.float32)

    def ribbon(self, rb, t, P, wu, wv):
        H = self.H
        ca, sa = math.cos(rb["angle"]), math.sin(rb["angle"])
        du, dv = wu - rb["cx"], wv - rb["cy"]
        x = du * ca + dv * sa
        y = -du * sa + dv * ca
        center = rb["amp"] * np.sin(rb["freq"] * x + t * rb["speed"] + rb["ph"])
        d = y - center
        theta = rb["twist"] * x + t * rb["tspeed"] * (1 + 1.5 * P.mid) + rb["ph2"]
        L = rb["length"]
        taper = smoothstep(-L, -L + 0.3, x) * smoothstep(L, L - 0.3, x)
        w = rb["w"] * (0.1 + 0.9 * np.abs(np.cos(theta))) * taper * (1 + 0.4 * P.bass)
        aa = 0.8 / H
        alpha = np.clip((w - np.abs(d)) / (2 * aa) + 0.5, 0, 1)
        s = d / (w + 1e-5)
        tilt = np.clip(np.tan(theta), -3, 3)
        hp = d * H * tilt + np.sqrt(np.clip(1 - s * s, 0, 1)) * w * H * 0.8
        return hp.astype(np.float32), alpha.astype(np.float32)

    def plate(self, pl, t, P):
        W, H = self.W, self.H
        ang = pl["ang"] + pl["spin"] * t
        push = 1 + 0.05 * P.bass
        cx = (pl["x"] + pl["drift"][0] * t) * push - self.pan[0] * 0.7
        cy = (pl["y"] + pl["drift"][1] * t) * push - self.pan[1] * 0.7
        R = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]], np.float32)
        pts = pl["poly"] @ R.T + np.array([cx, cy], np.float32)
        px = np.round((pts * H + np.array([W / 2, H / 2])) * 16).astype(np.int32)
        mask = np.zeros((H, W), np.uint8)
        cv2.fillPoly(mask, [px], 255, cv2.LINE_AA, shift=4)
        # machined cut-outs
        prng = np.random.default_rng(pl["seed"])
        for k in range(pl["slots"]):
            a = np.array([prng.uniform(-0.35, 0.1) * pl["w"], (k - (pl["slots"] - 1) / 2) * pl["h"] * 0.28], np.float32)
            b = a + np.array([pl["w"] * prng.uniform(0.15, 0.3), 0], np.float32)
            pa = ((a @ R.T + [cx, cy]) * H + [W / 2, H / 2]).astype(int)
            pb = ((b @ R.T + [cx, cy]) * H + [W / 2, H / 2]).astype(int)
            cv2.line(mask, tuple(pa), tuple(pb), 0, max(2, int(pl["h"] * H * 0.1)), cv2.LINE_AA)
        for k in range(pl["holes"]):
            a = np.array([pl["w"] * (0.3 + 0.06 * k), 0], np.float32)
            pa = ((a @ R.T + [cx, cy]) * H + [W / 2, H / 2]).astype(int)
            cv2.circle(mask, tuple(pa), max(2, int(pl["h"] * H * 0.12)), 0, -1, cv2.LINE_AA)
        alpha = mask.astype(np.float32) / 255.0
        dist = cv2.distanceTransform((mask > 127).astype(np.uint8), cv2.DIST_L2, 5)
        bevel = H * 0.011
        hp = np.minimum(dist, bevel)
        # tilted top face + brushed streaks along the plate's axis
        ru = self.u - cx
        rv = self.v - cy
        along = ru * math.cos(ang) + rv * math.sin(ang)
        across = -ru * math.sin(ang) + rv * math.cos(ang)
        hp = hp + (dist > bevel) * (pl["tilt"][0] * along + pl["tilt"][1] * across) * H * 0.9
        brushed = self.noise.sample(3, along * 60 + pl["seed"] % 500, across * 4000)
        hp = hp + brushed * 0.25 * (dist > 1)
        return hp.astype(np.float32), alpha

    # ------------------------------------------------------------------ hud
    def hud(self, t, P, focus):
        W, H = self.W, self.H
        pal = self.pal
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        hc = tuple(int(c * 255) for c in pal["hud"])
        ac = tuple(int(c * 255) for c in pal["accent"])
        flick = 1.0 - 0.35 * P.high * (0.5 + 0.5 * math.sin(t * 61.0))

        def A(a, c=hc):
            return c + (int(max(0, min(255, a * flick))),)

        lw = max(1, round(H / 720))
        m = int(H * 0.045)
        L = int(H * 0.05)
        fs, fsm, fb = self.font, self.font_small, self.font_big
        lh = int(fs.size * 1.35)

        # corner brackets
        for (x, y, sx, sy) in [(m, m, 1, 1), (W - m, m, -1, 1), (m, H - m, 1, -1), (W - m, H - m, -1, -1)]:
            d.line([(x, y + sy * L), (x, y), (x + sx * L, y)], fill=A(230), width=lw)
            d.rectangle([x + sx * 4 * lw - 2, y + sy * 4 * lw - 2, x + sx * 4 * lw + 2, y + sy * 4 * lw + 2], fill=A(200))

        # title + readouts, top-left
        x0, y0 = m + int(H * 0.025), m + int(H * 0.02)
        d.text((x0, y0), "METALHEART", font=fb, fill=A(235))
        d.text((x0 + int(fb.size * 6.4), y0 + int(fb.size * 0.35)), "//DEPTH.SYS", font=fsm, fill=A(170))
        rows = [
            f"T+{t:08.3f}   FRM {int(t * 24):06d}",
            f"CORE_FLUX   {0.5 + 0.5 * P.bass:0.4f}",
            f"TORSION     {P.mid * 360:07.2f}°",
            f"PHASE_ARR   0x{(int(t * 97) + self.seed * 4099) % 65535:04X}",
            self.hud_mode,
        ]
        for i, r in enumerate(rows):
            d.text((x0, y0 + int(fb.size * 1.5) + i * lh), r, font=fs, fill=A(200))
        yb = y0 + int(fb.size * 1.5) + len(rows) * lh + 4
        d.rectangle([x0, yb, x0 + int(H * 0.2), yb + int(lh * 0.5)], outline=A(160), width=lw)
        d.rectangle([x0 + 2, yb + 2, x0 + 2 + int((H * 0.2 - 4) * (0.3 + 0.7 * P.bass)), yb + int(lh * 0.5) - 2], fill=A(210))

        # accent tag, top-right (blinks)
        if int(t * 3) % 2 == 0 or P.onset > 0.5:
            tw, th = int(H * 0.11), int(H * 0.034)
            tx, ty = W - m - int(H * 0.03) - tw, m + int(H * 0.025)
            d.rectangle([tx, ty, tx + tw, ty + th], fill=ac + (235,))
            d.text((tx + int(th * 0.22), ty + int(th * 0.14)), "TRANSFORM", font=self.font_tag, fill=(8, 8, 8, 255))
        d.text((W - m - int(H * 0.03) - int(H * 0.11), m + int(H * 0.068)),
               f"SECTOR {self.seed:02d}-{int(t) % 100:02d}", font=fsm, fill=A(170))

        # long thin horizontal line with label
        yl = int(H * (self.hline_y + 0.01 * math.sin(t * 0.7)))
        d.line([(m + L, yl), (W - m - L, yl)], fill=A(70), width=1)
        d.text((W - m - L - int(H * 0.16), yl - int(fsm.size * 1.3)), "REF.PLANE  +0.00", font=fsm, fill=A(140))

        # reticle on the core
        cx, cy = focus
        R = H * 0.085
        rot = t * 35.0
        for k in range(4):
            s = rot + k * 90 + 12
            d.arc([cx - R, cy - R, cx + R, cy + R], s, s + 52, fill=A(210), width=lw)
        R2 = R * 1.32
        for k in range(48):
            if k % 4 == 0:
                continue
            s = -rot * 0.6 + k * 7.5
            d.arc([cx - R2, cy - R2, cx + R2, cy + R2], s, s + 3.5, fill=A(120), width=lw)
        g = R * 0.35
        for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            d.line([(cx + sx * g, cy + sy * g), (cx + sx * R * 1.7, cy + sy * R * 1.7)], fill=A(150), width=1)
        d.text((cx + R * 1.05, cy - R * 1.25), f"TGT {cx / W:0.3f}:{cy / H:0.3f}", font=fsm, fill=A(190))

        # leader line to a callout box
        lx, ly = cx - R * 0.6, cy + R * 0.7
        bx, by = cx - R * 2.8, cy + R * 2.0
        d.ellipse([lx - 3, ly - 3, lx + 3, ly + 3], outline=A(220), width=lw)
        d.line([(lx, ly), (bx + R * 0.9, by), (bx, by)], fill=A(170), width=lw)
        d.text((bx, by + 3), "ALLOY.SPEC 7075-T6", font=fsm, fill=A(190))
        d.text((bx, by + 3 + int(fsm.size * 1.25)), f"DEFORM {P.bass * 100:05.1f}%", font=fsm, fill=A(150, ac))

        # ruler along the bottom
        yr = H - m - int(H * 0.06)
        d.line([(m + L, yr), (W - m - L, yr)], fill=A(140), width=lw)
        spacing = max(6, W // 90)
        off = int((t * 40) % spacing)
        for i, x in enumerate(range(m + L + off, W - m - L, spacing)):
            big = ((x - off) // spacing) % 10 == 0
            d.line([(x, yr), (x, yr - (int(H * 0.018) if big else int(H * 0.007)))], fill=A(160 if big else 100), width=1)
            if big:
                d.text((x + 2, yr - int(H * 0.032)), f"{(x - off) // spacing:03d}", font=fsm, fill=A(130))

        # spectrum bars (audio-ready), bottom-left
        nb = 24
        if P.spectrum is not None:
            spec = np.interp(np.linspace(0, len(P.spectrum) - 1, nb), np.arange(len(P.spectrum)), P.spectrum)
        else:
            srng = np.random.default_rng(int(t * 12))
            spec = np.clip(srng.random(nb) * 0.4 + np.linspace(0.5, 0.1, nb) * (0.5 + P.bass), 0, 1)
        bw = max(2, int(H * 0.007))
        sx0, sy0 = m + int(H * 0.025), yr - int(H * 0.05)
        for i, s in enumerate(spec):
            hh = int(s * H * 0.07)
            d.rectangle([sx0 + i * (bw + 2), sy0 - hh, sx0 + i * (bw + 2) + bw, sy0], fill=A(90 + int(120 * s)))
        d.text((sx0, sy0 + 4), "SIG.INPUT  -- 24 BAND", font=fsm, fill=A(150))

        # barcode + serial, bottom-right
        bx0 = W - m - int(H * 0.03) - int(H * 0.2)
        by0 = yr - int(H * 0.075)
        x = bx0
        for i, bwid in enumerate(self.barcode):
            if i % 2 == 0:
                d.rectangle([x, by0, x + bwid * lw - 1, by0 + int(H * 0.035)], fill=A(200))
            x += bwid * lw + lw
        d.text((bx0, by0 + int(H * 0.04)), f"S/N MH-2001-{self.seed * 7919 % 99991:05d}", font=fsm, fill=A(160))

        # scattered plus markers
        for (mx, my) in self.markers:
            px, py = int(mx * W), int(my * H)
            k = max(3, int(H * 0.006))
            d.line([(px - k, py), (px + k, py)], fill=A(110), width=1)
            d.line([(px, py - k), (px, py + k)], fill=A(110), width=1)

        # vertical side text
        side = Image.new("RGBA", (int(H * 0.5), int(fsm.size * 1.6)), (0, 0, 0, 0))
        ImageDraw.Draw(side).text((0, 0), "// ANDREAS.LINDHOLM_REF  ::  DEPTHCORE 2001 ::", font=fsm, fill=A(110))
        side = side.rotate(90, expand=True)
        im.alpha_composite(side, (W - m - int(fsm.size * 1.6) + 2, int(H * 0.3)))

        arr = np.asarray(im).astype(np.float32) / 255.0
        return arr[..., :3], arr[..., 3:4]

    # ------------------------------------------------------------------ frame
    def render(self, t, P: Optional[Params] = None):
        P = P or Params()
        W, H = self.W, self.H
        pal = self.pal
        wu, wv = self.warp(t, P)

        # ---- foreground layers (premultiplied accumulation)
        fg = np.zeros((H, W, 3), np.float32)
        fa = np.zeros((H, W, 1), np.float32)

        def over(col, a, dof=0.0):
            nonlocal fg, fa
            a = a[..., None]
            if dof > 0:
                s = H * 0.012 * dof
                col = cv2.GaussianBlur(col * a, (0, 0), s)
                a = cv2.GaussianBlur(a, (0, 0), s)[..., None]
                fg = fg * (1 - a) + col
            else:
                fg = fg * (1 - a) + col * a
            fa = fa * (1 - a) + a

        core3d = None
        if self.core_mode == "3d":
            weights, look = self.choreo.weights(t)
            pose, cam = self.choreo.pose(t, P)
            eye = pose[0]
            az = math.atan2(float(eye[0]), float(eye[2]))
            el = math.asin(float(eye[1]) / (float(np.linalg.norm(eye)) + 1e-6))
            self.pan = (0.22 * math.sin(az), 0.18 * el)
            self.hud_mode = f"FORM {look.upper():<8} CAM {cam.upper()}"
            side = 1.0 if self.core[0] >= 0 else -1.0
            core3d = self.core3d.render(t, P, weights, pose=pose, shift=(-side * 0.42, 0.0), aa=self.aa)

        def rib(rb, depth):
            return self.ribbon(rb, t, P, wu + self.pan[0] * depth, wv + self.pan[1] * depth)

        decor2d = self.decor and self.core_mode != "3d"
        if decor2d:
            for rb in self.ribbons:
                if rb["layer"] == "back":
                    hp, a = rib(rb, 0.5)
                    over(self.shade(hp) * 0.85, a)
            for pl in self.plates:
                hp, a = self.plate(pl, t, P)
                over(self.shade(hp), a)
        if core3d is not None:
            col, a, focus, _ = core3d
            over(col, a)
        else:
            hp, a = self.blob(t, P, wu, wv)
            over(self.shade(hp), a)
            ys, xs = np.nonzero(a > 0.5)
            focus = (float(xs.mean()), float(ys.mean())) if len(xs) else (W * 0.6, H * 0.5)
        if decor2d:
            for rb in self.ribbons:
                if rb["layer"] == "front" and rb["dof"] == 0:
                    hp, a = rib(rb, 1.0)
                    over(self.shade(hp), a)

        # ---- background
        r = np.sqrt(self.u ** 2 + (self.v * 1.3) ** 2)
        g = smoothstep(0.0, 0.95, r)[..., None]
        bg = rgb(pal["bg_center"]) * (1 - g) + rgb(pal["bg_edge"]) * g
        neb = self.noise.sample(0, self.u * 180 + t * 4, self.v * 180 - t * 2)
        bg = bg * (0.75 + 0.3 * np.clip(neb, -1, 2)[..., None])
        bg = bg + self.dots[..., None] * rgb(pal["hud"]) * 0.05

        # ghosts: enlarged, heavily blurred copies of the foreground = depth
        for scale, sig, amt, flip, dx in ((1.9, 0.035, 0.30, False, 0.1), (1.35, 0.014, 0.22, True, -0.2)):
            M = cv2.getRotationMatrix2D((W / 2 + dx * H, H / 2), 8 if flip else -5, scale)
            gc = cv2.warpAffine(fg, M, (W, H))
            ga = cv2.warpAffine(fa, M, (W, H))[..., None]
            if flip:
                gc, ga = gc[:, ::-1], ga[:, ::-1]
            gc = cv2.GaussianBlur(gc, (0, 0), H * sig)
            ga = cv2.GaussianBlur(ga, (0, 0), H * sig)[..., None]
            bg = bg * (1 - amt * ga) + amt * gc * rgb(pal["sky_hor"]) * 0.8

        # drop shadow
        sh = cv2.warpAffine(fa, np.float32([[1, 0, H * 0.02], [0, 1, H * 0.035]]), (W, H))
        sh = cv2.GaussianBlur(sh, (0, 0), H * 0.02)[..., None]
        bg = bg * (1 - 0.65 * sh)

        img = bg * (1 - fa) + fg

        # out-of-focus foreground blade on top
        for rb in (self.ribbons if decor2d else []):
            if rb["dof"] > 0:
                hp, a = rib(rb, 1.6)
                a3 = a[..., None]
                s = H * 0.012 * rb["dof"]
                col = cv2.GaussianBlur(self.shade(hp) * a3 * 0.9, (0, 0), s)
                ab = cv2.GaussianBlur(a3, (0, 0), s)[..., None]
                img = img * (1 - ab) + col

        # ---- HUD with glow
        hc, ha = self.hud(t, P, focus)
        glow = cv2.GaussianBlur(hc * ha, (0, 0), max(1.0, H * 0.004))
        img = img * (1 - ha) + hc * ha + glow * 0.55

        return self.post(img, t, P)

    # ------------------------------------------------------------------ post
    def post(self, img, t, P):
        W, H = self.W, self.H
        pal = self.pal
        bright = np.clip(img - 1.0, 0, None)
        img = img + cv2.GaussianBlur(bright, (0, 0), H * 0.006) * 0.8
        img = img + cv2.GaussianBlur(bright, (0, 0), H * 0.03) * 0.6
        # anamorphic streaks
        k = int(W * 0.2) | 1
        streak = cv2.blur(bright, (k, 1))
        streak = cv2.GaussianBlur(streak, (0, 0), sigmaX=W * 0.03, sigmaY=1.2)
        img = img + streak * rgb(pal["rim"]) * (1.2 + 3.0 * P.onset)
        # onset flash
        img = img + P.onset * 0.06 * rgb(pal["rim"])

        # soft shoulder
        knee = 0.82
        over = np.maximum(img - knee, 0)
        img = np.minimum(img, knee) + (1 - knee) * np.tanh(over / (1 - knee))

        # chromatic offset
        amt = 0.0015 + 0.004 * P.onset
        out = img.copy()
        for ch, s in ((0, 1 + amt), (2, 1 - amt)):
            M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, s)
            out[..., ch] = cv2.warpAffine(img[..., ch], M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        img = out

        # slice glitch on strong onsets
        if P.onset > 0.7:
            grng = np.random.default_rng(int(t * 1000))
            for _ in range(3):
                y = int(grng.integers(0, H - 10))
                hh = int(grng.integers(2, max(3, H // 40)))
                img[y:y + hh] = np.roll(img[y:y + hh], int(grng.integers(-W // 30, W // 30)), axis=1)

        # vignette, scanlines, grain
        r2 = self.u ** 2 + self.v ** 2
        img = img * (1 - 0.55 * smoothstep(0.15, 0.75, r2))[..., None]
        if self.scanlines:
            img[1::3] *= 0.93
        grng = np.random.default_rng(int(t * 997) + 13)
        img = img + grng.standard_normal((H, W, 1)).astype(np.float32) * (0.018 + 0.015 * P.high)

        out8 = (np.clip(img, 0, 1) ** (1 / 1.05) * 255).astype(np.uint8)
        return cv2.cvtColor(out8, cv2.COLOR_RGB2BGR)


# ----------------------------------------------------------------------------- demo drivers
def synthetic_params(t, bpm=128):
    """Fake audio features so motion can be judged before real audio is wired in."""
    beat = 60.0 / bpm
    ph = (t % beat) / beat
    onset = math.exp(-ph * 9) if int(t / beat) % 4 != 3 else 0.2 * math.exp(-ph * 9)
    bass = 0.25 + 0.6 * math.exp(-ph * 5)
    mid = 0.4 + 0.3 * math.sin(t * 0.9)
    high = 0.3 + 0.3 * (0.5 + 0.5 * math.sin(t * 5.3))
    return Params(bass=bass, mid=mid, high=high, onset=onset)


def parse_size(s):
    w, h = s.lower().split("x")
    return int(w), int(h)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["still", "clip", "sheet"])
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--preset", default="steel", choices=list(PRESETS))
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--t", type=float, default=2.0, help="time for a still")
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--start", type=float, default=0.0, help="clip start time (for splitting renders)")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--no-scanlines", action="store_true")
    ap.add_argument("--core", default="3d", choices=["3d", "2d"], help="3d raymarched core or the original 2d one")
    ap.add_argument("--look", default="mercury",
                    help="comma list of looks, or 'cycle' for all: " + ", ".join(liquid3d.LOOKS))
    ap.add_argument("--camera", default="orbit",
                    help="comma list of camera moves, or 'cycle' for all: " + ", ".join(liquid3d.CAMERAS))
    ap.add_argument("--look-len", type=float, default=6.0, help="seconds per look when cycling")
    ap.add_argument("--cam-len", type=float, default=9.0, help="seconds per camera move when cycling")
    ap.add_argument("--core-scale", type=float, default=0.5, help="raymarch resolution relative to output")
    ap.add_argument("--no-decor", action="store_true", help="hide the ribbons and plates")
    ap.add_argument("--no-aa", action="store_true", help="skip edge supersampling (faster drafts)")
    a = ap.parse_args()

    looks = list(liquid3d.LOOKS) if a.look == "cycle" else a.look.split(",")
    cams = liquid3d.CAMERAS if a.camera == "cycle" else a.camera.split(",")
    W, H = parse_size(a.size)

    if a.mode == "sheet":   # grid: one row per look, one column per camera
        tw, th = W // len(cams), int(W // len(cams) * 9 / 16)
        rows = []
        for lk in looks:
            tiles = []
            for cm in cams:
                r = MetalheartRenderer(tw, th, seed=a.seed, preset=a.preset, scanlines=False, core=a.core,
                                       looks=[lk], cams=[cm], core_scale=1.0, decor=not a.no_decor,
                                       aa=not a.no_aa)
                tiles.append(r.render(a.t, Params(bass=0.5, mid=0.4, high=0.2, onset=0.4)))
            rows.append(np.hstack(tiles))
            print(f"row {lk} done", file=sys.stderr)
        cv2.imwrite(a.out, np.vstack(rows))
        print(f"wrote {a.out}")
        return

    r = MetalheartRenderer(W, H, seed=a.seed, preset=a.preset, scanlines=not a.no_scanlines, core=a.core,
                           looks=looks, cams=cams, look_len=a.look_len, cam_len=a.cam_len,
                           core_scale=a.core_scale, decor=not a.no_decor, aa=not a.no_aa)

    if a.mode == "still":
        t0 = time.time()
        frame = r.render(a.t, Params(bass=0.45, mid=0.4, high=0.2, onset=0.0))
        cv2.imwrite(a.out, frame)
        print(f"wrote {a.out} in {time.time() - t0:.2f}s")
        return

    n = int(a.seconds * a.fps)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
           "-r", str(a.fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", a.out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    for i in range(n):
        t = a.start + i / a.fps
        proc.stdin.write(r.render(t, synthetic_params(t)).tobytes())
        if i % a.fps == 0:
            el = time.time() - t0
            print(f"frame {i}/{n}  {el / (i + 1):.2f}s/frame", file=sys.stderr)
    proc.stdin.close()
    proc.wait()
    print(f"wrote {a.out}: {n} frames in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
