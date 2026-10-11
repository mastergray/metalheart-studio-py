# End-to-end integration test for analysis, rendering, encoding, and muxing

import json  # Parse ffprobe stream metadata
import math  # Generate deterministic tone phases
import shutil  # Skip cleanly when required media tools are unavailable
import struct  # Pack generated PCM samples into a WAV fixture
import subprocess  # Inspect rendered output with ffprobe
import wave  # Write generated mono PCM without external audio libraries
from pathlib import Path  # Manage temporary configs, audio, and output files
from typing import Any, Dict, List  # Python 3.8-compatible config annotations

import pytest  # Mark media integration coverage

from metalheart.analysis import AudioAnalysisCache  # Precompute the same full-track cache emitted by analyze
from metalheart.config import ConfigResolver  # Resolve and validate the temporary config
from metalheart.preview import PreviewService  # Render bounded native-UI still frames
from metalheart.progress import parseProgressLine  # Verify published render progress
from metalheart.reference_backend import ReferenceBackend  # Share the pinned backend across analysis and render
from metalheart.render import RenderPipeline  # Execute the complete render pipeline


# :: PATH, FLOAT -> NONE
# Writes a deterministic pulse-and-tone WAV suitable for reference analysis
def _writeAudio(path: Path, durationSec: float = 2.0) -> None:
    sampleRate = 22050
    frameCount = int(sampleRate * durationSec)
    samples = []
    for index in range(frameCount):
        timeSec = index / float(sampleRate)
        pulsePhase = timeSec % 0.5
        pulse = math.sin(2.0 * math.pi * 65.0 * timeSec) * math.exp(-pulsePhase * 18.0)
        tone = 0.25 * math.sin(2.0 * math.pi * 440.0 * timeSec)
        high = 0.08 * math.sin(2.0 * math.pi * 3200.0 * timeSec)
        value = max(-1.0, min(1.0, 0.65 * pulse + tone + high))
        samples.append(struct.pack("<h", int(value * 32767)))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sampleRate)
        handle.writeframes(b"".join(samples))


# :: PATH -> [STRING]
# Returns decoded video-frame hashes independently of container timestamps
def _frameHashes(path: Path) -> List[str]:
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-f", "framemd5", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        universal_newlines=True,
    )
    return [line.rsplit(",", 1)[-1].strip() for line in result.stdout.splitlines() if line and not line.startswith("#")]


# :: PATH, PATH -> ARRAY<STRING, ANY>
# Creates a two-second low-cost render config
def _config(audioPath: Path, configPath: Path) -> Dict[str, Any]:
    return {
        "version": 1,
        "audio": str(audioPath),
        "settings": {
            "width": 64,
            "height": 64,
            "fps": 4,
            "crf": 30,
            "seed": 11,
            "quality": "preview",
            "time_mode": "global",
            "workers": 2,
            "chunk_sec": 0.5,
            "resume": True,
        },
        "scenes": [
            {
                "id": "calm",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "template": "builtins/mercury-intro",
                "renderer": {"core": "2d", "decor": False, "anti_alias": False},
                "finish": {"scanlines": False},
                "reactivity": {"preset": "balanced"},
                "post": [
                    {"id": "rgb_shift", "parameters": {"rX": 2, "bX": -2}},
                    {"id": "tear", "parameters": {"direction": "horizontal", "bands": 5, "strength": 4, "seed": 2}},
                    {"id": "vhs", "parameters": {"tracking": 0.15, "chromaBleed": 0.2, "noise": 0.1, "headSwitch": 0.2}},
                ],
            },
            {
                "id": "impact",
                "start_sec": 1.0,
                "end_sec": 2.0,
                "template": "builtins/ferro-impact",
                "renderer": {
                    "core": "3d",
                    "palette": "ember",
                    "forms": ["mercury"],
                    "cameras": ["orbit"],
                    "core_scale": 0.1,
                    "decor": {
                        "enabled": True,
                        "ribbons": {
                            "enabled": True,
                            "count": 1,
                            "palette": "acid",
                            "post": [{"id": "rgb_shift", "parameters": {"rX": 2, "bX": -2}}],
                        },
                        "plates": {"enabled": False, "count": 0},
                    },
                    "surface": {"post": [{"id": "posterize", "parameters": {"levels": 4}}]},
                    "anti_alias": False,
                },
                "background": {
                    "palette": "steel",
                    "intensity": 1.4,
                    "post": [{"id": "scanlines", "parameters": {"strength": 0.2}}],
                },
                "finish": {
                    "scanlines": False,
                    "psx": {
                        "render_scale": 0.5,
                        "color_levels": 8,
                        "dither": "bayer4",
                        "dither_strength": 0.75,
                    },
                },
                "post": [
                    {"id": "rectangles", "parameters": {"n_rects": 2, "seed": 3}},
                    {"id": "tetrys", "parameters": {"block_size": 8, "direction": "left"}},
                    {"id": "ziti", "parameters": {"curvature": 0.35, "direction": "down"}},
                    {"id": "arcade", "parameters": {"curvature": 0.1, "maskStrength": 0.2, "paletteLevels": 5, "scanStrength": 0.15}},
                ],
            }
        ],
        "post": [{"id": "posterize", "parameters": {"levels": 6}, "mix": 0.35}],
    }


