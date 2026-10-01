# Owned frame-effect catalog derived from Glitzle post-filter operations and presets

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import copy  # Return catalog data without exposing shared mutable definitions
from typing import Any, Dict, List, Optional  # Python 3.8-compatible collection annotations


# :: STRING, ANY, FLOAT?, FLOAT?, FLOAT?, STRING? -> ARRAY<STRING, ANY>
# Describes one typed effect parameter for validation and future UI controls
def _parameter(
    valueType: str,
    default: Any,
    minimum: Any = None,
    maximum: Any = None,
    step: Any = None,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    value = {"type": valueType, "default": default}
    if minimum is not None:
        value["minimum"] = minimum
    if maximum is not None:
        value["maximum"] = maximum
    if step is not None:
        value["step"] = step
    if role is not None:
        value["role"] = role
    return value


# :: STRING, [STRING] -> ARRAY<STRING, ANY>
# Describes one enumerated string parameter for validation and Qt choices
def _enumParameter(default: str, values: List[str]) -> Dict[str, Any]:
    return {"type": "string", "default": default, "enum": values}


# :: STRING, STRING, STRING, [ARRAY<STRING, ANY>], ARRAY<STRING, ARRAY<STRING, ANY>>?, STRING, BOOL, BOOL, BOOL -> ARRAY<STRING, ANY>
# Builds one immutable catalog definition
def _effect(
    effectId: str,
    label: str,
    category: str,
    operations: List[Dict[str, Any]],
    parameters: Optional[Dict[str, Dict[str, Any]]] = None,
    source: str = "glitzle-studio-py",
    needsAudio: bool = False,
    needsPreviousFrames: bool = False,
    featured: bool = False,
) -> Dict[str, Any]:
    operationIds = [str(operation.get("op", "")) for operation in operations]
    temporalOperations = {
        "noise",
        "zoomShake",
        "sliceShiftY",
        "sliceShiftX",
        "blockJitter",
        "tear",
        "rectangles",
        "vhs",
        "xor",
        "tetrys",
        "ziti",
        "chromatic",
        "pixelSort",
        "slitscan",
        "scanlineCorrupt",
    }
    return {
        "id": effectId,
        "label": label,
        "category": category,
        "description": "{0}-derived {1} frame effect.".format(source, label.lower()),
        "type": "post_filter",
        "deterministic": True,
        "needs_audio": needsAudio,
        "needs_previous_frames": needsPreviousFrames,
        "featured": featured,
        "uses_time": bool(temporalOperations.intersection(operationIds)),
        "pixel_formats": ["bgr24"],
        "resolution_support": "arbitrary",
        "estimated_cost": "low" if len(operations) <= 2 else "medium",
        "quality_profiles": ["preview", "draft", "final"],
        "parameters": parameters or {},
        "operations": operations,
        "source": source,
    }


EFFECT_LIBRARY: Dict[str, Dict[str, Any]] = {}


# :: ARRAY<STRING, ANY> -> NONE
# Registers one definition while rejecting duplicate stable identifiers
def _register(definition: Dict[str, Any]) -> None:
    effectId = definition["id"]
    if effectId in EFFECT_LIBRARY:
        raise RuntimeError("duplicate effect id: {0}".format(effectId))
    EFFECT_LIBRARY[effectId] = definition


_register(
    _effect(
        "contrast",
        "Contrast",
        "Color",
        [{"op": "contrast", "value": 1.25}],
        {"value": _parameter("number", 1.25, 0.0, 3.0, 0.01, "gain")},
        source="glitchstation",
    )
)
_register(
    _effect(
        "saturation",
        "Saturation",
        "Color",
        [{"op": "saturation", "value": 1.35}],
        {"value": _parameter("number", 1.35, 0.0, 3.0, 0.01, "gain")},
        source="glitchstation",
    )
)
_register(
    _effect(
        "posterize",
        "Posterize",
        "Color",
        [{"op": "posterize", "levels": 5}],
        {"levels": _parameter("integer", 5, 2, 12, 1, "depth")},
        source="glitchstation",
    )
)
_register(
    _effect(
        "channels",
        "Channels",
        "Color",
        [{"op": "channels", "r": 1.2, "g": 1.0, "b": 1.2}],
        {
            "r": _parameter("number", 1.2, 0.0, 3.0, 0.01, "gain"),
            "g": _parameter("number", 1.0, 0.0, 3.0, 0.01, "gain"),
            "b": _parameter("number", 1.2, 0.0, 3.0, 0.01, "gain"),
        },
        source="glitchstation",
    )
)
_register(
    _effect(
        "grayscale",
        "Grayscale",
        "Color",
        [{"op": "grayscale", "amount": 1.0}],
        {"amount": _parameter("number", 1.0, 0.0, 1.0, 0.01, "blend")},
        source="glitchstation",
    )
)
_register(
    _effect(
        "invert",
        "Invert",
        "Color",
        [{"op": "invert", "amount": 1.0}],
        {"amount": _parameter("number", 1.0, 0.0, 1.0, 0.01, "blend")},
        source="glitchstation",
    )
)
_register(_effect("noise", "Noise", "Building Blocks", [{"op": "noise", "amount": 12.0}], {"amount": _parameter("number", 12.0, 0.0, 128.0)}))
_register(_effect("pixelate", "Pixelate", "Building Blocks", [{"op": "pixelate", "size": 4}], {"size": _parameter("integer", 4, 1, 256)}))
_register(_effect("scanlines", "Scanlines", "Building Blocks", [{"op": "scanlines", "strength": 0.16}], {"strength": _parameter("number", 0.16, 0.0, 1.0)}))
_register(
    _effect(
        "rgb_shift",
        "RGB Shift",
        "Shift",
        [{"op": "rgbShift", "rX": 6, "bX": -6, "edge_mode": "wrap"}],
        {
            "rX": _parameter("integer", 6, -40, 40, 1, "offset"),
            "bX": _parameter("integer", -6, -40, 40, 1, "offset"),
            "edge_mode": _enumParameter("wrap", ["wrap", "clamp"]),
        },
        source="glitchstation",
    )
)
_register(
    _effect(
        "scale",
        "Scale",
        "Building Blocks",
        [{"op": "scale", "x": 1.1, "y": 1.1}],
        {
            "x": _parameter("number", 1.1, 0.1, 4.0),
            "y": _parameter("number", 1.1, 0.1, 4.0),
        },
    )
)
_register(_effect("zoom_shake", "Zoom Shake", "Building Blocks", [{"op": "zoomShake", "amp": 0.04}], {"amp": _parameter("number", 0.04, 0.0, 0.5)}))
_register(
    _effect(
        "slice_shift_y",
        "Horizontal Slice Shift",
        "Building Blocks",
        [{"op": "sliceShiftY", "bands": 12, "strength": 18.0}],
        {
            "bands": _parameter("integer", 12, 1, 128),
            "strength": _parameter("number", 18.0, 0.0, 512.0),
        },
    )
)
_register(
    _effect(
        "slice_shift_x",
        "Vertical Slice Shift",
        "Building Blocks",
        [{"op": "sliceShiftX", "cols": 10, "strength": 14.0}],
        {
            "cols": _parameter("integer", 10, 1, 128),
            "strength": _parameter("number", 14.0, 0.0, 512.0),
        },
    )
)
_register(
    _effect(
        "block_jitter",
        "Block Jitter",
        "Shift",
        [{"op": "blockJitter", "size": 48, "strength": 14.0, "chance": 0.25, "seed": 0, "rate": 1.0}],
        {
            "size": _parameter("integer", 48, 4, 128, 1, "size"),
            "strength": _parameter("number", 14.0, 0.0, 64.0, 1, "magnitude"),
            "chance": _parameter("number", 0.25, 0.0, 1.0, 0.01, "chance"),
            "seed": _parameter("integer", 0, 0, 127, 1, "seed"),
            "rate": _parameter("number", 1.0, 0.0, 4.0, 0.05, "rate"),
        },
        source="glitchstation",
    )
)
_register(
    _effect(
        "tear",
        "Tear",
        "Shift",
        [{"op": "tear", "direction": "horizontal", "bands": 16, "strength": 18.0, "seed": 0, "rate": 1.0}],
        {
            "direction": _enumParameter("horizontal", ["horizontal", "vertical"]),
            "bands": _parameter("integer", 16, 1, 64, 1, "count"),
            "strength": _parameter("number", 18.0, 0.0, 64.0, 1, "magnitude"),
            "seed": _parameter("integer", 0, 0, 127, 1, "seed"),
            "rate": _parameter("number", 1.0, 0.0, 4.0, 0.05, "rate"),
        },
        source="glitchstation",
    )
)
_register(
    _effect(
        "rectangles",
        "Rectangles",
        "Blocks",
        [{"op": "rectangles", "n_rects": 8, "seed": 0, "rate": 1.0}],
        {
            "n_rects": _parameter("integer", 8, 0, 32, 1, "count"),
            "seed": _parameter("integer", 0, 0, 127, 1, "seed"),
            "rate": _parameter("number", 1.0, 0.0, 4.0, 0.05, "rate"),
        },
        source="glitchstation",
    )
)
_register(_effect("blur", "Blur", "Building Blocks", [{"op": "blur", "radius": 1.0}], {"radius": _parameter("number", 1.0, 0.0, 64.0)}))
_register(_effect("vignette", "Vignette", "Building Blocks", [{"op": "vignette", "amount": 0.25}], {"amount": _parameter("number", 0.25, 0.0, 1.0)}))


_register(
    _effect(
        "vhs",
        "VHS",
        "Screen",
        [{"op": "vhs", "tracking": 0.3, "chromaBleed": 0.4, "noise": 0.3, "headSwitch": 0.5, "seed": 0, "rate": 1.0}],
        {
            "tracking": _parameter("number", 0.3, 0.0, 1.0, 0.01, "magnitude"),
            "chromaBleed": _parameter("number", 0.4, 0.0, 1.0, 0.01, "magnitude"),
            "noise": _parameter("number", 0.3, 0.0, 1.0, 0.01, "magnitude"),
            "headSwitch": _parameter("number", 0.5, 0.0, 1.0, 0.01, "blend"),
            "seed": _parameter("integer", 0, 0, 127, 1, "seed"),
            "rate": _parameter("number", 1.0, 0.0, 4.0, 0.05, "rate"),
        },
        source="glitchstation",
    )
)
_register(
    _effect(
        "arcade",
        "Arcade",
        "Screen",
        [{"op": "arcade", "curvature": 0.15, "maskStrength": 0.4, "paletteLevels": 4, "scanStrength": 0.3}],
        {
            "curvature": _parameter("number", 0.15, 0.0, 0.5, 0.01, "magnitude"),
            "maskStrength": _parameter("number", 0.4, 0.0, 1.0, 0.01, "blend"),
            "paletteLevels": _parameter("integer", 4, 2, 8, 1, "depth"),
            "scanStrength": _parameter("number", 0.3, 0.0, 1.0, 0.01, "blend"),
        },
        source="glitchstation",
    )
)


_register(_effect("mirror_h", "Horizontal Mirror", "Dazzle / Mirror", [{"op": "mirrorH"}], source="dazzle-video-maker-py"))
_register(_effect("mirror_v", "Vertical Mirror", "Dazzle / Mirror", [{"op": "mirrorV"}], source="dazzle-video-maker-py"))
_register(_effect("mirror_quad", "Quad Mirror", "Dazzle / Mirror", [{"op": "mirrorQuad"}], source="dazzle-video-maker-py"))
_register(_effect("mirror_diamond", "Diamond Mirror", "Dazzle / Mirror", [{"op": "mirrorDiamond"}], source="dazzle-video-maker-py"))
_register(
    _effect(
        "xor",
        "XOR Interference",
        "Dazzle / Signal",
        [{"op": "xor", "shift_x": 10, "shift_y": 5}],
        {
            "shift_x": _parameter("integer", 10, -512, 512),
            "shift_y": _parameter("integer", 5, -512, 512),
        },
        source="dazzle-video-maker-py",
    )
)
_register(
    _effect(
        "tetrys",
        "Tetrys",
        "Dazzle / Warp",
        [{"op": "tetrys", "block_size": 16, "direction": "down"}],
        {
            "block_size": _parameter("integer", 16, 2, 512),
            "direction": _enumParameter("down", ["down", "up", "left", "right"]),
        },
        source="vidglitch-app",
    )
)
_register(
    _effect(
        "ziti",
        "Ziti",
        "Dazzle / Warp",
        [{"op": "ziti", "curvature": 0.3, "direction": "right"}],
        {
            "curvature": _parameter("number", 0.3, 0.05, 2.0),
            "direction": _enumParameter("right", ["right", "left", "down", "up"]),
        },
        source="dazzle-video-maker-py",
    )
)
_register(
    _effect(
        "chromatic",
        "Chromatic (Glitzle)",
        "Glitzle / Glitch",
        [{"op": "chromatic", "amount": 16.0, "direction": "circular", "audio_scale": 0.75}],
        {
            "amount": _parameter("number", 16.0, 0.0, 256.0),
            "direction": _enumParameter("circular", ["horizontal", "vertical", "circular"]),
            "audio_scale": _parameter("number", 0.75, 0.0, 1.0),
        },
        source="glitzle-studio-py/glitch-maker-py",
        needsAudio=True,
    )
)
_register(
    _effect(
        "pixel_sort",
        "Pixel Sort (Glitzle)",
        "Glitzle / Glitch",
        [
            {
                "op": "pixelSort",
                "sort_by": "brightness",
                "direction": "horizontal",
                "lower_threshold": 0.25,
                "upper_threshold": 0.8,
                "reverse": False,
                "angle": 0,
                "audio_scale": 0.5,
            }
        ],
        {
            "sort_by": _enumParameter("brightness", ["brightness", "hue", "saturation"]),
            "direction": _enumParameter("horizontal", ["horizontal", "vertical", "both"]),
            "lower_threshold": _parameter("number", 0.25, 0.0, 1.0),
            "upper_threshold": _parameter("number", 0.8, 0.0, 1.0),
            "reverse": _parameter("boolean", False),
            "angle": _parameter("integer", 0, 0, 359),
            "audio_scale": _parameter("number", 0.5, 0.0, 1.0),
        },
        source="glitzle-studio-py/glitch-maker-py",
        needsAudio=True,
    )
)
_register(
    _effect(
        "slitscan",
        "Slitscan (Glitzle)",
        "Glitzle / Glitch",
        [{"op": "slitscan", "direction": "horizontal", "max_delay_frames": 30, "audio_scale": 0.5}],
        {
            "direction": _enumParameter("horizontal", ["horizontal", "vertical"]),
            "max_delay_frames": _parameter("integer", 30, 1, 600),
            "audio_scale": _parameter("number", 0.5, 0.0, 1.0),
        },
        source="glitzle-studio-py/glitch-maker-py",
        needsAudio=True,
        needsPreviousFrames=True,
    )
)
_register(
    _effect(
        "scanline_corrupt",
        "Scanline Corrupt",
        "Glitch Maker",
        [{"op": "scanlineCorrupt", "band_count": 16, "thickness": 3, "displacement": 48, "chroma_amount": 10.0, "audio_scale": 0.65}],
        {
            "band_count": _parameter("integer", 16, 1, 128),
            "thickness": _parameter("integer", 3, 1, 128),
            "displacement": _parameter("integer", 48, 0, 1024),
            "chroma_amount": _parameter("number", 10.0, 0.0, 256.0),
            "audio_scale": _parameter("number", 0.65, 0.0, 1.0),
        },
        source="glitch-maker-py",
        needsAudio=True,
    )
)


_register(_effect("hyper_glitch_like", "Hyper Glitch", "Glitch", [{"op": "rgbShift", "rX": 6, "bX": -6}, {"op": "noise", "amount": 18}, {"op": "posterize", "levels": 5}, {"op": "contrast", "value": 1.45}, {"op": "saturation", "value": 1.8}]))
_register(_effect("digital_tear_like", "Digital Tear", "Glitch", [{"op": "rgbShift", "rX": 10, "bX": -10}, {"op": "posterize", "levels": 4}, {"op": "noise", "amount": 15}, {"op": "contrast", "value": 1.35}]))
_register(_effect("codec_crush_like", "Codec Crush", "Glitch", [{"op": "pixelate", "size": 4}, {"op": "posterize", "levels": 3}, {"op": "noise", "amount": 12}, {"op": "rgbShift", "rX": 4, "bX": -4}]))
_register(_effect("signal_bleed_like", "Signal Bleed", "Glitch", [{"op": "rgbShift", "rX": 3, "bX": -7}, {"op": "blur", "radius": 1.1}, {"op": "contrast", "value": 1.22}, {"op": "saturation", "value": 1.35}]))
_register(_effect("broken_mux_like", "Broken Mux", "Glitch", [{"op": "pixelate", "size": 5}, {"op": "rgbShift", "rX": 9, "bX": -3}, {"op": "noise", "amount": 20}, {"op": "posterize", "levels": 3}]))
_register(_effect("channel_drift_like", "Channel Drift", "Glitch", [{"op": "rgbShift", "rX": 12, "bX": -12}, {"op": "blur", "radius": 0.9}, {"op": "contrast", "value": 1.3}, {"op": "saturation", "value": 1.45}]))
_register(_effect("scan_corrupt_like", "Scan Corrupt", "Glitch", [{"op": "scanlines", "strength": 0.2}, {"op": "noise", "amount": 22}, {"op": "posterize", "levels": 4}, {"op": "rgbShift", "rX": 5, "bX": -9}]))
_register(_effect("compression_spike_like", "Compression Spike", "Glitch", [{"op": "pixelate", "size": 6}, {"op": "contrast", "value": 1.42}, {"op": "noise", "amount": 16}, {"op": "posterize", "levels": 5}]))
_register(_effect("phase_error_like", "Phase Error", "Glitch", [{"op": "rgbShift", "rX": 15, "bX": -6}, {"op": "scanlines", "strength": 0.14}, {"op": "saturation", "value": 1.5}, {"op": "contrast", "value": 1.3}]))
_register(_effect("packet_loss_like", "Packet Loss", "Glitch", [{"op": "pixelate", "size": 7}, {"op": "posterize", "levels": 2}, {"op": "rgbShift", "rX": 6, "bX": -6}, {"op": "noise", "amount": 18}]))
_register(_effect("packet_desync_like", "Packet Desync", "Glitch", [{"op": "sliceShiftY", "bands": 20, "strength": 20}, {"op": "blockJitter", "size": 58, "strength": 18, "chance": 0.38}, {"op": "noise", "amount": 16}, {"op": "contrast", "value": 1.24}]))
_register(_effect("datamosh_drift_like", "Datamosh Drift", "Glitch", [{"op": "blur", "radius": 1.2}, {"op": "sliceShiftX", "cols": 11, "strength": 14}, {"op": "rgbShift", "rX": 9, "bX": -9}, {"op": "contrast", "value": 1.18}]))
_register(
    _effect(
        "datamosh_breakup_like",
        "Datamosh Breakup",
        "Glitch",
        [{"op": "blockJitter", "size": 50, "strength": 24, "chance": 0.46}, {"op": "sliceShiftY", "bands": 16, "strength": 22}, {"op": "posterize", "levels": 3}, {"op": "noise", "amount": 18}],
        featured=True,
    )
)
_register(
    _effect(
        "scanline_desync_like",
        "Scanline Desync",
        "Glitch",
        [{"op": "scanlines", "strength": 0.24}, {"op": "sliceShiftY", "bands": 24, "strength": 16}, {"op": "rgbShift", "rX": 7, "bX": -7}, {"op": "contrast", "value": 1.2}],
        featured=True,
    )
)
_register(_effect("block_corrupt_like", "Block Corrupt", "Glitch", [{"op": "pixelate", "size": 6}, {"op": "blockJitter", "size": 44, "strength": 28, "chance": 0.55}, {"op": "noise", "amount": 20}, {"op": "contrast", "value": 1.32}]))
_register(
    _effect(
        "channel_smear_like",
        "Channel Smear",
        "Glitch",
        [{"op": "rgbShift", "rX": 13, "bX": -12}, {"op": "blur", "radius": 1.0}, {"op": "sliceShiftX", "cols": 9, "strength": 12}, {"op": "saturation", "value": 1.45}],
        featured=True,
    )
)
_register(
    _effect(
        "glitch_warpfield_like",
        "Glitch Warpfield",
        "Glitch",
        [{"op": "zoomShake", "amp": 0.05}, {"op": "sliceShiftY", "bands": 14, "strength": 18}, {"op": "noise", "amount": 17}, {"op": "contrast", "value": 1.28}],
        featured=True,
    )
)
_register(
    _effect(
        "bitplane_scramble_like",
        "Bitplane Scramble",
        "Glitch",
        [{"op": "posterize", "levels": 2}, {"op": "sliceShiftX", "cols": 12, "strength": 16}, {"op": "blockJitter", "size": 60, "strength": 16, "chance": 0.34}, {"op": "noise", "amount": 15}],
        featured=True,
    )
)
_register(
    _effect(
        "stutter_tear_like",
        "Stutter Tear",
        "Glitch",
        [{"op": "sliceShiftY", "bands": 22, "strength": 20}, {"op": "scanlines", "strength": 0.18}, {"op": "blockJitter", "size": 54, "strength": 18, "chance": 0.36}, {"op": "contrast", "value": 1.26}],
        featured=True,
    )
)
_register(_effect("chaos_breach_like", "Chaos Breach", "Chaos", [{"op": "sliceShiftY", "bands": 12, "strength": 20}, {"op": "rgbShift", "rX": 11, "bX": -13}, {"op": "noise", "amount": 24}, {"op": "contrast", "value": 1.55}, {"op": "saturation", "value": 1.75}]))
_register(_effect("chaos_vortex_like", "Chaos Vortex", "Chaos", [{"op": "zoomShake", "amp": 0.05}, {"op": "blur", "radius": 1.4}, {"op": "rgbShift", "rX": 5, "bX": -8}, {"op": "saturation", "value": 1.6}, {"op": "vignette", "amount": 0.28}]))
_register(_effect("film_decay_like", "Film Decay", "Decay", [{"op": "sliceShiftY", "bands": 10, "strength": 10}, {"op": "noise", "amount": 14}, {"op": "saturation", "value": 0.82}, {"op": "contrast", "value": 0.92}, {"op": "vignette", "amount": 0.26}]))
_register(_effect("aged_tape_decay_like", "Aged Tape Decay", "Decay", [{"op": "sliceShiftY", "bands": 16, "strength": 10}, {"op": "blur", "radius": 1.1}, {"op": "scanlines", "strength": 0.12}, {"op": "noise", "amount": 16}, {"op": "saturation", "value": 0.74}]))
_register(_effect("destructive_shatter_corrupt_like", "Destructive Shatter Corrupt", "Destructive", [{"op": "sliceShiftX", "cols": 11, "strength": 24}, {"op": "sliceShiftY", "bands": 15, "strength": 30}, {"op": "noise", "amount": 20}, {"op": "contrast", "value": 1.6}]))
_register(_effect("total_entropy_like", "Total Entropy", "Destructive", [{"op": "blockJitter", "size": 42, "strength": 32, "chance": 0.58}, {"op": "scale", "x": 1.34, "y": 1.2}, {"op": "rgbShift", "rX": 17, "bX": -17}, {"op": "noise", "amount": 35}, {"op": "contrast", "value": 2.2}]))
_register(_effect("retro_crt_like", "Retro CRT", "Retro / CRT", [{"op": "pixelate", "size": 3}, {"op": "scanlines", "strength": 0.16}, {"op": "noise", "amount": 8}, {"op": "saturation", "value": 0.85}]))
_register(_effect("tube_tv_soft_like", "Tube TV Soft", "Retro / CRT", [{"op": "blur", "radius": 1.3}, {"op": "scanlines", "strength": 0.12}, {"op": "saturation", "value": 0.8}, {"op": "contrast", "value": 1.08}]))
_register(_effect("arcade_phosphor_like", "Arcade Phosphor", "Retro / CRT", [{"op": "pixelate", "size": 2}, {"op": "scanlines", "strength": 0.22}, {"op": "saturation", "value": 1.28}, {"op": "contrast", "value": 1.22}]))
_register(_effect("vhs_soft_bleed_like", "VHS Soft Bleed", "Retro / CRT", [{"op": "blur", "radius": 1.6}, {"op": "scanlines", "strength": 0.1}, {"op": "noise", "amount": 10}, {"op": "saturation", "value": 0.92}]))
_register(_effect("arcade_night_like", "Arcade Night", "Retro / CRT", [{"op": "scanlines", "strength": 0.24}, {"op": "saturation", "value": 1.35}, {"op": "contrast", "value": 1.28}, {"op": "noise", "amount": 7}]))
_register(_effect("violent_like", "Violent", "Violent", [{"op": "sliceShiftY", "bands": 14, "strength": 22}, {"op": "rgbShift", "rX": 8, "bX": -8}, {"op": "noise", "amount": 26}, {"op": "contrast", "value": 1.7}, {"op": "saturation", "value": 2.1}, {"op": "posterize", "levels": 4}]))
_register(_effect("violent_impact_like", "Violent Impact", "Violent", [{"op": "zoomShake", "amp": 0.06}, {"op": "posterize", "levels": 3}, {"op": "contrast", "value": 2.0}, {"op": "scanlines", "strength": 0.22}, {"op": "vignette", "amount": 0.3}]))


# :: VOID -> [STRING]
# Returns stable effect identifiers for CLI choices and validation
def effectIds() -> List[str]:
    return sorted(EFFECT_LIBRARY)


# :: VOID -> [ARRAY<STRING, ANY>]
# Returns UI-safe effect metadata without internal operation implementations
def publicEffectCatalog() -> List[Dict[str, Any]]:
    entries = []
    for effectId in effectIds():
        definition = copy.deepcopy(EFFECT_LIBRARY[effectId])
        definition.pop("operations", None)
        entries.append(definition)
    return entries


# :: STRING -> ARRAY<STRING, ANY>?
# Returns a defensive copy of one complete effect definition
def effectDefinition(effectId: str) -> Any:
    definition = EFFECT_LIBRARY.get(effectId)
    return copy.deepcopy(definition) if definition is not None else None
