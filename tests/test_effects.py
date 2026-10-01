# Unit tests for the owned Glitzle-derived ordered effect library

import math  # Reconstruct compatible Ziti projection geometry
from typing import Any, Dict, List  # Python 3.8-compatible test annotations

import numpy as np  # Build compact deterministic BGR frame fixtures

from metalheart.effect_catalog import effectDefinition  # Inspect complete owned effect definitions
from metalheart.effect_catalog import effectIds  # Verify the stable public effect catalog
from metalheart.effect_catalog import publicEffectCatalog  # Verify UI-safe effect metadata
from metalheart.effects import EffectChain  # Exercise ordered deterministic frame processing


# :: VOID -> ANY
# Creates a nonuniform BGR frame that exposes color and spatial transforms
def _frame() -> np.ndarray:
    values = np.arange(24 * 32 * 3, dtype=np.uint32).reshape(24, 32, 3)
    return (values % 256).astype(np.uint8)


# :: STRING, FLOAT? -> ARRAY<STRING, ANY>
# Builds one resolved effect entry directly from catalog operations
def _entry(effectId: str, mix: float = 1.0) -> Dict[str, Any]:
    definition = effectDefinition(effectId)
    assert definition is not None
    return {
        "type": "post_filter",
        "id": effectId,
        "enabled": True,
        "mix": mix,
        "parameters": {},
        "operations": definition["operations"],
    }


# :: VOID -> NONE
# Verifies the first owned catalog spans Glitzle primitives and look categories
def testPublishesGlitzleDerivedCatalog() -> None:
    identifiers = effectIds()
    entries = publicEffectCatalog()
    categories = {entry["category"] for entry in entries}
    assert len(identifiers) >= 20
    assert "rgb_shift" in identifiers
    assert "hyper_glitch_like" in identifiers
    assert "retro_crt_like" in identifiers
    assert {
        "mirror_h",
        "mirror_v",
        "mirror_quad",
        "mirror_diamond",
        "xor",
        "tetrys",
        "ziti",
        "chromatic",
        "pixel_sort",
        "slitscan",
        "scanline_corrupt",
    } <= set(identifiers)
    assert {"Building Blocks", "Color", "Glitch", "Chaos", "Decay", "Destructive", "Retro / CRT", "Violent"} <= categories
    assert all("operations" not in entry for entry in entries)
    assert all(entry["pixel_formats"] == ["bgr24"] for entry in entries)
    assert all(entry["resolution_support"] == "arbitrary" for entry in entries)


# :: VOID -> NONE
# Verifies Glitchstation color controls publish matching defaults and UI metadata
def testPublishesGlitchstationColorControls() -> None:
    expected = {
        "contrast": {"value": (1.25, 0.0, 3.0, 0.01, "gain")},
        "saturation": {"value": (1.35, 0.0, 3.0, 0.01, "gain")},
        "posterize": {"levels": (5, 2, 12, 1, "depth")},
        "channels": {
            "r": (1.2, 0.0, 3.0, 0.01, "gain"),
            "g": (1.0, 0.0, 3.0, 0.01, "gain"),
            "b": (1.2, 0.0, 3.0, 0.01, "gain"),
        },
        "grayscale": {"amount": (1.0, 0.0, 1.0, 0.01, "blend")},
        "invert": {"amount": (1.0, 0.0, 1.0, 0.01, "blend")},
    }
    for effectId, parameters in expected.items():
        definition = effectDefinition(effectId)
        assert definition is not None
        assert definition["category"] == "Color"
        assert definition["source"] == "glitchstation"
        for name, values in parameters.items():
            metadata = definition["parameters"][name]
            assert (
                metadata["default"],
                metadata["minimum"],
                metadata["maximum"],
                metadata["step"],
                metadata["role"],
            ) == values


# :: VOID -> NONE
# Verifies the selected Glitchstation shift, block, and screen pedals are public
def testPublishesSelectedGlitchstationPedals() -> None:
    identifiers = set(effectIds())
    assert {"tear", "rectangles", "vhs", "arcade"} <= identifiers
    assert not {"blister", "randomize", "handheld"} & identifiers
    for effectId in ("tear", "rectangles", "vhs", "arcade", "rgb_shift", "block_jitter"):
        definition = effectDefinition(effectId)
        assert definition is not None
        assert definition["source"] == "glitchstation"
    tetrys = effectDefinition("tetrys")
    assert tetrys is not None
    assert tetrys["parameters"]["direction"]["enum"] == ["down", "up", "left", "right"]
    ziti = effectDefinition("ziti")
    assert ziti is not None
    assert ziti["parameters"]["direction"]["enum"] == ["right", "left", "down", "up"]


