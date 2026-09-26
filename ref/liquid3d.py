"""
liquid3d.py - CPU raymarched liquid-metal core for metalheart.py.

The core is a signed distance field (SDF): a function that returns, for any 3D
point, the distance to the nearest surface. Rays from a virtual camera step
through that field until they hit the surface, so the shape can be seen from any
angle, and every deformation below is just a change to the function.

Motion modes (blendable 0..1 weights, see MODES):
  merge    metaballs orbiting and fusing like mercury
  fission  the mass splits into separate droplets joined by thin bridges
  twist    the body wrings around its vertical axis
  fold     the body bends over itself
  ripple   travelling waves across the surface
  melt     sags and drips downward in columns
  spike    ferrofluid spikes erupt along rotating directions (beat-friendly)
  morph    blends toward a torus / rounded slab and back
  rings    thin chrome orbit rings around the core (Depthcore staple)

Camera moves (see CAMERAS): orbit, crane, dolly, low, top, macro, dutch, drift.
"""
import math
from dataclasses import dataclass, field

import cv2
import numpy as np

MODES = ["merge", "fission", "twist", "fold", "ripple", "melt", "spike", "morph", "rings"]
CAMERAS = ["orbit", "crane", "dolly", "low", "top", "macro", "dutch", "drift"]

# Named presets: mode weights that read well together
LOOKS = {
    "mercury":    dict(merge=1.0, ripple=0.3),
    "wring":      dict(merge=0.6, twist=1.0, ripple=0.2),
    "ferro":      dict(merge=0.5, spike=1.0),
    "drip":       dict(merge=0.7, melt=1.0, ripple=0.2),
    "split":      dict(fission=1.0, ripple=0.2),
    "fold":       dict(merge=0.6, fold=1.0, twist=0.3),
    "morph":      dict(merge=0.4, morph=1.0, ripple=0.3),
    "gyro":       dict(merge=0.8, rings=1.0, ripple=0.2),
    "chaos":      dict(merge=0.6, twist=0.6, spike=0.5, ripple=0.5, rings=0.6),
}


def _smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def _rot(a, b, ang):
    c, s = np.cos(ang), np.sin(ang)
    return a * c - b * s, a * s + b * c


def _fib_dirs(n, seed):
    rng = np.random.default_rng(seed)
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    th = math.pi * (1 + 5 ** 0.5) * i + rng.uniform(0, 6.28)
    return np.stack([np.cos(th) * np.sin(phi), np.cos(phi), np.sin(th) * np.sin(phi)], 1).astype(np.float32)


@dataclass
class Frame3D:
    """Everything the SDF needs for one frame, precomputed once."""
    t: float
    w: dict
    balls: np.ndarray        # (N,4) x,y,z,r
    k: float                 # smooth-min blend radius
    twist: float
    fold: float
    ripple_amp: float
    ripple_ph: float
    melt: float
    spike_amp: float
    spike_dirs: np.ndarray
    morph: float
    morph_to: float          # 0 torus .. 1 slab
    rings: list = field(default_factory=list)


