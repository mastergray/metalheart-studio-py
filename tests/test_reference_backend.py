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
# Verifies owned camera timing controls visibly alter a real reference 3D frame
def testCameraControlsAlter3dFrame() -> None:
    backend = ReferenceBackend.init()
    settings = {"width": 64, "height": 64, "seed": 5}
    scene = _scene()
    scene["renderer"].update(
        {"core": "3d", "forms": ["mercury"], "cameras": ["dolly"], "core_scale": 0.25}
    )
    params = backend.createParams(_analysis(), 0, 0.0, scene["reactivity"])
    modulators = backend.createModulators(_analysis(), 0, 0.0, scene["reactivity"])
    reference = backend.createRenderer(settings, scene).render(1.0, params, modulators)
    scene["renderer"].update(
        {"camera_speed": 3.0, "camera_phase_sec": 2.0, "camera_intensity": 1.8}
    )
    strengthened = backend.createRenderer(settings, scene).render(1.0, params, modulators)
    assert strengthened.shape == reference.shape
    assert not np.array_equal(strengthened, reference)


# :: VOID -> NONE
# Verifies the production-owned resonance SDF renders deterministic abstract frames
def testResonanceFrameIsDeterministic() -> None:
    backend = ReferenceBackend.init()
    settings = {"width": 64, "height": 64, "seed": 5}
    scene = _scene()
    scene["renderer"].update(
        {"core": "3d", "forms": ["resonance"], "cameras": ["orbit"], "core_scale": 0.25}
    )
    scene["reactivity"] = REACTIVITY_PRESETS["spectral-resonance"]
    params = backend.createParams(_analysis(), 0, 0.0, scene["reactivity"])
    modulators = backend.createModulators(_analysis(), 0, 0.0, scene["reactivity"])
    first = backend.createRenderer(settings, scene).render(0.5, params, modulators)
    second = backend.createRenderer(settings, scene).render(0.5, params, modulators)
    assert first.shape == (64, 64, 3)
    assert np.array_equal(first, second)
    assert int(first.max()) > 0


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
# Verifies camera destinations use the same typed audio binding evaluator
def testCameraModulatorsMapAnalysisValues() -> None:
    backend = ReferenceBackend.init()
    reactivity = REACTIVITY_PRESETS["camera-driven"]
    modulators = backend.createModulators(_analysis(), 0, 0.0, reactivity)
    assert 0.0 < modulators["camera_distance"] <= 0.28
    assert -0.08 <= modulators["camera_elevation"] <= 0.16
    assert -0.04 <= modulators["camera_roll"] <= 0.14
    assert modulators["camera_kick"] == 0.3


# :: VOID -> NONE
# Verifies spectral centroid and energy map onto resonance destinations
def testResonanceModulatorsMapAnalysisValues() -> None:
    backend = ReferenceBackend.init()
    reactivity = REACTIVITY_PRESETS["spectral-resonance"]
    modulators = backend.createModulators(_analysis(), 0, 0.0, reactivity)
    amplitude = 0.5 * 0.25 + 0.3 * 0.4 + 0.2 * 0.6
    expectedScale = amplitude * amplitude * (3.0 - 2.0 * amplitude) * 0.32
    assert abs(modulators["form_scale"] - expectedScale) < 1e-6
    assert abs(modulators["form_deformation"] - 0.5) < 1e-6
    assert modulators["form_ripple"] == 0.14


# :: VOID -> NONE
# Verifies amplitude and spectral features map onto stretch geometry destinations
def testStretchModulatorsMapAnalysisValues() -> None:
    backend = ReferenceBackend.init()
    reactivity = REACTIVITY_PRESETS["spectral-stretch"]
    modulators = backend.createModulators(_analysis(), 0, 0.0, reactivity)
    assert 0.0 < modulators["form_length"] <= 2.2
    assert 0.0 < modulators["form_curvature"] <= 1.25
    assert 0.0 < modulators["form_direction"] <= 6.283185
    assert 0.0 < modulators["form_twist"] <= 1.4
    assert modulators["form_snap"] == 0.35


# :: VOID -> NONE
# Verifies the production-owned stretch SDF renders a stable nonempty frame
def testStretchFrameIsDeterministic() -> None:
    backend = ReferenceBackend.init()
    settings = {"width": 64, "height": 64, "seed": 5}
    scene = _scene()
    scene["renderer"].update(
        {"core": "3d", "forms": ["stretch"], "cameras": ["orbit"], "core_scale": 0.25}
    )
    scene["reactivity"] = REACTIVITY_PRESETS["spectral-stretch"]
    params = backend.createParams(_analysis(), 0, 0.0, scene["reactivity"])
    modulators = backend.createModulators(_analysis(), 0, 0.0, scene["reactivity"])
    first = backend.createRenderer(settings, scene).render(0.5, params, modulators)
    second = backend.createRenderer(settings, scene).render(0.5, params, modulators)
    assert first.shape == (64, 64, 3)
    assert np.array_equal(first, second)
    assert int(first.max()) > 0


# :: VOID -> NONE
# Verifies a frame-space pulse visibly changes pixels without changing dimensions
def testFrameEffectsApplyVisiblePulse() -> None:
    frame = np.zeros((32, 32, 3), np.uint8)
    frame[10:22, 10:22] = 255
    output = FrameEffects.init().apply(frame, 0.25, {"pulse": 0.1})
    assert output.shape == frame.shape
    assert not np.array_equal(output, frame)
