# Unit tests for audio binding evaluation and deterministic reference frames

from pathlib import Path  # Type temporary image-skin paths
from types import SimpleNamespace  # Build compact in-memory analysis fixtures
from typing import Any, Dict  # Python 3.8-compatible config annotations

import cv2  # Write deterministic image-skin fixtures
import numpy as np  # Create feature arrays and compare rendered frames

from metalheart.background import BackgroundPass  # Exercise image fit behavior directly
from metalheart.catalog import DEFAULT_BACKGROUND  # Build resolved background fixtures
from metalheart.catalog import DEFAULT_RENDERER  # Start renderer fixtures from production defaults
from metalheart.catalog import DEFAULT_FINISH  # Supply owned finishing defaults
from metalheart.catalog import REACTIVITY_PRESETS  # Exercise resolved audio mappings
from metalheart.frame_effects import FrameEffects  # Exercise visible post-render modulation
from metalheart.reference_backend import ReferenceBackend  # Adapt immutable renderer reference code
from metalheart.surface_skin import SurfaceSkin  # Exercise resolution-independent image sampling


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
# Verifies amplitude and spectral features map onto radial geometry destinations
def testRadialModulatorsMapAnalysisValues() -> None:
    backend = ReferenceBackend.init()
    reactivity = REACTIVITY_PRESETS["spectral-radial"]
    modulators = backend.createModulators(_analysis(), 0, 0.0, reactivity)
    assert 0.0 < modulators["form_extent"] <= 0.95
    assert 0.0 < modulators["form_rotation"] <= 6.283185
    assert modulators["form_ripple"] == 0.12


# :: VOID -> NONE
# Verifies amplitude and centroid map onto bounded jagged radial controls
def testJaggedRadialModulatorsMapAnalysisValues() -> None:
    backend = ReferenceBackend.init()
    reactivity = REACTIVITY_PRESETS["spectral-radial-jagged"]
    modulators = backend.createModulators(_analysis(), 0, 0.0, reactivity)
    assert 0.0 < modulators["form_jaggedness"] <= 0.06
    assert 0.0 < modulators["form_jagged_scale"] <= 6.0


# :: VOID -> NONE
# Verifies background pulse uses the ordinary typed binding evaluator
def testBackgroundPulseMapsAnalysisValues() -> None:
    backend = ReferenceBackend.init()
    reactivity = {
        "modulators": {
            "background_pulse": {
                "source": "bass",
                "amount": 1.0,
                "bias": 0.0,
                "curve": "linear",
                "clamp": [0.0, 1.0],
            }
        }
    }
    modulators = backend.createModulators(_analysis(), 1, 0.25, reactivity)
    assert modulators["background_pulse"] == 0.75


# :: VOID -> NONE
# Verifies the production-owned radial SDF renders a stable nonempty frame
def testRadialFrameIsDeterministic() -> None:
    backend = ReferenceBackend.init()
    settings = {"width": 64, "height": 64, "seed": 5}
    scene = _scene()
    scene["renderer"].update(
        {"core": "3d", "forms": ["radial"], "cameras": ["orbit"], "core_scale": 0.25}
    )
    scene["reactivity"] = REACTIVITY_PRESETS["spectral-radial"]
    params = backend.createParams(_analysis(), 0, 0.0, scene["reactivity"])
    modulators = backend.createModulators(_analysis(), 0, 0.0, scene["reactivity"])
    first = backend.createRenderer(settings, scene).render(0.5, params, modulators)
    second = backend.createRenderer(settings, scene).render(0.5, params, modulators)
    assert first.shape == (64, 64, 3)
    assert np.array_equal(first, second)
    assert int(first.max()) > 0


