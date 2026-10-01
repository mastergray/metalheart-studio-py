# Adapter for the immutable audio-reactive reference renderer

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import importlib.util  # Load immutable reference modules without editing their source
import sys  # Register legacy bare-module imports required by the reference files
from pathlib import Path  # Locate reference modules relative to the repository
from types import ModuleType  # Annotate dynamically loaded reference modules
from typing import Any, Dict, List, Optional, Tuple  # Python 3.8-compatible type annotations

import numpy as np  # Build renderer parameters and blank HUD buffers

from metalheart.audio_form_core import AudioFormCore  # Install production-owned audio-composed geometry
from metalheart.background import BackgroundPass  # Compose configurable audio-reactive backgrounds
from metalheart.camera_choreo import CameraChoreo  # Strengthen camera timing without modifying reference code
from metalheart.catalog import DEFAULT_BACKGROUND  # Preserve defaults for direct backend callers
from metalheart.decor import DecorController  # Configure and skin 3D ribbons and plates independently
from metalheart.decor import resolveDecorConfig  # Expand legacy direct-backend decor booleans
from metalheart.effects import EffectChain  # Apply ordered Glitzle-derived post-filter effects
from metalheart.frame_effects import FrameEffects  # Apply authored audio-driven frame transforms
from metalheart.layer_effects import LayerEffects  # Isolate form and ribbon post-filter layers
from metalheart.finishing import FinishingPass  # Replace immutable finishing with authored controls
from metalheart.palette_catalog import additionalPalettes  # Install owned palettes beyond the immutable reference
from metalheart.surface_skin import SurfaceSkin  # Project authored images across 3D core surfaces
from metalheart.text_overlay import TextOverlay  # Draw configurable author text after modulation


REFERENCE_DIR = Path(__file__).resolve().parents[1] / "ref" / "audioReactive"
REFERENCE_VERSION = "audioReactive-2026-10-01-jungle-palette-v14"
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
        rendererModule.PRESETS.update(additionalPalettes())
        _REFERENCE_MODULES = (audioModule, liquidModule, rendererModule)
    return _REFERENCE_MODULES