# :: VOID -> NONE
# Verifies Glitchstation channel, grayscale, and invert pixel math on BGR frames
def testGlitchstationColorOperationsMatchRgbSemantics() -> None:
    frame = np.asarray([[[10, 20, 30], [120, 160, 200]]], dtype=np.uint8)

    channels = _entry("channels")
    channels["operations"][0].update({"r": 2.0, "g": 0.5, "b": 1.5})
    channelOutput = EffectChain.init([channels], 2, 1, 12, 7).apply(frame, 0.0, 0)
    assert np.array_equal(channelOutput, np.asarray([[[15, 10, 60], [180, 80, 255]]], dtype=np.uint8))

    grayscale = _entry("grayscale")
    grayscale["operations"][0]["amount"] = 0.5
    grayOutput = EffectChain.init([grayscale], 2, 1, 12, 7).apply(frame, 0.0, 0)
    luminance = 0.114 * frame[..., 0] + 0.587 * frame[..., 1] + 0.299 * frame[..., 2]
    expectedGray = np.floor(frame.astype(np.float32) * 0.5 + luminance[..., None] * 0.5 + 0.5)
    assert np.array_equal(grayOutput, expectedGray.astype(np.uint8))

    invert = _entry("invert")
    invert["operations"][0]["amount"] = 0.25
    invertOutput = EffectChain.init([invert], 2, 1, 12, 7).apply(frame, 0.0, 0)
    expectedInvert = np.floor(frame.astype(np.float32) * 0.75 + (255.0 - frame) * 0.25 + 0.5)
    assert np.array_equal(invertOutput, expectedInvert.astype(np.uint8))


# :: VOID -> NONE
# Verifies transparent layer processing moves mattes only for spatial operations
def testLayerEffectsCarrySpatialAlphaWithoutColorLeakage() -> None:
    frame = np.zeros((4, 6, 3), np.uint8)
    frame[:, :2] = [10, 20, 30]
    alpha = np.zeros((4, 6), np.float32)
    alpha[:, :2] = 1.0
    mirror = EffectChain.init([_entry("mirror_h")], 6, 4, 12, 7)
    mirroredFrame, mirroredAlpha = mirror.applyLayer(frame, alpha, 0.0, 0)
    expectedAlpha = alpha.copy()
    expectedAlpha[:, 3:] = np.fliplr(alpha[:, :3])
    expectedFrame = frame.copy()
    expectedFrame[:, 3:] = np.fliplr(frame[:, :3])
    assert np.array_equal(mirroredAlpha, expectedAlpha)
    assert np.array_equal(mirroredFrame, expectedFrame)

    invert = EffectChain.init([_entry("invert")], 6, 4, 12, 7)
    invertedFrame, invertedAlpha = invert.applyLayer(frame, alpha, 0.0, 0)
    assert np.array_equal(invertedAlpha, alpha)
    assert np.all(invertedFrame[:, :2] == np.asarray([245, 235, 225], np.uint8))


# :: VOID -> NONE
# Verifies direct RGB Shift uses Glitchstation's signed wrapping convention
def testRgbShiftSupportsGlitchstationWrapping() -> None:
    frame = np.asarray([[[1, 10, 100], [2, 20, 110], [3, 30, 120], [4, 40, 130]]], dtype=np.uint8)
    effect = _entry("rgb_shift")
    effect["operations"][0].update({"rX": 1, "bX": -1, "edge_mode": "wrap"})
    output = EffectChain.init([effect], 4, 1, 12, 7).apply(frame, 0.0, 0)
    assert np.array_equal(output[0, :, 2], np.asarray([130, 100, 110, 120], dtype=np.uint8))
    assert np.array_equal(output[0, :, 0], np.asarray([2, 3, 4, 1], dtype=np.uint8))
    assert np.array_equal(output[0, :, 1], frame[0, :, 1])


# :: VOID -> NONE
# Verifies Tear direction, seed, and rate select distinct stable band motion
def testTearSupportsHorizontalAndVerticalDirections() -> None:
    frame = _frame()
    horizontal = _entry("tear")
    horizontal["operations"][0].update({"direction": "horizontal", "bands": 6, "strength": 8, "seed": 3, "rate": 0.5})
    vertical = _entry("tear")
    vertical["operations"][0].update({"direction": "vertical", "bands": 6, "strength": 8, "seed": 3, "rate": 0.5})
    horizontalOutput = EffectChain.init([horizontal], 32, 24, 12, 7).apply(frame, 1.0, 12)
    verticalOutput = EffectChain.init([vertical], 32, 24, 12, 7).apply(frame, 1.0, 12)
    assert not np.array_equal(horizontalOutput, frame)
    assert not np.array_equal(verticalOutput, frame)
    assert not np.array_equal(horizontalOutput, verticalOutput)