# :: VOID -> NONE
# Verifies opt-in faceting, jaggedness, and stepping visibly change Radial
def testJaggedRadialFrameIsDistinctAndDeterministic() -> None:
    backend = ReferenceBackend.init()
    settings = {"width": 64, "height": 64, "seed": 5}
    scene = _scene()
    scene["renderer"].update(
        {
            "core": "3d",
            "forms": ["radial"],
            "cameras": ["orbit"],
            "core_scale": 0.25,
            "form_style": {
                "faceting": 0.55,
                "jaggedness": 0.02,
                "jagged_scale": 4.0,
                "geometry_steps": 6,
            },
        }
    )
    scene["reactivity"] = REACTIVITY_PRESETS["spectral-radial-jagged"]
    params = backend.createParams(_analysis(), 0, 0.0, scene["reactivity"])
    baseModulators = backend.createModulators(_analysis(), 0, 0.0, scene["reactivity"])
    flatModulators = dict(baseModulators, form_jaggedness=0.0, form_jagged_scale=0.0)
    first = backend.createRenderer(settings, scene).render(0.5, params, baseModulators)
    second = backend.createRenderer(settings, scene).render(0.5, params, baseModulators)
    flat = backend.createRenderer(settings, scene).render(0.5, params, flatModulators)
    assert np.array_equal(first, second)
    assert not np.array_equal(first, flat)


# :: VOID -> NONE
# Verifies different spectrum bands pull the radial form in different directions
def testRadialFrameRespondsToSpectrumDirection() -> None:
    backend = ReferenceBackend.init()
    settings = {"width": 64, "height": 64, "seed": 5}
    scene = _scene()
    scene["renderer"].update(
        {"core": "3d", "forms": ["radial"], "cameras": ["orbit"], "core_scale": 0.25}
    )
    scene["reactivity"] = REACTIVITY_PRESETS["spectral-radial"]
    lowAnalysis = _analysis()
    highAnalysis = _analysis()
    lowAnalysis.spectrum[0] = np.linspace(1.0, 0.0, 24, dtype=np.float32)
    highAnalysis.spectrum[0] = np.linspace(0.0, 1.0, 24, dtype=np.float32)
    lowParams = backend.createParams(lowAnalysis, 0, 0.0, scene["reactivity"])
    highParams = backend.createParams(highAnalysis, 0, 0.0, scene["reactivity"])
    lowModulators = backend.createModulators(lowAnalysis, 0, 0.0, scene["reactivity"])
    highModulators = backend.createModulators(highAnalysis, 0, 0.0, scene["reactivity"])
    lowFrame = backend.createRenderer(settings, scene).render(0.5, lowParams, lowModulators)
    highFrame = backend.createRenderer(settings, scene).render(0.5, highParams, highModulators)
    assert not np.array_equal(lowFrame, highFrame)


# :: PATH -> NONE
# Verifies a triplanar image skin changes only the configured 3D render path
def testImageSurfaceSkinChangesFrame(tmp_path: Path) -> None:
    texture = np.zeros((8, 8, 3), np.uint8)
    texture[:, :4] = [0, 0, 255]
    texture[:, 4:] = [0, 255, 0]
    imagePath = tmp_path / "skin.png"
    assert cv2.imwrite(str(imagePath), texture)
    backend = ReferenceBackend.init()
    settings = {"width": 64, "height": 64, "seed": 5}
    scene = _scene()
    scene["renderer"].update(
        {"core": "3d", "forms": ["mercury"], "cameras": ["orbit"], "core_scale": 0.25}
    )
    params = backend.createParams(_analysis(), 0, 0.0, scene["reactivity"])
    modulators = backend.createModulators(_analysis(), 0, 0.0, scene["reactivity"])
    reference = backend.createRenderer(settings, scene).render(0.5, params, modulators)
    scene["renderer"]["surface"] = {
        "image": str(imagePath),
        "mapping": "triplanar",
        "scale": 1.0,
        "rotation_deg": 0.0,
        "material": "metallic",
    }
    skinned = backend.createRenderer(settings, scene).render(0.5, params, modulators)
    assert skinned.shape == reference.shape
    assert not np.array_equal(skinned, reference)