# Wraps one configured reference-renderer instance
class ReferenceRendererSession:

    # CONSTRUCTOR :: moduleType, moduleType, ARRAY<STRING, ANY>, ARRAY<STRING, ANY>, [ARRAY<STRING, ANY>]? -> referenceRendererSession
    # Creates a renderer for one resolved scene
    def __init__(self, liquidModule: ModuleType, rendererModule: ModuleType, settings: Dict[str, Any], scene: Dict[str, Any], globalPost: Optional[List[Dict[str, Any]]] = None) -> None:
        self._liquidModule = liquidModule
        self._rendererModule = rendererModule
        self._settings = settings
        self._scene = scene
        self._frameEffects = FrameEffects.init()
        sceneSeed = int(scene.get("seed", settings["seed"]))
        globalSeed = int(settings["seed"]) + 1000003
        self._sceneEffects = EffectChain.init(scene.get("post", []), int(settings["width"]), int(settings["height"]), int(settings.get("fps", 30)), sceneSeed)
        self._globalEffects = EffectChain.init(globalPost or [], int(settings["width"]), int(settings["height"]), int(settings.get("fps", 30)), globalSeed)
        self._cameraChoreo: Optional[CameraChoreo] = None
        self._audioFormCore: Optional[AudioFormCore] = None
        self._surfaceSkin: Optional[SurfaceSkin] = None
        self._decorController: Optional[DecorController] = None
        self._layerEffects: Optional[LayerEffects] = None
        self._background: Optional[BackgroundPass] = None
        self._previousEffectOnset: float = 0.0
        overlayConfig = scene["overlay"]
        self._overlay = TextOverlay.init(overlayConfig, rendererModule.FONT_PATH)
        rendererConfig = scene["renderer"]
        decorConfig = resolveDecorConfig(rendererConfig.get("decor", True))
        ribbonPaletteId = decorConfig["ribbons"].get("palette") or rendererConfig["palette"]
        ribbonPalette = rendererModule.PRESETS[ribbonPaletteId]
        decorEnabled = bool(
            decorConfig["enabled"]
            and (
                (decorConfig["ribbons"]["enabled"] and decorConfig["ribbons"]["count"])
                or (decorConfig["plates"]["enabled"] and decorConfig["plates"]["count"])
            )
        )
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
            decor=decorEnabled,
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
                self._audioFormCore = AudioFormCore.init(
                    liquidModule,
                    scene.get("seed", settings["seed"]),
                    rendererConfig["form_style"],
                )
                self._renderer.core3d.core = self._audioFormCore
            if rendererConfig["surface"]["image"]:
                self._surfaceSkin = SurfaceSkin.init(self._renderer.core3d, rendererConfig["surface"])
                self._renderer.core3d._shade = self._surfaceSkin.shade
            if decorEnabled:
                self._decorController = DecorController.init(
                    liquidModule,
                    self._renderer.core3d,
                    decorConfig,
                    scene.get("seed", settings["seed"]),
                    ribbonPalette,
                )
            surfacePost = rendererConfig.get("surface", {}).get("post", [])
            ribbonPost = decorConfig.get("ribbons", {}).get("post", [])
            formEffects = EffectChain.init(
                surfacePost,
                int(settings["width"]),
                int(settings["height"]),
                int(settings.get("fps", 30)),
                sceneSeed + 2000003,
            ) if surfacePost else None
            ribbonEffects = EffectChain.init(
                ribbonPost,
                int(settings["width"]),
                int(settings["height"]),
                int(settings.get("fps", 30)),
                sceneSeed + 3000017,
            ) if ribbonPost else None
            if formEffects is not None or ribbonEffects is not None:
                self._layerEffects = LayerEffects.init(
                    self._renderer.core3d,
                    formEffects,
                    ribbonEffects,
                )
        backgroundConfig = scene.get("background", DEFAULT_BACKGROUND)
        backgroundPaletteId = backgroundConfig.get("palette") or rendererConfig["palette"]
        backgroundPalette = rendererModule.PRESETS[backgroundPaletteId]
        backgroundPost = backgroundConfig.get("post", [])
        backgroundEffects = EffectChain.init(
            backgroundPost,
            int(settings["width"]),
            int(settings["height"]),
            int(settings.get("fps", 30)),
            sceneSeed + 4000037,
        ) if backgroundPost else None
        self._background = BackgroundPass.init(
            self._renderer,
            backgroundConfig,
            backgroundEffects,
            self._layerEffects,
            backgroundPalette,
        )
        self._finishing = FinishingPass.init(self._renderer, scene["finish"])
        self._renderer.post = self._finishFrame
        self._renderer.hud_tag = "//AUDIO.REACTIVE"
        if not overlayConfig["enabled"] or not overlayConfig["reference_hud"]:
            self._renderer.hud = self._blankHud

    #
    # Instance Methods
    #

    # :: FLOAT, ANY, ARRAY<STRING, FLOAT>, INT?, INT?, ARRAY<STRING, ANY>? -> ANY
    # Renders, visibly modulates, and overlays one BGR frame
    def render(
        self,
        timeSec: float,
        params: Any,
        modulators: Dict[str, float],
        frameIndex: Optional[int] = None,
        sceneFrameIndex: Optional[int] = None,
        rawEffectSignals: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if self._cameraChoreo is not None:
            self._cameraChoreo.setSignals(modulators)
        if self._audioFormCore is not None:
            self._audioFormCore.setSignals(modulators)
        if self._decorController is not None:
            self._decorController.setSignals(modulators)
        if self._background is not None:
            self._background.setSignals(modulators)
        localFrame = frameIndex if sceneFrameIndex is None else sceneFrameIndex
        effectOnset = float(params.onset)
        effectSignals: Dict[str, Any] = rawEffectSignals or {
            "bass": float(params.bass),
            "mid": float(params.mid),
            "high": float(params.high),
            "treble": float(params.high),
            "rms": min(max(float(params.bass) * 0.5 + float(params.mid) * 0.3 + float(params.high) * 0.2, 0.0), 1.0),
            "onset": effectOnset,
            "transient": effectOnset >= 0.65 and self._previousEffectOnset < 0.65,
        }
        self._previousEffectOnset = effectOnset
        sceneEffectSignals = dict(effectSignals)
        globalEffectSignals = dict(effectSignals)
        if "chromatic_phase_scene" in effectSignals:
            sceneEffectSignals["chromatic_phase"] = effectSignals["chromatic_phase_scene"]
        if "chromatic_sign_scene" in effectSignals:
            sceneEffectSignals["chromatic_sign"] = effectSignals["chromatic_sign_scene"]
        if "chromatic_phase_global" in effectSignals:
            globalEffectSignals["chromatic_phase"] = effectSignals["chromatic_phase_global"]
        if "chromatic_sign_global" in effectSignals:
            globalEffectSignals["chromatic_sign"] = effectSignals["chromatic_sign_global"]
        if self._background is not None:
            self._background.setEffectContext(localFrame, sceneEffectSignals)
        frame = self._renderer.render(timeSec, params)
        frame = self._frameEffects.apply(frame, timeSec, modulators)
        frame = self._sceneEffects.apply(frame, timeSec, localFrame, sceneEffectSignals)
        frame = self._globalEffects.apply(frame, timeSec, frameIndex, globalEffectSignals)
        return self._overlay.apply(frame)

    #
    # Protected Methods
    #

    # :: ANY, FLOAT, ANY -> ANY
    # Rebuilds the authored background before applying whole-frame finishing
    def _finishFrame(self, image: Any, timeSec: float, params: Any) -> Any:
        if self._background is not None:
            image = self._background.apply(image, timeSec, params)
        return self._finishing.apply(image, timeSec, params)

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

    # Class Factory Method :: moduleType, moduleType, ARRAY<STRING, ANY>, ARRAY<STRING, ANY>, [ARRAY<STRING, ANY>]? -> referenceRendererSession
    # Creates a configured reference renderer session
    @classmethod
    def init(cls, liquidModule: ModuleType, rendererModule: ModuleType, settings: Dict[str, Any], scene: Dict[str, Any], globalPost: Optional[List[Dict[str, Any]]] = None) -> ReferenceRendererSession:
        return cls(liquidModule, rendererModule, settings, scene, globalPost)


# Provides analysis, Params mapping, and renderer construction through a stable boundary
class ReferenceBackend:

    # CONSTRUCTOR :: VOID -> referenceBackend
    # Loads the immutable reference modules
    def __init__(self) -> None:
        audioModule, liquidModule, rendererModule = _loadReferenceModules()
        self._audioModule = audioModule
        self._liquidModule = liquidModule
        self._rendererModule = rendererModule
        self._effectAnalysis: Optional[Any] = None
        self._effectBassPrefix: Optional[np.ndarray] = None
        self._effectTransientPrefix: Optional[np.ndarray] = None

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

    # :: ARRAY<STRING, ANY>, ARRAY<STRING, ANY>, [ARRAY<STRING, ANY>]? -> referenceRendererSession
    # Creates a per-scene renderer session
    def createRenderer(self, settings: Dict[str, Any], scene: Dict[str, Any], globalPost: Optional[List[Dict[str, Any]]] = None) -> ReferenceRendererSession:
        return ReferenceRendererSession.init(self._liquidModule, self._rendererModule, settings, scene, globalPost)

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

    # :: ANY, INT, INT -> ARRAY<STRING, ANY>
    # Builds raw Glitch Maker-style signals with deterministic scene and global phase history
    def createEffectSignals(self, analysis: Any, frameIndex: int, sceneFirstFrame: int) -> Dict[str, Any]:
        self._prepareEffectPrefixes(analysis)
        index = min(max(frameIndex, 0), max(0, analysis.n_frames - 1))
        sceneStart = min(max(sceneFirstFrame, 0), index)
        bassPrefix = self._effectBassPrefix
        transientPrefix = self._effectTransientPrefix
        if bassPrefix is None or transientPrefix is None:
            raise RuntimeError("effect signal prefixes were not initialized")
        globalBass = float(bassPrefix[index + 1])
        sceneBass = globalBass - float(bassPrefix[sceneStart])
        globalTransientCount = int(transientPrefix[index + 1])
        sceneTransientCount = globalTransientCount - int(transientPrefix[sceneStart])
        bass = min(max(float(analysis.bass[index]), 0.0), 1.0)
        mid = min(max(float(analysis.mid[index]), 0.0), 1.0)
        high = min(max(float(analysis.high[index]), 0.0), 1.0)
        onset = min(max(float(analysis.onset[index]), 0.0), 1.0)
        transient = int(transientPrefix[index + 1]) > int(transientPrefix[index])
        return {
            "bass": bass,
            "mid": mid,
            "high": high,
            "treble": high,
            "rms": bass * 0.5 + mid * 0.3 + high * 0.2,
            "onset": onset,
            "transient": transient,
            "chromatic_phase_global": (index + 1) * 0.12 + globalBass * 0.35,
            "chromatic_phase_scene": (index - sceneStart + 1) * 0.12 + sceneBass * 0.35,
            "chromatic_sign_global": -1.0 if globalTransientCount % 2 else 1.0,
            "chromatic_sign_scene": -1.0 if sceneTransientCount % 2 else 1.0,
        }

    #
    # Protected Methods
    #

    # :: ANY -> NONE
    # Caches cumulative bass and transient events for constant-time effect phase lookup
    def _prepareEffectPrefixes(self, analysis: Any) -> None:
        if self._effectAnalysis is analysis:
            return
        bass = np.asarray(analysis.bass, dtype=np.float64)
        onset = np.asarray(analysis.onset, dtype=np.float32)
        active = onset >= 0.65
        previous = np.concatenate((np.asarray([False]), active[:-1])) if active.size else active
        transients = np.logical_and(active, np.logical_not(previous)).astype(np.int64)
        self._effectAnalysis = analysis
        self._effectBassPrefix = np.concatenate((np.asarray([0.0]), np.cumsum(bass, dtype=np.float64)))
        self._effectTransientPrefix = np.concatenate((np.asarray([0], dtype=np.int64), np.cumsum(transients, dtype=np.int64)))

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
