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


# Adds spectrum-sculpted resonance and radial forms to the reference core
class AudioFormCore:

    # CONSTRUCTOR :: moduleType, INT -> audioFormCore
    # Wraps the immutable reference core for mixed owned/reference choreography
    def __init__(self, liquidModule: ModuleType, seed: int) -> None:
        self._base = liquidModule.LiquidCore(seed)
        self._signals: Dict[str, float] = {}
        random = np.random.default_rng(seed + 1701)
        directions = random.normal(size=(3, 3)).astype(np.float32)
        self._resonanceDirections = directions / np.maximum(np.linalg.norm(directions, axis=1, keepdims=True), 1e-6)
        count = 24
        indices = np.arange(count, dtype=np.float32) + 0.5
        polar = np.arccos(1.0 - 2.0 * indices / count)
        azimuth = math.pi * (1.0 + math.sqrt(5.0)) * indices + random.uniform(0.0, 2.0 * math.pi)
        self._radialDirections = np.stack(
            [np.cos(azimuth) * np.sin(polar), np.cos(polar), np.sin(azimuth) * np.sin(polar)],
            axis=1,
        ).astype(np.float32)

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
                "form_extent",
                "form_rotation",
            )
        }

    # :: FLOAT, ARRAY<STRING, FLOAT>, ANY -> ARRAY<STRING, ANY>
    # Precomputes reference, spectrum, resonance, and radial state for one frame
    def frame(self, timeSec: float, weights: Dict[str, float], params: Any) -> Dict[str, Any]:
        spectrumValue = getattr(params, "spectrum", None)
        spectrum = np.asarray(spectrumValue if spectrumValue is not None else [], np.float32).reshape(-1)
        if spectrum.size < 3:
            spectrum = np.pad(spectrum, (0, max(0, 3 - spectrum.size)))
        thirds = np.array_split(spectrum, 3)
        low = float(np.mean(thirds[0])) if thirds[0].size else 0.0
        mid = float(np.mean(thirds[1])) if thirds[1].size else 0.0
        high = float(np.mean(thirds[2])) if thirds[2].size else 0.0
        scale = min(max(self._signals.get("form_scale", 0.0), 0.0), 0.45)
        deformation = min(max(self._signals.get("form_deformation", 0.0), 0.0), 1.0)
        ripple = min(max(self._signals.get("form_ripple", 0.0), 0.0), 0.35)
        radialSpectrum = self._radialSpectrum(spectrum)
        return {
            "base": self._base.frame(timeSec, weights, params),
            "resonance": min(max(float(weights.get("resonance", 0.0)), 0.0), 1.0),
            "radial": min(max(float(weights.get("radial", 0.0)), 0.0), 1.0),
            "time": timeSec,
            "scale": 0.62 + scale,
            "density": 4.0 + 11.0 * deformation,
            "depth": 0.006 + 0.018 * deformation,
            "phase": timeSec * (2.4 + 1.8 * mid) + ripple * 8.0,
            "ripple": ripple,
            "low": low,
            "mid": mid,
            "high": high,
            "extent": min(max(self._signals.get("form_extent", 0.0), 0.0), 1.2),
            "rotation": float(self._signals.get("form_rotation", 0.0)) % (2.0 * math.pi),
            "radial_spectrum": radialSpectrum,
        }

    # :: ANY, ANY, ANY, ARRAY<STRING, ANY> -> ANY
    # Blends reference and owned distance fields through authored form weights
    def sdf(self, x: Any, y: Any, z: Any, frame: Dict[str, Any]) -> Any:
        resonanceWeight = frame["resonance"]
        radialWeight = frame["radial"]
        ownedWeight = min(resonanceWeight + radialWeight, 1.0)
        if ownedWeight <= 0.0:
            return self._base.sdf(x, y, z, frame["base"])
        result = None
        if resonanceWeight > 0.0:
            result = self._resonanceDistance(x, y, z, frame) * resonanceWeight
        if radialWeight > 0.0:
            radialDistance = self._radialDistance(x, y, z, frame) * radialWeight
            result = radialDistance if result is None else result + radialDistance
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
        for direction, strength in zip(self._resonanceDirections, strengths):
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
    # Builds multidirectional extensions whose directions follow individual spectrum bands
    def _radialDistance(self, x: Any, y: Any, z: Any, frame: Dict[str, Any]) -> Any:
        scale = 0.76
        qx, qy, qz = x / scale, y / scale, z / scale
        radial = np.sqrt(qx * qx + qy * qy + qz * qz) + 1e-6
        normalX, normalY, normalZ = qx / radial, qy / radial, qz / radial
        cosine = math.cos(frame["rotation"])
        sine = math.sin(frame["rotation"])
        rotatedX = normalX * cosine - normalZ * sine
        rotatedZ = normalX * sine + normalZ * cosine
        directional = np.zeros_like(radial)
        for direction, strength in zip(self._radialDirections, frame["radial_spectrum"]):
            alignment = np.clip(
                rotatedX * direction[0] + normalY * direction[1] + rotatedZ * direction[2],
                0.0,
                1.0,
            )
            directional = np.maximum(directional, float(strength) ** 0.7 * alignment ** 11)
        targetRadius = 0.56 + frame["extent"] * (0.12 + 1.02 * directional)
        wave = frame["depth"] * 0.5 * np.sin(
            12.0 * radial - frame["time"] * 5.5 + directional * 7.0
        )
        wave += frame["ripple"] * 0.35 * np.sin(
            8.0 * radial - frame["time"] * 7.0
        )
        return (radial - targetRadius + wave) * scale * 0.72

    # :: ANY -> ANY
    # Resamples and gently smooths arbitrary spectrum lengths onto 24 spatial directions
    def _radialSpectrum(self, spectrum: Any) -> Any:
        values = np.clip(np.asarray(spectrum, np.float32).reshape(-1), 0.0, 1.0)
        if values.size != 24:
            source = np.linspace(0.0, 1.0, max(values.size, 1), dtype=np.float32)
            target = np.linspace(0.0, 1.0, 24, dtype=np.float32)
            values = np.interp(target, source, values if values.size else np.zeros(1, np.float32)).astype(np.float32)
        return values * 0.6 + np.roll(values, 1) * 0.2 + np.roll(values, -1) * 0.2

    #
    # Class Methods
    #

    # Class Factory Method :: moduleType, INT -> audioFormCore
    # Creates a production-owned audio geometry adapter
    @classmethod
    def init(cls, liquidModule: ModuleType, seed: int) -> AudioFormCore:
        return cls(liquidModule, seed)
