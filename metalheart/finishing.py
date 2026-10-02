# Configurable owned finishing pass for reference-renderer float frames

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

from typing import Any, Dict  # Annotate the adapted renderer and finish settings

import cv2  # Apply bloom, streak, chroma, and glitch transforms
import numpy as np  # Evaluate deterministic pixel operations


BAYER_MATRICES = {
    "bayer2": np.asarray([[0, 2], [3, 1]], np.float32),
    "bayer4": np.asarray(
        [
            [0, 8, 2, 10],
            [12, 4, 14, 6],
            [3, 11, 1, 9],
            [15, 7, 13, 5],
        ],
        np.float32,
    ),
    "bayer8": np.asarray(
        [
            [0, 32, 8, 40, 2, 34, 10, 42],
            [48, 16, 56, 24, 50, 18, 58, 26],
            [12, 44, 4, 36, 14, 46, 6, 38],
            [60, 28, 52, 20, 62, 30, 54, 22],
            [3, 35, 11, 43, 1, 33, 9, 41],
            [51, 19, 59, 27, 49, 17, 57, 25],
            [15, 47, 7, 39, 13, 45, 5, 37],
            [63, 31, 55, 23, 61, 29, 53, 21],
        ],
        np.float32,
    ),
}


# :: ANY -> ANY
# Converts renderer palette tuples into float RGB vectors
def _rgb(value: Any) -> np.ndarray:
    return np.asarray(value, np.float32)


# :: FLOAT, FLOAT, ANY -> ANY
# Evaluates a stable smoothstep curve for vignette masks
def _smoothstep(edge0: float, edge1: float, value: np.ndarray) -> np.ndarray:
    amount = np.clip((value - edge0) / (edge1 - edge0 + 1e-9), 0.0, 1.0)
    return amount * amount * (3.0 - 2.0 * amount)


