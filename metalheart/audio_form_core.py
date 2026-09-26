# Production-owned abstract liquid geometry composed from analyzed audio

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import math  # Bend and twist deterministic audio-driven geometry
from types import ModuleType  # Type the dynamically loaded reference geometry module
from typing import Any, Dict  # Python 3.8-compatible state annotations

import numpy as np  # Evaluate vectorized signed-distance fields


# :: ANY, ANY, FLOAT -> ANY
# Smoothly merges two distance fields without modifying reference helpers
def _smoothMinimum(first: Any, second: Any, radius: float) -> Any:
    blend = np.clip(0.5 + 0.5 * (second - first) / radius, 0.0, 1.0)
    return second * (1.0 - blend) + first * blend - radius * blend * (1.0 - blend)


# Adds spectrum-sculpted resonance and elastic stretch forms to the reference core
class AudioFormCore:

    # CONSTRUCTOR :: moduleType, INT -> audioFormCore
    # Wraps the immutable reference core for mixed owned/reference choreography
    def __init__(self, liquidModule: ModuleType, seed: int) -> None:
        self._base = liquidModule.LiquidCore(seed)
        self._signals: Dict[str, float] = {}
        random = np.random.default_rng(seed + 1701)
        directions = random.normal(size=(3, 3)).astype(np.float32)
        self._directions = directions / np.maximum(np.linalg.norm(directions, axis=1, keepdims=True), 1e-6)

    #
    # Instance Methods
    #

    # :: ARRAY<STRING, FLOAT> -> NONE
    # Stores deterministic per-frame owned-form modulation values
    def setSignals(self, signals: Dict[str, float]) -> None:
        self._signals = {
            key: float(signals.get(key, 0.0))
            for key in (
                "form_scale",
                "form_deformation",
                "form_ripple",
                "form_length",
                "form_curvature",
                "form_direction",
                "form_twist",
                "form_snap",
            )
        }

    # :: FLOAT, ARRAY<STRING, FLOAT>, ANY -> ARRAY<STRING, ANY>
    # Precomputes reference, spectrum, resonance, and stretch state for one frame
    def frame(self, timeSec: float, weights: Dict[str, float], params: Any) -> Dict[str, Any]:
        spectrum = np.asarray(params.spectrum, np.float32)
        if spectrum.size < 3:
            spectrum = np.pad(spectrum, (0, max(0, 3 - spectrum.size)))
        thirds = np.array_split(spectrum, 3)
        low = float(np.mean(thirds[0])) if thirds[0].size else 0.0
        mid = float(np.mean(thirds[1])) if thirds[1].size else 0.0
        high = float(np.mean(thirds[2])) if thirds[2].size else 0.0
        scale = min(max(self._signals.get("form_scale", 0.0), 0.0), 0.45)
        deformation = min(max(self._signals.get("form_deformation", 0.0), 0.0), 1.0)
        ripple = min(max(self._signals.get("form_ripple", 0.0), 0.0), 0.35)
        return {
            "base": self._base.frame(timeSec, weights, params),
            "resonance": min(max(float(weights.get("resonance", 0.0)), 0.0), 1.0),
            "stretch": min(max(float(weights.get("stretch", 0.0)), 0.0), 1.0),
            "time": timeSec,
            "scale": 0.62 + scale,
            "density": 4.0 + 11.0 * deformation,
            "depth": 0.006 + 0.018 * deformation,
            "phase": timeSec * (2.4 + 1.8 * mid) + ripple * 8.0,
            "low": low,
            "mid": mid,
            "high": high,
            "length": min(max(self._signals.get("form_length", 0.0), 0.0), 2.4),
            "curvature": min(max(self._signals.get("form_curvature", 0.0), 0.0), 1.5),
            "direction": float(self._signals.get("form_direction", 0.0)) % (2.0 * math.pi),
            "twist": min(max(self._signals.get("form_twist", 0.0), -2.5), 2.5),
            "snap": min(max(self._signals.get("form_snap", 0.0), 0.0), 0.5),
        }

    # :: ANY, ANY, ANY, ARRAY<STRING, ANY> -> ANY
    # Blends reference and owned distance fields through authored form weights
    def sdf(self, x: Any, y: Any, z: Any, frame: Dict[str, Any]) -> Any:
        resonanceWeight = frame["resonance"]
        stretchWeight = frame["stretch"]
        ownedWeight = min(resonanceWeight + stretchWeight, 1.0)
        if ownedWeight <= 0.0:
            return self._base.sdf(x, y, z, frame["base"])
        result = None
        if resonanceWeight > 0.0:
            result = self._resonanceDistance(x, y, z, frame) * resonanceWeight
        if stretchWeight > 0.0:
            stretchDistance = self._stretchDistance(x, y, z, frame) * stretchWeight
            result = stretchDistance if result is None else result + stretchDistance
        if ownedWeight < 1.0:
            baseDistance = self._base.sdf(x, y, z, frame["base"])
            result = baseDistance * (1.0 - ownedWeight) + result
        return result

    #
    # Protected Methods
    #

    # :: ANY, ANY, ANY, ARRAY<STRING, ANY> -> ANY
    # Builds an abstract multi-lobed mass directly from spectral band energy
    def _resonanceDistance(self, x: Any, y: Any, z: Any, frame: Dict[str, Any]) -> Any:
        scale = frame["scale"]
        qx = x / (scale * (0.88 + 0.32 * frame["low"]))
        qy = y / (scale * (0.88 + 0.32 * frame["mid"]))
        qz = z / (scale * (0.88 + 0.32 * frame["high"]))
        distance = np.sqrt(qx * qx + qy * qy + qz * qz) - 0.62
        strengths = (frame["low"], frame["mid"], frame["high"])
        for direction, strength in zip(self._directions, strengths):
            offset = direction * (0.42 + 0.62 * strength)
            radius = 0.21 + 0.28 * strength
            lobe = np.sqrt(
                (qx - offset[0]) * (qx - offset[0])
                + (qy - offset[1]) * (qy - offset[1])
                + (qz - offset[2]) * (qz - offset[2])
            ) - radius
            distance = _smoothMinimum(distance, lobe, 0.11)
        radial = np.sqrt(qx * qx + qy * qy + qz * qz) + 1e-6
        azimuth = np.arctan2(qz, qx)
        carrier = np.sin(frame["density"] * radial - frame["phase"])
        harmonics = (
            frame["low"] * np.sin(2.0 * azimuth + 2.0 * qy - frame["phase"] * 0.45) * 0.5
            + frame["mid"] * np.sin(5.0 * azimuth - 3.0 * qy + frame["phase"] * 0.7) * 0.32
            + frame["high"] * np.sin(9.0 * azimuth + 5.0 * qy - frame["phase"] * 1.1) * 0.18
        )
        normalization = max(0.4 + frame["low"] + frame["mid"] + frame["high"], 1e-6)
        return (distance + frame["depth"] * (carrier + harmonics / normalization)) * scale

    # :: ANY, ANY, ANY, ARRAY<STRING, ANY> -> ANY
    # Builds an amplitude-lengthened capsule curved and twisted by spectral content
    def _stretchDistance(self, x: Any, y: Any, z: Any, frame: Dict[str, Any]) -> Any:
        halfLength = 0.48 + 0.44 * frame["length"]
        normalized = np.clip(x / halfLength, -1.0, 1.0)
        axis = normalized * halfLength
        bend = frame["curvature"] * halfLength * 0.42 * normalized * normalized
        direction = frame["direction"]
        centerY = bend * math.cos(direction)
        centerZ = bend * math.sin(direction)
        snapWave = frame["snap"] * halfLength * 0.22 * np.sin(math.pi * normalized + frame["time"] * 8.0)
        centerY = centerY + snapWave * math.cos(direction + math.pi * 0.5)
        centerZ = centerZ + snapWave * math.sin(direction + math.pi * 0.5)
        localX = x - axis
        localY = y - centerY
        localZ = z - centerZ
        twistAngle = frame["twist"] * normalized + frame["time"] * 0.12
        cosine = np.cos(twistAngle)
        sine = np.sin(twistAngle)
        twistedY = localY * cosine - localZ * sine
        twistedZ = localY * sine + localZ * cosine
        taper = 0.72 + 0.28 * np.cos(normalized * math.pi * 0.5)
        radius = (0.27 + 0.045 * frame["length"]) * taper
        radial = np.sqrt((twistedY / 0.82) ** 2 + (twistedZ / 1.18) ** 2)
        distance = np.sqrt(localX * localX + radial * radial) - radius
        ridges = 0.009 * (0.3 + 0.7 * frame["high"]) * np.sin(
            8.0 * normalized - frame["time"] * 3.0 + direction
        )
        return distance + ridges

    #
    # Class Methods
    #

    # Class Factory Method :: moduleType, INT -> audioFormCore
    # Creates a production-owned audio geometry adapter
    @classmethod
    def init(cls, liquidModule: ModuleType, seed: int) -> AudioFormCore:
        return cls(liquidModule, seed)
