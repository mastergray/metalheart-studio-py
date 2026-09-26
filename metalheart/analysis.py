# Content-addressed audio analysis cache

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import hashlib  # Fingerprint audio content and analysis parameters
import json  # Store cache metadata beside NumPy analysis data
from pathlib import Path  # Manage cache paths
from typing import Any, Optional  # Python 3.8-compatible type annotations

from metalheart.reference_backend import ReferenceBackend  # Analyze and serialize reference signals


ANALYZER_VERSION = "reference-analysis-v1"


# Describes a loaded or newly generated analysis cache entry
class AnalysisResult:

    # CONSTRUCTOR :: ANY, STRING, BOOL -> analysisResult
    # Stores analysis data, its cache path, and cache-hit state
    def __init__(self, analysis: Any, cachePath: str, cacheHit: bool) -> None:
        self._analysis = analysis
        self._cachePath = cachePath
        self._cacheHit = cacheHit

    #
    # Properties
    #

    # PROPERTY :: VOID -> ANY
    # Returns the backend analysis object
    @property
    def analysis(self) -> Any:
        return self._analysis

    # PROPERTY :: VOID -> STRING
    # Returns the compressed analysis cache path
    @property
    def cachePath(self) -> str:
        return self._cachePath

    # PROPERTY :: VOID -> BOOL
    # Reports whether analysis was loaded from a valid cache
    @property
    def cacheHit(self) -> bool:
        return self._cacheHit


# Creates and validates content-addressed audio analysis caches
class AudioAnalysisCache:

    # CONSTRUCTOR :: referenceBackend, PATH -> audioAnalysisCache
    # Creates a cache manager rooted at the supplied directory
    def __init__(self, backend: ReferenceBackend, cacheRoot: Path) -> None:
        self._backend = backend
        self._cacheRoot = cacheRoot

    #
    # Instance Methods
    #

    # :: STRING, FLOAT, FLOAT, FLOAT?, FLOAT?, STRING? -> analysisResult
    # Loads a valid analysis cache or computes and stores a new one
    def get(self, audioPath: str, fps: float, startSec: float, durationSec: Optional[float], bpmHint: Optional[float] = None, explicitPath: Optional[str] = None) -> AnalysisResult:
        audioDigest = self._audioDigest(audioPath)
        cacheKey = self._cacheKey(audioDigest, fps, startSec, durationSec, bpmHint)
        cachePath = Path(explicitPath) if explicitPath else self._cacheRoot / (cacheKey + ".npz")
        metadataPath = cachePath.with_suffix(cachePath.suffix + ".json")
        if cachePath.is_file() and metadataPath.is_file() and self._metadataMatches(metadataPath, cacheKey):
            return AnalysisResult(self._backend.loadAnalysis(str(cachePath)), str(cachePath), True)
        if explicitPath and cachePath.is_file() and metadataPath.is_file():
            compatible = self._compatibleExplicitCache(metadataPath, cachePath, audioDigest, fps, startSec, durationSec, bpmHint)
            if compatible is not None:
                return AnalysisResult(compatible, str(cachePath), True)
        cachePath.parent.mkdir(parents=True, exist_ok=True)
        analysis = self._backend.analyzeAudio(audioPath, fps, startSec, durationSec, bpmHint)
        self._backend.saveAnalysis(analysis, str(cachePath))
        metadata = {
            "key": cacheKey,
            "audio_digest": audioDigest,
            "analyzer_version": ANALYZER_VERSION,
            "backend_version": self._backend.version,
            "audio": str(Path(audioPath).resolve()),
            "fps": fps,
            "start_sec": startSec,
            "duration_sec": durationSec,
            "bpm_hint": bpmHint,
        }
        with metadataPath.open("w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, sort_keys=True)
            handle.write("\n")
        return AnalysisResult(analysis, str(cachePath), False)

    #
    # Protected Methods
    #

    # :: STRING -> STRING
    # Hashes source audio bytes independently from analysis parameters
    def _audioDigest(self, audioPath: str) -> str:
        digest = hashlib.sha256()
        with Path(audioPath).open("rb") as handle:
            while True:
                block = handle.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
        return digest.hexdigest()

    # :: STRING, FLOAT, FLOAT, FLOAT?, FLOAT? -> STRING
    # Hashes audio identity and all analysis-affecting inputs
    def _cacheKey(self, audioDigest: str, fps: float, startSec: float, durationSec: Optional[float], bpmHint: Optional[float]) -> str:
        digest = hashlib.sha256()
        digest.update(audioDigest.encode("ascii"))
        parameters = json.dumps(
            {
                "analyzer_version": ANALYZER_VERSION,
                "backend_version": self._backend.version,
                "fps": fps,
                "start_sec": startSec,
                "duration_sec": durationSec,
                "bpm_hint": bpmHint,
            },
            sort_keys=True,
        )
        digest.update(parameters.encode("utf-8"))
        return digest.hexdigest()

    # :: PATH, STRING -> BOOL
    # Checks whether cache metadata contains the expected content key
    def _metadataMatches(self, metadataPath: Path, expectedKey: str) -> bool:
        try:
            with metadataPath.open("r", encoding="utf-8") as handle:
                metadata = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return False
        return isinstance(metadata, dict) and metadata.get("key") == expectedKey

    # :: PATH, PATH, STRING, FLOAT, FLOAT, FLOAT?, FLOAT? -> ANY?
    # Reuses an explicit full-range cache when it safely covers the render range
    def _compatibleExplicitCache(self, metadataPath: Path, cachePath: Path, audioDigest: str, fps: float, startSec: float, durationSec: Optional[float], bpmHint: Optional[float]) -> Optional[Any]:
        try:
            with metadataPath.open("r", encoding="utf-8") as handle:
                metadata = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(metadata, dict):
            return None
        expected = {
            "audio_digest": audioDigest,
            "analyzer_version": ANALYZER_VERSION,
            "backend_version": self._backend.version,
            "fps": fps,
            "start_sec": startSec,
            "bpm_hint": bpmHint,
        }
        if any(metadata.get(key) != value for key, value in expected.items()):
            return None
        analysis = self._backend.loadAnalysis(str(cachePath))
        neededFrames = int(round(durationSec * fps)) if durationSec is not None else 0
        return analysis if int(analysis.n_frames) >= neededFrames else None

    #
    # Class Methods
    #

    # Class Factory Method :: referenceBackend, PATH -> audioAnalysisCache
    # Creates an analysis cache manager
    @classmethod
    def init(cls, backend: ReferenceBackend, cacheRoot: Path) -> AudioAnalysisCache:
        return cls(backend, cacheRoot)
