# Adapter for the immutable audio-reactive reference renderer

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import importlib.util  # Load immutable reference modules without editing their source
import math  # Evaluate smooth audio binding curves
import sys  # Register legacy bare-module imports required by the reference files
from pathlib import Path  # Locate reference modules relative to the repository
from types import ModuleType  # Annotate dynamically loaded reference modules
from typing import Any, Dict, Optional, Tuple  # Python 3.8-compatible type annotations

import numpy as np  # Build renderer parameters and blank HUD buffers

from metalheart.audio_form_core import AudioFormCore  # Install production-owned audio-composed geometry
from metalheart.camera_choreo import CameraChoreo  # Strengthen camera timing without modifying reference code
from metalheart.frame_effects import FrameEffects  # Apply authored audio-driven frame transforms
from metalheart.finishing import FinishingPass  # Replace immutable finishing with authored controls
from metalheart.surface_skin import SurfaceSkin  # Project authored images across 3D core surfaces
from metalheart.text_overlay import TextOverlay  # Draw configurable author text after modulation


REFERENCE_DIR = Path(__file__).resolve().parents[1] / "ref" / "audioReactive"
REFERENCE_VERSION = "audioReactive-2026-09-23"
_REFERENCE_MODULES: Optional[Tuple[ModuleType, ModuleType, ModuleType]] = None


