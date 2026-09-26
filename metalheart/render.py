# Frame scheduling, audio analysis, encoding, muxing, and render profiles

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import copy  # Resolve runtime seed values without mutating caller configuration
import hashlib  # Address resumable work by complete resolved render inputs
import json  # Write render manifests
import os  # Atomically replace completed output files
import secrets  # Resolve exploratory null seeds before rendering
import shutil  # Locate tools and clean successful temporary renders
import subprocess  # Stream frames to FFmpeg and mux source audio
import sys  # Print unbuffered progress to stderr
import tempfile  # Isolate intermediate files per render
import time  # Measure progress and total render duration
from concurrent.futures import ProcessPoolExecutor, as_completed  # Render independent chunks concurrently
from pathlib import Path  # Manage output, cache, and temporary paths
from typing import Any, Dict, List, Optional, Tuple  # Python 3.8-compatible type annotations

from metalheart.analysis import AnalysisResult  # Describe cache hit and analysis data
from metalheart.analysis import AudioAnalysisCache  # Analyze source audio once per render range
from metalheart.chunks import renderChunk  # Execute isolated chunk encodes
from metalheart.config import ConfigError  # Report render preflight failures
from metalheart.config import ConfigResolver  # Write resolved profiles
from metalheart.reference_backend import ReferenceBackend  # Render frames through the reference adapter
from metalheart.reference_backend import ReferenceRendererSession  # Type per-scene renderer sessions


# Describes the files and timing produced by a successful render
class RenderResult:

    # CONSTRUCTOR :: STRING, STRING, STRING, INT, FLOAT, BOOL, INT, INT, INT -> renderResult
    # Stores output, timing, cache, and chunk execution status
    def __init__(self, outputPath: str, profilePath: str, manifestPath: str, frameCount: int, elapsedSec: float, cacheHit: bool, chunkCount: int = 1, reusedChunks: int = 0, workers: int = 1) -> None:
        self._outputPath = outputPath
        self._profilePath = profilePath
        self._manifestPath = manifestPath
        self._frameCount = frameCount
        self._elapsedSec = elapsedSec
        self._cacheHit = cacheHit
        self._chunkCount = chunkCount
        self._reusedChunks = reusedChunks
        self._workers = workers

    #
    # Properties
    #

    # PROPERTY :: VOID -> STRING
    # Returns the final video path
    @property
    def outputPath(self) -> str:
        return self._outputPath

    # PROPERTY :: VOID -> STRING
    # Returns the resolved profile path
    @property
    def profilePath(self) -> str:
        return self._profilePath

    # PROPERTY :: VOID -> STRING
    # Returns the render manifest path
    @property
    def manifestPath(self) -> str:
        return self._manifestPath

    # PROPERTY :: VOID -> INT
    # Returns the encoded video frame count
    @property
    def frameCount(self) -> int:
        return self._frameCount

    # PROPERTY :: VOID -> FLOAT
    # Returns total elapsed render seconds
    @property
    def elapsedSec(self) -> float:
        return self._elapsedSec

    # PROPERTY :: VOID -> BOOL
    # Reports whether cached audio analysis was reused
    @property
    def cacheHit(self) -> bool:
        return self._cacheHit

    # PROPERTY :: VOID -> INT
    # Returns the number of deterministic video chunks
    @property
    def chunkCount(self) -> int:
        return self._chunkCount

    # PROPERTY :: VOID -> INT
    # Returns how many completed chunks were reused
    @property
    def reusedChunks(self) -> int:
        return self._reusedChunks

    # PROPERTY :: VOID -> INT
    # Returns the effective process-worker count
    @property
    def workers(self) -> int:
        return self._workers

    #
    # Instance Methods
    #

    # :: VOID -> ARRAY<STRING, ANY>
    # Serializes the render result for CLI JSON output
    def toDict(self) -> Dict[str, Any]:
        return {
            "output": self._outputPath,
            "profile": self._profilePath,
            "manifest": self._manifestPath,
            "frames": self._frameCount,
            "elapsed_sec": self._elapsedSec,
            "analysis_cache_hit": self._cacheHit,
            "chunks": self._chunkCount,
            "reused_chunks": self._reusedChunks,
            "workers": self._workers,
        }


