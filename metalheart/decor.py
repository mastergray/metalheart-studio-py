# Independent 3D ribbon and plate geometry, skins, and audio controls

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import copy  # Expand legacy decor booleans without sharing nested defaults
import math  # Evaluate deterministic decor transforms and texture rotation
from pathlib import Path  # Load optional local-coordinate image skins
from types import ModuleType  # Type the immutable liquid3d reference module
from typing import Any, Dict, Optional, Tuple  # Type renderer state and texture coordinates

import cv2  # Decode authored ribbon and plate image skins
import numpy as np  # Evaluate decor frames, local coordinates, and texture samples

from metalheart.catalog import DEFAULT_DECOR  # Preserve the legacy decor appearance by default


# :: ARRAY<STRING, ANY>, ANY -> ARRAY<STRING, ANY>
# Deep-merges a small nested configuration without importing the resolver
def _merge(base: Dict[str, Any], override: Any) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    if not isinstance(override, dict):
        return result
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


# :: ANY -> ARRAY<STRING, ANY>
# Expands direct backend callers that still provide the legacy decor boolean
def resolveDecorConfig(value: Any) -> Dict[str, Any]:
    if isinstance(value, bool):
        return _merge(
            DEFAULT_DECOR,
            {
                "enabled": value,
                "ribbons": {"enabled": value},
                "plates": {"enabled": value},
            },
        )
    return _merge(DEFAULT_DECOR, value)