# :: PATH, ANY -> NONE
# Verifies a JSON config produces exact video frames plus an audio stream
@pytest.mark.integration
def testRendersSynchronizedVideoAndAudio(tmp_path: Path, capsys: Any) -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg and ffprobe are required")
    audioPath = tmp_path / "fixture.wav"
    configPath = tmp_path / "project.json"
    outputPath = tmp_path / "output.mp4"
    _writeAudio(audioPath)
    backend = ReferenceBackend.init()
    analysisResult = AudioAnalysisCache.init(backend, tmp_path / ".metalheart-cache").get(str(audioPath), 4.0, 0.0, None)
    authored = _config(audioPath, configPath)
    authored["analysis"] = {"cache": analysisResult.cachePath}
    configPath.write_text(json.dumps(authored), encoding="utf-8")
    resolver = ConfigResolver.init()
    resolved = resolver.resolve(resolver.load(str(configPath)), str(configPath))
    report = resolver.validate(resolved)
    assert report.isValid, report.errors
    assert len(resolved["scenes"]) == 2
    result = RenderPipeline.init(backend=backend, progress=True).render(
        resolved, str(outputPath)
    )
    progressEvents = [
        event
        for event in (
            parseProgressLine(line)
            for line in capsys.readouterr().err.splitlines()
        )
        if event is not None
    ]
    assert [event["phase"] for event in progressEvents[:2]] == [
        "preflight",
        "analysis",
    ]
    frameEvents = [
        event
        for event in progressEvents
        if event["phase"] == "rendering" and event["unit"] == "frames"
    ]
    assert frameEvents
    assert all(event["total"] == 8 for event in frameEvents)
    assert frameEvents[-1]["completed"] == 8
    assert any("remaining_sec" in event for event in frameEvents[:-1])
    assert any(event.get("context", {}).get("scene") for event in frameEvents)
    assert progressEvents[-1]["phase"] == "complete"
    assert result.frameCount == 8
    assert result.cacheHit
    assert result.chunkCount == 4
    assert result.workers == 2
    assert result.reusedChunks == 0
    assert resolved["scenes"][1]["renderer"]["palette"] == "ember"
    assert resolved["scenes"][1]["background"]["palette"] == "steel"
    assert resolved["scenes"][1]["background"]["intensity"] == 1.4
    assert resolved["scenes"][1]["renderer"]["decor"]["ribbons"]["palette"] == "acid"
    assert resolved["scenes"][1]["finish"]["psx"]["render_scale"] == 0.5
    assert resolved["scenes"][1]["finish"]["psx"]["dither"] == "bayer4"
    assert outputPath.is_file()
    assert Path(result.profilePath).is_file()
    assert Path(result.manifestPath).is_file()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,nb_frames,width,height,duration", "-of", "json", str(outputPath)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        universal_newlines=True,
    )
    streams = json.loads(probe.stdout)["streams"]
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    assert int(video["nb_frames"]) == 8
    assert video["width"] == 64
    assert video["height"] == 64
    audio = next(stream for stream in streams if stream["codec_type"] == "audio")
    assert abs(float(video["duration"]) - 2.0) < 0.001
    assert abs(float(audio["duration"]) - 2.0) < 0.001
    cachedOutputPath = tmp_path / "output-cached.mp4"
    cachedResult = RenderPipeline.init(backend=backend).render(resolved, str(cachedOutputPath))
    assert cachedResult.cacheHit
    assert cachedResult.frameCount == result.frameCount
    resumedResult = RenderPipeline.init(backend=backend).render(resolved, str(outputPath))
    assert resumedResult.reusedChunks == 4
    assert resumedResult.frameCount == result.frameCount

    clipDirectory = tmp_path / "clips"
    clipResults = RenderPipeline.init(backend=backend).renderScenes(resolved, str(clipDirectory))
    assert [Path(item.outputPath).name for item in clipResults] == ["001-calm.mp4", "002-impact.mp4"]
    assert [item.frameCount for item in clipResults] == [4, 4]
    clipFrameHashes = []
    for index, item in enumerate(clipResults):
        clipPath = Path(item.outputPath)
        profile = json.loads(Path(item.profilePath).read_text(encoding="utf-8"))
        assert clipPath.is_file()
        assert Path(item.manifestPath).is_file()
        assert len(profile["scenes"]) == 1
        assert profile["scenes"][0]["id"] == resolved["scenes"][index]["id"]
        assert profile["scenes"][0]["renderer"] == resolved["scenes"][index]["renderer"]
        assert profile["post"] == resolved["post"]
        clipProbe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,nb_frames,duration", "-of", "json", str(clipPath)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            universal_newlines=True,
        )
        clipStreams = json.loads(clipProbe.stdout)["streams"]
        clipVideo = next(stream for stream in clipStreams if stream["codec_type"] == "video")
        clipAudio = next(stream for stream in clipStreams if stream["codec_type"] == "audio")
        assert int(clipVideo["nb_frames"]) == 4
        assert abs(float(clipVideo["duration"]) - 1.0) < 0.001
        assert abs(float(clipAudio["duration"]) - 1.0) < 0.001
        clipFrameHashes.extend(_frameHashes(clipPath))
    assert clipFrameHashes == _frameHashes(outputPath)


