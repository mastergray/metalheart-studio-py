# Built-in renderer, reactivity, template, and schema catalogs

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

from typing import Any, Dict  # Python 3.8-compatible collection annotations


PALETTES = ["steel", "acid", "ember"]
CORES = ["3d", "2d"]
FORMS = ["mercury", "wring", "ferro", "drip", "split", "fold", "morph", "gyro", "chaos", "resonance", "radial"]
LOOKS = FORMS
CAMERAS = ["orbit", "crane", "dolly", "low", "top", "macro", "dutch", "drift"]
CURVES = ["linear", "ease_in", "ease_out", "smoothstep", "square"]
SOURCES = ["bass", "mid", "high", "amplitude", "energy", "spectral_centroid", "onset", "beat", "downbeat", "tension"]
DESTINATIONS = ["bass", "mid", "high", "onset"]
MODULATORS = [
    "pulse",
    "shake",
    "flash",
    "chroma",
    "camera_distance",
    "camera_elevation",
    "camera_roll",
    "camera_kick",
    "form_scale",
    "form_deformation",
    "form_ripple",
    "form_extent",
    "form_rotation",
    "form_jaggedness",
    "form_jagged_scale",
    "background_pulse",
    "background_ripple",
    "background_ripple_scale",
    "background_ripple_impact",
]

QUALITY_PROFILES: Dict[str, Dict[str, Any]] = {
    "preview": {"width": 320, "height": 180, "fps": 12, "crf": 23},
    "draft": {"width": 960, "height": 540, "fps": 24, "crf": 20},
    "final": {"width": 1920, "height": 1080, "fps": 30, "crf": 18},
}

QUALITY_RENDERER_PROFILES: Dict[str, Dict[str, Any]] = {
    "preview": {"core_scale": 0.35, "anti_alias": False},
    "draft": {"core_scale": 0.5, "anti_alias": True},
    "final": {"core_scale": 0.75, "anti_alias": True},
}

DEFAULT_SETTINGS: Dict[str, Any] = {
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "crf": 18,
    "seed": 3,
    "quality": "final",
    "time_mode": "global",
    "workers": "auto",
    "chunk_sec": 4.0,
    "resume": True,
}

DEFAULT_RENDERER: Dict[str, Any] = {
    "id": "metalheart",
    "palette": "steel",
    "core": "3d",
    "forms": ["mercury"],
    "cameras": ["orbit"],
    "form_len_sec": 6.0,
    "camera_len_sec": 9.0,
    "camera_speed": 1.0,
    "camera_phase_sec": 0.0,
    "camera_intensity": 1.0,
    "crossfade_sec": 1.8,
    "decor": True,
    "anti_alias": True,
    "core_scale": 0.5,
    "surface": {
        "image": None,
        "mapping": "triplanar",
        "scale": 1.0,
        "rotation_deg": 0.0,
        "material": "metallic",
        "sampling": "bilinear",
        "texel_steps": 0,
        "lighting_steps": 0,
    },
    "form_style": {
        "faceting": 0.0,
        "jaggedness": 0.0,
        "jagged_scale": 4.0,
        "geometry_steps": 0,
    },
}

DEFAULT_OVERLAY: Dict[str, Any] = {
    "enabled": False,
    "reference_hud": False,
    "items": [],
}

DEFAULT_BACKGROUND: Dict[str, Any] = {
    "source": "palette",
    "image": None,
    "fit": "cover",
    "scale": 1.0,
    "rotation_deg": 0.0,
    "offset": [0.0, 0.0],
    "opacity": 1.0,
    "pulse_brightness": 0.35,
    "pulse_scale": 0.08,
    "pulse_center": [0.5, 0.5],
    "material": "flat",
    "ripple": {
        "enabled": False,
        "amount": 0.035,
        "scale": 5.0,
        "travel_speed": 0.4,
        "warp": 0.012,
        "specular": 0.45,
        "roughness": 0.65,
    },
    "dots": True,
    "ghosts": True,
    "shadow": True,
}

DEFAULT_FINISH: Dict[str, Any] = {
    "bloom": 0.65,
    "wide_bloom": 0.35,
    "streaks": 0.7,
    "onset_streaks": 1.5,
    "flash": 0.04,
    "chroma": 0.0005,
    "chroma_onset": 0.002,
    "slice_glitch": False,
    "slice_threshold": 0.7,
    "vignette": 0.5,
    "scanlines": False,
    "grain": 0.006,
    "grain_high": 0.006,
}