# Samples and lights one local-coordinate decor image
class DecorTexture:

    # CONSTRUCTOR :: ARRAY<STRING, ANY>, STRING -> decorTexture
    # Loads an optional image and stores its deterministic sampling treatment
    def __init__(self, config: Dict[str, Any], material: str) -> None:
        self._material = material
        self._scale = float(config["scale"])
        self._rotation = math.radians(float(config["rotation_deg"]))
        self._sampling = str(config["sampling"])
        self._texelSteps = int(config["texel_steps"])
        self._lightingSteps = int(config["lighting_steps"])
        self._texture: Optional[np.ndarray] = None
        imagePath = config.get("image")
        if imagePath:
            texture = cv2.imread(str(Path(imagePath)), cv2.IMREAD_COLOR)
            if texture is None:
                raise ValueError("unable to decode decor image: {0}".format(imagePath))
            self._texture = cv2.cvtColor(texture, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

    #
    # Properties
    #

    # PROPERTY :: VOID -> BOOL
    # Reports whether the reference metallic shader can pass through unchanged
    @property
    def isDefault(self) -> bool:
        return self._texture is None and self._material == "metallic"

    #
    # Instance Methods
    #

    # :: ANY, ANY, ANY -> ANY
    # Applies local image color or a matte treatment over reference illumination
    def shade(self, chrome: Any, horizontal: Any, vertical: Any) -> Any:
        if self.isDefault:
            return chrome
        luminance = chrome @ np.asarray([0.2126, 0.7152, 0.0722], np.float32)
        if self._texture is None:
            light = self._quantize(np.clip(luminance, 0.0, 1.0), 1.0)
            return np.clip(chrome, 0.0, 1.0) * (0.48 + 0.38 * light[:, None])
        texture = self._sample(horizontal, vertical)
        if self._material == "matte":
            light = self._quantize(np.clip(luminance, 0.0, 1.0), 1.0)
            return texture * (0.38 + 0.52 * light[:, None])
        reflection = self._quantize(np.clip(luminance, 0.0, 1.2), 1.2)
        base = texture * (0.2 + 0.75 * reflection)[:, None]
        highlight = self._quantize(np.clip((luminance - 0.52) * 1.8, 0.0, 1.1), 1.1)
        return base + highlight[:, None] * 0.65

    #
    # Protected Methods
    #

    # :: ANY, ANY -> ANY
    # Samples a repeating rotated image in ribbon- or plate-local coordinates
    def _sample(self, horizontal: Any, vertical: Any) -> Any:
        if self._texture is None:
            raise RuntimeError("decor texture is unavailable")
        centeredX = horizontal - 0.5
        centeredY = vertical - 0.5
        cosine = math.cos(self._rotation)
        sine = math.sin(self._rotation)
        normalizedX = np.mod((centeredX * cosine - centeredY * sine) * self._scale + 0.5, 1.0)
        normalizedY = np.mod((centeredX * sine + centeredY * cosine) * self._scale + 0.5, 1.0)
        if self._texelSteps:
            normalizedX = (np.floor(normalizedX * self._texelSteps) + 0.5) / self._texelSteps
            normalizedY = (np.floor(normalizedY * self._texelSteps) + 0.5) / self._texelSteps
        height, width = self._texture.shape[:2]
        mapX = normalizedX * width
        mapY = normalizedY * height
        firstX = np.floor(mapX).astype(np.int32) % width
        firstY = np.floor(mapY).astype(np.int32) % height
        if self._sampling == "nearest":
            return self._texture[firstY, firstX]
        secondX = (firstX + 1) % width
        secondY = (firstY + 1) % height
        fractionX = (mapX - np.floor(mapX))[:, None]
        fractionY = (mapY - np.floor(mapY))[:, None]
        top = self._texture[firstY, firstX] * (1.0 - fractionX) + self._texture[firstY, secondX] * fractionX
        bottom = self._texture[secondY, firstX] * (1.0 - fractionX) + self._texture[secondY, secondX] * fractionX
        return top * (1.0 - fractionY) + bottom * fractionY

    # :: ANY, FLOAT -> ANY
    # Reduces illumination to configured stable bands
    def _quantize(self, values: Any, maximum: float) -> Any:
        if self._lightingSteps == 0:
            return values
        intervals = float(self._lightingSteps - 1)
        return np.round(np.clip(values / maximum, 0.0, 1.0) * intervals) * maximum / intervals

    #
    # Class Methods
    #

    # Class Factory Method :: ARRAY<STRING, ANY>, STRING -> decorTexture
    # Creates a local-coordinate decor texture
    @classmethod
    def init(cls, config: Dict[str, Any], material: str) -> DecorTexture:
        return cls(config, material)


# Replaces reference 3D decor construction while delegating its stable SDFs
class DecorController:

    # CONSTRUCTOR :: moduleType, ANY, ARRAY<STRING, ANY>, INT -> decorController
    # Builds deterministic independent decor sets and installs optional skin shading
    def __init__(self, liquidModule: ModuleType, coreRenderer: Any, config: Dict[str, Any], seed: int) -> None:
        self._liquidModule = liquidModule
        self._renderer = coreRenderer
        self._config = config
        self._signals: Dict[str, float] = {}
        ribbonConfig = config["ribbons"]
        plateConfig = config["plates"]
        ribbonCount = int(ribbonConfig["count"]) if ribbonConfig["enabled"] else 0
        plateCount = int(plateConfig["count"]) if plateConfig["enabled"] else 0
        decorSeed = int(config["seed"]) if config["seed"] is not None else seed
        self._decor = liquidModule.Decor3D(decorSeed, n_ribbons=ribbonCount, n_plates=plateCount)
        self._ribbonTexture = DecorTexture.init(ribbonConfig["surface"], ribbonConfig["material"])
        self._plateTexture = DecorTexture.init(plateConfig["surface"], plateConfig["material"])
        self._baseShade = coreRenderer._shade
        setattr(self, "sdf_parts", self.sdfParts)
        coreRenderer.decor = self
        if not self._ribbonTexture.isDefault or not self._plateTexture.isDefault:
            coreRenderer._shade = self.shade

    #
    # Instance Methods
    #

    # :: ARRAY<STRING, FLOAT> -> NONE
    # Stores the current bounded decor-only audio destinations
    def setSignals(self, signals: Dict[str, float]) -> None:
        self._signals = signals

    # :: FLOAT, ANY -> ARRAY<STRING, ANY>
    # Produces one decor frame with explicit or backward-compatible audio response
    def frame(self, timeSec: float, params: Any) -> Dict[str, Any]:
        ribbons = []
        width = self._signal("ribbon_width", 0.35 * float(params.bass), -0.5, 1.5)
        twist = self._signal("ribbon_twist", 1.2 * float(params.mid), -0.8, 3.0)
        wave = self._signal("ribbon_wave", 0.0, -0.5, 1.5)
        speed = self._signal("ribbon_speed", 0.0, -0.9, 3.0)
        for ribbon in self._decor.ribbons:
            rotation = self._liquidModule._rotmat(*(ribbon["eul"] + ribbon["spin"] * timeSec))
            amplitudeY = ribbon["A"] * (1.0 + wave)
            amplitudeZ = ribbon["B"] * (1.0 + wave)
            widthNow = ribbon["w"] * (1.0 + width)
            lip = (
                math.sqrt(
                    1.0
                    + (amplitudeY * ribbon["f"]) ** 2
                    + (amplitudeZ * 0.63 * ribbon["f"]) ** 2
                )
                + abs(ribbon["k"]) * widthNow
            )
            ribbons.append(
                dict(
                    ribbon,
                    R=rotation,
                    A=amplitudeY,
                    B=amplitudeZ,
                    t1=timeSec * ribbon["sp"] * (1.0 + speed) + ribbon["ph"],
                    t2=timeSec * ribbon["ks"] * (1.0 + twist),
                    w_now=widthNow,
                    lip=lip,
                    rad=ribbon["L"] + amplitudeY + amplitudeZ + widthNow * 2.0,
                )
            )
        plates = []
        orbit = self._signal("plate_orbit", 0.0, -0.9, 3.0)
        displacement = self._signal("plate_displacement", 0.06 * float(params.bass), -0.4, 0.4)
        for plate in self._decor.plates:
            angle = plate["orbit"] * timeSec * (1.0 + orbit)
            orbitRotation = np.asarray(
                [
                    [math.cos(angle), 0.0, math.sin(angle)],
                    [0.0, 1.0, 0.0],
                    [-math.sin(angle), 0.0, math.cos(angle)],
                ],
                np.float32,
            )
            center = (orbitRotation @ plate["c"]) * (1.0 + displacement)
            plates.append(
                dict(
                    plate,
                    R=self._liquidModule._rotmat(*(plate["eul"] + plate["spin"] * timeSec)),
                    c_now=center,
                    rad=math.sqrt(plate["hx"] ** 2 + plate["hy"] ** 2 + plate["hz"] ** 2) + 0.02,
                )
            )
        return {"ribbons": ribbons, "plates": plates}

    # :: ANY, ANY, ANY, ARRAY<STRING, ANY> -> (ANY, ANY)
    # Delegates distance evaluation to the immutable reference decor SDFs
    def sdfParts(self, x: Any, y: Any, z: Any, frame: Dict[str, Any]) -> Tuple[Any, Any]:
        return self._decor.sdf_parts(x, y, z, frame)

    # :: ANY, ANY, ANY, ANY, ANY, ANY, ARRAY<STRING, ANY> -> ANY
    # Replaces only ribbon and plate colors with their own local-coordinate surfaces
    def shade(
        self,
        eye: Any,
        rayX: Any,
        rayY: Any,
        rayZ: Any,
        distance: Any,
        coreFrame: Any,
        decorFrame: Dict[str, Any],
    ) -> Any:
        chrome = self._baseShade(eye, rayX, rayY, rayZ, distance, coreFrame, decorFrame)
        pointX = eye[0] + rayX * distance
        pointY = eye[1] + rayY * distance
        pointZ = eye[2] + rayZ * distance
        coreDistance = self._renderer.core.sdf(pointX, pointY, pointZ, coreFrame)
        ribbonDistance, plateDistance = self.sdfParts(pointX, pointY, pointZ, decorFrame)
        material = np.argmin(np.stack([coreDistance, ribbonDistance, plateDistance]), axis=0)
        output = chrome.copy()
        if decorFrame["ribbons"] and not self._ribbonTexture.isDefault:
            self._shadeRibbons(output, chrome, material, pointX, pointY, pointZ, decorFrame)
        if decorFrame["plates"] and not self._plateTexture.isDefault:
            self._shadePlates(output, chrome, material, pointX, pointY, pointZ, decorFrame)
        return output

    #
    # Protected Methods
    #

    # :: STRING, FLOAT, FLOAT, FLOAT -> FLOAT
    # Reads a present explicit destination or falls back to reference audio behavior
    def _signal(self, name: str, fallback: float, minimum: float, maximum: float) -> float:
        value = float(self._signals[name]) if name in self._signals else fallback
        return min(max(value, minimum), maximum)

    # :: ANY, ANY, ANY, ANY, ANY, ANY, ARRAY<STRING, ANY> -> NONE
    # Shades each ribbon hit from longitudinal and twisted-width coordinates
    def _shadeRibbons(
        self,
        output: Any,
        chrome: Any,
        material: Any,
        pointX: Any,
        pointY: Any,
        pointZ: Any,
        decorFrame: Dict[str, Any],
    ) -> None:
        distances = np.stack(
            [self._decor._ribbon(pointX, pointY, pointZ, ribbon) for ribbon in decorFrame["ribbons"]],
            axis=0,
        )
        nearest = np.argmin(distances, axis=0)
        for index, ribbon in enumerate(decorFrame["ribbons"]):
            mask = (material == 1) & (nearest == index)
            if not np.any(mask):
                continue
            horizontal, vertical = self._ribbonCoordinates(
                pointX[mask],
                pointY[mask],
                pointZ[mask],
                ribbon,
            )
            output[mask] = self._ribbonTexture.shade(chrome[mask], horizontal, vertical)

    # :: ANY, ANY, ANY, ANY -> (ANY, ANY)
    # Converts world hits into coordinates that bend and twist with a ribbon
    def _ribbonCoordinates(self, pointX: Any, pointY: Any, pointZ: Any, ribbon: Dict[str, Any]) -> Tuple[Any, Any]:
        localX, localY, localZ = self._liquidModule._local(
            pointX,
            pointY,
            pointZ,
            ribbon["R"],
            ribbon["c"],
        )
        centerY = ribbon["A"] * np.sin(ribbon["f"] * localX + ribbon["t1"])
        centerZ = ribbon["B"] * np.sin(0.63 * ribbon["f"] * localX + ribbon["t1"] * 0.7 + 1.3)
        twist = ribbon["k"] * localX + ribbon["t2"]
        across = (localY - centerY) * np.cos(twist) + (localZ - centerZ) * np.sin(twist)
        horizontal = localX / (2.0 * ribbon["L"]) + 0.5
        vertical = across / (2.0 * ribbon["w_now"] + 1e-9) + 0.5
        return horizontal, vertical

    # :: ANY, ANY, ANY, ANY, ANY, ANY, ARRAY<STRING, ANY> -> NONE
    # Shades each plate hit from its stable planar local coordinates
    def _shadePlates(
        self,
        output: Any,
        chrome: Any,
        material: Any,
        pointX: Any,
        pointY: Any,
        pointZ: Any,
        decorFrame: Dict[str, Any],
    ) -> None:
        distances = np.stack(
            [self._decor._plate(pointX, pointY, pointZ, plate) for plate in decorFrame["plates"]],
            axis=0,
        )
        nearest = np.argmin(distances, axis=0)
        for index, plate in enumerate(decorFrame["plates"]):
            mask = (material == 2) & (nearest == index)
            if not np.any(mask):
                continue
            localX, localY, localZ = self._liquidModule._local(
                pointX[mask],
                pointY[mask],
                pointZ[mask],
                plate["R"],
                plate["c_now"],
            )
            del localZ
            horizontal = localX / (2.0 * plate["hx"]) + 0.5
            vertical = localY / (2.0 * plate["hy"]) + 0.5
            output[mask] = self._plateTexture.shade(chrome[mask], horizontal, vertical)

    #
    # Class Methods
    #

    # Class Factory Method :: moduleType, ANY, ARRAY<STRING, ANY>, INT -> decorController
    # Creates an independently configurable 3D decor controller
    @classmethod
    def init(
        cls,
        liquidModule: ModuleType,
        coreRenderer: Any,
        config: Dict[str, Any],
        seed: int,
    ) -> DecorController:
        return cls(liquidModule, coreRenderer, config, seed)
