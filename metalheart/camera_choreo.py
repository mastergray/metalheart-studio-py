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
        self._signals: Dict[str, float] = {}
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

    # :: ARRAY<STRING, FLOAT> -> NONE
    # Stores deterministic per-frame camera modulation values
    def setSignals(self, signals: Dict[str, float]) -> None:
        self._signals = {
            key: float(signals.get(key, 0.0))
            for key in ("camera_distance", "camera_elevation", "camera_roll", "camera_kick")
        }

    # :: FLOAT, ANY -> (ANY, STRING)
    # Applies camera-only speed and phase before strengthening the selected pose
    def pose(self, timeSec: float, params: Any) -> Tuple[Any, str]:
        cameraTime = timeSec * self._cameraSpeed + self._cameraPhaseSec
        pose, camera = self._choreo.pose(cameraTime, params)
        if abs(self._cameraIntensity - 1.0) >= 1e-9:
            neutralPose = self._liquidModule.camera_pose("orbit", cameraTime, params)
            pose = self._blendPose(neutralPose, pose, self._cameraIntensity)
        return self._reactPose(pose, timeSec), camera

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

    # :: ANY, FLOAT -> ANY
    # Applies bounded audio-driven dolly, elevation, roll, and onset impulses
    def _reactPose(self, pose: Any, timeSec: float) -> Any:
        if not any(abs(value) > 1e-12 for value in self._signals.values()):
            return pose
        eye, target, roll, fov = pose
        eye = np.asarray(eye, np.float32).copy()
        target = np.asarray(target, np.float32).copy()
        relative = eye - target
        distance = max(float(np.linalg.norm(relative)), 1e-6)
        distanceSignal = min(max(self._signals.get("camera_distance", 0.0), -0.75), 0.75)
        relative *= 1.0 - distanceSignal
        elevation = min(max(self._signals.get("camera_elevation", 0.0), -0.75), 0.75)
        relative[1] += elevation * distance
        kick = min(max(self._signals.get("camera_kick", 0.0), 0.0), 0.75)
        kickPhase = timeSec * 47.123 + 0.7
        kickAngle = kick * math.sin(kickPhase)
        cosine = math.cos(kickAngle)
        sine = math.sin(kickAngle)
        xValue = float(relative[0]) * cosine + float(relative[2]) * sine
        zValue = -float(relative[0]) * sine + float(relative[2]) * cosine
        relative[0] = xValue
        relative[2] = zValue
        relative[1] += kick * distance * 0.35 * math.cos(kickPhase * 0.83)
        boundedDistance = min(max(float(np.linalg.norm(relative)), 1.2), 8.0)
        currentDistance = max(float(np.linalg.norm(relative)), 1e-6)
        relative *= boundedDistance / currentDistance
        cameraRoll = min(max(self._signals.get("camera_roll", 0.0), -1.2), 1.2)
        roll = float(roll) + cameraRoll + kick * 0.2 * math.sin(kickPhase * 0.71)
        return (target + relative).astype(np.float32), target, roll, float(fov)

    #
    # Class Methods
    #

    # Class Factory Method :: moduleType, [STRING], [STRING], FLOAT, FLOAT, FLOAT, FLOAT, FLOAT, FLOAT -> cameraChoreo
    # Creates an owned camera choreography adapter
    @classmethod
    def init(cls, liquidModule: ModuleType, forms: List[str], cameras: List[str], formLenSec: float, cameraLenSec: float, crossfadeSec: float, cameraSpeed: float, cameraPhaseSec: float, cameraIntensity: float) -> CameraChoreo:
        return cls(liquidModule, forms, cameras, formLenSec, cameraLenSec, crossfadeSec, cameraSpeed, cameraPhaseSec, cameraIntensity)