# Replaces the immutable reference post pass with authored finish controls
class FinishingPass:

    # CONSTRUCTOR :: ANY, ARRAY<STRING, ANY> -> finishingPass
    # Stores renderer geometry and resolved finishing values
    def __init__(self, renderer: Any, config: Dict[str, Any]) -> None:
        self._renderer = renderer
        self._config = config

    #
    # Properties
    #

    # PROPERTY :: VOID -> FLOAT
    # Returns the authored internal render-size multiplier
    @property
    def renderScale(self) -> float:
        return float(self._config["psx"]["render_scale"])

    #
    # Instance Methods
    #

    # :: ANY, FLOAT, ANY -> ANY
    # Finishes one linear RGB float frame and returns BGR bytes
    def apply(self, image: np.ndarray, timeSec: float, params: Any) -> np.ndarray:
        height, width = image.shape[:2]
        palette = self._renderer.pal
        bright = np.clip(image - 1.0, 0.0, None)
        bloom = float(self._config["bloom"])
        if bloom > 0.0:
            image = image + cv2.GaussianBlur(bright, (0, 0), height * 0.006) * bloom
        wideBloom = float(self._config["wide_bloom"])
        if wideBloom > 0.0:
            image = image + cv2.GaussianBlur(bright, (0, 0), height * 0.03) * wideBloom
        streaks = float(self._config["streaks"])
        onsetStreaks = float(self._config["onset_streaks"])
        if streaks > 0.0 or onsetStreaks > 0.0:
            kernel = int(width * 0.2) | 1
            streak = cv2.blur(bright, (kernel, 1))
            streak = cv2.GaussianBlur(streak, (0, 0), sigmaX=width * 0.03, sigmaY=1.2)
            image = image + streak * _rgb(palette["rim"]) * (streaks + onsetStreaks * params.onset)
        image = image + params.onset * float(self._config["flash"]) * _rgb(palette["rim"])
        image = self._shoulder(image)
        image = self._chroma(image, params)
        image = self._sliceGlitch(image, timeSec, params)
        radius = self._renderer.u ** 2 + self._renderer.v ** 2
        image = image * (1.0 - float(self._config["vignette"]) * _smoothstep(0.15, 0.75, radius))[..., None]
        if self._config["scanlines"]:
            image[1::3] *= 0.93
        grain = float(self._config["grain"]) + float(self._config["grain_high"]) * params.high
        if grain > 0.0:
            random = np.random.default_rng(int(timeSec * 997) + 13)
            image = image + random.standard_normal((height, width, 1)).astype(np.float32) * grain
        output = (np.clip(image, 0.0, 1.0) ** (1.0 / 1.05) * 255.0).astype(np.uint8)
        return cv2.cvtColor(output, cv2.COLOR_RGB2BGR)

    # :: ANY -> ANY
    # Applies final ordered color reduction after all authored post effects
    def applyPsx(self, image: np.ndarray) -> np.ndarray:
        psx = self._config["psx"]
        colorLevels = int(psx["color_levels"])
        if colorLevels == 0:
            return image
        values = image.astype(np.float32) / 255.0
        matrix = BAYER_MATRICES.get(str(psx["dither"]))
        if matrix is not None and float(psx["dither_strength"]) > 0.0:
            height, width = image.shape[:2]
            repeatsY = int(np.ceil(height / float(matrix.shape[0])))
            repeatsX = int(np.ceil(width / float(matrix.shape[1])))
            threshold = np.tile(matrix, (repeatsY, repeatsX))[:height, :width]
            threshold = (threshold + 0.5) / float(matrix.size) - 0.5
            values = values + threshold[..., None] * float(psx["dither_strength"]) / float(colorLevels - 1)
        reduced = np.floor(np.clip(values, 0.0, 1.0) * float(colorLevels - 1) + 0.5)
        return np.clip(reduced / float(colorLevels - 1) * 255.0, 0.0, 255.0).astype(np.uint8)

    #
    # Protected Methods
    #

    # :: ANY -> ANY
    # Applies a soft highlight shoulder
    def _shoulder(self, image: np.ndarray) -> np.ndarray:
        knee = 0.82
        excess = np.maximum(image - knee, 0.0)
        return np.minimum(image, knee) + (1.0 - knee) * np.tanh(excess / (1.0 - knee))

    # :: ANY, ANY -> ANY
    # Applies configurable red and blue channel separation
    def _chroma(self, image: np.ndarray, params: Any) -> np.ndarray:
        height, width = image.shape[:2]
        amount = float(self._config["chroma"]) + float(self._config["chroma_onset"]) * params.onset
        if amount <= 0.0:
            return image
        output = image.copy()
        for channel, scale in ((0, 1.0 + amount), (2, 1.0 - amount)):
            matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), 0.0, scale)
            output[..., channel] = cv2.warpAffine(image[..., channel], matrix, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        return output

    # :: ANY, FLOAT, ANY -> ANY
    # Applies deterministic onset slices only when explicitly enabled
    def _sliceGlitch(self, image: np.ndarray, timeSec: float, params: Any) -> np.ndarray:
        if not self._config["slice_glitch"] or params.onset <= float(self._config["slice_threshold"]):
            return image
        height, width = image.shape[:2]
        random = np.random.default_rng(int(timeSec * 1000))
        for index in range(3):
            del index
            y = int(random.integers(0, height - 10))
            sliceHeight = int(random.integers(2, max(3, height // 40)))
            image[y:y + sliceHeight] = np.roll(image[y:y + sliceHeight], int(random.integers(-width // 30, width // 30)), axis=1)
        return image

    #
    # Class Methods
    #

    # Class Factory Method :: ANY, ARRAY<STRING, ANY> -> finishingPass
    # Creates an owned finish processor for one renderer session
    @classmethod
    def init(cls, renderer: Any, config: Dict[str, Any]) -> FinishingPass:
        return cls(renderer, config)