# :: PATH -> NONE
# Verifies background pulse changes only pixels outside the opaque 3D foreground
def testImageBackgroundPulseLeavesOpaqueForegroundStable(tmp_path: Path) -> None:
    texture = np.zeros((12, 8, 3), np.uint8)
    texture[:6] = [0, 0, 255]
    texture[6:] = [255, 0, 0]
    imagePath = tmp_path / "background.png"
    assert cv2.imwrite(str(imagePath), texture)
    backend = ReferenceBackend.init()
    settings = {"width": 64, "height": 64, "seed": 5}
    scene = _scene()
    scene["renderer"].update(
        {"core": "3d", "forms": ["radial"], "cameras": ["orbit"], "core_scale": 0.25}
    )
    scene["background"] = dict(
        DEFAULT_BACKGROUND,
        source="image",
        image=str(imagePath),
        dots=False,
        ghosts=False,
        shadow=False,
        pulse_brightness=0.8,
        pulse_scale=0.25,
    )
    scene["finish"].update(
        {
            "bloom": 0.0,
            "wide_bloom": 0.0,
            "streaks": 0.0,
            "onset_streaks": 0.0,
            "flash": 0.0,
            "chroma": 0.0,
            "chroma_onset": 0.0,
            "vignette": 0.0,
            "grain": 0.0,
            "grain_high": 0.0,
        }
    )
    params = backend.createParams(_analysis(), 1, 0.5, scene["reactivity"])
    session = backend.createRenderer(settings, scene)
    quiet = session.render(0.5, params, {"background_pulse": 0.0})
    loud = session.render(0.5, params, {"background_pulse": 1.0})
    assert session._background is not None
    assert session._background._foreground is not None
    alpha = session._background._foreground[1]
    opaque = alpha >= 0.999
    exposed = alpha <= 0.001
    assert np.any(opaque)
    assert np.any(exposed)
    assert np.array_equal(quiet[opaque], loud[opaque])
    assert not np.array_equal(quiet[exposed], loud[exposed])


# :: PATH -> NONE
# Verifies cover, contain, and tile produce stable frame-sized image layers
def testImageBackgroundFitModes(tmp_path: Path) -> None:
    texture = np.zeros((8, 4, 3), np.uint8)
    texture[:, :2] = [0, 0, 255]
    texture[:, 2:] = [0, 255, 0]
    imagePath = tmp_path / "background.png"
    assert cv2.imwrite(str(imagePath), texture)
    height = 8
    width = 16
    vertical, horizontalPixels = np.mgrid[0:height, 0:width].astype(np.float32)
    renderer = SimpleNamespace(
        W=width,
        H=height,
        u=(horizontalPixels - width / 2.0) / height,
        v=(vertical - height / 2.0) / height,
    )
    layers = {}
    for fit in ("cover", "contain", "tile"):
        config = dict(DEFAULT_BACKGROUND, source="image", image=str(imagePath), fit=fit)
        layers[fit] = BackgroundPass.init(renderer, config)._image(0.0)
        assert layers[fit][0].shape == (height, width, 3)
        assert layers[fit][1].shape == (height, width)
    assert np.all(layers["cover"][1] == 1.0)
    assert np.all(layers["tile"][1] == 1.0)
    assert np.any(layers["contain"][1] == 0.0)
    assert np.any(layers["contain"][1] == 1.0)


# :: PATH -> NONE
# Verifies bilinear skin sampling supports more hit points than OpenCV remap limits
def testImageSurfaceSkinSamplesLargeHitSet(tmp_path: Path) -> None:
    texture = np.zeros((4, 4, 3), np.uint8)
    texture[:, 2:] = 255
    imagePath = tmp_path / "skin.png"
    assert cv2.imwrite(str(imagePath), texture)
    renderer = SimpleNamespace(_shade=lambda *arguments: arguments)
    skin = SurfaceSkin.init(
        renderer,
        {
            "image": str(imagePath),
            "scale": 1.0,
            "rotation_deg": 0.0,
            "material": "metallic",
        },
    )
    coordinates = np.linspace(-2.0, 2.0, 40000, dtype=np.float32)
    sampled = skin._sample(coordinates, coordinates)
    assert sampled.shape == (40000, 3)
    assert np.isfinite(sampled).all()


