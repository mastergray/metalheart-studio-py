# Audio-driven scene planning for renderable JSON configs

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import math  # Divide oversized musical sections into balanced bounded scenes
import os  # Express generated audio and cache paths relative to the config
from pathlib import Path  # Resolve source and destination paths
from typing import Any, Dict, List, Optional  # Python 3.8-compatible type annotations


SCENE_MODES = ("phrases", "single")
AUTO_SCENE_MAX_SEC = 5.0


# Converts analyzed tempo into contiguous phrase-aligned scene skeletons
class ScenePlanner:

    # CONSTRUCTOR :: INT, INT, INT, INT, INT, STRING, STRING, FLOAT? -> scenePlanner
    # Creates a planner with output settings and an explicit skeleton template
    def __init__(self, width: int = 1920, height: int = 1080, fps: int = 30, crf: int = 18, seed: int = 3, quality: str = "final", template: str = "builtins/mercury-intro", maxSceneSec: Optional[float] = None) -> None:
        self._width = width
        self._height = height
        self._fps = fps
        self._crf = crf
        self._seed = seed
        self._quality = quality
        self._template = template
        self._maxSceneSec = maxSceneSec

    #
    # Instance Methods
    #

    # :: ANY, STRING, STRING, INT, STRING, STRING -> ARRAY<STRING, ANY>
    # Builds a complete authored config as one full-track scene or aligned phrases
    def plan(self, analysis: Any, audioPath: str, configPath: str, barsPerScene: int, cachePath: str, sceneMode: str = "phrases") -> Dict[str, Any]:
        configDirectory = Path(configPath).resolve().parent
        totalFrames = int(analysis.n_frames)
        if totalFrames <= 0:
            raise ValueError("audio analysis produced no renderable frames")
        if sceneMode not in SCENE_MODES:
            raise ValueError("scene mode must be one of: {0}".format(", ".join(SCENE_MODES)))
        boundaries = [0, totalFrames] if sceneMode == "single" else self._boundaries(analysis, barsPerScene)
        sceneName = "Full Track" if sceneMode == "single" else None
        scenes = [
            self._scene(analysis, boundaries[index], boundaries[index + 1], index, sceneName)
            for index in range(len(boundaries) - 1)
        ]
        return {
            "version": 1,
            "audio": os.path.relpath(str(Path(audioPath).resolve()), str(configDirectory)),
            "analysis": {
                "cache": os.path.relpath(str(Path(cachePath).resolve()), str(configDirectory)),
                "detected_bpm": round(float(analysis.bpm), 6),
            },
            "settings": {
                "width": self._width,
                "height": self._height,
                "fps": self._fps,
                "crf": self._crf,
                "seed": self._seed,
                "quality": self._quality,
                "time_mode": "global",
            },
            "scenes": scenes,
            "post": [],
        }

    #
    # Protected Methods
    #

    # :: ANY, INT -> [INT]
    # Calculates phrase-aligned frame boundaries covering the complete analysis
    def _boundaries(self, analysis: Any, barsPerScene: int) -> List[int]:
        bars = max(1, int(barsPerScene))
        barSec = 4.0 * 60.0 / max(float(analysis.bpm), 1e-6)
        phraseFrames = max(1, int(round(bars * barSec * self._fps)))
        firstDownbeat = float(analysis.downbeat_times[0]) if getattr(analysis.downbeat_times, "size", 0) else 0.0
        firstDownbeatFrame = max(0, int(round(firstDownbeat * self._fps)))
        boundaries = [0]
        maximumFrames = self._maximumSceneFrames()
        minimumOpeningFrames = max(self._fps, phraseFrames // 2)
        if maximumFrames is not None:
            minimumOpeningFrames = min(minimumOpeningFrames, maximumFrames)
        if minimumOpeningFrames <= firstDownbeatFrame < analysis.n_frames:
            boundaries.append(firstDownbeatFrame)
            nextBoundary = firstDownbeatFrame + phraseFrames
        else:
            nextBoundary = firstDownbeatFrame + phraseFrames
        while nextBoundary < analysis.n_frames:
            if nextBoundary > boundaries[-1]:
                boundaries.append(nextBoundary)
            nextBoundary += phraseFrames
        minimumTailFrames = max(1, phraseFrames // 2)
        if len(boundaries) > 1 and analysis.n_frames - boundaries[-1] < minimumTailFrames:
            boundaries.pop()
        if boundaries[-1] != analysis.n_frames:
            boundaries.append(int(analysis.n_frames))
        return (
            self._capBoundaries(boundaries, maximumFrames)
            if maximumFrames is not None
            else boundaries
        )

    # :: VOID -> INT?
    # Converts the authored maximum duration into a hard frame-precision bound
    def _maximumSceneFrames(self) -> Optional[int]:
        if self._maxSceneSec is None or self._maxSceneSec <= 0.0:
            return None
        return max(1, int(math.floor(self._maxSceneSec * self._fps + 1e-9)))

    # :: [INT], INT -> [INT]
    # Evenly subdivides oversized musical sections while preserving their boundaries
    def _capBoundaries(self, boundaries: List[int], maximumFrames: int) -> List[int]:
        capped = [boundaries[0]]
        for startFrame, endFrame in zip(boundaries, boundaries[1:]):
            durationFrames = endFrame - startFrame
            partCount = max(1, int(math.ceil(durationFrames / float(maximumFrames))))
            for partIndex in range(1, partCount + 1):
                boundary = (
                    endFrame
                    if partIndex == partCount
                    else startFrame + int(round(durationFrames * partIndex / float(partCount)))
                )
                if boundary > capped[-1]:
                    capped.append(boundary)
        return capped

    # :: ANY, INT, INT, INT, STRING? -> ARRAY<STRING, ANY>
    # Creates one neutral scene skeleton with objective analysis metadata
    def _scene(self, analysis: Any, startFrame: int, endFrame: int, index: int, sceneName: Optional[str] = None) -> Dict[str, Any]:
        startSec = startFrame / float(self._fps)
        endSec = endFrame / float(self._fps)
        beatCount = self._eventCount(analysis.beat_times, startSec, endSec)
        downbeatCount = self._eventCount(analysis.downbeat_times, startSec, endSec)
        return {
            "id": "scene-{0:02d}".format(index + 1),
            "name": sceneName or "Phrase {0}".format(index + 1),
            "start_sec": round(startSec, 9),
            "end_sec": round(endSec, 9),
            "beats": beatCount,
            "downbeats": downbeatCount,
            "analysis": {"mean_energy": round(self._meanEnergy(analysis, startFrame, endFrame), 6)},
            "template": self._template,
        }

    # :: ANY, INT, INT -> FLOAT
    # Calculates mean normalized energy for one scene range
    def _meanEnergy(self, analysis: Any, startFrame: int, endFrame: int) -> float:
        return float(analysis.energy[startFrame:endFrame].mean()) if endFrame > startFrame else 0.0

    # :: ANY, FLOAT, FLOAT -> INT
    # Counts detected event timestamps inside a half-open scene range
    def _eventCount(self, values: Any, startSec: float, endSec: float) -> int:
        return int(((values >= startSec) & (values < endSec)).sum())

    #
    # Class Methods
    #

    # Class Factory Method :: INT, INT, INT, INT, INT, STRING, STRING, FLOAT? -> scenePlanner
    # Creates a scene planner with output and skeleton-template settings
    @classmethod
    def init(cls, width: int = 1920, height: int = 1080, fps: int = 30, crf: int = 18, seed: int = 3, quality: str = "final", template: str = "builtins/mercury-intro", maxSceneSec: Optional[float] = None) -> ScenePlanner:
        return cls(width, height, fps, crf, seed, quality, template, maxSceneSec)