class LiquidCore:
    def __init__(self, seed=1):
        rng = np.random.default_rng(seed + 101)
        n = 7
        self.orb = dict(
            base=(rng.uniform(-0.6, 0.6, (n, 3)) * np.array([1.2, 0.8, 1.0])).astype(np.float32),
            amp=rng.uniform(0.15, 0.45, (n, 3)).astype(np.float32),
            freq=rng.uniform(0.25, 0.8, (n, 3)).astype(np.float32) * rng.choice([-1, 1], (n, 3)),
            ph=rng.uniform(0, 6.28, (n, 3)).astype(np.float32),
            r=np.r_[0.46, rng.uniform(0.2, 0.38, n - 1)].astype(np.float32),
            out=_fib_dirs(n, seed),
        )
        self.spike_dirs = _fib_dirs(16, seed + 5)
        self.ring_specs = [dict(R=rng.uniform(1.15, 1.6), r=rng.uniform(0.012, 0.03),
                                tilt=rng.uniform(-1.2, 1.2, 2), spin=rng.uniform(0.3, 0.9) * rng.choice([-1, 1]))
                           for _ in range(3)]
        self.seed = seed
        self.size = 0.82   # overall scale of the core in world units

    # ------------------------------------------------------------------ per-frame state
    def frame(self, t, w, P):
        w = {m: float(w.get(m, 0.0)) for m in MODES}
        o = self.orb
        spread = 1.0 + 1.3 * w["fission"] * (0.6 + 0.4 * math.sin(t * 0.5))
        c = o["base"] * 0.6 + o["amp"] * np.sin(o["freq"] * t + o["ph"]) * (0.4 + 0.6 * w["merge"])
        c = c + o["out"] * 0.35 * (spread - 1.0)
        c[0] *= 0.2
        r = o["r"] * (1 + 0.25 * P.bass) * (1 - 0.25 * w["fission"])
        balls = np.concatenate([c, r[:, None]], 1).astype(np.float32)
        k = 0.32 * (1 - 0.7 * w["fission"]) + 0.04
        sa = t * 0.23
        R = np.array([[math.cos(sa), 0, math.sin(sa)], [0, 1, 0], [-math.sin(sa), 0, math.cos(sa)]], np.float32)
        rings = []
        if w["rings"] > 0:
            for i, rs in enumerate(self.ring_specs):
                rings.append(dict(R=rs["R"] * (0.9 + 0.1 * w["rings"]), r=rs["r"] * (0.3 + 0.7 * w["rings"]),
                                  a1=rs["tilt"][0] + t * rs["spin"], a2=rs["tilt"][1] + t * rs["spin"] * 0.6))
        return Frame3D(
            t=t, w=w, balls=balls, k=k,
            twist=w["twist"] * (1.4 * math.sin(t * 0.55) + 0.6 * P.mid),
            fold=w["fold"] * 0.9 * math.sin(t * 0.4),
            ripple_amp=w["ripple"] * (0.025 + 0.05 * P.bass),
            ripple_ph=t * 4.0,
            melt=w["melt"],
            spike_amp=w["spike"] * (0.18 + 0.5 * P.onset + 0.15 * P.bass),
            spike_dirs=self.spike_dirs @ R.T,
            morph=w["morph"] * (0.5 + 0.5 * math.sin(t * 0.35)),
            morph_to=0.5 + 0.5 * math.sin(t * 0.21),
            rings=rings,
        )

    # ------------------------------------------------------------------ distance field
    def sdf(self, x, y, z, F: Frame3D):
        t = F.t
        # --- domain deformations
        wt, wf = F.w["twist"], F.w["fold"]
        x, y, z = x / self.size, y / self.size, z / self.size
        if F.fold != 0:
            x, y = _rot(x, y, F.fold * x)
        if F.twist != 0:
            x, z = _rot(x, z, F.twist * y)
        lip = 1.0 + 0.5 * abs(F.twist) + 0.5 * abs(F.fold)
        if wt > 0:   # stretch into a column so the wringing reads
            y = y / (1 + 0.6 * wt)
        if wf > 0:   # stretch into a bar so the bend reads
            x = x / (1 + 0.9 * wf)
            lip *= 1 + 0.9 * wf
        if F.melt > 0:
            col = 0.5 + 0.5 * np.sin(3.1 * x + 0.7 * t) * np.sin(2.7 * z - 0.5 * t)
            y = y + F.melt * 0.9 * col * np.clip(-y - 0.1, 0, None) ** 1.5 / (1 + np.clip(-y - 0.1, 0, None))
        # --- base: smooth union of metaballs
        d = None
        for bx, by, bz, br in F.balls:
            di = np.sqrt((x - bx) ** 2 + (y - by) ** 2 + (z - bz) ** 2) - br
            d = di if d is None else _smin(d, di, F.k)
        if wt > 0:   # flutes that the twist turns into helices
            d = d + wt * 0.045 * np.sin(7.0 * np.arctan2(z, x))
        if wf > 0:   # ribs across the bar that fan open as it bends
            d = d + wf * 0.035 * np.sin(14.0 * x)
        # --- morph toward torus / rounded slab
        if F.morph > 0:
            q = np.sqrt(x * x + z * z) - 0.75
            torus = np.sqrt(q * q + y * y) - 0.3
            ax, ay, az = np.abs(x) - 0.75, np.abs(y) - 0.12, np.abs(z) - 0.6
            slab = (np.sqrt(np.maximum(ax, 0) ** 2 + np.maximum(ay, 0) ** 2 + np.maximum(az, 0) ** 2)
                    + np.minimum(np.maximum(ax, np.maximum(ay, az)), 0) - 0.12)
            target = torus * (1 - F.morph_to) + slab * F.morph_to
            d = d * (1 - F.morph) + target * F.morph
        # --- surface displacement
        rr = np.sqrt(x * x + y * y + z * z) + 1e-6
        d = d + 0.045 * np.sin(3.3 * x + t * 0.9) * np.sin(2.9 * y + t * 1.1) * np.sin(3.1 * z - t * 0.7)
        d = d + 0.018 * np.sin(7.1 * x - t * 1.3 + 2 * np.sin(5.3 * z)) * np.sin(6.3 * y + t)
        if F.ripple_amp > 0:
            d = d + F.ripple_amp * np.sin(11.0 * rr - F.ripple_ph) * (0.6 + 0.4 * np.sin(4 * x + 3 * z + t))
        if F.spike_amp > 0:
            nx, ny, nz = x / rr, y / rr, z / rr
            s = np.full_like(x, -1.0)
            for dx, dy, dz in F.spike_dirs:
                s = np.maximum(s, nx * dx + ny * dy + nz * dz)
            d = d - F.spike_amp * np.clip(s, 0, 1) ** 40 * np.clip(rr, 0, 1.2)
        if F.melt > 0:  # falling droplets under the mass
            for i in range(3):
                ph = (t * 0.45 + i / 3.0) % 1.0
                dx, dz = 0.35 * math.sin(i * 2.1 + self.seed), 0.3 * math.cos(i * 1.7)
                dy = -0.7 - ph * 1.3
                rad = 0.12 * F.melt * (1 - ph * 0.5)
                drop = np.sqrt((x - dx) ** 2 + ((y - dy) * 0.75) ** 2 + (z - dz) ** 2) - rad
                d = _smin(d, drop, 0.12 * (1 - ph))
        # --- orbit rings (hard union, undeformed space would be nicer but this is cheap)
        for rg in F.rings:
            a, b, c = x, y, z
            b, c = _rot(b, c, rg["a1"])
            a, b = _rot(a, b, rg["a2"])
            q = np.sqrt(a * a + c * c) - rg["R"]
            d = np.minimum(d, np.sqrt(q * q + b * b) - rg["r"])
        return d / lip * self.size