# Executes a validated Metalheart config as one synchronized video render
class RenderPipeline:

    # CONSTRUCTOR :: STRING, STRING, referenceBackend? -> renderPipeline
    # Creates a render pipeline with explicit FFmpeg tools
    def __init__(self, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", backend: Optional[ReferenceBackend] = None) -> None:
        self._ffmpeg = ffmpeg
        self._ffprobe = ffprobe
        self._backend = backend or ReferenceBackend.init()
        self._resolver = ConfigResolver.init()

    #
    # Instance Methods
    #

    # :: ARRAY<STRING, ANY>, STRING -> renderResult
    # Renders one resolved and validated config into an atomic final output
    def render(self, config: Dict[str, Any], outputPath: str) -> RenderResult:
        self._validateTools()
        report = self._resolver.validate(config)
        if not report.isValid:
            raise ConfigError("render config is invalid:\n- " + "\n- ".join(report.errors))
        resolved = copy.deepcopy(config)
        settings = resolved["settings"]
        if settings.get("seed") is None:
            settings["seed"] = secrets.randbelow(2 ** 31)
        output = Path(outputPath).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        fps = int(settings["fps"])
        ranges = self._sceneRanges(resolved["scenes"], fps)
        firstFrame = ranges[0][0]
        lastFrame = ranges[-1][1]
        frameCount = lastFrame - firstFrame
        startSec = firstFrame / float(fps)
        durationSec = frameCount / float(fps)
        cacheRoot = Path(resolved["_meta"]["config_path"]).parent / ".metalheart-cache"
        cache = AudioAnalysisCache.init(self._backend, cacheRoot)
        bpmHint = resolved.get("analysis", {}).get("bpm_hint")
        explicitCache = resolved.get("analysis", {}).get("cache")
        print("[analysis] {0:.3f}s–{1:.3f}s at {2} fps".format(startSec, startSec + durationSec, fps), file=sys.stderr, flush=True)
        analysisResult = cache.get(resolved["audio"], fps, startSec, durationSec, bpmHint, explicitCache)
        print("[analysis] {0}: {1}".format("cache hit" if analysisResult.cacheHit else "computed", analysisResult.cachePath), file=sys.stderr, flush=True)
        renderFingerprint = self._renderFingerprint(resolved, analysisResult.cachePath)
        workPath = output.parent / ".metalheart-work" / "{0}-{1}".format(output.stem, renderFingerprint[:16])
        workPath.mkdir(parents=True, exist_ok=True)
        silentPath = workPath / "video.mp4"
        partialHandle = tempfile.NamedTemporaryFile(prefix=".{0}.".format(output.name), suffix=".partial.mp4", dir=str(output.parent), delete=False)
        partialPath = Path(partialHandle.name)
        partialHandle.close()
        started = time.monotonic()
        try:
            chunkRanges = self._chunkRanges(firstFrame, lastFrame, fps, float(settings["chunk_sec"]))
            workers = self._workerCount(settings["workers"], len(chunkRanges))
            chunkPaths, reusedChunks = self._renderChunks(
                resolved,
                analysisResult,
                ranges,
                firstFrame,
                chunkRanges,
                workPath,
                renderFingerprint,
                workers,
                bool(settings["resume"]),
            )
            self._concatChunks(chunkPaths, workPath, silentPath)
            self._muxAudio(silentPath, resolved["audio"], startSec, durationSec, partialPath)
            os.replace(str(partialPath), str(output))
            elapsedSec = time.monotonic() - started
            profilePath = output.with_suffix(output.suffix + ".profile.json")
            manifestPath = output.with_suffix(output.suffix + ".manifest.json")
            self._resolver.write(resolved, str(profilePath))
            self._writeManifest(resolved, output, manifestPath, analysisResult, frameCount, startSec, durationSec, elapsedSec, len(chunkRanges), reusedChunks, workers, str(workPath))
            return RenderResult(str(output), str(profilePath), str(manifestPath), frameCount, elapsedSec, analysisResult.cacheHit, len(chunkRanges), reusedChunks, workers)
        except Exception:
            print("[render] failed; resumable intermediates preserved at {0}".format(workPath), file=sys.stderr, flush=True)
            if partialPath.exists() and partialPath.stat().st_size == 0:
                partialPath.unlink()
            raise

    #
    # Protected Methods
    #

    # :: VOID -> NONE
    # Verifies required media tools before expensive work begins
    def _validateTools(self) -> None:
        for name, executable in (("ffmpeg", self._ffmpeg), ("ffprobe", self._ffprobe)):
            if shutil.which(executable) is None:
                raise ConfigError("{0} executable not found: {1}".format(name, executable))

    # :: [ARRAY<STRING, ANY>], INT -> [(INT, INT, ARRAY<STRING, ANY>)]
    # Maps scene time boundaries to exact global output-frame ranges
    def _sceneRanges(self, scenes: List[Dict[str, Any]], fps: int) -> List[Tuple[int, int, Dict[str, Any]]]:
        return [
            (int(round(float(scene["start_sec"]) * fps)), int(round(float(scene["end_sec"]) * fps)), scene)
            for scene in scenes
        ]

    # :: ARRAY<STRING, ANY>, STRING -> STRING
    # Hashes all frame-affecting inputs into a resumable-work identity
    def _renderFingerprint(self, config: Dict[str, Any], analysisPath: str) -> str:
        payload = {
            "config": config,
            "analysis": str(Path(analysisPath).resolve()),
            "backend": self._backend.version,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    # :: INT, INT, INT, FLOAT -> [(INT, INT)]
    # Splits the exact output frame interval into stable ordered chunks
    def _chunkRanges(self, firstFrame: int, lastFrame: int, fps: int, chunkSec: float) -> List[Tuple[int, int]]:
        chunkFrames = max(1, int(round(chunkSec * fps)))
        ranges = []
        startFrame = firstFrame
        while startFrame < lastFrame:
            endFrame = min(lastFrame, startFrame + chunkFrames)
            ranges.append((startFrame, endFrame))
            startFrame = endFrame
        return ranges

    # :: ANY, INT -> INT
    # Resolves a conservative automatic process count
    def _workerCount(self, configured: Any, chunkCount: int) -> int:
        if configured == "auto":
            available = max(1, (os.cpu_count() or 1) // 2)
            return max(1, min(2, available, chunkCount))
        return max(1, min(int(configured), chunkCount))

    # :: ARRAY<STRING, ANY>, analysisResult, [(INT, INT, ARRAY<STRING, ANY>)], INT, [(INT, INT)], PATH, STRING, INT, BOOL -> ([PATH], INT)
    # Reuses valid chunks and renders missing chunks sequentially or in parallel
    def _renderChunks(self, config: Dict[str, Any], analysisResult: AnalysisResult, sceneRanges: List[Tuple[int, int, Dict[str, Any]]], analysisFirstFrame: int, chunkRanges: List[Tuple[int, int]], workPath: Path, fingerprint: str, workers: int, resume: bool) -> Tuple[List[Path], int]:
        chunkPaths: List[Path] = []
        pending: List[Dict[str, Any]] = []
        reused = 0
        for index, (firstFrame, lastFrame) in enumerate(chunkRanges):
            chunkPath = workPath / "chunk-{0:05d}-{1}-{2}.mp4".format(index, firstFrame, lastFrame)
            chunkPaths.append(chunkPath)
            if resume and self._chunkIsReusable(chunkPath, fingerprint, firstFrame, lastFrame):
                reused += 1
                continue
            pending.append(
                {
                    "index": index,
                    "config": config,
                    "analysis_path": analysisResult.cachePath,
                    "analysis_first_frame": analysisFirstFrame,
                    "scene_ranges": sceneRanges,
                    "first_frame": firstFrame,
                    "last_frame": lastFrame,
                    "output": str(chunkPath),
                    "ffmpeg": self._ffmpeg,
                }
            )
        print("[render] {0} chunks, {1} workers, {2} reused".format(len(chunkRanges), workers, reused), file=sys.stderr, flush=True)
        if workers == 1:
            for done, task in enumerate(pending, 1):
                result = renderChunk(task)
                self._writeChunkMarker(Path(result["output"]), fingerprint, result)
                print("[render] chunk {0}/{1} complete".format(done + reused, len(chunkRanges)), file=sys.stderr, flush=True)
        elif pending:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(renderChunk, task): task for task in pending}
                completed = reused
                for future in as_completed(futures):
                    result = future.result()
                    self._writeChunkMarker(Path(result["output"]), fingerprint, result)
                    completed += 1
                    print("[render] chunk {0}/{1} complete".format(completed, len(chunkRanges)), file=sys.stderr, flush=True)
        return chunkPaths, reused

    # :: PATH, STRING, INT, INT -> BOOL
    # Verifies one chunk marker matches the requested render identity and range
    def _chunkIsReusable(self, chunkPath: Path, fingerprint: str, firstFrame: int, lastFrame: int) -> bool:
        markerPath = chunkPath.with_suffix(".json")
        if not chunkPath.is_file() or chunkPath.stat().st_size <= 0 or not markerPath.is_file():
            return False
        try:
            with markerPath.open("r", encoding="utf-8") as handle:
                marker = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return False
        return marker.get("fingerprint") == fingerprint and marker.get("first_frame") == firstFrame and marker.get("last_frame") == lastFrame

    # :: PATH, STRING, ARRAY<STRING, ANY> -> NONE
    # Writes a completed-chunk marker after its atomic video publish
    def _writeChunkMarker(self, chunkPath: Path, fingerprint: str, result: Dict[str, Any]) -> None:
        marker = {
            "fingerprint": fingerprint,
            "first_frame": result["first_frame"],
            "last_frame": result["last_frame"],
            "frames": result["frames"],
            "elapsed_sec": result["elapsed_sec"],
        }
        markerPath = chunkPath.with_suffix(".json")
        temporaryPath = markerPath.with_suffix(".partial.json")
        with temporaryPath.open("w", encoding="utf-8") as handle:
            json.dump(marker, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(str(temporaryPath), str(markerPath))

    # :: [PATH], PATH, PATH -> NONE
    # Concatenates ordered silent H.264 chunks without re-encoding
    def _concatChunks(self, chunkPaths: List[Path], workPath: Path, outputPath: Path) -> None:
        concatPath = workPath / "concat.txt"
        with concatPath.open("w", encoding="utf-8") as handle:
            for chunkPath in chunkPaths:
                escaped = str(chunkPath.resolve()).replace("'", "'\\''")
                handle.write("file '{0}'\n".format(escaped))
        command = [
            self._ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concatPath),
            "-an",
            "-c",
            "copy",
            str(outputPath),
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise RuntimeError("FFmpeg chunk concat failed: {0}".format(result.stderr.decode("utf-8", errors="replace").strip()))

    # :: ARRAY<STRING, ANY>, analysisResult, [(INT, INT, ARRAY<STRING, ANY>)], INT, INT, PATH -> NONE
    # Streams scheduled BGR frames to one silent H.264 segment
    def _encodeVideo(self, config: Dict[str, Any], analysisResult: AnalysisResult, ranges: List[Tuple[int, int, Dict[str, Any]]], firstFrame: int, lastFrame: int, outputPath: Path) -> None:
        settings = config["settings"]
        fps = int(settings["fps"])
        command = [
            self._ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            "{0}x{1}".format(settings["width"], settings["height"]),
            "-r",
            str(fps),
            "-i",
            "-",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            str(settings["crf"]),
            "-pix_fmt",
            "yuv420p",
            str(outputPath),
        ]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        if process.stdin is None:
            raise RuntimeError("unable to open FFmpeg frame input")
        sceneIndex = -1
        session: Optional[ReferenceRendererSession] = None
        sceneStartFrame = firstFrame
        started = time.monotonic()
        lastUpdate = started
        try:
            for sourceFrame in range(firstFrame, lastFrame):
                nextSceneIndex = self._sceneIndex(ranges, sourceFrame)
                if nextSceneIndex != sceneIndex:
                    sceneIndex = nextSceneIndex
                    sceneStartFrame = ranges[sceneIndex][0]
                    session = self._backend.createRenderer(settings, ranges[sceneIndex][2])
                    print("[render] scene {0}: {1}".format(sceneIndex + 1, ranges[sceneIndex][2]["id"]), file=sys.stderr, flush=True)
                if session is None:
                    raise RuntimeError("frame schedule did not select a scene")
                analysisFrame = sourceFrame - firstFrame
                relativeTimeSec = analysisFrame / float(fps)
                scene = ranges[sceneIndex][2]
                params = self._backend.createParams(analysisResult.analysis, analysisFrame, relativeTimeSec, scene["reactivity"])
                modulators = self._backend.createModulators(analysisResult.analysis, analysisFrame, relativeTimeSec, scene["reactivity"])
                timeMode = scene.get("time_mode", settings["time_mode"])
                rendererTime = sourceFrame / float(fps) if timeMode == "global" else (sourceFrame - sceneStartFrame) / float(fps)
                frame = session.render(rendererTime, params, modulators)
                process.stdin.write(frame.tobytes())
                now = time.monotonic()
                if now - lastUpdate >= 1.0:
                    done = analysisFrame + 1
                    rate = done / max(now - started, 1e-9)
                    print("[render] {0}/{1} frames ({2:.2f} fps)".format(done, lastFrame - firstFrame, rate), file=sys.stderr, flush=True)
                    lastUpdate = now
            process.stdin.close()
            errorBytes = process.stderr.read() if process.stderr is not None else b""
            returnCode = process.wait()
        except Exception:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            process.kill()
            process.wait()
            raise
        if returnCode != 0:
            raise RuntimeError("FFmpeg video encode failed: {0}".format(errorBytes.decode("utf-8", errors="replace").strip()))

    # :: [(INT, INT, ARRAY<STRING, ANY>)], INT -> INT
    # Finds the scene containing one global source frame
    def _sceneIndex(self, ranges: List[Tuple[int, int, Dict[str, Any]]], sourceFrame: int) -> int:
        for index, (startFrame, endFrame, scene) in enumerate(ranges):
            del scene
            if startFrame <= sourceFrame < endFrame:
                return index
        raise RuntimeError("no scene covers source frame {0}".format(sourceFrame))

    # :: PATH, STRING, FLOAT, FLOAT, PATH -> NONE
    # Muxes the requested original-audio range with the silent video
    def _muxAudio(self, videoPath: Path, audioPath: str, startSec: float, durationSec: float, outputPath: Path) -> None:
        command = [
            self._ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(videoPath),
            "-ss",
            "{0:.9f}".format(startSec),
            "-i",
            audioPath,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "256k",
            "-t",
            "{0:.9f}".format(durationSec),
            "-movflags",
            "+faststart",
            str(outputPath),
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise RuntimeError("FFmpeg audio mux failed: {0}".format(result.stderr.decode("utf-8", errors="replace").strip()))

    # :: ARRAY<STRING, ANY>, PATH, PATH, analysisResult, INT, FLOAT, FLOAT, FLOAT, INT, INT, INT, STRING -> NONE
    # Writes hashes, timing, versions, and output metadata for a completed render
    def _writeManifest(self, config: Dict[str, Any], outputPath: Path, manifestPath: Path, analysisResult: AnalysisResult, frameCount: int, startSec: float, durationSec: float, elapsedSec: float, chunkCount: int, reusedChunks: int, workers: int, workPath: str) -> None:
        manifest = {
            "version": 1,
            "output": str(outputPath),
            "config": config["_meta"]["config_path"],
            "backend_version": self._backend.version,
            "analysis_cache": analysisResult.cachePath,
            "analysis_cache_hit": analysisResult.cacheHit,
            "start_sec": startSec,
            "duration_sec": durationSec,
            "frames": frameCount,
            "fps": config["settings"]["fps"],
            "elapsed_sec": elapsedSec,
            "chunks": chunkCount,
            "reused_chunks": reusedChunks,
            "workers": workers,
            "work_path": workPath,
        }
        with manifestPath.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")

    #
    # Class Methods
    #

    # Class Factory Method :: STRING, STRING, referenceBackend? -> renderPipeline
    # Creates a render pipeline with explicit tools and optional backend
    @classmethod
    def init(cls, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", backend: Optional[ReferenceBackend] = None) -> RenderPipeline:
        return cls(ffmpeg, ffprobe, backend)