# :: VOID -> NONE
# Verifies Glitchstation block and rectangle seeds deterministically change layouts
def testSeededBlockEffectsAreStableAndConfigurable() -> None:
    frame = np.arange(48 * 64 * 3, dtype=np.uint32).reshape(48, 64, 3).astype(np.uint8)
    for effectId in ("block_jitter", "rectangles"):
        firstEffect = _entry(effectId)
        secondEffect = _entry(effectId)
        if effectId == "block_jitter":
            firstEffect["operations"][0].update({"size": 8, "strength": 7, "chance": 1.0, "seed": 4})
            secondEffect["operations"][0].update({"size": 8, "strength": 7, "chance": 1.0, "seed": 5})
        else:
            firstEffect["operations"][0].update({"n_rects": 6, "seed": 4})
            secondEffect["operations"][0].update({"n_rects": 6, "seed": 5})
        first = EffectChain.init([firstEffect], 64, 48, 12, 7).apply(frame, 0.5, 6)
        repeated = EffectChain.init([firstEffect], 64, 48, 12, 7).apply(frame, 0.5, 6)
        second = EffectChain.init([secondEffect], 64, 48, 12, 7).apply(frame, 0.5, 6)
        assert np.array_equal(first, repeated), effectId
        assert not np.array_equal(first, frame), effectId
        assert not np.array_equal(first, second), effectId


# :: VOID -> NONE
# Verifies configurable VHS and Arcade programs transform frames deterministically
def testGlitchstationScreenProgramsExecute() -> None:
    frame = _frame()
    for effectId in ("vhs", "arcade"):
        effect = _entry(effectId)
        first = EffectChain.init([effect], 32, 24, 12, 7).apply(frame, 0.5, 6)
        repeated = EffectChain.init([effect], 32, 24, 12, 7).apply(frame, 0.5, 6)
        assert np.array_equal(first, repeated), effectId
        assert not np.array_equal(first, frame), effectId


# :: VOID -> NONE
# Verifies the complete Glitzle Glitch preset category and featured subset are published
def testPublishesCompleteGlitzleGlitchPresetCategory() -> None:
    expected = {
        "hyper_glitch_like",
        "digital_tear_like",
        "codec_crush_like",
        "signal_bleed_like",
        "broken_mux_like",
        "channel_drift_like",
        "scan_corrupt_like",
        "compression_spike_like",
        "phase_error_like",
        "packet_loss_like",
        "packet_desync_like",
        "datamosh_drift_like",
        "datamosh_breakup_like",
        "scanline_desync_like",
        "block_corrupt_like",
        "channel_smear_like",
        "glitch_warpfield_like",
        "bitplane_scramble_like",
        "stutter_tear_like",
    }
    entries = publicEffectCatalog()
    glitchEntries = [entry for entry in entries if entry["category"] == "Glitch"]
    featured = {entry["id"] for entry in glitchEntries if entry["featured"]}
    assert {entry["id"] for entry in glitchEntries} == expected
    assert featured == {
        "datamosh_breakup_like",
        "scanline_desync_like",
        "channel_smear_like",
        "glitch_warpfield_like",
        "bitplane_scramble_like",
        "stutter_tear_like",
    }


# :: VOID -> NONE
# Verifies featured recipes retain Glitzle's exact authored operation order
def testFeaturedGlitchRecipesPreserveOperationOrder() -> None:
    expected = {
        "datamosh_breakup_like": ["blockJitter", "sliceShiftY", "posterize", "noise"],
        "stutter_tear_like": ["sliceShiftY", "scanlines", "blockJitter", "contrast"],
        "bitplane_scramble_like": ["posterize", "sliceShiftX", "blockJitter", "noise"],
        "channel_smear_like": ["rgbShift", "blur", "sliceShiftX", "saturation"],
        "scanline_desync_like": ["scanlines", "sliceShiftY", "rgbShift", "contrast"],
        "glitch_warpfield_like": ["zoomShake", "sliceShiftY", "noise", "contrast"],
    }
    for effectId, operationNames in expected.items():
        definition = effectDefinition(effectId)
        assert definition is not None
        assert [operation["op"] for operation in definition["operations"]] == operationNames


