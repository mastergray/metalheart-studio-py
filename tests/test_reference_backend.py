# Unit tests for audio binding evaluation and deterministic reference frames

from types import SimpleNamespace  # Build compact in-memory analysis fixtures
from typing import Any, Dict  # Python 3.8-compatible config annotations

import numpy as np  # Create feature arrays and compare rendered frames

from metalheart.catalog import DEFAULT_RENDERER  # Start renderer fixtures from production defaults
from metalheart.catalog import DEFAULT_FINISH  # Supply owned finishing defaults
from metalheart.catalog import REACTIVITY_PRESETS  # Exercise resolved audio mappings
from metalheart.frame_effects import FrameEffects  # Exercise visible post-render modulation
from metalheart.reference_backend import ReferenceBackend  # Adapt immutable renderer reference code


# :: VOID -> ANY
# Creates two frames of normalized audio features
def _analysis() -> Any:
    return SimpleNamespace(
        n_frames=2,
        fps=4.0,
        bass=np.array([0.25, 0.75], np.float32),
        mid=np.array([0.4, 0.5], np.float32),
        high=np.array([0.6, 0.2], np.float32),
        onset=np.array([1.0, 0.0], np.float32),
        energy=np.array([0.5, 0.6], np.float32),
        spectrum=np.full((2, 24), 0.25, np.float32),
        beat_times=np.array([0.0], np.float32),
        downbeat_times=np.array([0.0], np.float32),
    )


# :: VOID -> ARRAY<STRING, ANY>
# Creates a fast fixed-seed 2D renderer scene
def _scene() -> Dict[str, Any]:
    renderer = dict(DEFAULT_RENDERER)
    renderer.update({"core": "2d", "decor": False, "anti_alias": False})
    return {
        "id": "test",
        "renderer": renderer,
        "reactivity": REACTIVITY_PRESETS["balanced"],
        "overlay": {"enabled": False, "reference_hud": False, "items": []},
        "finish": dict(DEFAULT_FINISH),
    }


# :: VOID -> NONE
# Verifies a fixed seed, time, and Params produce the same BGR frame
def testFixedSeedFrameIsDeterministic() -> None:
    backend = ReferenceBackend.init()
    settings = {"width": 64, "height": 64, "seed": 5}
    scene = _scene()
    params = backend.createParams(_analysis(), 0, 0.0, scene["reactivity"])
    modulators = backend.createModulators(_analysis(), 0, 0.0, scene["reactivity"])
    first = backend.createRenderer(settings, scene).render(0.0, params, modulators)
    second = backend.createRenderer(settings, scene).render(0.0, params, modulators)
    assert first.shape == (64, 64, 3)
    assert first.dtype == np.uint8
    assert np.array_equal(first, second)


# :: VOID -> NONE
# Verifies balanced bindings preserve normalized feature values
def testBalancedBindingsMapAnalysisValues() -> None:
    backend = ReferenceBackend.init()
    params = backend.createParams(_analysis(), 1, 0.25, {"bindings": REACTIVITY_PRESETS["balanced"]["bindings"]})
    assert abs(params.bass - 0.75) < 1e-6
    assert abs(params.mid - 0.5) < 1e-6
    assert abs(params.high - 0.2) < 1e-6
    assert params.onset == 0.0


# :: VOID -> NONE
# Verifies thresholded frame modulators create bounded visible controls
def testBalancedModulatorsMapAnalysisValues() -> None:
    backend = ReferenceBackend.init()
    modulators = backend.createModulators(_analysis(), 0, 0.0, REACTIVITY_PRESETS["balanced"])
    assert 0.0 < modulators["pulse"] <= 0.08
    assert modulators["shake"] == 0.012
    assert modulators["flash"] == 0.16
    assert 0.0 < modulators["chroma"] <= 0.004


# :: VOID -> NONE
# Verifies a frame-space pulse visibly changes pixels without changing dimensions
def testFrameEffectsApplyVisiblePulse() -> None:
    frame = np.zeros((32, 32, 3), np.uint8)
    frame[10:22, 10:22] = 255
    output = FrameEffects.init().apply(frame, 0.25, {"pulse": 0.1})
    assert output.shape == frame.shape
    assert not np.array_equal(output, frame)
