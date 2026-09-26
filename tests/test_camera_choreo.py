# Unit tests for owned camera timing and signature controls

from types import SimpleNamespace  # Build a compact reference-module substitute
from typing import Any, Dict, List, Tuple  # Python 3.8-compatible fixture annotations

import numpy as np  # Construct and compare camera vectors

from metalheart.camera_choreo import CameraChoreo  # Exercise owned camera choreography


# Minimal reference choreography substitute for timing isolation
class _FakeChoreo:

    # CONSTRUCTOR :: [STRING], [STRING], FLOAT, FLOAT, FLOAT -> fakeChoreo
    # Accepts the reference constructor contract
    def __init__(self, looks: List[str], cams: List[str], look_len: float, cam_len: float, xfade: float) -> None:
        del looks, cams, look_len, cam_len, xfade

    # :: FLOAT -> (ARRAY<STRING, FLOAT>, STRING)
    # Exposes the unmodified form time for assertions
    def weights(self, timeSec: float) -> Tuple[Dict[str, float], str]:
        return {"time": timeSec}, "mercury"

    # :: FLOAT, ANY -> (ANY, STRING)
    # Returns a camera pose whose difference from Orbit is easy to measure
    def pose(self, timeSec: float, params: Any) -> Tuple[Any, str]:
        del params
        pose = (np.array([1.0 + timeSec, 0.0, 0.0], np.float32), np.array([1.0, 0.0, 0.0], np.float32), 0.2, 0.5)
        return pose, "dolly"


# :: STRING, FLOAT, ANY -> ANY
# Supplies the neutral Orbit pose expected by the owned adapter
def _cameraPose(mode: str, timeSec: float, params: Any) -> Any:
    del mode, timeSec, params
    return np.array([1.0, 0.0, 0.0], np.float32), np.zeros(3, np.float32), 0.0, 0.4


# :: VOID -> NONE
# Verifies camera controls do not accelerate form choreography
def testCameraTimingIsIndependentFromFormTiming() -> None:
    module = SimpleNamespace(Choreo=_FakeChoreo, camera_pose=_cameraPose)
    choreo = CameraChoreo.init(module, ["mercury"], ["dolly"], 6.0, 9.0, 1.8, 2.0, 3.0, 1.0)
    weights, form = choreo.weights(1.0)
    pose, camera = choreo.pose(1.0, SimpleNamespace())
    assert weights == {"time": 1.0}
    assert form == "mercury"
    assert pose[0][0] == 6.0
    assert camera == "dolly"


# :: VOID -> NONE
# Verifies intensity extrapolates a camera signature away from Orbit
def testCameraIntensityStrengthensPoseDifference() -> None:
    module = SimpleNamespace(Choreo=_FakeChoreo, camera_pose=_cameraPose)
    choreo = CameraChoreo.init(module, ["mercury"], ["dolly"], 6.0, 9.0, 1.8, 1.0, 0.0, 2.0)
    pose, camera = choreo.pose(1.0, SimpleNamespace())
    assert camera == "dolly"
    assert np.allclose(pose[0], [3.0, 0.0, 0.0])
    assert np.allclose(pose[1], [2.0, 0.0, 0.0])
    assert abs(pose[2] - 0.4) < 1e-6
    assert abs(pose[3] - 0.6) < 1e-6


# :: VOID -> NONE
# Verifies audio signals alter camera space without changing the base choreography
def testCameraSignalsModulatePose() -> None:
    module = SimpleNamespace(Choreo=_FakeChoreo, camera_pose=_cameraPose)
    choreo = CameraChoreo.init(module, ["mercury"], ["dolly"], 6.0, 9.0, 1.8, 1.0, 0.0, 1.0)
    choreo.setSignals(
        {"camera_distance": 0.25, "camera_elevation": 0.2, "camera_roll": 0.1}
    )
    pose, camera = choreo.pose(1.0, SimpleNamespace())
    assert camera == "dolly"
    assert np.allclose(pose[1], [1.0, 0.0, 0.0])
    assert abs(np.linalg.norm(pose[0] - pose[1]) - 1.2) < 1e-6
    assert pose[0][0] < 2.2
    assert pose[0][1] > 0.3
    assert abs(pose[2] - 0.3) < 1e-6
