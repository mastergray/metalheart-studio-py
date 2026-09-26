# Configurable resolution-independent text overlays

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

from typing import Any, Dict  # Annotate resolved overlay configuration

import cv2  # Convert renderer BGR frames to and from RGB
import numpy as np  # Type frame arrays
from PIL import Image, ImageColor, ImageDraw, ImageFont  # Compose antialiased text layers


ANCHORS = {
    "top_left": "lt",
    "top_center": "mt",
    "top_right": "rt",
    "center": "mm",
    "bottom_left": "lb",
    "bottom_center": "mb",
    "bottom_right": "rb",
}


# Draws author-supplied text after visual modulation so labels remain stable
class TextOverlay:

    # CONSTRUCTOR :: ARRAY<STRING, ANY>, STRING -> textOverlay
    # Stores resolved items and the renderer's known-good font path
    def __init__(self, config: Dict[str, Any], fontPath: str) -> None:
        self._enabled = bool(config.get("enabled", False))
        self._items = list(config.get("items", []))
        self._fontPath = fontPath
        self._fonts: Dict[int, Any] = {}

    #
    # Instance Methods
    #

    # :: ANY -> ANY
    # Draws every configured text item on a transparent RGBA layer
    def apply(self, frame: np.ndarray) -> np.ndarray:
        if not self._enabled or not self._items:
            return frame
        height, width = frame.shape[:2]
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        for item in self._items:
            size = max(8, int(round(float(item.get("size", 0.035)) * height)))
            font = self._font(size)
            position = item.get("position", [0.05, 0.05])
            point = (int(round(float(position[0]) * width)), int(round(float(position[1]) * height)))
            color = ImageColor.getrgb(str(item.get("color", "#D8ECFF")))
            alpha = int(round(min(max(float(item.get("opacity", 1.0)), 0.0), 1.0) * 255.0))
            anchor = ANCHORS.get(str(item.get("anchor", "top_left")), "lt")
            draw.text(point, str(item.get("text", "")), font=font, fill=color + (alpha,), anchor=anchor)
        composed = Image.alpha_composite(image, layer).convert("RGB")
        return cv2.cvtColor(np.asarray(composed), cv2.COLOR_RGB2BGR)

    #
    # Protected Methods
    #

    # :: INT -> ANY
    # Loads and caches one font size
    def _font(self, size: int) -> Any:
        if size not in self._fonts:
            self._fonts[size] = ImageFont.truetype(self._fontPath, size)
        return self._fonts[size]

    #
    # Class Methods
    #

    # Class Factory Method :: ARRAY<STRING, ANY>, STRING -> textOverlay
    # Creates a configured text overlay
    @classmethod
    def init(cls, config: Dict[str, Any], fontPath: str) -> TextOverlay:
        return cls(config, fontPath)
