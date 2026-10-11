# Low-cost still previews backed by the production renderer and audio analysis

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import copy  # Build an isolated preview profile without mutating the project
from pathlib import Path  # Locate the project-local analysis cache
from typing import Any, Callable, Dict, List, Optional, Tuple  # Python 3.8-compatible annotations

import cv2  # Convert renderer BGR output into display-ready RGB
import numpy as np  # Type the returned preview frame

from metalheart.analysis import AudioAnalysisCache  # Reuse content-addressed audio analysis
from metalheart.config import ConfigError  # Report invalid projects before expensive work
from metalheart.config import ConfigResolver  # Resolve the canonical authored JSON document
from metalheart.reference_backend import ReferenceBackend  # Render the selected scene frame
from metalheart.render import RenderPipeline  # Discover finite effect-history requirements


PREVIEW_MAX_WIDTH = 480
PREVIEW_MAX_HEIGHT = 270
PREVIEW_MAX_FPS = 12
PREVIEW_CORE_SCALE = 0.2
PREVIEW_DEFAULT_RANGE_SEC = 4.0
PREVIEW_MAX_RANGE_SEC = 8.0


# Carries one display frame and the effective preview context
class PreviewResult:

    # CONSTRUCTOR :: ANY, INT, FLOAT, STRING, INT, INT -> previewResult
    # Stores an RGB frame and its selected scene metadata
    def __init__(
        self,
        frame: np.ndarray,
        sceneIndex: int,
        timeSec: float,
        sceneId: str,
        width: int,
        height: int,
    ) -> None:
        self._frame = frame
        self._sceneIndex = sceneIndex
        self._timeSec = timeSec
        self._sceneId = sceneId
        self._width = width
        self._height = height

    #
    # Properties
    #

    # PROPERTY :: VOID -> ANY
    # Returns the Qt-ready RGB byte frame
    @property
    def frame(self) -> np.ndarray:
        return self._frame

    # PROPERTY :: VOID -> INT
    # Returns the rendered scene index
    @property
    def sceneIndex(self) -> int:
        return self._sceneIndex

    # PROPERTY :: VOID -> FLOAT
    # Returns the rendered global project time
    @property
    def timeSec(self) -> float:
        return self._timeSec

    # PROPERTY :: VOID -> STRING
    # Returns the rendered scene identifier
    @property
    def sceneId(self) -> str:
        return self._sceneId

    # PROPERTY :: VOID -> INT
    # Returns the effective preview width
    @property
    def width(self) -> int:
        return self._width

    # PROPERTY :: VOID -> INT
    # Returns the effective preview height
    @property
    def height(self) -> int:
        return self._height

    #
    # Class Methods
    #

    # Class Factory Method :: ANY, INT, FLOAT, STRING, INT, INT -> previewResult
    # Creates a display-ready preview result
    @classmethod
    def init(
        cls,
        frame: np.ndarray,
        sceneIndex: int,
        timeSec: float,
        sceneId: str,
        width: int,
        height: int,
    ) -> PreviewResult:
        return cls(frame, sceneIndex, timeSec, sceneId, width, height)