REACTIVITY_PRESETS: Dict[str, Dict[str, Any]] = {
    "balanced": {
        "bindings": {
            "bass": {"source": "bass", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "mid": {"source": "mid", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "high": {"source": "high", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "onset": {"source": "onset", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
        },
        "modulators": {
            "pulse": {"source": "bass", "amount": 0.08, "bias": 0.0, "curve": "ease_out", "clamp": [0.0, 0.08]},
            "shake": {"source": "onset", "amount": 0.012, "bias": 0.0, "curve": "ease_out", "threshold": 0.35, "clamp": [0.0, 0.012]},
            "flash": {"source": "onset", "amount": 0.16, "bias": 0.0, "curve": "ease_out", "threshold": 0.45, "clamp": [0.0, 0.16]},
            "chroma": {"source": "high", "amount": 0.004, "bias": 0.0, "curve": "linear", "threshold": 0.45, "clamp": [0.0, 0.004]},
        },
    },
    "sub-heavy": {
        "bindings": {
            "bass": {"source": "bass", "amount": 1.35, "bias": 0.0, "curve": "ease_out", "clamp": [0.0, 1.0]},
            "mid": {"source": "mid", "amount": 0.7, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "high": {"source": "high", "amount": 0.4, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "onset": {"source": "onset", "amount": 0.8, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
        },
        "modulators": {
            "pulse": {"source": "bass", "amount": 0.11, "bias": 0.0, "curve": "ease_out", "clamp": [0.0, 0.11]},
            "shake": {"source": "onset", "amount": 0.01, "bias": 0.0, "curve": "ease_out", "threshold": 0.4, "clamp": [0.0, 0.01]},
        },
    },
    "percussive": {
        "bindings": {
            "bass": {"source": "bass", "amount": 0.9, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "mid": {"source": "mid", "amount": 0.8, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "high": {"source": "high", "amount": 0.8, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "onset": {"source": "onset", "amount": 1.4, "bias": 0.0, "curve": "ease_out", "clamp": [0.0, 1.0]},
        },
        "modulators": {
            "pulse": {"source": "bass", "amount": 0.07, "bias": 0.0, "curve": "ease_out", "clamp": [0.0, 0.07]},
            "shake": {"source": "onset", "amount": 0.018, "bias": 0.0, "curve": "ease_out", "threshold": 0.3, "clamp": [0.0, 0.018]},
            "flash": {"source": "onset", "amount": 0.22, "bias": 0.0, "curve": "ease_out", "threshold": 0.35, "clamp": [0.0, 0.22]},
            "chroma": {"source": "high", "amount": 0.006, "bias": 0.0, "curve": "linear", "threshold": 0.4, "clamp": [0.0, 0.006]},
        },
    },
    "ambient": {
        "bindings": {
            "bass": {"source": "bass", "amount": 0.65, "bias": 0.08, "curve": "smoothstep", "clamp": [0.0, 1.0]},
            "mid": {"source": "mid", "amount": 0.55, "bias": 0.08, "curve": "smoothstep", "clamp": [0.0, 1.0]},
            "high": {"source": "high", "amount": 0.35, "bias": 0.05, "curve": "smoothstep", "clamp": [0.0, 1.0]},
            "onset": {"source": "onset", "amount": 0.25, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
        },
        "modulators": {
            "pulse": {"source": "energy", "amount": 0.035, "bias": 0.0, "curve": "smoothstep", "clamp": [0.0, 0.035]},
        },
    },
    "ferro-impact": {
        "bindings": {
            "bass": {"source": "bass", "amount": 1.6, "bias": 0.0, "curve": "ease_out", "clamp": [0.0, 1.6]},
            "mid": {"source": "mid", "amount": 1.2, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.2]},
            "high": {"source": "high", "amount": 0.8, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "onset": {"source": "onset", "amount": 2.2, "bias": 0.0, "curve": "ease_out", "threshold": 0.15, "clamp": [0.0, 2.2]},
        },
        "modulators": {
            "pulse": {"source": "bass", "amount": 0.12, "bias": 0.0, "curve": "ease_out", "clamp": [0.0, 0.12]},
            "shake": {"source": "onset", "amount": 0.025, "bias": 0.0, "curve": "ease_out", "threshold": 0.25, "clamp": [0.0, 0.025]},
            "flash": {"source": "onset", "amount": 0.3, "bias": 0.0, "curve": "ease_out", "threshold": 0.3, "clamp": [0.0, 0.3]},
            "chroma": {"source": "onset", "amount": 0.012, "bias": 0.0, "curve": "ease_out", "threshold": 0.35, "clamp": [0.0, 0.012]},
        },
    },
    "camera-driven": {
        "bindings": {
            "bass": {"source": "bass", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "mid": {"source": "mid", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "high": {"source": "high", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "onset": {"source": "onset", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
        },
        "modulators": {
            "camera_distance": {"source": "bass", "amount": 0.28, "bias": 0.0, "curve": "ease_out", "clamp": [0.0, 0.28]},
            "camera_elevation": {"source": "mid", "amount": 0.24, "bias": -0.08, "curve": "smoothstep", "clamp": [-0.08, 0.16]},
            "camera_roll": {"source": "high", "amount": 0.18, "bias": -0.04, "curve": "smoothstep", "clamp": [-0.04, 0.14]},
            "camera_kick": {"source": "onset", "amount": 0.3, "bias": 0.0, "curve": "ease_out", "threshold": 0.2, "clamp": [0.0, 0.3]},
        },
    },
    "spectral-resonance": {
        "bindings": {
            "bass": {"source": "bass", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "mid": {"source": "mid", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "high": {"source": "high", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "onset": {"source": "onset", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
        },
        "modulators": {
            "form_scale": {"source": "amplitude", "amount": 0.32, "bias": 0.0, "curve": "smoothstep", "clamp": [0.0, 0.32]},
            "form_deformation": {"source": "spectral_centroid", "amount": 1.0, "bias": 0.0, "curve": "smoothstep", "clamp": [0.0, 1.0]},
            "form_ripple": {"source": "onset", "amount": 0.14, "bias": 0.0, "curve": "ease_out", "threshold": 0.15, "clamp": [0.0, 0.14]},
        },
    },
    "spectral-radial": {
        "bindings": {
            "bass": {"source": "bass", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "mid": {"source": "mid", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "high": {"source": "high", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "onset": {"source": "onset", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
        },
        "modulators": {
            "form_extent": {"source": "amplitude", "amount": 0.95, "bias": 0.0, "curve": "smoothstep", "clamp": [0.0, 0.95]},
            "form_rotation": {"source": "spectral_centroid", "amount": 6.283185, "bias": 0.0, "curve": "smoothstep", "clamp": [0.0, 6.283185]},
            "form_ripple": {"source": "onset", "amount": 0.12, "bias": 0.0, "curve": "ease_out", "threshold": 0.15, "clamp": [0.0, 0.12]},
        },
    },
    "spectral-radial-jagged": {
        "bindings": {
            "bass": {"source": "bass", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "mid": {"source": "mid", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "high": {"source": "high", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
            "onset": {"source": "onset", "amount": 1.0, "bias": 0.0, "curve": "linear", "clamp": [0.0, 1.0]},
        },
        "modulators": {
            "form_extent": {"source": "amplitude", "amount": 0.95, "bias": 0.0, "curve": "smoothstep", "clamp": [0.0, 0.95]},
            "form_rotation": {"source": "spectral_centroid", "amount": 6.283185, "bias": 0.0, "curve": "smoothstep", "clamp": [0.0, 6.283185]},
            "form_ripple": {"source": "onset", "amount": 0.12, "bias": 0.0, "curve": "ease_out", "threshold": 0.15, "clamp": [0.0, 0.12]},
            "form_jaggedness": {"source": "amplitude", "amount": 0.06, "bias": 0.0, "curve": "smoothstep", "clamp": [0.0, 0.06]},
            "form_jagged_scale": {"source": "spectral_centroid", "amount": 6.0, "bias": 0.0, "curve": "smoothstep", "clamp": [0.0, 6.0]},
        },
    },
    "manual": {"bindings": {}, "modulators": {}},
}

TEMPLATES: Dict[str, Dict[str, Any]] = {
    "builtins/mercury-intro": {
        "renderer": {
            "palette": "steel",
            "forms": ["mercury", "wring"],
            "cameras": ["orbit", "crane"],
            "form_len_sec": 6.0,
            "camera_len_sec": 9.0,
        },
        "reactivity": {"preset": "balanced"},
        "post": [],
    },
    "builtins/ferro-impact": {
        "renderer": {
            "palette": "steel",
            "forms": ["ferro", "chaos"],
            "cameras": ["dutch", "macro"],
            "form_len_sec": 4.0,
            "camera_len_sec": 4.0,
        },
        "reactivity": {"preset": "ferro-impact"},
        "post": [],
    },
}

CONFIG_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://mastergray.local/metalheart/config-v1.schema.json",
    "title": "Metalheart Studio config",
    "type": "object",
    "required": ["version", "audio", "scenes"],
    "properties": {
        "version": {"const": 1},
        "audio": {"type": "string", "minLength": 1},
        "analysis": {"type": "object"},
        "settings": {
            "type": "object",
            "properties": {
                "quality": {"enum": sorted(QUALITY_PROFILES)},
                "width": {"type": "integer", "minimum": 2, "multipleOf": 2},
                "height": {"type": "integer", "minimum": 2, "multipleOf": 2},
                "fps": {"type": "integer", "minimum": 1},
                "crf": {"type": "integer", "minimum": 0, "maximum": 51},
                "seed": {"type": ["integer", "null"]},
                "time_mode": {"enum": ["global", "scene"]},
                "workers": {"anyOf": [{"const": "auto"}, {"type": "integer", "minimum": 1}]},
                "chunk_sec": {"type": "number", "exclusiveMinimum": 0},
                "resume": {"type": "boolean"},
            },
            "additionalProperties": True,
        },
        "scenes": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/scene"},
        },
        "post": {"type": "array"},
    },
    "$defs": {
        "binding": {
            "type": "object",
            "required": ["source"],
            "properties": {
                "source": {"enum": SOURCES},
                "amount": {"type": "number"},
                "bias": {"type": "number"},
                "curve": {"enum": CURVES},
                "threshold": {"type": "number", "minimum": 0.0, "exclusiveMaximum": 1.0},
                "clamp": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "number"}},
            },
            "additionalProperties": True,
        },
        "renderer": {
            "type": "object",
            "properties": {
                "id": {"const": "metalheart"},
                "palette": {"enum": PALETTES},
                "core": {"enum": CORES},
                "forms": {"type": "array", "minItems": 1, "items": {"enum": FORMS}},
                "cameras": {"type": "array", "minItems": 1, "items": {"enum": CAMERAS}},
                "form_len_sec": {"type": "number", "exclusiveMinimum": 0},
                "camera_len_sec": {"type": "number", "exclusiveMinimum": 0},
                "camera_speed": {"type": "number", "minimum": 0.0, "maximum": 8.0},
                "camera_phase_sec": {"type": "number", "minimum": 0.0, "maximum": 120.0},
                "camera_intensity": {"type": "number", "minimum": 0.0, "maximum": 3.0},
                "crossfade_sec": {"type": "number", "exclusiveMinimum": 0},
                "decor": {"type": "boolean"},
                "anti_alias": {"type": "boolean"},
                "core_scale": {"type": "number", "minimum": 0.1, "maximum": 1.0},
                "surface": {"$ref": "#/$defs/surface"},
                "form_style": {"$ref": "#/$defs/formStyle"},
            },
            "additionalProperties": True,
        },
        "surface": {
            "type": "object",
            "properties": {
                "image": {"type": ["string", "null"]},
                "mapping": {"const": "triplanar"},
                "scale": {"type": "number", "minimum": 0.05, "maximum": 100.0},
                "rotation_deg": {"type": "number", "minimum": -3600.0, "maximum": 3600.0},
                "material": {"enum": ["metallic", "matte"]},
                "sampling": {"enum": ["bilinear", "nearest"]},
                "texel_steps": {
                    "anyOf": [
                        {"const": 0},
                        {"type": "integer", "minimum": 2, "maximum": 1024},
                    ],
                },
                "lighting_steps": {
                    "anyOf": [
                        {"const": 0},
                        {"type": "integer", "minimum": 2, "maximum": 64},
                    ],
                },
            },
            "additionalProperties": True,
        },
        "formStyle": {
            "type": "object",
            "properties": {
                "faceting": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "jaggedness": {"type": "number", "minimum": 0.0, "maximum": 0.12},
                "jagged_scale": {"type": "number", "minimum": 1.0, "maximum": 16.0},
                "geometry_steps": {
                    "anyOf": [
                        {"const": 0},
                        {"type": "integer", "minimum": 2, "maximum": 32},
                    ],
                },
            },
            "additionalProperties": True,
        },
        "finish": {
            "type": "object",
            "properties": {
                "bloom": {"type": "number", "minimum": 0.0, "maximum": 5.0},
                "wide_bloom": {"type": "number", "minimum": 0.0, "maximum": 5.0},
                "streaks": {"type": "number", "minimum": 0.0, "maximum": 5.0},
                "onset_streaks": {"type": "number", "minimum": 0.0, "maximum": 10.0},
                "flash": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "chroma": {"type": "number", "minimum": 0.0, "maximum": 0.05},
                "chroma_onset": {"type": "number", "minimum": 0.0, "maximum": 0.05},
                "slice_glitch": {"type": "boolean"},
                "slice_threshold": {"type": "number", "minimum": 0.0, "maximum": 10.0},
                "vignette": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "scanlines": {"type": "boolean"},
                "grain": {"type": "number", "minimum": 0.0, "maximum": 0.2},
                "grain_high": {"type": "number", "minimum": 0.0, "maximum": 0.2},
            },
            "additionalProperties": True,
        },
        "overlayItem": {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string", "minLength": 1},
                "position": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "number", "minimum": 0.0, "maximum": 1.0}},
                "anchor": {"enum": ["top_left", "top_center", "top_right", "center", "bottom_left", "bottom_center", "bottom_right"]},
                "size": {"type": "number", "minimum": 0.005, "maximum": 0.25},
                "color": {"type": "string", "pattern": "^#[0-9A-Fa-f]{6}$"},
                "opacity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
            "additionalProperties": True,
        },
        "overlay": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "reference_hud": {"type": "boolean"},
                "items": {"type": "array", "items": {"$ref": "#/$defs/overlayItem"}},
            },
            "additionalProperties": True,
        },
        "background": {
            "type": "object",
            "properties": {
                "source": {"enum": ["palette", "image"]},
                "image": {"type": ["string", "null"]},
                "fit": {"enum": ["cover", "contain", "tile"]},
                "scale": {"type": "number", "minimum": 0.1, "maximum": 10.0},
                "rotation_deg": {"type": "number", "minimum": -3600.0, "maximum": 3600.0},
                "offset": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {"type": "number", "minimum": -2.0, "maximum": 2.0},
                },
                "opacity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "pulse_brightness": {"type": "number", "minimum": 0.0, "maximum": 2.0},
                "pulse_scale": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "pulse_center": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "material": {"enum": ["flat", "matte", "metallic"]},
                "ripple": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "amount": {"type": "number", "minimum": 0.0, "maximum": 0.5},
                        "scale": {"type": "number", "minimum": 0.25, "maximum": 24.0},
                        "travel_speed": {"type": "number", "minimum": 0.0, "maximum": 4.0},
                        "warp": {"type": "number", "minimum": 0.0, "maximum": 0.2},
                        "specular": {"type": "number", "minimum": 0.0, "maximum": 2.0},
                        "roughness": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    },
                    "additionalProperties": True,
                },
                "dots": {"type": "boolean"},
                "ghosts": {"type": "boolean"},
                "shadow": {"type": "boolean"},
            },
            "additionalProperties": True,
        },
        "scene": {
            "type": "object",
            "required": ["start_sec", "end_sec"],
            "properties": {
                "id": {"type": "string", "minLength": 1},
                "name": {"type": "string"},
                "start_sec": {"type": "number", "minimum": 0.0},
                "end_sec": {"type": "number", "exclusiveMinimum": 0.0},
                "template": {"type": "string"},
                "renderer": {"$ref": "#/$defs/renderer"},
                "reactivity": {
                    "type": "object",
                    "properties": {
                        "preset": {"enum": sorted(REACTIVITY_PRESETS)},
                        "bindings": {"type": "object", "additionalProperties": {"$ref": "#/$defs/binding"}},
                        "modulators": {"type": "object", "additionalProperties": {"$ref": "#/$defs/binding"}},
                    },
                    "additionalProperties": True,
                },
                "finish": {"$ref": "#/$defs/finish"},
                "overlay": {"$ref": "#/$defs/overlay"},
                "background": {"$ref": "#/$defs/background"},
                "post": {"type": "array"},
            },
            "additionalProperties": True,
        },
    },
    "additionalProperties": True,
}