# ---------------------------------------------------------------------- camera
def camera_pose(mode, t, P, dist=3.4):
    """Returns eye, target, roll (radians), vertical fov (radians)."""
    fov = math.radians(38)
    roll = 0.0
    target = np.zeros(3, np.float32)
    if mode == "orbit":
        az, el = t * 0.35, 0.28
    elif mode == "crane":
        az, el = 0.5 + t * 0.08, -0.2 + 1.3 * (0.5 - 0.5 * math.cos(t * 0.3))
    elif mode == "dolly":
        az, el = 0.3 + t * 0.05, 0.2
        dist = 4.6 - 2.4 * (0.5 - 0.5 * math.cos(t * 0.35))
    elif mode == "low":
        az, el = 0.8 + t * 0.12, -0.45
        fov = math.radians(46)
    elif mode == "top":
        az, el = t * 0.2, 1.35
    elif mode == "macro":
        az, el = t * 0.18, 0.15
        dist, fov = 2.0, math.radians(30)
        target = np.array([0.25, 0.15, 0.0], np.float32)
    elif mode == "dutch":
        az, el = t * 0.25, 0.2
        roll = 0.4 * math.sin(t * 0.45)
    else:  # drift: slow wandering mix of everything
        az = t * 0.17 + 0.6 * math.sin(t * 0.11)
        el = 0.25 + 0.55 * math.sin(t * 0.13)
        dist = 3.4 + 0.8 * math.sin(t * 0.09)
        roll = 0.15 * math.sin(t * 0.21)
    # beat shake
    sh = 0.03 * P.onset
    eye = np.array([dist * math.cos(el) * math.sin(az), dist * math.sin(el), dist * math.cos(el) * math.cos(az)],
                   np.float32) + np.array([sh * math.sin(t * 91), sh * math.cos(t * 77), 0], np.float32)
    return eye, target, roll, fov