# Carries a bounded sequence of display frames and synchronized source-audio timing
class PreviewClipResult:

    # CONSTRUCTOR :: [ANY], INT, FLOAT, FLOAT, STRING, STRING, INT, INT, INT -> previewClipResult
    # Stores RGB frames and the exact selected global range they represent
    def __init__(
        self,
        frames: List[np.ndarray],
        sceneIndex: int,
        startSec: float,
        endSec: float,
        sceneId: str,
        audioPath: str,
        width: int,
        height: int,
        fps: int,
    ) -> None:
        self._frames = frames
        self._sceneIndex = sceneIndex
        self._startSec = startSec
        self._endSec = endSec
        self._sceneId = sceneId
        self._audioPath = audioPath
        self._width = width
        self._height = height
        self._fps = fps

    #
    # Properties
    #

    # PROPERTY :: VOID -> [ANY]
    # Returns the ordered RGB preview frames
    @property
    def frames(self) -> List[np.ndarray]:
        return self._frames

    # PROPERTY :: VOID -> INT
    # Returns the rendered scene index
    @property
    def sceneIndex(self) -> int:
        return self._sceneIndex

    # PROPERTY :: VOID -> FLOAT
    # Returns the first represented global project time
    @property
    def startSec(self) -> float:
        return self._startSec

    # PROPERTY :: VOID -> FLOAT
    # Returns the exclusive selected-range end time
    @property
    def endSec(self) -> float:
        return self._endSec

    # PROPERTY :: VOID -> STRING
    # Returns the rendered scene identifier
    @property
    def sceneId(self) -> str:
        return self._sceneId

    # PROPERTY :: VOID -> STRING
    # Returns the source audio synchronized with the selected range
    @property
    def audioPath(self) -> str:
        return self._audioPath

    # PROPERTY :: VOID -> INT
    # Returns the effective preview width
    @property
    def width(self) -> int:
        return self._width

    # PROPERTY :: VOID -> INT
    # Returns the effective preview height
    @property
    def height(self) -> int:
        return self._height

    # PROPERTY :: VOID -> INT
    # Returns the effective preview playback rate
    @property
    def fps(self) -> int:
        return self._fps

    #
    # Class Methods
    #

    # Class Factory Method :: [ANY], INT, FLOAT, FLOAT, STRING, STRING, INT, INT, INT -> previewClipResult
    # Creates a bounded display-ready range result
    @classmethod
    def init(
        cls,
        frames: List[np.ndarray],
        sceneIndex: int,
        startSec: float,
        endSec: float,
        sceneId: str,
        audioPath: str,
        width: int,
        height: int,
        fps: int,
    ) -> PreviewClipResult:
        return cls(
            frames,
            sceneIndex,
            startSec,
            endSec,
            sceneId,
            audioPath,
            width,
            height,
            fps,
        )


