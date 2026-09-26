# Unit tests for phrase-aligned audio scene planning

from types import SimpleNamespace  # Build compact analyzed-audio fixtures
from pathlib import Path  # Provide stable config and cache path inputs
from typing import Any  # Annotate analysis fixture values

import numpy as np  # Create energy and event arrays

from metalheart.planner import ScenePlanner  # Generate scene-based authored configs


# :: VOID -> ANY
# Creates forty seconds of analyzed audio at 120 BPM
def _analysis() -> Any:
    fps = 10
    frames = 400
    energy = np.r_[np.full(160, 0.2, np.float32), np.full(frames - 160, 0.9, np.float32)]
    beatTimes = np.arange(0.0, 40.0, 0.5, dtype=np.float32)
    return SimpleNamespace(
        n_frames=frames,
        fps=float(fps),
        duration=40.0,
        bpm=120.0,
        energy=energy,
        beat_times=beatTimes,
        downbeat_times=beatTimes[::4],
    )


# :: PATH -> NONE
# Verifies neutral scene skeletons cover the track contiguously
def testPlansContiguousNeutralScenes(tmp_path: Path) -> None:
    planner = ScenePlanner.init(fps=10, template="builtins/ferro-impact", maxSceneSec=9.0)
    config = planner.plan(_analysis(), str(tmp_path / "audio.wav"), str(tmp_path / "project.json"), 4, str(tmp_path / "features.npz"))
    scenes = config["scenes"]
    assert scenes[0]["start_sec"] == 0.0
    assert scenes[-1]["end_sec"] == 40.0
    for first, second in zip(scenes, scenes[1:]):
        assert first["end_sec"] == second["start_sec"]
    assert scenes[-1]["end_sec"] - scenes[-1]["start_sec"] >= 4.0
    assert all(scene["template"] == "builtins/ferro-impact" for scene in scenes)
    assert all("label" not in scene for scene in scenes)
    assert all(scene["name"].startswith("Phrase ") for scene in scenes)
    assert scenes[0]["analysis"]["mean_energy"] == 0.2
    assert scenes[-1]["analysis"]["mean_energy"] == 0.9
    assert all(scene["beats"] > 0 for scene in scenes)
