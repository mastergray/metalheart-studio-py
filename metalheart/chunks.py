# Isolated deterministic render-chunk worker used by sequential and parallel renders

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import os  # Atomically publish completed chunk files
import subprocess  # Stream raw frames into a bounded FFmpeg encoder
import time  # Report chunk render timing
from pathlib import Path  # Manage exact chunk and partial paths
from typing import Any, Dict, List, Optional, Tuple  # Python 3.8-compatible annotations

from metalheart.reference_backend import ReferenceBackend  # Create process-local renderer modules
from metalheart.reference_backend import ReferenceRendererSession  # Type active scene sessions


# :: [ARRAY<STRING, ANY>], INT -> (INT, INT, ARRAY<STRING, ANY>)
# Finds the resolved scene that owns one global source frame
def _sceneRange(ranges: List[Tuple[int, int, Dict[str, Any]]], sourceFrame: int) -> Tuple[int, int, Dict[str, Any]]:
    for startFrame, endFrame, scene in ranges:
        if startFrame <= sourceFrame < endFrame:
            return startFrame, endFrame, scene
    raise RuntimeError("no scene covers source frame {0}".format(sourceFrame))


# :: ARRAY<STRING, ANY> -> ARRAY<STRING, ANY>
# Renders one independent silent H.264 chunk and atomically publishes it
def renderChunk(task: Dict[str, Any]) -> Dict[str, Any]:
    config = task["config"]
    settings = config["settings"]
    firstFrame = int(task["first_frame"])
    lastFrame = int(task["last_frame"])
    analysisFirstFrame = int(task["analysis_first_frame"])
    outputPath = Path(task["output"])
    partialPath = outputPath.with_suffix(".partial.mp4")
    backend = ReferenceBackend.init()
    analysis = backend.loadAnalysis(task["analysis_path"])
    fps = int(settings["fps"])
    command = [
        task["ffmpeg"],
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
        "-threads",
        "1",
        "-pix_fmt",
        "yuv420p",
        str(partialPath),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.stdin is None:
        raise RuntimeError("unable to open FFmpeg frame input for chunk {0}".format(task["index"]))
    ranges = task["scene_ranges"]
    activeId: Optional[str] = None
    session: Optional[ReferenceRendererSession] = None
    sceneStartFrame = firstFrame
    started = time.monotonic()
    try:
        for sourceFrame in range(firstFrame, lastFrame):
            nextStartFrame, nextEndFrame, scene = _sceneRange(ranges, sourceFrame)
            del nextEndFrame
            if scene["id"] != activeId:
                activeId = scene["id"]
                sceneStartFrame = nextStartFrame
                session = backend.createRenderer(settings, scene)
            if session is None:
                raise RuntimeError("chunk frame schedule did not select a scene")
            analysisFrame = sourceFrame - analysisFirstFrame
            relativeTimeSec = analysisFrame / float(fps)
            params = backend.createParams(analysis, analysisFrame, relativeTimeSec, scene["reactivity"])
            modulators = backend.createModulators(analysis, analysisFrame, relativeTimeSec, scene["reactivity"])
            timeMode = scene.get("time_mode", settings["time_mode"])
            rendererTime = sourceFrame / float(fps) if timeMode == "global" else (sourceFrame - sceneStartFrame) / float(fps)
            process.stdin.write(session.render(rendererTime, params, modulators).tobytes())
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
        raise RuntimeError("FFmpeg chunk encode failed: {0}".format(errorBytes.decode("utf-8", errors="replace").strip()))
    os.replace(str(partialPath), str(outputPath))
    return {
        "index": int(task["index"]),
        "output": str(outputPath),
        "first_frame": firstFrame,
        "last_frame": lastFrame,
        "frames": lastFrame - firstFrame,
        "elapsed_sec": time.monotonic() - started,
    }
