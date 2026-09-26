# Owned camera timing and signature controls around the immutable reference choreography

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import math  # Clamp the authored field of view in radians
from types import ModuleType  # Type the dynamically loaded reference renderer module
from typing import Any, Dict, List, Tuple  # Python 3.8-compatible collection annotations

import numpy as np  # Blend and safely bound reference camera vectors


# Preserves form choreography while making reference camera moves authorable
class CameraChoreo:

    # CONSTRUCTOR :: moduleType, [STRING], [STRING], FLOAT, FLOAT, FLOAT, FLOAT, FLOAT, FLOAT -> cameraChoreo
    # Creates an independent reference choreography with owned camera timing controls
    def __init__(self, liquidModule: ModuleType, forms: List[str], cameras: List[str], formLenSec: float, cameraLenSec: float, crossfadeSec: float, cameraSpeed: float, cameraPhaseSec: float, cameraIntensity: float) -> None:
        self._liquidModule = liquidModule
        self._cameraSpeed = cameraSpeed
        self._cameraPhaseSec = cameraPhaseSec
        self._cameraIntensity = cameraIntensity
        self._choreo = liquidModule.Choreo(
            looks=forms,
            cams=cameras,
            look_len=formLenSec,
            cam_len=cameraLenSec,
            xfade=crossfadeSec,
        )

    #
    # Instance Methods
    #

    # :: FLOAT -> (ARRAY<STRING, FLOAT>, STRING)
    # Preserves the reference form schedule at unmodified renderer time
    def weights(self, timeSec: float) -> Tuple[Dict[str, float], str]:
        return self._choreo.weights(timeSec)

    # :: FLOAT, ANY -> (ANY, STRING)
    # Applies camera-only speed and phase before strengthening the selected pose
    def pose(self, timeSec: float, params: Any) -> Tuple[Any, str]:
        cameraTime = timeSec * self._cameraSpeed + self._cameraPhaseSec
        pose, camera = self._choreo.pose(cameraTime, params)
        if abs(self._cameraIntensity - 1.0) < 1e-9:
            return pose, camera
        neutralPose = self._liquidModule.camera_pose("orbit", cameraTime, params)
        return self._blendPose(neutralPose, pose, self._cameraIntensity), camera

    #
    # Protected Methods
    #

    # :: ANY, ANY, FLOAT -> ANY
    # Extrapolates a camera away from Orbit while bounding unsafe distance and FOV
    def _blendPose(self, neutralPose: Any, cameraPose: Any, intensity: float) -> Any:
        neutralEye, neutralTarget, neutralRoll, neutralFov = neutralPose
        cameraEye, cameraTarget, cameraRoll, cameraFov = cameraPose
        eye = np.asarray(neutralEye) + (np.asarray(cameraEye) - np.asarray(neutralEye)) * intensity
        distance = float(np.linalg.norm(eye))
        boundedDistance = min(max(distance, 1.2), 8.0)
        if distance > 1e-6 and abs(distance - boundedDistance) > 1e-6:
            eye = eye * (boundedDistance / distance)
        target = np.asarray(neutralTarget) + (np.asarray(cameraTarget) - np.asarray(neutralTarget)) * intensity
        roll = float(neutralRoll) + (float(cameraRoll) - float(neutralRoll)) * intensity
        fov = float(neutralFov) + (float(cameraFov) - float(neutralFov)) * intensity
        fov = min(max(fov, math.radians(15.0)), math.radians(75.0))
        return eye.astype(np.float32), target.astype(np.float32), roll, fov

    #
    # Class Methods
    #

    # Class Factory Method :: moduleType, [STRING], [STRING], FLOAT, FLOAT, FLOAT, FLOAT, FLOAT, FLOAT -> cameraChoreo
    # Creates an owned camera choreography adapter
    @classmethod
    def init(cls, liquidModule: ModuleType, forms: List[str], cameras: List[str], formLenSec: float, cameraLenSec: float, crossfadeSec: float, cameraSpeed: float, cameraPhaseSec: float, cameraIntensity: float) -> CameraChoreo:
        return cls(liquidModule, forms, cameras, formLenSec, cameraLenSec, crossfadeSec, cameraSpeed, cameraPhaseSec, cameraIntensity)