# :: VOID -> NONE
# Verifies selected Retro and CRT recipes retain Glitzle's exact operation order
def testSelectedRetroRecipesPreserveOperationOrder() -> None:
    expected = {
        "vhs_soft_bleed_like": ["blur", "scanlines", "noise", "saturation"],
        "tube_tv_soft_like": ["blur", "scanlines", "saturation", "contrast"],
        "arcade_night_like": ["scanlines", "saturation", "contrast", "noise"],
    }
    for effectId, operationNames in expected.items():
        definition = effectDefinition(effectId)
        assert definition is not None
        assert definition["category"] == "Retro / CRT"
        assert [operation["op"] for operation in definition["operations"]] == operationNames


# :: VOID -> NONE
# Verifies randomized effects reproduce exactly for one seed and frame index
def testNoiseAndBlockEffectsAreDeterministic() -> None:
    effects = [_entry("packet_desync_like"), _entry("noise")]
    first = EffectChain.init(effects, 32, 24, 12, 91).apply(_frame(), 0.5, 6)
    second = EffectChain.init(effects, 32, 24, 12, 91).apply(_frame(), 0.5, 6)
    changed = EffectChain.init(effects, 32, 24, 12, 92).apply(_frame(), 0.5, 6)
    assert np.array_equal(first, second)
    assert not np.array_equal(first, changed)


# :: VOID -> NONE
# Verifies authored ordering matters and bypass or zero mix preserves input bytes
def testEffectsApplyInOrderAndSupportBypass() -> None:
    frame = _frame()
    contrast = _entry("contrast")
    contrast["operations"][0]["value"] = 1.8
    posterize = _entry("posterize")
    posterize["operations"][0]["levels"] = 3
    forward = EffectChain.init([contrast, posterize], 32, 24, 12, 7).apply(frame, 0.0, 0)
    reverse = EffectChain.init([posterize, contrast], 32, 24, 12, 7).apply(frame, 0.0, 0)
    bypassed = _entry("contrast")
    bypassed["enabled"] = False
    zeroMix = _entry("noise", 0.0)
    preserved = EffectChain.init([bypassed, zeroMix], 32, 24, 12, 7).apply(frame, 0.0, 0)
    assert not np.array_equal(forward, reverse)
    assert np.array_equal(frame, preserved)


# :: VOID -> NONE
# Verifies Dazzle mirrors copy the documented source half or quadrant
def testDazzleMirrorGeometry() -> None:
    frame = _frame()
    horizontal = EffectChain.init([_entry("mirror_h")], 32, 24, 12, 7).apply(frame, 0.0, 0)
    vertical = EffectChain.init([_entry("mirror_v")], 32, 24, 12, 7).apply(frame, 0.0, 0)
    quadrant = EffectChain.init([_entry("mirror_quad")], 32, 24, 12, 7).apply(frame, 0.0, 0)
    assert np.array_equal(horizontal[:, 16:], np.fliplr(horizontal[:, :16]))
    assert np.array_equal(vertical[12:], np.flipud(vertical[:12]))
    assert np.array_equal(quadrant[:12, 16:], np.fliplr(quadrant[:12, :16]))
    assert np.array_equal(quadrant[12:, :16], np.flipud(quadrant[:12, :16]))


# :: VOID -> NONE
# Verifies animated Dazzle and Glitch Maker effects evolve by global frame index
def testAnimatedImportedEffectsEvolve() -> None:
    frame = _frame()
    for effectId in ("xor", "tetrys", "ziti", "chromatic", "scanline_corrupt"):
        chain = EffectChain.init([_entry(effectId)], 32, 24, 12, 7)
        first = chain.apply(frame, 0.0, 0)
        later = chain.apply(frame, 1.0, 12)
        assert not np.array_equal(first, later), effectId


# :: VOID -> NONE
# Verifies Tetrys retains VidGlitch's exact per-column rolling algorithm
def testTetrysMatchesVidGlitchAlgorithm() -> None:
    frame = _frame()
    effect = _entry("tetrys")
    effect["operations"][0]["block_size"] = 7
    actual = EffectChain.init([effect], 32, 24, 12, 7).apply(frame, 1.0, 17)
    expected = np.zeros_like(frame)
    columnCount = 32 // 7
    for column in range(columnCount):
        start = column * 7
        end = min(32, start + 7)
        drop = int((17 * (0.5 + column * 0.3)) % 24)
        expected[:, start:end] = np.roll(frame[:, start:end], drop, axis=0)
    expected[:, columnCount * 7:] = frame[:, columnCount * 7:]
    assert np.array_equal(actual, expected)


