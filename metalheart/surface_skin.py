# Object-space image skinning for the immutable 3D reference renderer

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import math  # Rotate object-space texture coordinates
from typing import Any, Dict, Tuple  # Type renderer, configuration, and computed normals

import cv2  # Load authored image skins
import numpy as np  # Blend triplanar samples across raymarched surface normals


# Replaces core palette color with a seamless image under metallic or matte lighting
class SurfaceSkin:

    # CONSTRUCTOR :: ANY, ARRAY<STRING, ANY> -> surfaceSkin
    # Loads one image and captures the renderer's original shader
    def __init__(self, coreRenderer: Any, config: Dict[str, Any]) -> None:
        imagePath = str(config["image"])
        texture = cv2.imread(imagePath, cv2.IMREAD_COLOR)
        if texture is None:
            raise ValueError("unable to decode surface image: {0}".format(imagePath))
        self._renderer = coreRenderer
        self._baseShade = coreRenderer._shade
        self._texture = cv2.cvtColor(texture, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        self._scale = float(config["scale"])
        self._rotation = math.radians(float(config["rotation_deg"]))
        self._material = str(config["material"])
        self._sampling = str(config.get("sampling", "bilinear"))
        self._texelSteps = int(config.get("texel_steps", 0))
        self._lightingSteps = int(config.get("lighting_steps", 0))

    #
    # Instance Methods
    #

    # :: ANY, ANY, ANY, ANY, ANY, ANY, ANY -> ANY
    # Shades reference geometry, then replaces core color with triplanar image samples
    def shade(self, eye: Any, rayX: Any, rayY: Any, rayZ: Any, distance: Any, frame: Any, decor: Any) -> Any:
        chrome = self._baseShade(eye, rayX, rayY, rayZ, distance, frame, decor)
        pointX = eye[0] + rayX * distance
        pointY = eye[1] + rayY * distance
        pointZ = eye[2] + rayZ * distance
        normalX, normalY, normalZ = self._normals(pointX, pointY, pointZ, frame, decor)
        texture = self._triplanar(pointX, pointY, pointZ, normalX, normalY, normalZ)
        skinned = self._applyMaterial(chrome, texture)
        if decor is None:
            return skinned
        coreDistance = self._renderer.core.sdf(pointX, pointY, pointZ, frame)
        ribbonDistance, plateDistance = self._renderer.decor.sdf_parts(pointX, pointY, pointZ, decor)
        material = np.argmin(np.stack([coreDistance, ribbonDistance, plateDistance]), axis=0)
        return np.where((material == 0)[:, None], skinned, chrome)

    #
    # Protected Methods
    #

    # :: ANY, ANY -> ANY
    # Uses palette shading as neutral light while the image supplies all base color
    def _applyMaterial(self, chrome: Any, texture: Any) -> Any:
        luminance = chrome @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        if self._material == "matte":
            light = self._quantize(np.clip(luminance, 0.0, 1.0), 1.0, self._lightingSteps)
            diffuse = 0.38 + 0.52 * light
            return texture * diffuse[:, None]
        reflection = self._quantize(np.clip(luminance, 0.0, 1.2), 1.2, self._lightingSteps)
        base = texture * (0.2 + 0.75 * reflection)[:, None]
        highlight = np.clip((luminance - 0.52) * 1.8, 0.0, 1.1)
        highlight = self._quantize(highlight, 1.1, self._lightingSteps)
        return base + highlight[:, None] * 0.65

    # :: ANY, FLOAT, INTEGER -> ANY
    # Reduces a bounded scalar field to a fixed number of stable levels
    def _quantize(self, values: Any, maximum: float, steps: int) -> Any:
        if steps == 0:
            return values
        intervals = float(steps - 1)
        return np.round(np.clip(values / maximum, 0.0, 1.0) * intervals) * maximum / intervals

    # :: ANY, ANY, ANY, ANY, ANY -> (ANY, ANY, ANY)
    # Reconstructs surface normals using the reference tetrahedral estimator
    def _normals(self, pointX: Any, pointY: Any, pointZ: Any, frame: Any, decor: Any) -> Tuple[Any, Any, Any]:
        epsilon = 0.0016
        first = self._renderer.scene(pointX + epsilon, pointY - epsilon, pointZ - epsilon, frame, decor)
        second = self._renderer.scene(pointX - epsilon, pointY - epsilon, pointZ + epsilon, frame, decor)
        third = self._renderer.scene(pointX - epsilon, pointY + epsilon, pointZ - epsilon, frame, decor)
        fourth = self._renderer.scene(pointX + epsilon, pointY + epsilon, pointZ + epsilon, frame, decor)
        normalX = first - second - third + fourth
        normalY = -first - second + third + fourth
        normalZ = -first + second - third + fourth
        inverseLength = 1.0 / (np.sqrt(normalX * normalX + normalY * normalY + normalZ * normalZ) + 1e-9)
        return normalX * inverseLength, normalY * inverseLength, normalZ * inverseLength

    # :: ANY, ANY, ANY, ANY, ANY, ANY -> ANY
    # Blends three wrapped planar projections by the dominant surface normal
    def _triplanar(self, pointX: Any, pointY: Any, pointZ: Any, normalX: Any, normalY: Any, normalZ: Any) -> Any:
        cosine = math.cos(self._rotation)
        sine = math.sin(self._rotation)
        rotatedX = pointX * cosine - pointZ * sine
        rotatedZ = pointX * sine + pointZ * cosine
        xProjection = self._sample(rotatedZ, pointY)
        yProjection = self._sample(rotatedX, rotatedZ)
        zProjection = self._sample(rotatedX, pointY)
        weights = np.stack([np.abs(normalX), np.abs(normalY), np.abs(normalZ)], axis=1) ** 4
        weights /= np.maximum(weights.sum(axis=1, keepdims=True), 1e-9)
        return (
            xProjection * weights[:, 0:1]
            + yProjection * weights[:, 1:2]
            + zProjection * weights[:, 2:3]
        )

    # :: ANY, ANY -> ANY
    # Samples one repeating planar projection with configurable stable quantization
    def _sample(self, horizontal: Any, vertical: Any) -> Any:
        height, width = self._texture.shape[:2]
        normalizedX = np.mod(horizontal * self._scale + 0.5, 1.0)
        normalizedY = np.mod(vertical * self._scale + 0.5, 1.0)
        if self._texelSteps:
            normalizedX = (np.floor(normalizedX * self._texelSteps) + 0.5) / self._texelSteps
            normalizedY = (np.floor(normalizedY * self._texelSteps) + 0.5) / self._texelSteps
        mapX = normalizedX * width
        mapY = normalizedY * height
        firstX = np.floor(mapX).astype(np.int32) % width
        firstY = np.floor(mapY).astype(np.int32) % height
        if self._sampling == "nearest":
            return self._texture[firstY, firstX]
        secondX = (firstX + 1) % width
        secondY = (firstY + 1) % height
        fractionX = (mapX - np.floor(mapX)).reshape(-1, 1)
        fractionY = (mapY - np.floor(mapY)).reshape(-1, 1)
        top = self._texture[firstY, firstX] * (1.0 - fractionX) + self._texture[firstY, secondX] * fractionX
        bottom = self._texture[secondY, firstX] * (1.0 - fractionX) + self._texture[secondY, secondX] * fractionX
        return top * (1.0 - fractionY) + bottom * fractionY

    #
    # Class Methods
    #

    # Class Factory Method :: ANY, ARRAY<STRING, ANY> -> surfaceSkin
    # Creates a loaded triplanar skin shader
    @classmethod
    def init(cls, coreRenderer: Any, config: Dict[str, Any]) -> SurfaceSkin:
        return cls(coreRenderer, config)
