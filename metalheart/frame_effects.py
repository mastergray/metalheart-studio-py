# Audio-reactive frame-space modulation owned by Metalheart Studio

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import math  # Generate deterministic shake motion
from typing import Dict  # Annotate resolved modulator values

import cv2  # Apply spatial and channel transforms
import numpy as np  # Blend flash values without overflow


# Applies visible audio-driven transforms after the base renderer
class FrameEffects:

    # :: ANY, FLOAT, ARRAY<STRING, FLOAT> -> ANY
    # Applies configured modulators in stable pulse, shake, chroma, flash order
    def apply(self, frame: np.ndarray, timeSec: float, modulators: Dict[str, float]) -> np.ndarray:
        pulse = float(modulators.get("pulse", 0.0))
        shake = float(modulators.get("shake", 0.0))
        output = self._spatial(frame, timeSec, 1.0 + pulse, shake) if pulse > 0.0 or shake > 0.0 else frame
        chroma = float(modulators.get("chroma", 0.0))
        if chroma > 0.0:
            output = self._chroma(output, chroma)
        flash = float(modulators.get("flash", 0.0))
        if flash > 0.0:
            output = self._flash(output, flash)
        return output

    # :: ANY, FLOAT, FLOAT, FLOAT -> ANY
    # Combines pulse and shake into one high-quality spatial resample
    def _spatial(self, frame: np.ndarray, timeSec: float, scale: float, shake: float) -> np.ndarray:
        height, width = frame.shape[:2]
        shiftX = math.sin(timeSec * 47.123 + 0.7) * shake * width
        shiftY = math.cos(timeSec * 53.731 + 1.3) * shake * height
        matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), 0.0, scale)
        matrix[0, 2] += shiftX
        matrix[1, 2] += shiftY
        return cv2.warpAffine(frame, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)

    # :: ANY, FLOAT -> ANY
    # Separates red and blue channels by a resolution-relative amount
    def _chroma(self, frame: np.ndarray, amount: float) -> np.ndarray:
        height, width = frame.shape[:2]
        pixels = max(1, int(round(amount * width)))
        output = frame.copy()
        output[..., 0] = np.roll(frame[..., 0], -pixels, axis=1)
        output[..., 2] = np.roll(frame[..., 2], pixels, axis=1)
        return output

    # :: ANY, FLOAT -> ANY
    # Adds a bounded white flash in linear byte space
    def _flash(self, frame: np.ndarray, amount: float) -> np.ndarray:
        value = min(max(amount, 0.0), 1.0)
        blended = frame.astype(np.float32) * (1.0 - value) + 255.0 * value
        return np.clip(blended, 0.0, 255.0).astype(np.uint8)

    #
    # Class Methods
    #

    # Class Factory Method :: VOID -> frameEffects
    # Creates the stateless frame-effects processor
    @classmethod
    def init(cls) -> FrameEffects:
        return cls()