# :: PATH -> NONE
# Verifies both materials preserve image hue instead of palette hue
def testImageSurfaceSkinReplacesPaletteColor(tmp_path: Path) -> None:
    imagePath = tmp_path / "skin.png"
    assert cv2.imwrite(str(imagePath), np.zeros((2, 2, 3), np.uint8))
    renderer = SimpleNamespace(_shade=lambda *arguments: arguments)
    chrome = np.array([[0.05, 0.1, 1.0]], np.float32)
    texture = np.array([[1.0, 0.0, 0.0]], np.float32)
    outputs = []
    for material in ["metallic", "matte"]:
        skin = SurfaceSkin.init(
            renderer,
            {
                "image": str(imagePath),
                "scale": 1.0,
                "rotation_deg": 0.0,
                "material": material,
            },
        )
        outputs.append(skin._applyMaterial(chrome, texture))
    for output in outputs:
        assert output[0, 0] > output[0, 2]
        assert output[0, 1] == 0.0
        assert output[0, 2] == 0.0


# :: PATH -> NONE
# Verifies nearest sampling and coordinate steps create stable visible texels
def testImageSurfaceSkinQuantizesTextureSampling(tmp_path: Path) -> None:
    texture = np.zeros((8, 8, 3), np.uint8)
    for column in range(8):
        texture[:, column] = [column * 20, column * 10, column * 30]
    imagePath = tmp_path / "skin.png"
    assert cv2.imwrite(str(imagePath), texture)
    renderer = SimpleNamespace(_shade=lambda *arguments: arguments)
    baseConfig = {
        "image": str(imagePath),
        "scale": 1.0,
        "rotation_deg": 0.0,
        "material": "matte",
        "texel_steps": 0,
        "lighting_steps": 0,
    }
    bilinear = SurfaceSkin.init(renderer, dict(baseConfig, sampling="bilinear"))
    nearest = SurfaceSkin.init(renderer, dict(baseConfig, sampling="nearest"))
    horizontal = np.array([0.01], np.float32)
    vertical = np.array([0.01], np.float32)
    assert not np.array_equal(
        bilinear._sample(horizontal, vertical), nearest._sample(horizontal, vertical)
    )
    stepped = SurfaceSkin.init(
        renderer, dict(baseConfig, sampling="nearest", texel_steps=2)
    )
    sampled = stepped._sample(
        np.array([0.01, 0.2], np.float32), np.array([0.01, 0.2], np.float32)
    )
    assert np.array_equal(sampled[0], sampled[1])


# :: PATH -> NONE
# Verifies lighting steps reduce smooth shading to deterministic bands
def testImageSurfaceSkinQuantizesLighting(tmp_path: Path) -> None:
    imagePath = tmp_path / "skin.png"
    assert cv2.imwrite(str(imagePath), np.zeros((2, 2, 3), np.uint8))
    renderer = SimpleNamespace(_shade=lambda *arguments: arguments)
    baseConfig = {
        "image": str(imagePath),
        "scale": 1.0,
        "rotation_deg": 0.0,
        "material": "matte",
        "sampling": "bilinear",
        "texel_steps": 0,
    }
    chrome = np.array([[0.1, 0.1, 0.1], [0.12, 0.12, 0.12]], np.float32)
    texture = np.ones((2, 3), np.float32)
    smooth = SurfaceSkin.init(renderer, dict(baseConfig, lighting_steps=0))
    stepped = SurfaceSkin.init(renderer, dict(baseConfig, lighting_steps=4))
    smoothOutput = smooth._applyMaterial(chrome, texture)
    steppedOutput = stepped._applyMaterial(chrome, texture)
    assert not np.array_equal(smoothOutput[0], smoothOutput[1])
    assert np.array_equal(steppedOutput[0], steppedOutput[1])


# :: VOID -> NONE
# Verifies a frame-space pulse visibly changes pixels without changing dimensions
def testFrameEffectsApplyVisiblePulse() -> None:
    frame = np.zeros((32, 32, 3), np.uint8)
    frame[10:22, 10:22] = 255
    output = FrameEffects.init().apply(frame, 0.25, {"pulse": 0.1})
    assert output.shape == frame.shape
    assert not np.array_equal(output, frame)