# ---------------------------------------------------------------------- renderer
def _rotmat(a, b, c):
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    Rx = np.array([[1, 0, 0], [0, ca, -sa], [0, sa, ca]], np.float32)
    Ry = np.array([[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]], np.float32)
    Rz = np.array([[cc, -sc, 0], [sc, cc, 0], [0, 0, 1]], np.float32)
    return Rz @ Ry @ Rx


def _local(x, y, z, R, c):
    px, py, pz = x - c[0], y - c[1], z - c[2]
    return (R[0, 0] * px + R[0, 1] * py + R[0, 2] * pz,
            R[1, 0] * px + R[1, 1] * py + R[1, 2] * pz,
            R[2, 0] * px + R[2, 1] * py + R[2, 2] * pz)


def _bounded(fn, x, y, z, c, radius, margin=0.25):
    """Evaluate an expensive SDF only where points are near the object's bounding sphere."""
    db = np.sqrt((x - c[0]) ** 2 + (y - c[1]) ** 2 + (z - c[2]) ** 2) - radius
    near = db < margin
    if not near.any():
        return db
    out = db.copy()
    out[near] = fn(x[near], y[near], z[near])
    return out


class Decor3D:
    """Twisted chrome ribbons and machined plates living in the same 3D space as the core."""

    def __init__(self, seed=1, n_ribbons=4, n_plates=3):
        rng = np.random.default_rng(seed + 303)
        sgn = lambda: float(rng.choice([-1, 1]))  # noqa: E731
        self.ribbons = []
        for i in range(n_ribbons):
            d = rng.normal(size=3)
            d /= np.linalg.norm(d)
            pierce = i == 0
            off = rng.uniform(0.0, 0.25) if pierce else rng.uniform(0.9, 1.2)
            # orient the ribbon's long axis roughly perpendicular to its offset so it sweeps past the core
            a = np.cross(d, rng.normal(size=3))
            a /= np.linalg.norm(a)
            yaw = math.atan2(a[2], a[0])
            pitch = math.asin(float(np.clip(a[1], -1, 1)))
            self.ribbons.append(dict(
                c=(d * off).astype(np.float32),
                eul=np.array([rng.uniform(-math.pi, math.pi), yaw, pitch]), spin=rng.uniform(-0.06, 0.06, 3),
                L=rng.uniform(1.3, 1.9), A=rng.uniform(0.1, 0.25), B=rng.uniform(0.15, 0.4),
                f=rng.uniform(1.3, 2.6), ph=rng.uniform(0, 6.28), sp=rng.uniform(0.4, 0.9) * sgn(),
                k=rng.uniform(1.8, 4.0) * sgn(), ks=rng.uniform(0.5, 1.1) * sgn(),
                w=rng.uniform(0.045, 0.085), th=0.012))
        self.plates = []
        for i in range(n_plates):
            d = rng.normal(size=3)
            d[1] *= 0.5
            d /= np.linalg.norm(d)
            hx, hy = rng.uniform(0.3, 0.55), rng.uniform(0.07, 0.14)
            self.plates.append(dict(
                c=(d * rng.uniform(1.2, 1.7)).astype(np.float32),
                eul=rng.uniform(-math.pi, math.pi, 3), spin=rng.uniform(-0.25, 0.25, 3),
                orbit=rng.uniform(0.05, 0.15) * sgn(),
                hx=hx, hy=hy, hz=0.024, ch=min(hx, hy) * rng.uniform(0.35, 0.6),
                slots=[(rng.uniform(-0.6, 0.0) * hx, rng.uniform(0.15, 0.45) * hx,
                        (k - 0.5 * (n - 1)) * hy * 0.55) for n in [int(rng.integers(1, 3))] for k in range(n)],
                holes=[(hx * (0.55 + 0.17 * k)) for k in range(int(rng.integers(0, 3)))]))

    def frame(self, t, P):
        rib = []
        for r in self.ribbons:
            R = _rotmat(*(r["eul"] + r["spin"] * t))
            lip = math.sqrt(1 + (r["A"] * r["f"]) ** 2 + (r["B"] * 0.63 * r["f"]) ** 2) + abs(r["k"]) * r["w"]
            rib.append(dict(r, R=R, t1=t * r["sp"] + r["ph"], t2=t * r["ks"] * (1 + 1.2 * P.mid),
                            w_now=r["w"] * (1 + 0.35 * P.bass), lip=lip,
                            rad=r["L"] + r["A"] + r["B"] + r["w"] * 2))
        pl = []
        for p in self.plates:
            oa = p["orbit"] * t
            Ro = np.array([[math.cos(oa), 0, math.sin(oa)], [0, 1, 0], [-math.sin(oa), 0, math.cos(oa)]], np.float32)
            c = (Ro @ p["c"]) * (1 + 0.06 * P.bass)
            pl.append(dict(p, R=_rotmat(*(p["eul"] + p["spin"] * t)), c_now=c,
                           rad=math.sqrt(p["hx"] ** 2 + p["hy"] ** 2 + p["hz"] ** 2) + 0.02))
        return dict(ribbons=rib, plates=pl)

    @staticmethod
    def _ribbon(x, y, z, r):
        lx, ly, lz = _local(x, y, z, r["R"], r["c"])
        cy = r["A"] * np.sin(r["f"] * lx + r["t1"])
        cz = r["B"] * np.sin(0.63 * r["f"] * lx + r["t1"] * 0.7 + 1.3)
        dy, dz = ly - cy, lz - cz
        th = r["k"] * lx + r["t2"]
        c, s = np.cos(th), np.sin(th)
        a, b = dy * c + dz * s, -dy * s + dz * c
        u = np.clip(np.abs(lx) / r["L"], 0, 1)
        wl = r["w_now"] * (1 - u ** 3) + 0.002           # tapers to a point at each end
        # stadium cross-section (flat blade with rounded edges) so the edges shade smoothly
        qa = np.maximum(np.abs(a) - np.maximum(wl - r["th"], 0), 0)
        qx = np.maximum(np.abs(lx) - r["L"], 0)
        d = np.sqrt(qa * qa + b * b + qx * qx) - r["th"]
        return d / r["lip"]

    @staticmethod
    def _plate(x, y, z, p):
        qx, qy, qz = _local(x, y, z, p["R"], p["c_now"])
        rr = 0.008
        bx, by, bz = np.abs(qx) - p["hx"] + rr, np.abs(qy) - p["hy"] + rr, np.abs(qz) - p["hz"] + rr
        d = (np.sqrt(np.maximum(bx, 0) ** 2 + np.maximum(by, 0) ** 2 + np.maximum(bz, 0) ** 2)
             + np.minimum(np.maximum(bx, np.maximum(by, bz)), 0) - rr)
        d = np.maximum(d, (np.abs(qx) + np.abs(qy) - (p["hx"] + p["hy"] - p["ch"])) * 0.7071)   # chamfered corners
        for x0, ln, yc in p["slots"]:
            sx = np.clip(qx, x0, x0 + ln)
            d = np.maximum(d, -(np.sqrt((qx - sx) ** 2 + (qy - yc) ** 2) - p["hy"] * 0.14))
        for xh in p["holes"]:
            d = np.maximum(d, -(np.sqrt((qx - xh) ** 2 + qy * qy) - p["hy"] * 0.2))
        d = d + 0.0016 * np.sin(qy * 170.0 + 2.0 * np.sin(qx * 7.0))  # brushed streaks across the face
        return d

    def sdf_parts(self, x, y, z, D):
        dr = np.full_like(x, 1e3)
        for r in D["ribbons"]:
            dr = np.minimum(dr, _bounded(lambda a, b, c, r=r: self._ribbon(a, b, c, r), x, y, z, r["c"], r["rad"]))
        dp = np.full_like(x, 1e3)
        for p in D["plates"]:
            dp = np.minimum(dp, _bounded(lambda a, b, c, p=p: self._plate(a, b, c, p), x, y, z, p["c_now"], p["rad"]))
        return dr, dp