# :: STRING, PATH -> moduleType
# Loads one reference module from an explicit path
def _loadModule(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load reference module: {0}".format(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# :: VOID -> (moduleType, moduleType, moduleType)
# Loads audio, liquid3d, and Metalheart reference modules once
def _loadReferenceModules() -> Tuple[ModuleType, ModuleType, ModuleType]:
    global _REFERENCE_MODULES
    if _REFERENCE_MODULES is None:
        audioModule = _loadModule("audio", REFERENCE_DIR / "audio.py")
        liquidModule = _loadModule("liquid3d", REFERENCE_DIR / "liquid3d.py")
        rendererModule = _loadModule("_metalheart_reference", REFERENCE_DIR / "metalheart.py")
        _REFERENCE_MODULES = (audioModule, liquidModule, rendererModule)
    return _REFERENCE_MODULES


# Wraps one configured reference-renderer instance
class ReferenceRendererSession:

    # CONSTRUCTOR :: moduleType, moduleType, ARRAY<STRING, ANY>, ARRAY<STRING, ANY> -> referenceRendererSession
    # Creates a renderer for one resolved scene
    def __init__(self, liquidModule: ModuleType, rendererModule: ModuleType, settings: Dict[str, Any], scene: Dict[str, Any]) -> None:
        self._liquidModule = liquidModule
        self._rendererModule = rendererModule
        self._settings = settings
        self._scene = scene
        self._frameEffects = FrameEffects.init()
        self._cameraChoreo: Optional[CameraChoreo] = None
        self._audioFormCore: Optional[AudioFormCore] = None
        self._surfaceSkin: Optional[SurfaceSkin] = None
        overlayConfig = scene["overlay"]
        self._overlay = TextOverlay.init(overlayConfig, rendererModule.FONT_PATH)
        rendererConfig = scene["renderer"]
        self._renderer = rendererModule.MetalheartRenderer(
            width=settings["width"],
            height=settings["height"],
            seed=scene.get("seed", settings["seed"]),
            preset=rendererConfig["palette"],
            scanlines=False,
            core=rendererConfig["core"],
            looks=rendererConfig["forms"],
            cams=rendererConfig["cameras"],
            look_len=rendererConfig["form_len_sec"],
            cam_len=rendererConfig["camera_len_sec"],
            core_scale=rendererConfig["core_scale"],
            decor=rendererConfig["decor"],
            aa=rendererConfig["anti_alias"],
        )
        if rendererConfig["core"] == "3d":
            self._cameraChoreo = CameraChoreo.init(
                liquidModule=liquidModule,
                forms=rendererConfig["forms"],
                cameras=rendererConfig["cameras"],
                formLenSec=rendererConfig["form_len_sec"],
                cameraLenSec=rendererConfig["camera_len_sec"],
                crossfadeSec=rendererConfig["crossfade_sec"],
                cameraSpeed=rendererConfig["camera_speed"],
                cameraPhaseSec=rendererConfig["camera_phase_sec"],
                cameraIntensity=rendererConfig["camera_intensity"],
            )
            self._renderer.choreo = self._cameraChoreo
            if any(form in ("resonance", "radial") for form in rendererConfig["forms"]):
                self._audioFormCore = AudioFormCore.init(liquidModule, scene.get("seed", settings["seed"]))
                self._renderer.core3d.core = self._audioFormCore
            if rendererConfig["surface"]["image"]:
                self._surfaceSkin = SurfaceSkin.init(self._renderer.core3d, rendererConfig["surface"])
                self._renderer.core3d._shade = self._surfaceSkin.shade
        self._finishing = FinishingPass.init(self._renderer, scene["finish"])
        self._renderer.post = self._finishing.apply
        self._renderer.hud_tag = "//AUDIO.REACTIVE"
        if not overlayConfig["enabled"] or not overlayConfig["reference_hud"]:
            self._renderer.hud = self._blankHud

    #
    # Instance Methods
    #

    # :: FLOAT, ANY, ARRAY<STRING, FLOAT> -> ANY
    # Renders, visibly modulates, and overlays one BGR frame
    def render(self, timeSec: float, params: Any, modulators: Dict[str, float]) -> Any:
        if self._cameraChoreo is not None:
            self._cameraChoreo.setSignals(modulators)
        if self._audioFormCore is not None:
            self._audioFormCore.setSignals(modulators)
        frame = self._renderer.render(timeSec, params)
        frame = self._frameEffects.apply(frame, timeSec, modulators)
        return self._overlay.apply(frame)

    #
    # Protected Methods
    #

    # :: FLOAT, ANY, ANY -> (ANY, ANY)
    # Returns transparent HUD buffers when HUD rendering is disabled
    def _blankHud(self, timeSec: float, params: Any, focus: Any) -> Tuple[Any, Any]:
        del timeSec, params, focus
        height = self._settings["height"]
        width = self._settings["width"]
        return (
            np.zeros((height, width, 3), np.float32),
            np.zeros((height, width, 1), np.float32),
        )

    #
    # Class Methods
    #

    # Class Factory Method :: moduleType, moduleType, ARRAY<STRING, ANY>, ARRAY<STRING, ANY> -> referenceRendererSession
    # Creates a configured reference renderer session
    @classmethod
    def init(cls, liquidModule: ModuleType, rendererModule: ModuleType, settings: Dict[str, Any], scene: Dict[str, Any]) -> ReferenceRendererSession:
        return cls(liquidModule, rendererModule, settings, scene)


# Provides analysis, Params mapping, and renderer construction through a stable boundary
class ReferenceBackend:

    # CONSTRUCTOR :: VOID -> referenceBackend
    # Loads the immutable reference modules
    def __init__(self) -> None:
        audioModule, liquidModule, rendererModule = _loadReferenceModules()
        self._audioModule = audioModule
        self._liquidModule = liquidModule
        self._rendererModule = rendererModule

    #
    # Properties
    #

    # PROPERTY :: VOID -> STRING
    # Returns the pinned reference backend revision label
    @property
    def version(self) -> str:
        return REFERENCE_VERSION

    #
    # Instance Methods
    #

    # :: STRING, FLOAT, FLOAT, FLOAT?, FLOAT? -> ANY
    # Analyzes an audio range at output-frame cadence
    def analyzeAudio(self, path: str, fps: float, startSec: float, durationSec: Optional[float], bpmHint: Optional[float] = None) -> Any:
        return self._audioModule.analyze(path, fps=fps, start=startSec, duration=durationSec, bpm_hint=bpmHint)

    # :: ANY, STRING -> NONE
    # Saves a reference Analysis into a compressed NumPy cache
    def saveAnalysis(self, analysis: Any, path: str) -> None:
        analysis.save(path)

    # :: STRING -> ANY
    # Loads a cached reference Analysis
    def loadAnalysis(self, path: str) -> Any:
        return self._audioModule.Analysis.load(path)

    # :: ARRAY<STRING, ANY>, ARRAY<STRING, ANY> -> referenceRendererSession
    # Creates a per-scene renderer session
    def createRenderer(self, settings: Dict[str, Any], scene: Dict[str, Any]) -> ReferenceRendererSession:
        return ReferenceRendererSession.init(self._liquidModule, self._rendererModule, settings, scene)

    # :: ANY, INT, FLOAT, ARRAY<STRING, ANY> -> ANY
    # Maps analyzed features through resolved bindings into reference Params
    def createParams(self, analysis: Any, frameIndex: int, relativeTimeSec: float, reactivity: Dict[str, Any]) -> Any:
        index, values = self._sourceValues(analysis, frameIndex, relativeTimeSec)
        mapped = {"bass": 0.0, "mid": 0.0, "high": 0.0, "onset": 0.0}
        for destination, binding in reactivity.get("bindings", {}).items():
            sourceValue = values.get(binding.get("source"), 0.0)
            mapped[destination] = self._mapValue(sourceValue, binding)
        return self._rendererModule.Params(
            bass=mapped["bass"],
            mid=mapped["mid"],
            high=mapped["high"],
            onset=mapped["onset"],
            spectrum=analysis.spectrum[index],
        )

    # :: ANY, INT, FLOAT, ARRAY<STRING, ANY> -> ARRAY<STRING, FLOAT>
    # Maps analyzed features onto visible frame-space effects
    def createModulators(self, analysis: Any, frameIndex: int, relativeTimeSec: float, reactivity: Dict[str, Any]) -> Dict[str, float]:
        index, values = self._sourceValues(analysis, frameIndex, relativeTimeSec)
        del index
        return {
            destination: self._mapValue(values.get(binding.get("source"), 0.0), binding)
            for destination, binding in reactivity.get("modulators", {}).items()
        }

    #
    # Protected Methods
    #

    # :: ANY, INT, FLOAT -> (INT, ARRAY<STRING, FLOAT>)
    # Samples all public analysis sources once for a render frame
    def _sourceValues(self, analysis: Any, frameIndex: int, relativeTimeSec: float) -> Tuple[int, Dict[str, float]]:
        index = min(max(frameIndex, 0), max(0, analysis.n_frames - 1))
        values: Dict[str, float] = {
            "bass": float(analysis.bass[index]),
            "mid": float(analysis.mid[index]),
            "high": float(analysis.high[index]),
            "amplitude": min(
                max(
                    0.5 * float(analysis.bass[index])
                    + 0.3 * float(analysis.mid[index])
                    + 0.2 * float(analysis.high[index]),
                    0.0,
                ),
                1.0,
            ),
            "energy": float(analysis.energy[index]),
            "spectral_centroid": self._spectralCentroid(analysis.spectrum[index]),
            "onset": float(analysis.onset[index]),
            "beat": self._eventValue(analysis.beat_times, relativeTimeSec, analysis.fps),
            "downbeat": self._eventValue(analysis.downbeat_times, relativeTimeSec, analysis.fps),
            "tension": float(analysis.energy[index]),
        }
        return index, values

    # :: ANY -> FLOAT
    # Reduces normalized spectrum energy to a stable zero-to-one brightness centroid
    def _spectralCentroid(self, spectrum: Any) -> float:
        values = np.maximum(np.asarray(spectrum, np.float32), 0.0)
        if values.size == 0:
            return 0.0
        positions = np.linspace(0.0, 1.0, values.size, dtype=np.float32)
        total = float(values.sum())
        return float(np.dot(values, positions) / total) if total > 1e-9 else 0.0

    # :: FLOAT, ARRAY<STRING, ANY> -> FLOAT
    # Applies a resolved scalar binding to one source value
    def _mapValue(self, value: float, binding: Dict[str, Any]) -> float:
        curve = binding.get("curve", "linear")
        shaped = min(max(float(value), 0.0), 1.0)
        threshold = float(binding.get("threshold", 0.0))
        shaped = max(0.0, shaped - threshold) / max(1.0 - threshold, 1e-9)
        if curve == "ease_in" or curve == "square":
            shaped = shaped * shaped
        elif curve == "ease_out":
            shaped = 1.0 - (1.0 - shaped) * (1.0 - shaped)
        elif curve == "smoothstep":
            shaped = shaped * shaped * (3.0 - 2.0 * shaped)
        amount = float(binding.get("amount", 1.0))
        bias = float(binding.get("bias", 0.0))
        clamp = binding.get("clamp", [0.0, 1.0])
        return min(max(shaped * amount + bias, float(clamp[0])), float(clamp[1]))

    # :: ANY, FLOAT, FLOAT -> FLOAT
    # Returns a one-frame impulse when an event occurs near the frame center
    def _eventValue(self, eventTimes: Any, timeSec: float, fps: float) -> float:
        if getattr(eventTimes, "size", 0) == 0:
            return 0.0
        distance = float(np.min(np.abs(eventTimes - timeSec)))
        return 1.0 if distance <= 0.5 / fps else 0.0

    #
    # Class Methods
    #

    # Class Factory Method :: VOID -> referenceBackend
    # Creates the reference backend adapter
    @classmethod
    def init(cls) -> ReferenceBackend:
        return cls()
