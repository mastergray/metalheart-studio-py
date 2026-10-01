# Stable owned palette adaptations for the Metalheart lighting model

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

from typing import Dict, List, Tuple  # Python 3.8-compatible palette annotations


Color = Tuple[float, float, float]
Palette = Dict[str, Color]

NATIVE_PALETTE_IDS: List[str] = ["steel", "acid", "ember"]
DAZZLE_PALETTE_IDS: List[str] = [
    "rainbow",
    "ice",
    "electric",
    "neon",
    "grayscale",
]
PALETTE_IDS: List[str] = NATIVE_PALETTE_IDS + DAZZLE_PALETTE_IDS

# Dazzle's indexed ramps are sampled and luminance-compressed into Metalheart's
# static environment, rim, accent, HUD, and background lighting roles. Fire,
# lava, and ocean are intentionally omitted because ember, steel, and ice
# already cover those families without adding meaningfully distinct output.
DAZZLE_PALETTES: Dict[str, Palette] = {
    "rainbow": {
        "sky_top": (0.32, 0.00, 0.70),
        "sky_hor": (1.00, 0.20, 0.78),
        "ground_hor": (0.07, 0.02, 0.00),
        "ground_low": (0.00, 0.26, 0.04),
        "key": (1.00, 0.82, 0.82),
        "rim": (0.00, 0.70, 1.00),
        "accent": (0.92, 1.00, 0.00),
        "hud": (0.78, 0.90, 1.00),
        "bg_center": (0.06, 0.02, 0.13),
        "bg_edge": (0.006, 0.002, 0.000),
    },
    "ice": {
        "sky_top": (0.00, 0.14, 0.42),
        "sky_hor": (0.76, 1.00, 1.00),
        "ground_hor": (0.00, 0.00, 0.03),
        "ground_low": (0.00, 0.12, 0.28),
        "key": (1.00, 1.00, 1.00),
        "rim": (0.44, 0.94, 1.00),
        "accent": (0.10, 0.60, 0.82),
        "hud": (0.76, 1.00, 1.00),
        "bg_center": (0.00, 0.025, 0.095),
        "bg_edge": (0.000, 0.000, 0.006),
    },
    "electric": {
        "sky_top": (0.06, 0.09, 0.58),
        "sky_hor": (0.84, 0.10, 0.94),
        "ground_hor": (0.004, 0.025, 0.040),
        "ground_low": (0.03, 0.05, 0.25),
        "key": (1.00, 0.78, 1.00),
        "rim": (0.54, 0.08, 0.85),
        "accent": (0.08, 0.16, 0.72),
        "hud": (0.88, 0.72, 1.00),
        "bg_center": (0.02, 0.025, 0.11),
        "bg_edge": (0.001, 0.004, 0.008),
    },
    "neon": {
        "sky_top": (0.62, 0.12, 0.00),
        "sky_hor": (0.10, 1.00, 0.52),
        "ground_hor": (0.07, 0.00, 0.055),
        "ground_low": (0.18, 0.07, 0.00),
        "key": (0.72, 1.00, 1.00),
        "rim": (0.12, 1.00, 0.10),
        "accent": (1.00, 0.40, 0.00),
        "hud": (0.64, 1.00, 0.82),
        "bg_center": (0.12, 0.00, 0.03),
        "bg_edge": (0.008, 0.000, 0.006),
    },
    "grayscale": {
        "sky_top": (0.22, 0.22, 0.22),
        "sky_hor": (0.88, 0.88, 0.88),
        "ground_hor": (0.015, 0.015, 0.015),
        "ground_low": (0.22, 0.22, 0.22),
        "key": (1.00, 1.00, 1.00),
        "rim": (0.72, 0.72, 0.72),
        "accent": (0.55, 0.55, 0.55),
        "hud": (0.84, 0.84, 0.84),
        "bg_center": (0.055, 0.055, 0.055),
        "bg_edge": (0.002, 0.002, 0.002),
    },
}


# :: VOID -> ARRAY<STRING, ARRAY<STRING, (FLOAT, FLOAT, FLOAT)>>
# Returns isolated adapted palettes for installation into a renderer module
def adaptedDazzlePalettes() -> Dict[str, Palette]:
    return {
        paletteId: dict(values)
        for paletteId, values in DAZZLE_PALETTES.items()
    }