# Resolves, analyzes, and renders one deliberately bounded still preview
class PreviewService:

    # CONSTRUCTOR :: configResolver?, referenceBackend? -> previewService
    # Creates a preview service with injectable production dependencies
    def __init__(
        self,
        resolver: Optional[ConfigResolver] = None,
        backend: Optional[ReferenceBackend] = None,
    ) -> None:
        self._resolver = resolver or ConfigResolver.init()
        self._backend = backend or ReferenceBackend.init()

    #
    # Instance Methods
    #

    # :: ARRAY<STRING, ANY>, STRING, INT, FLOAT, (() -> BOOL)? -> previewResult
    # Renders a normalized position within one scene at a bounded preview cost
    def render(
        self,
        authored: Dict[str, Any],
        configPath: str,
        sceneIndex: int,
        position: float = 0.5,
        cancelled: Optional[Callable[[], bool]] = None,
    ) -> PreviewResult:
        resolved = self._resolver.resolve(authored, configPath)
        report = self._resolver.validate(resolved)
        if not report.isValid:
            raise ConfigError("project is invalid:\n- " + "\n- ".join(report.errors))
        if sceneIndex < 0 or sceneIndex >= len(resolved["scenes"]):
            raise ConfigError("scene index is out of range: {0}".format(sceneIndex))
        preview = self._previewConfig(resolved)
        scene = preview["scenes"][sceneIndex]
        boundedPosition = min(max(float(position), 0.0), 1.0)
        startSec = float(scene["start_sec"])
        endSec = float(scene["end_sec"])
        timeSec = startSec + (endSec - startSec) * boundedPosition
        fps = int(preview["settings"]["fps"])
        frameIndex = min(
            max(int(round(timeSec * fps)), 0),
            max(int(round(endSec * fps)) - 1, 0),
        )
        sceneFirstFrame = int(round(startSec * fps))
        if cancelled is not None and cancelled():
            raise InterruptedError("preview cancelled")
        cacheRoot = Path(configPath).resolve().parent / ".metalheart-cache"
        analysisResult = AudioAnalysisCache.init(self._backend, cacheRoot).get(
            preview["audio"],
            float(fps),
            0.0,
            None,
        )
        session = self._backend.createRenderer(
            preview["settings"],
            scene,
            preview.get("post", []),
        )
        historyFrames = RenderPipeline.init(backend=self._backend)._historyFrames(preview)
        firstFrame = max(sceneFirstFrame, frameIndex - historyFrames)
        frame: Optional[np.ndarray] = None
        for sourceFrame in range(firstFrame, frameIndex + 1):
            if cancelled is not None and cancelled():
                raise InterruptedError("preview cancelled")
            relativeTimeSec = sourceFrame / float(fps)
            params = self._backend.createParams(
                analysisResult.analysis,
                sourceFrame,
                relativeTimeSec,
                scene["reactivity"],
            )
            modulators = self._backend.createModulators(
                analysisResult.analysis,
                sourceFrame,
                relativeTimeSec,
                scene["reactivity"],
            )
            effectSignals = self._backend.createEffectSignals(
                analysisResult.analysis,
                sourceFrame,
                sceneFirstFrame,
            )
            rendererTime = (
                sourceFrame / float(fps)
                if scene.get("time_mode", preview["settings"]["time_mode"]) == "global"
                else (sourceFrame - sceneFirstFrame) / float(fps)
            )
            frame = session.render(
                rendererTime,
                params,
                modulators,
                sourceFrame,
                sourceFrame - sceneFirstFrame,
                effectSignals,
            )
        if frame is None:
            raise RuntimeError("preview renderer produced no frame")
        rgbFrame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return PreviewResult.init(
            rgbFrame,
            sceneIndex,
            frameIndex / float(fps),
            str(scene["id"]),
            int(preview["settings"]["width"]),
            int(preview["settings"]["height"]),
        )

    # :: ARRAY<STRING, ANY>, STRING, INT, FLOAT, FLOAT, (() -> BOOL)?, (INT, INT -> NONE)? -> previewClipResult
    # Renders one bounded scene-local selection with temporal-effect preroll
    def renderRange(
        self,
        authored: Dict[str, Any],
        configPath: str,
        sceneIndex: int,
        startPosition: float,
        endPosition: float,
        cancelled: Optional[Callable[[], bool]] = None,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> PreviewClipResult:
        resolved = self._resolver.resolve(authored, configPath)
        report = self._resolver.validate(resolved)
        if not report.isValid:
            raise ConfigError("project is invalid:\n- " + "\n- ".join(report.errors))
        if sceneIndex < 0 or sceneIndex >= len(resolved["scenes"]):
            raise ConfigError("scene index is out of range: {0}".format(sceneIndex))
        preview = self._previewConfig(resolved)
        scene = preview["scenes"][sceneIndex]
        boundedStart = min(max(float(startPosition), 0.0), 1.0)
        boundedEnd = min(max(float(endPosition), 0.0), 1.0)
        if boundedEnd <= boundedStart:
            raise ConfigError("preview range end must be greater than its start")
        sceneStartSec = float(scene["start_sec"])
        sceneEndSec = float(scene["end_sec"])
        sceneDurationSec = sceneEndSec - sceneStartSec
        requestedDurationSec = sceneDurationSec * (boundedEnd - boundedStart)
        if requestedDurationSec > PREVIEW_MAX_RANGE_SEC + 1e-9:
            raise ConfigError(
                "preview range must be {0:.0f} seconds or shorter".format(
                    PREVIEW_MAX_RANGE_SEC
                )
            )
        fps = int(preview["settings"]["fps"])
        sceneFirstFrame = int(round(sceneStartSec * fps))
        sceneLastFrame = max(
            sceneFirstFrame + 1,
            int(round(sceneEndSec * fps)),
        )
        firstFrame = min(
            max(int(round((sceneStartSec + sceneDurationSec * boundedStart) * fps)), sceneFirstFrame),
            sceneLastFrame - 1,
        )
        lastFrame = min(
            max(int(round((sceneStartSec + sceneDurationSec * boundedEnd) * fps)), firstFrame + 1),
            sceneLastFrame,
        )
        historyFrames = RenderPipeline.init(backend=self._backend)._historyFrames(preview)
        warmupFirstFrame = max(sceneFirstFrame, firstFrame - historyFrames)
        totalFrames = lastFrame - warmupFirstFrame
        if cancelled is not None and cancelled():
            raise InterruptedError("preview cancelled")
        cacheRoot = Path(configPath).resolve().parent / ".metalheart-cache"
        analysisResult = AudioAnalysisCache.init(self._backend, cacheRoot).get(
            preview["audio"],
            float(fps),
            0.0,
            None,
        )
        session = self._backend.createRenderer(
            preview["settings"],
            scene,
            preview.get("post", []),
        )
        frames: List[np.ndarray] = []
        for completed, sourceFrame in enumerate(
            range(warmupFirstFrame, lastFrame),
            1,
        ):
            if cancelled is not None and cancelled():
                raise InterruptedError("preview cancelled")
            relativeTimeSec = sourceFrame / float(fps)
            params = self._backend.createParams(
                analysisResult.analysis,
                sourceFrame,
                relativeTimeSec,
                scene["reactivity"],
            )
            modulators = self._backend.createModulators(
                analysisResult.analysis,
                sourceFrame,
                relativeTimeSec,
                scene["reactivity"],
            )
            effectSignals = self._backend.createEffectSignals(
                analysisResult.analysis,
                sourceFrame,
                sceneFirstFrame,
            )
            rendererTime = (
                sourceFrame / float(fps)
                if scene.get("time_mode", preview["settings"]["time_mode"]) == "global"
                else (sourceFrame - sceneFirstFrame) / float(fps)
            )
            frame = session.render(
                rendererTime,
                params,
                modulators,
                sourceFrame,
                sourceFrame - sceneFirstFrame,
                effectSignals,
            )
            if sourceFrame >= firstFrame:
                frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if progress is not None:
                progress(completed, totalFrames)
        if not frames:
            raise RuntimeError("preview renderer produced no range frames")
        return PreviewClipResult.init(
            frames,
            sceneIndex,
            firstFrame / float(fps),
            lastFrame / float(fps),
            str(scene["id"]),
            str(preview["audio"]),
            int(preview["settings"]["width"]),
            int(preview["settings"]["height"]),
            fps,
        )

    #
    # Protected Methods
    #

    # :: ARRAY<STRING, ANY> -> ARRAY<STRING, ANY>
    # Applies a fixed performance ceiling while preserving project aspect ratio
    def _previewConfig(self, resolved: Dict[str, Any]) -> Dict[str, Any]:
        preview = copy.deepcopy(resolved)
        width, height = self._previewSize(
            int(resolved["settings"]["width"]),
            int(resolved["settings"]["height"]),
        )
        preview["settings"].update(
            {
                "width": width,
                "height": height,
                "fps": min(int(resolved["settings"]["fps"]), PREVIEW_MAX_FPS),
                "workers": 1,
                "resume": False,
            }
        )
        for scene in preview["scenes"]:
            renderer = scene.get("renderer", {})
            if isinstance(renderer, dict):
                renderer["core_scale"] = min(
                    float(renderer.get("core_scale", PREVIEW_CORE_SCALE)),
                    PREVIEW_CORE_SCALE,
                )
                renderer["anti_alias"] = False
        return preview

    # :: INT, INT -> (INT, INT)
    # Fits an even-sized frame within the conservative preview envelope
    def _previewSize(self, width: int, height: int) -> Tuple[int, int]:
        scale = min(
            PREVIEW_MAX_WIDTH / float(max(width, 1)),
            PREVIEW_MAX_HEIGHT / float(max(height, 1)),
            1.0,
        )
        previewWidth = max(2, int(width * scale) // 2 * 2)
        previewHeight = max(2, int(height * scale) // 2 * 2)
        return previewWidth, previewHeight

    #
    # Class Methods
    #

    # Class Factory Method :: configResolver?, referenceBackend? -> previewService
    # Creates a bounded production-backed preview service
    @classmethod
    def init(
        cls,
        resolver: Optional[ConfigResolver] = None,
        backend: Optional[ReferenceBackend] = None,
    ) -> PreviewService:
        return cls(resolver, backend)
