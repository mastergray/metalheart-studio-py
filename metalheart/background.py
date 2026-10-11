# Configurable image and palette backgrounds for captured 3D foregrounds

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import copy  # Compare inherited palette defaults without mutating shared catalog data
import math  # Rotate normalized background coordinates
from typing import Any, Dict, Optional, Tuple  # Type renderer state and captured foregrounds

import cv2  # Fit, transform, blur, and composite background imagery
import numpy as np  # Evaluate procedural backgrounds and alpha composition

from metalheart.catalog import DEFAULT_BACKGROUND  # Detect the unchanged reference background contract
from metalheart.effects import EffectChain  # Apply a scoped chain before foreground composition
from metalheart.layer_effects import LayerEffects  # Process captured form and ribbon materials


# :: FLOAT, FLOAT, ANY -> ANY
# Evaluates the reference background's stable smoothstep curve
def _smoothstep(edge0: float, edge1: float, value: Any) -> Any:
    amount = np.clip((value - edge0) / (edge1 - edge0 + 1e-9), 0.0, 1.0)
    return amount * amount * (3.0 - 2.0 * amount)


# Rebuilds the 3D composition around an authored background before finishing
class BackgroundPass:

    # CONSTRUCTOR :: ANY, ARRAY<STRING, ANY>, effectChain?, layerEffects?, ARRAY<STRING, ANY>? -> backgroundPass
    # Loads an optional image and prepares foreground capture
    def __init__(
        self,
        renderer: Any,
        config: Dict[str, Any],
        backgroundEffects: Optional[EffectChain] = None,
        layerEffects: Optional[LayerEffects] = None,
        palette: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._renderer = renderer
        self._config = config
        self._signals: Dict[str, float] = {}
        self._effectSignals: Dict[str, Any] = {}
        self._frameIndex: Optional[int] = None
        self._foreground: Optional[Tuple[Any, Any, Any]] = None
        self._baseCoreRender: Optional[Any] = None
        self._backgroundEffects = backgroundEffects
        self._layerEffects = layerEffects
        self._paletteValues = palette or getattr(renderer, "pal", {})
        comparison = copy.deepcopy(config)
        default = copy.deepcopy(DEFAULT_BACKGROUND)
        comparison["palette"] = None
        default["palette"] = None
        self._custom = (
            config["source"] == "palette"
            or comparison != default
            or self._paletteValues != getattr(renderer, "pal", self._paletteValues)
        )
        self._texture: Optional[np.ndarray] = None
        imagePath = config.get("image")
        if config["source"] == "image" and imagePath:
            texture = cv2.imread(str(imagePath), cv2.IMREAD_COLOR)
            if texture is None:
                raise ValueError("unable to decode background image: {0}".format(imagePath))
            self._texture = cv2.cvtColor(texture, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        if hasattr(renderer, "core3d"):
            self._baseCoreRender = renderer.core3d.render
            renderer.core3d.render = self._captureCoreRender

    #
    # Instance Methods
    #

    # :: ARRAY<STRING, FLOAT> -> NONE
    # Stores the current bounded background-only audio controls
    def setSignals(self, signals: Dict[str, float]) -> None:
        self._signals = signals

    # :: INT?, ARRAY<STRING, ANY> -> NONE
    # Stores frame-local post-filter timing and audio signals before rendering
    def setEffectContext(self, frameIndex: Optional[int], signals: Dict[str, Any]) -> None:
        self._frameIndex = frameIndex
        self._effectSignals = signals

    # :: ANY, FLOAT, ANY -> ANY
    # Replaces only the background while retaining captured foreground and HUD layers
    def apply(self, referenceImage: Any, timeSec: float, params: Any) -> Any:
        bass = min(max(float(getattr(params, "bass", 0.0)), 0.0), 1.0)
        pulse = min(max(float(self._signals.get("background_pulse", 0.05 * bass)), 0.0), 1.0)
        if (
            not self._custom
            and pulse <= 0.0
            and self._backgroundEffects is None
            and self._layerEffects is None
        ):
            return referenceImage
        if self._foreground is None:
            return referenceImage
        foreground, alpha, focus = self._foreground
        horizontal, vertical = self._coordinates(pulse)
        surface = self._rippleSurface(timeSec, params)
        if surface is not None:
            horizontal = horizontal + surface[0]
            vertical = vertical + surface[1]
        background = self._palette(timeSec, horizontal, vertical)
        if self._texture is not None:
            image, imageAlpha = self._image(horizontal, vertical)
            opacity = float(self._config["opacity"]) * imageAlpha[..., None]
            background = background * (1.0 - opacity) + image * opacity
        if surface is not None:
            background = self._lightSurface(background, surface[2], surface[3], surface[4])
        if self._config["dots"]:
            background = background + self._renderer.dots[..., None] * np.asarray(
                self._paletteValues["hud"], np.float32
            ) * 0.05
        background *= 1.0 + pulse * float(self._config["pulse_brightness"])
        if self._config["ghosts"]:
            background = self._ghosts(background, foreground * alpha[..., None], alpha)
        if self._config["shadow"]:
            background = self._shadow(background, alpha)
        if self._backgroundEffects is not None:
            backgroundRgb = np.clip(background * 255.0, 0.0, 255.0).astype(np.uint8)
            backgroundBgr = cv2.cvtColor(backgroundRgb, cv2.COLOR_RGB2BGR)
            backgroundBgr = self._backgroundEffects.apply(
                backgroundBgr,
                timeSec,
                self._frameIndex,
                self._effectSignals,
            )
            background = cv2.cvtColor(backgroundBgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        if self._layerEffects is not None:
            foreground, alpha = self._layerEffects.apply(
                foreground,
                alpha,
                timeSec,
                self._frameIndex,
                self._effectSignals,
            )
        alphaLayer = alpha[..., None]
        image = background * (1.0 - alphaLayer) + foreground * alphaLayer
        hudColor, hudAlpha = self._renderer.hud(timeSec, params, focus)
        glow = cv2.GaussianBlur(
            hudColor * hudAlpha,
            (0, 0),
            max(1.0, self._renderer.H * 0.004),
        )
        return image * (1.0 - hudAlpha) + hudColor * hudAlpha + glow * 0.55

    #
    # Protected Methods
    #

    # :: *ANY, **ANY -> ANY
    # Captures the already-rendered foreground without tracing it a second time
    def _captureCoreRender(self, *arguments: Any, **keywords: Any) -> Any:
        if self._baseCoreRender is None:
            raise RuntimeError("background foreground capture is unavailable")
        result = self._baseCoreRender(*arguments, **keywords)
        self._foreground = (result[0], result[1], result[2])
        return result

    # :: FLOAT, FLOAT -> (ANY, ANY)
    # Produces centered normalized sampling coordinates with authored pulse zoom
    def _coordinates(self, pulse: float) -> Tuple[Any, Any]:
        width = self._renderer.W
        height = self._renderer.H
        center = self._config["pulse_center"]
        pivotX = (float(center[0]) * width - width / 2.0) / height
        pivotY = float(center[1]) - 0.5
        zoom = 1.0 + pulse * float(self._config["pulse_scale"])
        horizontal = pivotX + (self._renderer.u - pivotX) / zoom
        vertical = pivotY + (self._renderer.v - pivotY) / zoom
        offset = self._config["offset"]
        horizontal -= float(offset[0]) * width / height
        vertical -= float(offset[1])
        scale = float(self._config["scale"])
        horizontal /= scale
        vertical /= scale
        rotation = math.radians(float(self._config["rotation_deg"]))
        cosine = math.cos(rotation)
        sine = math.sin(rotation)
        return horizontal * cosine + vertical * sine, -horizontal * sine + vertical * cosine

    # :: FLOAT, ANY, ANY -> ANY
    # Recreates the reference palette gradient and moving nebula without foreground effects
    def _palette(self, timeSec: float, horizontal: Any, vertical: Any) -> Any:
        radius = np.sqrt(horizontal * horizontal + (vertical * 1.3) ** 2)
        gradient = _smoothstep(0.0, 0.95, radius)[..., None]
        palette = self._paletteValues
        sky = np.asarray(palette["sky_top"], np.float32)
        accent = np.asarray(palette["accent"], np.float32)
        center = (
            np.asarray(palette["bg_center"], np.float32) * 1.8
            + sky * 0.08
            + accent * 0.04
        )
        edge = (
            np.asarray(palette["bg_edge"], np.float32) * 1.5
            + sky * 0.05
            + accent * 0.02
        )
        background = center * (1.0 - gradient) + edge * gradient
        nebula = self._renderer.noise.sample(
            0,
            horizontal * 180.0 + timeSec * 4.0,
            vertical * 180.0 - timeSec * 2.0,
        )
        intensity = float(self._config.get("intensity", 1.0))
        return (
            background
            * (0.75 + 0.3 * np.clip(nebula, -1.0, 2.0)[..., None])
            * intensity
        )

    # :: ANY, ANY -> (ANY, ANY)
    # Samples the configured image with cover, contain, or repeating tile behavior
    def _image(self, horizontal: Any, vertical: Any) -> Tuple[Any, Any]:
        if self._texture is None:
            raise RuntimeError("background image is unavailable")
        sourceHeight, sourceWidth = self._texture.shape[:2]
        outputHeight = self._renderer.H
        outputWidth = self._renderer.W
        if self._config["fit"] == "cover":
            fitScale = max(outputWidth / sourceWidth, outputHeight / sourceHeight)
            borderMode = cv2.BORDER_REFLECT_101
        elif self._config["fit"] == "contain":
            fitScale = min(outputWidth / sourceWidth, outputHeight / sourceHeight)
            borderMode = cv2.BORDER_CONSTANT
        else:
            fitScale = min(outputWidth / sourceWidth, outputHeight / sourceHeight)
            borderMode = cv2.BORDER_WRAP
        mapX = sourceWidth / 2.0 + horizontal * outputHeight / fitScale
        mapY = sourceHeight / 2.0 + vertical * outputHeight / fitScale
        image = cv2.remap(
            self._texture,
            mapX.astype(np.float32),
            mapY.astype(np.float32),
            cv2.INTER_LINEAR,
            borderMode=borderMode,
        )
        if self._config["fit"] != "contain":
            return image, np.ones((outputHeight, outputWidth), np.float32)
        mask = cv2.remap(
            np.ones((sourceHeight, sourceWidth), np.float32),
            mapX.astype(np.float32),
            mapY.astype(np.float32),
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
        )
        return image, np.clip(mask, 0.0, 1.0)

    # :: FLOAT, ANY -> (ANY, ANY, ANY, ANY, ANY)?
    # Builds spectrum-directed displacement and reconstructed sheet normals
    def _rippleSurface(self, timeSec: float, params: Any) -> Optional[Tuple[Any, Any, Any, Any, Any]]:
        ripple = self._config["ripple"]
        material = self._config["material"]
        if not ripple["enabled"] and material == "flat":
            return None
        bass = min(max(float(getattr(params, "bass", 0.0)), 0.0), 1.0)
        mid = min(max(float(getattr(params, "mid", 0.0)), 0.0), 1.0)
        high = min(max(float(getattr(params, "high", 0.0)), 0.0), 1.0)
        onset = min(max(float(getattr(params, "onset", 0.0)), 0.0), 1.0)
        amplitude = (bass + mid + high) / 3.0
        amountSignal = min(
            max(float(self._signals.get("background_ripple", 0.7 * amplitude)), 0.0),
            1.0,
        )
        impactSignal = min(
            max(float(self._signals.get("background_ripple_impact", 0.35 * onset)), 0.0),
            1.0,
        )
        scaleSignal = min(
            max(float(self._signals.get("background_ripple_scale", 0.25 + 0.6 * high)), 0.0),
            1.0,
        )
        horizontal = self._renderer.u
        vertical = self._renderer.v
        height = np.zeros_like(horizontal, np.float32)
        amount = float(ripple["amount"])
        scale = float(ripple["scale"]) * (0.75 + 0.5 * scaleSignal)
        travel = float(ripple["travel_speed"])
        if ripple["enabled"] and amountSignal > 0.0:
            bands = self._spectrumBands(params, 8)
            normalization = max(float(np.sqrt(np.sum(bands * bands))), 1.0)
            for index, energy in enumerate(bands):
                position = index / max(len(bands) - 1, 1)
                angle = index * math.pi * (3.0 - math.sqrt(5.0))
                direction = horizontal * math.cos(angle) + vertical * math.sin(angle)
                frequency = scale * (0.55 + 1.45 * position)
                phase = (
                    direction * math.tau * frequency
                    - timeSec * math.tau * travel * (0.35 + 0.65 * position)
                    + index * 0.73
                )
                height += np.sin(phase).astype(np.float32) * float(energy)
            height *= amount * amountSignal / normalization
            height += (
                np.sin(
                    (horizontal * 0.8 + vertical * 0.35) * math.tau * scale * 0.45
                    - timeSec * math.tau * travel * 0.3
                ).astype(np.float32)
                * amount
                * amountSignal
                * bass
                * 0.3
            )
        if ripple["enabled"] and impactSignal > 0.0:
            center = self._config["pulse_center"]
            centerX = (float(center[0]) * self._renderer.W - self._renderer.W / 2.0) / self._renderer.H
            centerY = float(center[1]) - 0.5
            radius = np.sqrt((horizontal - centerX) ** 2 + (vertical - centerY) ** 2)
            height += (
                np.sin(
                    radius * math.tau * scale * 1.4
                    - timeSec * math.tau * max(travel, 0.05) * 1.8
                ).astype(np.float32)
                * amount
                * impactSignal
                * 0.8
            )
        gradientX = cv2.Sobel(height, cv2.CV_32F, 1, 0, ksize=3) * self._renderer.H / 8.0
        gradientY = cv2.Sobel(height, cv2.CV_32F, 0, 1, ksize=3) * self._renderer.H / 8.0
        inverseLength = 1.0 / np.sqrt(gradientX * gradientX + gradientY * gradientY + 1.0)
        normalX = -gradientX * inverseLength
        normalY = -gradientY * inverseLength
        normalZ = inverseLength
        warp = float(ripple["warp"])
        return normalX * warp, normalY * warp, normalX, normalY, normalZ

    # :: ANY, INT -> ANY
    # Reduces the live spectrum to directional sheet-wave weights
    def _spectrumBands(self, params: Any, count: int) -> Any:
        spectrum = np.asarray(getattr(params, "spectrum", []), np.float32).reshape(-1)
        if spectrum.size == 0:
            spectrum = np.asarray(
                [
                    getattr(params, "bass", 0.0),
                    getattr(params, "mid", 0.0),
                    getattr(params, "high", 0.0),
                ],
                np.float32,
            )
        bands = np.interp(
            np.linspace(0.0, spectrum.size - 1, count),
            np.arange(spectrum.size),
            spectrum,
        ).astype(np.float32)
        peak = max(float(np.max(np.abs(bands))), 1e-6)
        return np.clip(bands / peak, 0.0, 1.0)

    # :: ANY, ANY, ANY, ANY -> ANY
    # Relights displaced albedo with neutral matte or metallic illumination
    def _lightSurface(self, image: Any, normalX: Any, normalY: Any, normalZ: Any) -> Any:
        material = self._config["material"]
        if material == "flat":
            return image
        light = np.asarray([-0.42, -0.48, 0.77], np.float32)
        light /= np.linalg.norm(light)
        diffuse = np.clip(
            normalX * light[0] + normalY * light[1] + normalZ * light[2],
            0.0,
            1.0,
        )
        if material == "matte":
            return image * (0.72 + 0.36 * diffuse[..., None])
        roughness = float(self._config["ripple"]["roughness"])
        exponent = 8.0 + (1.0 - roughness) * 88.0
        highlight = np.power(diffuse, exponent)[..., None]
        specular = float(self._config["ripple"]["specular"])
        return image * (0.64 + 0.46 * diffuse[..., None]) + highlight * specular

    # :: ANY, ANY, ANY -> ANY
    # Adds optional enlarged blurred foreground echoes behind the primary form
    def _ghosts(self, background: Any, foreground: Any, alpha: Any) -> Any:
        width = self._renderer.W
        height = self._renderer.H
        sky = np.asarray(self._paletteValues["sky_hor"], np.float32)
        for scale, sigma, amount, flip, offsetX in (
            (1.9, 0.035, 0.30, False, 0.1),
            (1.35, 0.014, 0.22, True, -0.2),
        ):
            matrix = cv2.getRotationMatrix2D(
                (width / 2.0 + offsetX * height, height / 2.0),
                8.0 if flip else -5.0,
                scale,
            )
            ghostColor = cv2.warpAffine(foreground, matrix, (width, height))
            ghostAlpha = cv2.warpAffine(alpha, matrix, (width, height))
            if flip:
                ghostColor = ghostColor[:, ::-1]
                ghostAlpha = ghostAlpha[:, ::-1]
            ghostColor = cv2.GaussianBlur(ghostColor, (0, 0), height * sigma)
            ghostAlpha = cv2.GaussianBlur(ghostAlpha, (0, 0), height * sigma)[..., None]
            background = background * (1.0 - amount * ghostAlpha) + amount * ghostColor * sky * 0.8
        return background

    # :: ANY, ANY -> ANY
    # Applies the optional reference-style foreground drop shadow to the background
    def _shadow(self, background: Any, alpha: Any) -> Any:
        height = self._renderer.H
        width = self._renderer.W
        matrix = np.float32([[1.0, 0.0, height * 0.02], [0.0, 1.0, height * 0.035]])
        shadow = cv2.warpAffine(alpha, matrix, (width, height))
        shadow = cv2.GaussianBlur(shadow, (0, 0), height * 0.02)[..., None]
        return background * (1.0 - 0.65 * shadow)

    #
    # Class Methods
    #

    # Class Factory Method :: ANY, ARRAY<STRING, ANY>, effectChain?, layerEffects?, ARRAY<STRING, ANY>? -> backgroundPass
    # Creates a configured background compositor
    @classmethod
    def init(
        cls,
        renderer: Any,
        config: Dict[str, Any],
        backgroundEffects: Optional[EffectChain] = None,
        layerEffects: Optional[LayerEffects] = None,
        palette: Optional[Dict[str, Any]] = None,
    ) -> BackgroundPass:
        return cls(renderer, config, backgroundEffects, layerEffects, palette)
