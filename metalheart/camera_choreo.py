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
        self._forms = list(forms)
        self._formLenSec = formLenSec
        self._crossfadeSec = crossfadeSec
        self._signals: Dict[str, float] = {}
        referenceForms = ["mercury" if form == "resonance" else form for form in forms]
        self._choreo = liquidModule.Choreo(
            looks=referenceForms,
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
        if "resonance" in self._forms:
            return self._resonanceWeights(timeSec)
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

    # :: FLOAT -> (ARRAY<STRING, FLOAT>, STRING)
    # Resolves reference and owned forms through the reference crossfade schedule
    def _resonanceWeights(self, timeSec: float) -> Tuple[Dict[str, float], str]:
        formCount = len(self._forms)
        segment = int(math.floor(timeSec / self._formLenSec))
        progress = (timeSec - (segment + 1) * self._formLenSec + self._crossfadeSec) / self._crossfadeSec
        progress = min(max(progress, 0.0), 1.0) if formCount > 1 else 0.0
        progress = progress * progress * (3.0 - 2.0 * progress)
        first = self._forms[segment % formCount]
        second = self._forms[(segment + 1) % formCount]
        firstWeights = self._formWeights(first)
        secondWeights = self._formWeights(second)
        modes = list(self._liquidModule.MODES) + ["resonance"]
        weights = {
            mode: firstWeights.get(mode, 0.0) * (1.0 - progress) + secondWeights.get(mode, 0.0) * progress
            for mode in modes
        }
        return weights, first if progress < 0.5 else second

    # :: STRING -> ARRAY<STRING, FLOAT>
    # Returns owned or reference mode weights for one public form
    def _formWeights(self, form: str) -> Dict[str, float]:
        if form == "resonance":
            return {"resonance": 1.0}
        return dict(self._liquidModule.LOOKS[form])

    #
    # Class Methods
    #

    # Class Factory Method :: moduleType, [STRING], [STRING], FLOAT, FLOAT, FLOAT, FLOAT, FLOAT, FLOAT -> cameraChoreo
    # Creates an owned camera choreography adapter
    @classmethod
    def init(cls, liquidModule: ModuleType, forms: List[str], cameras: List[str], formLenSec: float, cameraLenSec: float, crossfadeSec: float, cameraSpeed: float, cameraPhaseSec: float, cameraIntensity: float) -> CameraChoreo:
        return cls(liquidModule, forms, cameras, formLenSec, cameraLenSec, crossfadeSec, cameraSpeed, cameraPhaseSec, cameraIntensity)