# :: PATH -> NONE
# Verifies finite-history Slitscan preroll produces the same frames across chunk boundaries
@pytest.mark.integration
def testSlitscanHistorySurvivesParallelChunks(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg and ffprobe are required")
    audioPath = tmp_path / "slitscan.wav"
    configPath = tmp_path / "slitscan.json"
    _writeAudio(audioPath)
    authored = _config(audioPath, configPath)
    authored["settings"].update({"crf": 0, "workers": 1, "chunk_sec": 2.0, "resume": False})
    scene = authored["scenes"][0]
    scene["end_sec"] = 2.0
    scene["post"] = [
        {
            "id": "slitscan",
            "parameters": {"direction": "horizontal", "max_delay_frames": 3, "audio_scale": 0.0},
        }
    ]
    authored["scenes"] = [scene]
    authored["post"] = []
    configPath.write_text(json.dumps(authored), encoding="utf-8")
    resolver = ConfigResolver.init()
    singleConfig = resolver.resolve(resolver.load(str(configPath)), str(configPath))
    singlePath = tmp_path / "slitscan-single.mp4"
    RenderPipeline.init().render(singleConfig, str(singlePath))
    authored["settings"].update({"workers": 2, "chunk_sec": 0.5})
    configPath.write_text(json.dumps(authored), encoding="utf-8")
    chunkedConfig = resolver.resolve(resolver.load(str(configPath)), str(configPath))
    chunkedPath = tmp_path / "slitscan-chunked.mp4"
    RenderPipeline.init().render(chunkedConfig, str(chunkedPath))
    assert _frameHashes(chunkedPath) == _frameHashes(singlePath)


# :: PATH -> NONE
# Verifies the UI preview path shares resolution, validation, audio, and renderer services
@pytest.mark.integration
def testRendersBoundedStillPreview(tmp_path: Path) -> None:
    audioPath = tmp_path / "preview.wav"
    configPath = tmp_path / "preview.json"
    _writeAudio(audioPath, 1.0)
    authored = _config(audioPath, configPath)
    authored["settings"].update({"width": 1920, "height": 1080, "fps": 30})
    authored["scenes"] = [authored["scenes"][0]]
    authored["scenes"][0]["end_sec"] = 1.0
    result = PreviewService.init().render(authored, str(configPath), 0, 0.5)
    assert result.frame.shape == (270, 480, 3)
    assert result.frame.dtype.name == "uint8"
    assert result.sceneId == "calm"
    assert abs(result.timeSec - 0.5) < 0.1


# :: PATH -> NONE
# Verifies selected-range preview preserves exact frame timing and progress
@pytest.mark.integration
def testRendersBoundedRangePreview(tmp_path: Path) -> None:
    audioPath = tmp_path / "range-preview.wav"
    configPath = tmp_path / "range-preview.json"
    _writeAudio(audioPath, 1.0)
    authored = _config(audioPath, configPath)
    authored["settings"].update({"width": 64, "height": 64, "fps": 4})
    authored["scenes"] = [authored["scenes"][0]]
    authored["scenes"][0]["end_sec"] = 1.0
    progress = []
    result = PreviewService.init().renderRange(
        authored,
        str(configPath),
        0,
        0.25,
        0.75,
        progress=lambda completed, total: progress.append((completed, total)),
    )
    assert len(result.frames) == 2
    assert all(frame.shape == (64, 64, 3) for frame in result.frames)
    assert result.fps == 4
    assert result.sceneId == "calm"
    assert result.startSec == 0.25
    assert result.endSec == 0.75
    assert progress[-1][0] == progress[-1][1]
