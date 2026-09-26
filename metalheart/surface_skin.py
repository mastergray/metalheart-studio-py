# Object-space image skinning for the immutable 3D reference renderer

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import math  # Rotate object-space texture coordinates
from typing import Any, Dict, Tuple  # Type renderer, configuration, and computed normals

import cv2  # Load and bilinearly sample authored image skins
import numpy as np  # Blend triplanar samples across raymarched surface normals


# Applies a seamless image tint to core hits while retaining reference chrome lighting
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
        self._strength = float(config["strength"])

    #
    # Instance Methods
    #

    # :: ANY, ANY, ANY, ANY, ANY, ANY, ANY -> ANY
    # Shades reference chrome, then tints only core hits with triplanar image samples
    def shade(self, eye: Any, rayX: Any, rayY: Any, rayZ: Any, distance: Any, frame: Any, decor: Any) -> Any:
        chrome = self._baseShade(eye, rayX, rayY, rayZ, distance, frame, decor)
        pointX = eye[0] + rayX * distance
        pointY = eye[1] + rayY * distance
        pointZ = eye[2] + rayZ * distance
        normalX, normalY, normalZ = self._normals(pointX, pointY, pointZ, frame, decor)
        texture = self._triplanar(pointX, pointY, pointZ, normalX, normalY, normalZ)
        tinted = chrome * (0.3 + 1.05 * texture)
        mixed = chrome * (1.0 - self._strength) + tinted * self._strength
        if decor is None:
            return mixed
        coreDistance = self._renderer.core.sdf(pointX, pointY, pointZ, frame)
        ribbonDistance, plateDistance = self._renderer.decor.sdf_parts(pointX, pointY, pointZ, decor)
        material = np.argmin(np.stack([coreDistance, ribbonDistance, plateDistance]), axis=0)
        return np.where((material == 0)[:, None], mixed, chrome)

    #
    # Protected Methods
    #

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
    # Samples one repeating planar projection with bilinear filtering
    def _sample(self, horizontal: Any, vertical: Any) -> Any:
        height, width = self._texture.shape[:2]
        mapX = np.mod(horizontal * self._scale + 0.5, 1.0) * width
        mapY = np.mod(vertical * self._scale + 0.5, 1.0) * height
        firstX = np.floor(mapX).astype(np.int32) % width
        firstY = np.floor(mapY).astype(np.int32) % height
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