# :: VOID -> NONE
# Verifies Tetrys can drop strips in all four cardinal directions
def testTetrysSupportsCardinalDirections() -> None:
    frame = _frame()
    outputs = {}
    for direction in ("down", "up", "left", "right"):
        effect = _entry("tetrys")
        effect["operations"][0].update({"block_size": 7, "direction": direction})
        outputs[direction] = EffectChain.init([effect], 32, 24, 12, 7).apply(frame, 1.0, 17)
    assert all(not np.array_equal(frame, output) for output in outputs.values())
    assert not np.array_equal(outputs["down"], outputs["up"])
    assert not np.array_equal(outputs["left"], outputs["right"])
    assert not np.array_equal(outputs["down"], outputs["right"])


# :: VOID -> NONE
# Verifies Ziti can orient and animate its cylinder along all cardinal directions
def testZitiSupportsCardinalDirections() -> None:
    frame = _frame()
    outputs = {}
    for direction in ("right", "left", "down", "up"):
        effect = _entry("ziti")
        effect["operations"][0].update({"curvature": 0.55, "direction": direction})
        outputs[direction] = EffectChain.init([effect], 32, 24, 12, 7).apply(frame, 1.0, 17)
    assert all(not np.array_equal(frame, output) for output in outputs.values())
    assert not np.array_equal(outputs["right"], outputs["left"])
    assert not np.array_equal(outputs["down"], outputs["up"])
    assert not np.array_equal(outputs["right"], outputs["down"])


# :: VOID -> NONE
# Verifies Ziti's default right direction preserves its prior horizontal projection
def testZitiRightPreservesCompatibleProjection() -> None:
    frame = _frame()
    effect = _entry("ziti")
    effect["operations"][0].update({"curvature": 0.3, "direction": "right"})
    actual = EffectChain.init([effect], 32, 24, 12, 7).apply(frame, 1.0, 17)
    centerX = 16.0
    yValues, xValues = np.mgrid[:24, :32]
    angle = (xValues - centerX) / centerX * (math.pi * 0.3) + 17 * 0.01
    sourceX = centerX + centerX * np.sin(angle) / max(0.1, math.pi * 0.3)
    sourceX = np.clip(sourceX, 0, 31).astype(np.int64)
    assert np.array_equal(actual, frame[yValues, sourceX])


# :: VOID -> NONE
# Verifies Glitch Maker ports scale their displacement from bounded audio activity
def testChromaticAndScanlineCorruptReactToAudio() -> None:
    frame = _frame()
    lowSignals = {"bass": 0.0, "mid": 0.0, "high": 0.0, "onset": 0.0}
    highSignals = {"bass": 1.0, "mid": 1.0, "high": 1.0, "onset": 1.0}
    for effectId in ("chromatic", "pixel_sort", "scanline_corrupt"):
        effect = _entry(effectId)
        if effectId == "pixel_sort":
            effect["operations"][0]["reverse"] = True
        chain = EffectChain.init([effect], 32, 24, 12, 7)
        low = chain.apply(frame, 0.25, 3, lowSignals)
        high = chain.apply(frame, 0.25, 3, highSignals)
        assert not np.array_equal(low, high), effectId


# :: VOID -> NONE
# Verifies Glitzle slitscan samples progressively older frames across its direction
def testSlitscanUsesBoundedFrameHistory() -> None:
    effect = _entry("slitscan")
    effect["operations"][0].update({"direction": "horizontal", "max_delay_frames": 3, "audio_scale": 0.0})
    chain = EffectChain.init([effect], 32, 24, 12, 7)
    output = _frame()
    for frameIndex in range(4):
        frame = np.full((24, 32, 3), frameIndex * 40, dtype=np.uint8)
        output = chain.apply(frame, frameIndex / 12.0, frameIndex)
    assert np.all(output[0] == 120)
    assert np.all(output[-1] == 0)
    assert np.any(output[1:-1] != output[0])


# :: VOID -> NONE
# Verifies every registered first-slice effect produces valid deterministic BGR bytes
def testEveryCatalogEffectExecutes() -> None:
    frame = _frame()
    for effectId in effectIds():
        effect = _entry(effectId)
        first = EffectChain.init([effect], 32, 24, 12, 5).apply(frame, 0.25, 3)
        second = EffectChain.init([effect], 32, 24, 12, 5).apply(frame, 0.25, 3)
        assert first.shape == frame.shape, effectId
        assert first.dtype == np.uint8, effectId
        assert np.array_equal(first, second), effectId