class CoreRenderer:
    """Sphere-traces the whole 3D scene (core + ribbons + plates) and returns an RGBA layer."""

    def __init__(self, width, height, env_fn, pal, seed=1, scale=0.5, max_steps=72, decor=True):
        self.W, self.H = width, height
        self.w, self.h = max(64, int(width * scale)), max(36, int(height * scale))
        self.env_fn, self.pal = env_fn, pal
        self.core = LiquidCore(seed)
        self.decor = Decor3D(seed) if decor else None
        self.max_steps = max_steps + (32 if decor else 0)
        yy, xx = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        self.sx = ((xx + 0.5) / self.w * 2 - 1) * (self.w / self.h)
        self.sy = -((yy + 0.5) / self.h * 2 - 1)
        self.pix = 2.0 / self.h  # screen-space size of one pixel

    def scene(self, x, y, z, F, D):
        d = self.core.sdf(x, y, z, F)
        if D is not None:
            dr, dp = self.decor.sdf_parts(x, y, z, D)
            d = np.minimum(d, np.minimum(dr, dp))
        return d

    # ------------------------------------------------------------------ tracing
    def _trace(self, eye, dx, dy, dz, F, D, bound):
        """March rays; return colour (n,3), hit mask, hit distance, closest cone ratio."""
        n = dx.size
        b = eye[0] * dx + eye[1] * dy + eye[2] * dz
        c = float(eye @ eye) - bound * bound
        disc = b * b - c
        ok = disc > 0
        sq = np.sqrt(np.where(ok, disc, 0))
        t0 = np.maximum(-b - sq, 0.45)  # near clip
        t1 = -b + sq
        hit = np.zeros(n, bool)
        thit = np.full(n, np.inf, np.float32)
        mincone = np.full(n, 1e9, np.float32)
        idx = np.nonzero(ok)[0]
        tt = t0[idx].astype(np.float32)
        for _ in range(self.max_steps):
            if idx.size == 0:
                break
            px, py, pz = eye[0] + dx[idx] * tt, eye[1] + dy[idx] * tt, eye[2] + dz[idx] * tt
            d = self.scene(px, py, pz, F, D)
            mincone[idx] = np.minimum(mincone[idx], d / np.maximum(tt, 1e-3))
            h = d < 0.0008 * tt
            hit[idx[h]] = True
            thit[idx[h]] = tt[h]
            tt = tt + d * 0.7
            keep = ~h & (tt < t1[idx])
            idx, tt = idx[keep], tt[keep]
        col = np.zeros((n, 3), np.float32)
        hi = np.nonzero(hit)[0]
        if hi.size:
            col[hi] = self._shade(eye, dx[hi], dy[hi], dz[hi], thit[hi], F, D)
        return col, hit, thit, mincone

    def _shade(self, eye, rdx, rdy, rdz, th, F, D):
        px, py, pz = eye[0] + rdx * th, eye[1] + rdy * th, eye[2] + rdz * th
        e = 0.0016
        k1 = self.scene(px + e, py - e, pz - e, F, D)
        k2 = self.scene(px - e, py - e, pz + e, F, D)
        k3 = self.scene(px - e, py + e, pz - e, F, D)
        k4 = self.scene(px + e, py + e, pz + e, F, D)
        nx, ny, nz = k1 - k2 - k3 + k4, -k1 - k2 + k3 + k4, -k1 + k2 - k3 + k4
        nl = 1 / (np.sqrt(nx * nx + ny * ny + nz * nz) + 1e-9)
        nx, ny, nz = nx * nl, ny * nl, nz * nl
        dn = rdx * nx + rdy * ny + rdz * nz
        if D is not None:   # thin two-sided sheets: face the normal toward the viewer
            flip = dn > 0
            nx, ny, nz = np.where(flip, -nx, nx), np.where(flip, -ny, ny), np.where(flip, -nz, nz)
            dn = -np.abs(dn)
        rx, ry, rz = rdx - 2 * dn * nx, rdy - 2 * dn * ny, rdz - 2 * dn * nz
        env = self.env_fn(rx[None], (ry - 0.12)[None], rz[None], self.pal, bands=0.35)[0]
        if D is not None:   # material: 0 core, 1 ribbon, 2 plate
            dcore = self.core.sdf(px, py, pz, F)
            dr, dp = self.decor.sdf_parts(px, py, pz, D)
            mat = np.argmin(np.stack([dcore, dr, dp]), 0)
            env = env * np.where(mat == 2, 0.8, np.where(mat == 1, 0.95, 1.0))[:, None]
        ao = np.ones_like(px)
        for hs, wt in ((0.06, 3.0), (0.18, 1.2)):
            ao -= wt * np.clip(hs - self.scene(px + nx * hs, py + ny * hs, pz + nz * hs, F, D), 0, None)
        ao = np.clip(ao, 0.25, 1.0)
        fres = (1 - np.abs(dn)) ** 4
        rim = np.asarray(self.pal["rim"], np.float32)
        return env * (0.55 + 0.45 * ao[:, None]) * ao[:, None] ** 0.5 + fres[:, None] * rim * 0.45

    # ------------------------------------------------------------------ frame
    def render(self, t, P, weights, cam="orbit", shift=(0.0, 0.0), bound=None, pose=None, dof=True, aa=True):
        F = self.core.frame(t, weights, P)
        D = self.decor.frame(t, P) if self.decor is not None else None
        bound = bound or (3.2 if D is not None else 2.4)
        eye, target, roll, fov = pose if pose is not None else camera_pose(cam, t, P)
        eye = np.asarray(eye, np.float32)
        fw = target - eye
        fw = fw / np.linalg.norm(fw)
        rt = np.cross(fw, np.array([0, 1, 0], np.float32))
        rt /= np.linalg.norm(rt) + 1e-8
        up = np.cross(rt, fw)
        if roll:
            rt, up = rt * math.cos(roll) + up * math.sin(roll), up * math.cos(roll) - rt * math.sin(roll)
        tf = math.tan(fov / 2)

        def rays(sx, sy):
            su, sv = (sx + shift[0]) * tf, (sy + shift[1]) * tf
            dx = fw[0] + su * rt[0] + sv * up[0]
            dy = fw[1] + su * rt[1] + sv * up[1]
            dz = fw[2] + su * rt[2] + sv * up[2]
            inv = 1 / np.sqrt(dx * dx + dy * dy + dz * dz)
            return dx * inv, dy * inv, dz * inv

        dx, dy, dz = rays(self.sx.ravel(), self.sy.ravel())
        col, hit, thit, mincone = self._trace(eye, dx, dy, dz, F, D, bound)
        h, w = self.h, self.w
        col = col.reshape(h, w, 3)
        hm = hit.reshape(h, w).astype(np.float32)
        depth = thit.reshape(h, w)
        soft = np.clip(1 - mincone.reshape(h, w) / (self.pix * 1.2), 0, 1)
        alpha = np.maximum(hm, soft * (1 - hm))

        # fill colour/depth into soft (missed-but-close) pixels from their hit neighbours
        num = cv2.GaussianBlur(col * hm[..., None], (0, 0), 1.0)
        den = cv2.GaussianBlur(hm, (0, 0), 1.0)[..., None]
        col = np.where(hm[..., None] > 0, col, num / np.maximum(den, 1e-4))
        dnum = cv2.GaussianBlur(np.where(hm > 0, depth, 0), (0, 0), 1.0)
        depth = np.where(hm > 0, depth, dnum / np.maximum(den[..., 0], 1e-4))

        # adaptive anti-aliasing: re-trace silhouette/edge pixels with 4 sub-pixel rays
        if aa:
            lum = col @ np.array([0.3, 0.5, 0.2], np.float32)
            dmax = cv2.dilate(np.where(hm > 0, depth, 50).astype(np.float32), np.ones((3, 3), np.uint8))
            dmin = cv2.erode(np.where(hm > 0, depth, 50).astype(np.float32), np.ones((3, 3), np.uint8))
            lmax = cv2.dilate(lum, np.ones((3, 3), np.uint8))
            lmin = cv2.erode(lum, np.ones((3, 3), np.uint8))
            edge = ((dmax - dmin) > 0.08) | ((lmax - lmin) > 0.35)
            ey, ex = np.nonzero(edge)
            if ey.size:
                acc = np.zeros((ey.size, 3), np.float32)
                cov = np.zeros(ey.size, np.float32)
                dsum = np.zeros(ey.size, np.float32)
                px_w = 2.0 / h
                for ox, oy in ((-0.25, -0.25), (0.25, -0.25), (-0.25, 0.25), (0.25, 0.25)):
                    sx = self.sx[ey, ex] + ox * px_w
                    sy = self.sy[ey, ex] - oy * px_w
                    rx, ry, rz = rays(sx, sy)
                    c2, h2, t2, _ = self._trace(eye, rx, ry, rz, F, D, bound)
                    acc += c2
                    cov += h2
                    dsum += np.where(h2, t2, 0)
                has = cov > 0
                col[ey[has], ex[has]] = acc[has] / cov[has, None]
                depth[ey[has], ex[has]] = dsum[has] / cov[has]
                alpha[ey, ex] = cov / 4.0

        depth = np.where(alpha > 0, depth, 1e3).astype(np.float32)
        if dof:
            col, alpha = self._depth_of_field(col, alpha, depth, float(np.linalg.norm(target - eye)))

        col = cv2.resize(col, (self.W, self.H), interpolation=cv2.INTER_LINEAR)
        alpha = np.clip(cv2.resize(alpha, (self.W, self.H), interpolation=cv2.INTER_LINEAR), 0, 1)
        # where the target point lands on screen (for the HUD reticle)
        v = target - eye
        zc = float(v @ fw)
        fx = float(v @ rt) / (zc * tf) - shift[0]
        fy = float(v @ up) / (zc * tf) - shift[1]
        focus = ((fx * self.h / self.w * 0.5 + 0.5) * self.W, (0.5 - fy * 0.5) * self.H)
        return col, alpha, focus, (eye, fw)

    def _depth_of_field(self, col, alpha, depth, focus_d):
        """Split into a near layer (in front of the focus plane) and blur it, lens-style."""
        near = np.clip((focus_d - 0.45 - depth) / 0.7, 0, 1) * (alpha > 0)
        far = np.clip((depth - focus_d - 1.0) / 1.5, 0, 0.6) * (depth < 100)
        if near.max() <= 0.01 and far.max() <= 0.01:
            return col, alpha
        s = self.h * 0.035
        wn = near.astype(np.float32)
        a3 = alpha[..., None]
        prem = col * a3
        # far: mild blur in place
        if far.max() > 0.01:
            pb = cv2.GaussianBlur(prem, (0, 0), s * 0.3)
            ab = cv2.GaussianBlur(alpha, (0, 0), s * 0.3)
            f3 = far[..., None]
            prem = prem * (1 - f3) + pb * f3
            alpha = alpha * (1 - far) + ab * far
            a3 = alpha[..., None]
        # near: separate, blur wide, composite back on top
        nP = prem * wn[..., None]
        nA = alpha * wn
        rP, rA = prem - nP, alpha - nA
        nPb = cv2.GaussianBlur(nP, (0, 0), s)
        nAb = cv2.GaussianBlur(nA, (0, 0), s)
        outP = nPb + rP * (1 - nAb[..., None])
        outA = nAb + rA * (1 - nAb)
        return (outP / np.maximum(outA, 1e-4)[..., None]).astype(np.float32), np.clip(outA, 0, 1)


