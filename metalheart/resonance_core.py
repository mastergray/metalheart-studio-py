# Production-owned liquid-heart distance field driven by analyzed audio spectra

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import math  # Advance deterministic traveling-wave phases
from types import ModuleType  # Type the dynamically loaded reference geometry module
from typing import Any, Dict  # Python 3.8-compatible state annotations

import numpy as np  # Evaluate the vectorized heart distance field


# Adds a spectrum-driven liquid-heart form while preserving reference forms
class ResonanceCore:

    # CONSTRUCTOR :: moduleType, INT -> resonanceCore
    # Wraps the immutable reference core for mixed-form choreography
    def __init__(self, liquidModule: ModuleType, seed: int) -> None:
        self._base = liquidModule.LiquidCore(seed)
        self._signals: Dict[str, float] = {}
        self._seed = seed

    #
    # Instance Methods
    #

    # :: ARRAY<STRING, FLOAT> -> NONE
    # Stores deterministic per-frame form modulation values
    def setSignals(self, signals: Dict[str, float]) -> None:
        self._signals = {
            key: float(signals.get(key, 0.0))
            for key in ("form_scale", "form_deformation", "form_ripple")
        }

    # :: FLOAT, ARRAY<STRING, FLOAT>, ANY -> ARRAY<STRING, ANY>
    # Precomputes one reference frame plus bounded heart-wave parameters
    def frame(self, timeSec: float, weights: Dict[str, float], params: Any) -> Dict[str, Any]:
        spectrum = np.asarray(params.spectrum, np.float32)
        if spectrum.size < 3:
            spectrum = np.pad(spectrum, (0, max(0, 3 - spectrum.size)))
        thirds = np.array_split(spectrum, 3)
        low = float(np.mean(thirds[0])) if thirds[0].size else 0.0
        mid = float(np.mean(thirds[1])) if thirds[1].size else 0.0
        high = float(np.mean(thirds[2])) if thirds[2].size else 0.0
        amplitude = min(max(self._signals.get("form_scale", 0.0), 0.0), 0.45)
        deformation = min(max(self._signals.get("form_deformation", 0.0), 0.0), 1.0)
        ripple = min(max(self._signals.get("form_ripple", 0.0), 0.0), 0.35)
        return {
            "base": self._base.frame(timeSec, weights, params),
            "resonance": min(max(float(weights.get("resonance", 0.0)), 0.0), 1.0),
            "scale": 0.64 * (0.88 + amplitude),
            "density": 5.0 + 12.0 * deformation,
            "depth": 0.006 + 0.018 * deformation,
            "phase": timeSec * (2.4 + 1.8 * mid) + ripple * 8.0,
            "low": low,
            "mid": mid,
            "high": high,
        }

    # :: ANY, ANY, ANY, ARRAY<STRING, ANY> -> ANY
    # Blends the reference SDF with a rippling analytic heart surface
    def sdf(self, x: Any, y: Any, z: Any, frame: Dict[str, Any]) -> Any:
        weight = frame["resonance"]
        if weight <= 0.0:
            return self._base.sdf(x, y, z, frame["base"])
        heartDistance = self._heartDistance(x, y, z, frame)
        if weight >= 1.0:
            return heartDistance
        baseDistance = self._base.sdf(x, y, z, frame["base"])
        return baseDistance * (1.0 - weight) + heartDistance * weight

    #
    # Protected Methods
    #

    # :: ANY, ANY, ANY, ARRAY<STRING, ANY> -> ANY
    # Evaluates an approximate heart SDF plus spectrum-shaped surface waves
    def _heartDistance(self, x: Any, y: Any, z: Any, frame: Dict[str, Any]) -> Any:
        scale = frame["scale"]
        hx = x / scale
        hy = (y + 0.04 * scale) / scale
        hz = z / (scale * 0.72)
        axis = hx * hx + hy * hy + 2.25 * hz * hz - 1.0
        field = axis * axis * axis - hx * hx * hy * hy * hy - 0.1125 * hz * hz * hy * hy * hy
        axisSquared = axis * axis
        gradientX = 6.0 * hx * axisSquared - 2.0 * hx * hy * hy * hy
        gradientY = 6.0 * hy * axisSquared - 3.0 * hx * hx * hy * hy - 0.3375 * hz * hz * hy * hy
        gradientZ = 13.5 * hz * axisSquared - 0.225 * hz * hy * hy * hy
        gradient = np.sqrt(gradientX * gradientX + gradientY * gradientY + gradientZ * gradientZ)
        distance = np.clip(field / np.maximum(gradient, 0.35), -0.4, 0.4) * scale * 0.72
        radius = np.sqrt(hx * hx + hy * hy + hz * hz) + 1e-6
        azimuth = np.arctan2(hz, hx)
        density = frame["density"]
        phase = frame["phase"]
        carrier = np.sin(density * radius - phase)
        lowWave = frame["low"] * np.sin(2.0 * azimuth + 2.2 * hy - phase * 0.45)
        midWave = frame["mid"] * np.sin(5.0 * azimuth - 3.0 * hy + phase * 0.7)
        highWave = frame["high"] * np.sin(9.0 * azimuth + 5.0 * hy - phase * 1.1)
        harmonics = (lowWave * 0.5 + midWave * 0.32 + highWave * 0.18) / max(
            0.4 + frame["low"] + frame["mid"] + frame["high"],
            1e-6,
        )
        modulation = 0.65 + 0.35 * np.sin(3.0 * azimuth + 2.0 * hy + self._seed * 0.17)
        return distance + frame["depth"] * (carrier * modulation + harmonics)

    #
    # Class Methods
    #

    # Class Factory Method :: moduleType, INT -> resonanceCore
    # Creates a production-owned resonance geometry adapter
    @classmethod
    def init(cls, liquidModule: ModuleType, seed: int) -> ResonanceCore:
        return cls(liquidModule, seed)