# ---------------------------------------------------------------------- choreography
def _ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


class Choreo:
    """Cycles through looks and camera moves with smooth crossfades."""

    def __init__(self, looks=("mercury",), cams=("orbit",), look_len=6.0, cam_len=9.0, xfade=1.8):
        self.looks, self.cams = list(looks), list(cams)
        self.look_len, self.cam_len, self.xfade = look_len, cam_len, xfade

    def _seg(self, t, length, n):
        i = int(t // length)
        f = _ease((t - (i + 1) * length + self.xfade) / self.xfade) if n > 1 else 0.0
        return i % n, (i + 1) % n, f

    def weights(self, t):
        a, b, f = self._seg(t, self.look_len, len(self.looks))
        wa, wb = LOOKS[self.looks[a]], LOOKS[self.looks[b]]
        w = {m: wa.get(m, 0.0) * (1 - f) + wb.get(m, 0.0) * f for m in MODES}
        return w, (self.looks[a] if f < 0.5 else self.looks[b])

    def pose(self, t, P):
        a, b, f = self._seg(t, self.cam_len, len(self.cams))
        pa = camera_pose(self.cams[a], t, P)
        if f <= 0:
            return pa, self.cams[a]
        pb = camera_pose(self.cams[b], t, P)
        da, db = np.linalg.norm(pa[0]), np.linalg.norm(pb[0])
        eye = pa[0] * (1 - f) + pb[0] * f
        eye = eye / (np.linalg.norm(eye) + 1e-6) * (da * (1 - f) + db * f)  # travel around, not through
        pose = (eye, pa[1] * (1 - f) + pb[1] * f, pa[2] * (1 - f) + pb[2] * f, pa[3] * (1 - f) + pb[3] * f)
        return pose, (self.cams[a] if f < 0.5 else self.cams[b])
