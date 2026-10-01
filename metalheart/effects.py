# Deterministic ordered frame effects derived from Glitzle's NumPy post filters

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import hashlib  # Derive stable per-frame random seeds across worker processes
import math  # Animate zoom and slice operations deterministically
from collections import deque  # Retain bounded frame history for Glitzle slitscan
from typing import Any, Dict, List, Optional, Tuple  # Python 3.8-compatible type annotations

import cv2  # Apply resolution-safe spatial frame operations
import numpy as np  # Evaluate vectorized pixel transformations
from PIL import Image  # Match Glitch Maker's arbitrary-angle pixel-sort rotation

from metalheart.effect_catalog import effectDefinition  # Resolve direct callers against the owned catalog


# Applies a resolved ordered effect chain to BGR byte frames
class EffectChain:

    # CONSTRUCTOR :: [ARRAY<STRING, ANY>], INT, INT, INT, INT -> effectChain
    # Stores resolved effects and deterministic render context
    def __init__(self, effects: List[Dict[str, Any]], width: int, height: int, fps: int, seed: int) -> None:
        self._effects: List[Dict[str, Any]] = effects
        self._width: int = width
        self._height: int = height
        self._fps: int = fps
        self._seed: int = seed
        self._operationState: Dict[Tuple[int, int], Dict[str, Any]] = {}

    #
    # Instance Methods
    #

    # :: ANY, FLOAT, INT?, ARRAY<STRING, FLOAT>? -> ANY
    # Applies enabled effects in authored order with optional output mixing
    def apply(
        self,
        frame: np.ndarray,
        timeSec: float,
        frameIndex: Optional[int] = None,
        signals: Optional[Dict[str, float]] = None,
    ) -> np.ndarray:
        resolvedFrame = int(round(timeSec * self._fps)) if frameIndex is None else int(frameIndex)
        output = frame
        for effectIndex, entry in enumerate(self._effects):
            if not entry.get("enabled", True):
                continue
            original = output
            effected = output
            operations = entry.get("operations")
            if not isinstance(operations, list):
                definition = effectDefinition(str(entry.get("id", "")))
                operations = definition.get("operations", []) if definition else []
            for operationIndex, operation in enumerate(operations):
                random = self._random(resolvedFrame, effectIndex, operationIndex)
                effected = self._applyOperation(
                    effected,
                    operation,
                    resolvedFrame,
                    random,
                    signals or {},
                    (effectIndex, operationIndex),
                )
            mix = float(entry.get("mix", 1.0))
            if mix <= 0.0:
                output = original
            elif mix >= 1.0:
                output = effected
            else:
                blended = original.astype(np.float32) * (1.0 - mix) + effected.astype(np.float32) * mix
                output = np.clip(blended, 0.0, 255.0).astype(np.uint8)
        return output

    # :: ANY, ANY, FLOAT, INT?, ARRAY<STRING, FLOAT>? -> (ANY, ANY)
    # Applies the chain to a transparent BGR layer while carrying its matte
    def applyLayer(
        self,
        frame: np.ndarray,
        alpha: np.ndarray,
        timeSec: float,
        frameIndex: Optional[int] = None,
        signals: Optional[Dict[str, float]] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        resolvedFrame = int(round(timeSec * self._fps)) if frameIndex is None else int(frameIndex)
        output = frame
        outputAlpha = self._bytes(np.clip(alpha, 0.0, 1.0) * 255.0)
        for effectIndex, entry in enumerate(self._effects):
            if not entry.get("enabled", True):
                continue
            original = output
            originalAlpha = outputAlpha
            effected = output
            effectedAlpha = outputAlpha
            operations = entry.get("operations")
            if not isinstance(operations, list):
                definition = effectDefinition(str(entry.get("id", "")))
                operations = definition.get("operations", []) if definition else []
            for operationIndex, operation in enumerate(operations):
                random = self._random(resolvedFrame, effectIndex, operationIndex)
                effected = self._applyOperation(
                    effected,
                    operation,
                    resolvedFrame,
                    random,
                    signals or {},
                    (effectIndex, operationIndex),
                )
                matteOperation = self._matteOperation(operation)
                if matteOperation is not None:
                    matteFrame = np.repeat(effectedAlpha[..., None], 3, axis=2)
                    matteRandom = self._random(resolvedFrame, effectIndex + 1000000, operationIndex)
                    matteFrame = self._applyOperation(
                        matteFrame,
                        matteOperation,
                        resolvedFrame,
                        matteRandom,
                        signals or {},
                        (effectIndex + 1000000, operationIndex),
                    )
                    effectedAlpha = np.max(matteFrame, axis=2)
            mix = float(entry.get("mix", 1.0))
            if mix <= 0.0:
                output = original
                outputAlpha = originalAlpha
            elif mix >= 1.0:
                output = effected
                outputAlpha = effectedAlpha
            else:
                blended = original.astype(np.float32) * (1.0 - mix) + effected.astype(np.float32) * mix
                blendedAlpha = originalAlpha.astype(np.float32) * (1.0 - mix) + effectedAlpha.astype(np.float32) * mix
                output = np.clip(blended, 0.0, 255.0).astype(np.uint8)
                outputAlpha = np.clip(blendedAlpha, 0.0, 255.0).astype(np.uint8)
        return output, outputAlpha.astype(np.float32) / 255.0

    #
    # Protected Methods
    #

    # :: ARRAY<STRING, ANY> -> ARRAY<STRING, ANY>?
    # Selects a geometry-only operation for carrying transparent layer alpha
    def _matteOperation(self, operation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        name = str(operation.get("op", ""))
        if name in {
            "pixelate",
            "scale",
            "zoomShake",
            "sliceShiftY",
            "sliceShiftX",
            "tear",
            "blockJitter",
            "rectangles",
            "blur",
            "mirrorH",
            "mirrorV",
            "mirrorQuad",
            "mirrorDiamond",
            "tetrys",
            "ziti",
            "slitscan",
            "rgbShift",
            "chromatic",
            "scanlineCorrupt",
        }:
            return operation
        if name == "vhs":
            return dict(operation, noise=0.0)
        if name == "arcade":
            return dict(operation, paletteLevels=256, maskStrength=0.0, scanStrength=0.0)
        return None

    # :: ANY, ARRAY<STRING, ANY>, INT, ANY, ARRAY<STRING, FLOAT>, (INT, INT) -> ANY
    # Dispatches one Glitzle-compatible primitive operation
    def _applyOperation(
        self,
        frame: np.ndarray,
        operation: Dict[str, Any],
        frameIndex: int,
        random: np.random.Generator,
        signals: Dict[str, float],
        stateKey: Tuple[int, int],
    ) -> np.ndarray:
        name = operation.get("op")
        if name == "contrast":
            value = float(operation.get("value", 1.0))
            return self._roundedBytes((frame.astype(np.float32) - 128.0) * value + 128.0)
        if name == "saturation":
            value = float(operation.get("value", 1.0))
            values = frame.astype(np.float32)
            blue, green, red = values[..., 0], values[..., 1], values[..., 2]
            luminance = 0.114 * blue + 0.587 * green + 0.299 * red
            return self._roundedBytes(luminance[..., None] + (values - luminance[..., None]) * value)
        if name == "posterize":
            levels = max(2, int(operation.get("levels", 4)))
            values = np.floor(frame.astype(np.float32) / 255.0 * (levels - 1) + 0.5)
            return self._roundedBytes(values / float(levels - 1) * 255.0)
        if name == "channels":
            values = frame.astype(np.float32)
            values[..., 2] *= float(operation.get("r", 1.0))
            values[..., 1] *= float(operation.get("g", 1.0))
            values[..., 0] *= float(operation.get("b", 1.0))
            return self._roundedBytes(values)
        if name == "grayscale":
            amount = min(max(float(operation.get("amount", 1.0)), 0.0), 1.0)
            values = frame.astype(np.float32)
            luminance = 0.114 * values[..., 0] + 0.587 * values[..., 1] + 0.299 * values[..., 2]
            return self._roundedBytes(values * (1.0 - amount) + luminance[..., None] * amount)
        if name == "invert":
            amount = min(max(float(operation.get("amount", 1.0)), 0.0), 1.0)
            values = frame.astype(np.float32)
            return self._roundedBytes(values * (1.0 - amount) + (255.0 - values) * amount)
        if name == "noise":
            amount = max(0.0, float(operation.get("amount", 0.0)))
            values = random.uniform(-amount, amount, frame.shape).astype(np.float32)
            return self._bytes(frame.astype(np.float32) + values)
        if name == "pixelate":
            size = max(1, int(operation.get("size", 2)))
            downWidth = max(1, int(math.ceil(self._width / float(size))))
            downHeight = max(1, int(math.ceil(self._height / float(size))))
            reduced = cv2.resize(frame, (downWidth, downHeight), interpolation=cv2.INTER_AREA)
            return cv2.resize(reduced, (self._width, self._height), interpolation=cv2.INTER_NEAREST)
        if name == "scanlines":
            strength = min(max(float(operation.get("strength", 0.15)), 0.0), 1.0)
            output = frame.copy()
            output[::2] = self._bytes(output[::2].astype(np.float32) * (1.0 - strength))
            return output
        if name == "rgbShift":
            return self._rgbShift(frame, operation)
        if name == "scale" or name == "zoomShake":
            return self._spatial(frame, operation, frameIndex)
        if name == "sliceShiftY":
            return self._sliceShiftY(frame, operation, frameIndex)
        if name == "sliceShiftX":
            return self._sliceShiftX(frame, operation, frameIndex)
        if name == "tear":
            return self._tear(frame, operation, frameIndex)
        if name == "blockJitter":
            return self._blockJitter(frame, operation, frameIndex, random)
        if name == "rectangles":
            return self._rectangles(frame, operation, frameIndex)
        if name == "blur":
            radius = max(0, int(math.floor(float(operation.get("radius", 1.0)) + 0.5)))
            kernel = radius * 2 + 1
            return cv2.blur(frame, (kernel, kernel)) if radius > 0 else frame.copy()
        if name == "vignette":
            return self._vignette(frame, float(operation.get("amount", 0.2)))
        if name in ("mirrorH", "mirrorV", "mirrorQuad", "mirrorDiamond"):
            return self._mirror(frame, str(name))
        if name == "xor":
            shiftX = int(operation.get("shift_x", 10)) + int(frameIndex * 0.3) % 20
            shiftY = int(operation.get("shift_y", 5)) + int(frameIndex * 0.2) % 15
            shifted = np.roll(frame, shift=(shiftY, shiftX), axis=(0, 1))
            return np.bitwise_xor(frame, shifted)
        if name == "tetrys":
            return self._tetrys(frame, operation, frameIndex)
        if name == "ziti":
            return self._ziti(frame, operation, frameIndex)
        if name == "vhs":
            return self._vhs(frame, operation, frameIndex)
        if name == "arcade":
            return self._arcade(frame, operation)
        if name == "chromatic":
            return self._chromatic(frame, operation, frameIndex, signals)
        if name == "pixelSort":
            return self._pixelSort(frame, operation, signals)
        if name == "slitscan":
            return self._slitscan(frame, operation, frameIndex, signals, stateKey)
        if name == "scanlineCorrupt":
            return self._scanlineCorrupt(frame, operation, frameIndex, random, signals)
        return frame.copy()

    # :: ANY, ARRAY<STRING, ANY> -> ANY
    # Separates red and blue channels with Glitchstation wrapping or legacy clamping
    def _rgbShift(self, frame: np.ndarray, operation: Dict[str, Any]) -> np.ndarray:
        redOffset = int(operation.get("rX", 0))
        blueOffset = int(operation.get("bX", 0))
        columns = np.arange(self._width)
        edgeMode = operation.get("edge_mode")
        if edgeMode == "wrap":
            redColumns = (columns - redOffset) % self._width
            blueColumns = (columns - blueOffset) % self._width
        elif edgeMode == "clamp":
            redColumns = np.clip(columns - redOffset, 0, self._width - 1)
            blueColumns = np.clip(columns - blueOffset, 0, self._width - 1)
        else:
            redColumns = np.clip(columns + redOffset, 0, self._width - 1)
            blueColumns = np.clip(columns + blueOffset, 0, self._width - 1)
        output = frame.copy()
        output[..., 2] = frame[:, redColumns, 2]
        output[..., 0] = frame[:, blueColumns, 0]
        return output

    # :: ANY, ARRAY<STRING, ANY>, INT -> ANY
    # Applies authored scale or time-varying Glitzle zoom shake
    def _spatial(self, frame: np.ndarray, operation: Dict[str, Any], frameIndex: int) -> np.ndarray:
        if operation.get("op") == "zoomShake":
            amplitude = max(0.0, float(operation.get("amp", 0.03)))
            scaleX = 1.0 + math.sin(frameIndex * 0.18) * amplitude
            scaleY = scaleX
            shiftX = math.floor(math.sin(frameIndex * 0.31) * self._width * amplitude * 0.25 + 0.5)
            shiftY = math.floor(math.cos(frameIndex * 0.27) * self._height * amplitude * 0.25 + 0.5)
        else:
            scaleX = max(0.1, float(operation.get("x", 1.0)))
            scaleY = max(0.1, float(operation.get("y", 1.0)))
            shiftX = 0
            shiftY = 0
        matrix = np.asarray(
            [
                [scaleX, 0.0, (1.0 - scaleX) * self._width / 2.0 + shiftX],
                [0.0, scaleY, (1.0 - scaleY) * self._height / 2.0 + shiftY],
            ],
            dtype=np.float32,
        )
        return cv2.warpAffine(frame, matrix, (self._width, self._height), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_REPLICATE)

    # :: ANY, ARRAY<STRING, ANY>, NUMBER -> ANY
    # Shifts horizontal bands with stable frame-driven motion
    def _sliceShiftY(self, frame: np.ndarray, operation: Dict[str, Any], frameIndex: float) -> np.ndarray:
        bands = max(1, int(operation.get("bands", 12)))
        strength = max(0.0, float(operation.get("strength", 0.0)))
        bandHeight = max(1, self._height // bands)
        output = frame.copy()
        for y in range(0, self._height, bandHeight):
            band = y // bandHeight
            shift = int(math.floor((math.sin(band * 1.7 + frameIndex * 0.03) * 0.5 + 0.5) * strength + 0.5))
            if band % 2:
                shift = -shift
            output[y:min(y + bandHeight, self._height)] = np.roll(frame[y:min(y + bandHeight, self._height)], shift, axis=1)
        return output

    # :: ANY, ARRAY<STRING, ANY>, NUMBER -> ANY
    # Shifts vertical columns with stable frame-driven motion
    def _sliceShiftX(self, frame: np.ndarray, operation: Dict[str, Any], frameIndex: float) -> np.ndarray:
        columns = max(1, int(operation.get("cols", 10)))
        strength = max(0.0, float(operation.get("strength", 0.0)))
        columnWidth = max(1, self._width // columns)
        output = frame.copy()
        for x in range(0, self._width, columnWidth):
            column = x // columnWidth
            shift = int(math.floor((math.sin(column * 1.9 + frameIndex * 0.025) * 0.5 + 0.5) * strength + 0.5))
            if column % 2:
                shift = -shift
            output[:, x:min(x + columnWidth, self._width)] = np.roll(frame[:, x:min(x + columnWidth, self._width)], shift, axis=0)
        return output

    # :: ANY, ARRAY<STRING, ANY>, INT -> ANY
    # Applies Glitchstation's direction-selectable band tearing
    def _tear(self, frame: np.ndarray, operation: Dict[str, Any], frameIndex: int) -> np.ndarray:
        rate = max(0.0, float(operation.get("rate", 1.0)))
        phaseFrame = frameIndex * rate + int(operation.get("seed", 0))
        direction = str(operation.get("direction", "horizontal"))
        if direction == "vertical":
            translated = {
                "op": "sliceShiftX",
                "cols": int(operation.get("bands", 16)),
                "strength": float(operation.get("strength", 18.0)),
            }
            return self._sliceShiftX(frame, translated, phaseFrame)
        translated = {
            "op": "sliceShiftY",
            "bands": int(operation.get("bands", 16)),
            "strength": float(operation.get("strength", 18.0)),
        }
        return self._sliceShiftY(frame, translated, phaseFrame)

    # :: ANY, ARRAY<STRING, ANY>, INT, ANY -> ANY
    # Copies displaced blocks using Glitchstation or legacy deterministic randomness
    def _blockJitter(
        self,
        frame: np.ndarray,
        operation: Dict[str, Any],
        frameIndex: int,
        random: np.random.Generator,
    ) -> np.ndarray:
        size = max(4, int(operation.get("size", 32)))
        strength = max(0.0, float(operation.get("strength", 8.0)))
        chance = min(max(float(operation.get("chance", 0.25)), 0.0), 1.0)
        output = frame.copy()
        if "seed" in operation or "rate" in operation:
            phase = frameIndex * max(0.0, float(operation.get("rate", 1.0))) + int(operation.get("seed", 0)) * 257
            for y in range(0, self._height, size):
                for x in range(0, self._width, size):
                    if self._glitchRandom(x * 17 + y * 31 + phase * 53) > chance:
                        continue
                    blockHeight = min(size, self._height - y)
                    blockWidth = min(size, self._width - x)
                    shiftX = int(math.floor((self._glitchRandom(x + phase * 7) * 2.0 - 1.0) * strength + 0.5))
                    shiftY = int(math.floor((self._glitchRandom(y + phase * 11) * 2.0 - 1.0) * strength + 0.5))
                    sourceX = min(max(0, x + shiftX), max(0, self._width - blockWidth))
                    sourceY = min(max(0, y + shiftY), max(0, self._height - blockHeight))
                    output[y:y + blockHeight, x:x + blockWidth] = frame[
                        sourceY:sourceY + blockHeight,
                        sourceX:sourceX + blockWidth,
                    ]
            return output
        for y in range(0, self._height, size):
            for x in range(0, self._width, size):
                if float(random.random()) > chance:
                    continue
                blockHeight = min(size, self._height - y)
                blockWidth = min(size, self._width - x)
                shiftX = int(math.floor((float(random.random()) * 2.0 - 1.0) * strength + 0.5))
                shiftY = int(math.floor((float(random.random()) * 2.0 - 1.0) * strength + 0.5))
                sourceY = np.clip(np.arange(y, y + blockHeight) + shiftY, 0, self._height - 1)
                sourceX = np.clip(np.arange(x, x + blockWidth) + shiftX, 0, self._width - 1)
                output[y:y + blockHeight, x:x + blockWidth] = frame[np.ix_(sourceY, sourceX)]
        return output

    # :: ANY, ARRAY<STRING, ANY>, INT -> ANY
    # Swaps deterministic Glitchstation rectangles across the frame
    def _rectangles(self, frame: np.ndarray, operation: Dict[str, Any], frameIndex: int) -> np.ndarray:
        count = max(0, int(operation.get("n_rects", 8)))
        rate = max(0.0, float(operation.get("rate", 1.0)))
        phase = frameIndex * rate + int(operation.get("seed", 0)) * 257
        maximumHeight = max(21, self._height // 3)
        maximumWidth = max(21, self._width // 3)
        output = frame.copy()
        for index in range(count):
            blockHeight = min(self._height, self._glitchRandomInt(phase, index, 20, maximumHeight))
            blockWidth = min(self._width, self._glitchRandomInt(phase + 1, index, 20, maximumWidth))
            if blockHeight >= self._height or blockWidth >= self._width:
                continue
            firstY = self._glitchRandomInt(phase + 2, index, 0, self._height - blockHeight)
            firstX = self._glitchRandomInt(phase + 3, index, 0, self._width - blockWidth)
            secondY = self._glitchRandomInt(phase + 4, index, 0, self._height - blockHeight)
            secondX = self._glitchRandomInt(phase + 5, index, 0, self._width - blockWidth)
            source = output.copy()
            output[firstY:firstY + blockHeight, firstX:firstX + blockWidth] = source[
                secondY:secondY + blockHeight,
                secondX:secondX + blockWidth,
            ]
            output[secondY:secondY + blockHeight, secondX:secondX + blockWidth] = source[
                firstY:firstY + blockHeight,
                firstX:firstX + blockWidth,
            ]
        return output

    # :: ANY, FLOAT -> ANY
    # Applies a resolution-independent radial edge darkening
    def _vignette(self, frame: np.ndarray, amount: float) -> np.ndarray:
        bounded = min(max(amount, 0.0), 1.0)
        centerX = self._width / 2.0
        centerY = self._height / 2.0
        maximum = math.hypot(centerX, centerY)
        yValues = np.arange(self._height, dtype=np.float32)[:, None]
        xValues = np.arange(self._width, dtype=np.float32)[None, :]
        distance = np.hypot(xValues - centerX, yValues - centerY) / maximum
        multiplier = np.maximum(0.0, 1.0 - bounded * distance * distance)
        return self._bytes(frame.astype(np.float32) * multiplier[..., None])

    # :: ANY, STRING -> ANY
    # Applies Dazzle's four source-half and source-quadrant mirror modes
    def _mirror(self, frame: np.ndarray, mode: str) -> np.ndarray:
        output = frame.copy()
        middleX = self._width // 2
        middleY = self._height // 2
        if mode == "mirrorH":
            output[:, middleX:] = np.fliplr(output[:, :middleX])[:, :self._width - middleX]
        elif mode == "mirrorV":
            output[middleY:, :] = np.flipud(output[:middleY, :])[:self._height - middleY, :]
        elif mode == "mirrorQuad":
            quadrant = output[:middleY, :middleX]
            output[:middleY, middleX:] = np.fliplr(quadrant)[:, :self._width - middleX]
            output[middleY:, :middleX] = np.flipud(quadrant)[:self._height - middleY, :]
            output[middleY:, middleX:] = np.flipud(np.fliplr(quadrant))[:self._height - middleY, :self._width - middleX]
        else:
            size = min(self._height, self._width)
            square = output[:size, :size].copy()
            yValues, xValues = np.mgrid[:size, :size]
            sourceY = np.minimum(yValues, xValues)
            sourceX = np.maximum(yValues, xValues)
            output[:size, :size] = square[sourceY, sourceX]
            output[:, middleX:] = np.fliplr(output[:, :middleX])[:, :self._width - middleX]
        return output

    # :: ANY, ARRAY<STRING, ANY>, INT -> ANY
    # Drops VidGlitch-style strips toward any authored cardinal direction
    def _tetrys(self, frame: np.ndarray, operation: Dict[str, Any], frameIndex: int) -> np.ndarray:
        size = max(2, int(operation.get("block_size", 16)))
        direction = str(operation.get("direction", "down"))
        output = np.zeros_like(frame)
        if direction in ("left", "right"):
            rowCount = self._height // size
            sign = -1 if direction == "left" else 1
            for row in range(rowCount):
                start = row * size
                end = min(self._height, start + size)
                drop = int((frameIndex * (0.5 + row * 0.3)) % self._width)
                output[start:end, :] = np.roll(frame[start:end, :], sign * drop, axis=1)
            if rowCount * size < self._height:
                output[rowCount * size:, :] = frame[rowCount * size:, :]
            return output
        columnCount = self._width // size
        sign = -1 if direction == "up" else 1
        for column in range(columnCount):
            start = column * size
            end = min(self._width, start + size)
            drop = int((frameIndex * (0.5 + column * 0.3)) % self._height)
            output[:, start:end] = np.roll(frame[:, start:end], sign * drop, axis=0)
        if columnCount * size < self._width:
            output[:, columnCount * size:] = frame[:, columnCount * size:]
        return output

    # :: ANY, ARRAY<STRING, ANY>, INT -> ANY
    # Wraps the frame around a cardinally directed animated cylinder projection
    def _ziti(self, frame: np.ndarray, operation: Dict[str, Any], frameIndex: int) -> np.ndarray:
        bounded = max(0.05, float(operation.get("curvature", 0.3)))
        direction = str(operation.get("direction", "right"))
        sign = -1.0 if direction in ("left", "up") else 1.0
        phase = sign * frameIndex * 0.01
        yValues, xValues = np.mgrid[:self._height, :self._width]
        if direction in ("down", "up"):
            centerY = self._height / 2.0
            angle = (yValues - centerY) / centerY * (math.pi * bounded) + phase
            sourceY = centerY + centerY * np.sin(angle) / max(0.1, math.pi * bounded)
            sourceY = np.clip(sourceY, 0, self._height - 1).astype(np.int64)
            return frame[sourceY, xValues]
        centerX = self._width / 2.0
        angle = (xValues - centerX) / centerX * (math.pi * bounded) + phase
        sourceX = centerX + centerX * np.sin(angle) / max(0.1, math.pi * bounded)
        sourceX = np.clip(sourceX, 0, self._width - 1).astype(np.int64)
        return frame[yValues, sourceX]

    # :: ANY, ARRAY<STRING, ANY>, INT -> ANY
    # Applies Glitchstation tracking, chroma bleed, noise, and head-switch tearing
    def _vhs(self, frame: np.ndarray, operation: Dict[str, Any], frameIndex: int) -> np.ndarray:
        rate = max(0.0, float(operation.get("rate", 1.0)))
        phaseFrame = frameIndex * rate
        tracking = max(0.0, float(operation.get("tracking", 0.0)))
        chroma = int(math.floor(float(operation.get("chromaBleed", 0.0)) * 10.0 + 0.5))
        noiseAmount = max(0.0, float(operation.get("noise", 0.0))) * 34.0
        seed = int(operation.get("seed", 0))
        head = min(max(float(operation.get("headSwitch", 0.0)), 0.0), 1.0)
        bandHeight = max(1, self._height // 28)
        headHeight = int(math.floor(self._height * 0.12 * head + 0.5))
        headShift = int(
            math.floor(
                (self._glitchRandom(phaseFrame * 29 + seed * 997) * 2.0 - 1.0)
                * self._width
                * 0.08
                * head
                + 0.5
            )
        )
        shifts = np.empty(self._height, dtype=np.int64)
        for y in range(self._height):
            band = y // bandHeight
            shift = int(math.floor((math.sin(band * 1.7 + (phaseFrame + seed) * 0.03) * 0.5 + 0.5) * tracking * 22.0 + 0.5))
            if band % 2:
                shift = -shift
            if y >= self._height - headHeight:
                shift += headShift
            shifts[y] = shift
        columns = np.arange(self._width, dtype=np.int64)[None, :]
        greenColumns = (columns - shifts[:, None]) % self._width
        redColumns = (greenColumns - chroma) % self._width
        blueColumns = (greenColumns + chroma) % self._width
        noise = self._lcgNoise(phaseFrame, seed, noiseAmount)
        output = frame.copy().astype(np.float32)
        output[..., 2] = np.take_along_axis(frame[..., 2], redColumns, axis=1) + noise
        output[..., 1] = np.take_along_axis(frame[..., 1], greenColumns, axis=1) + noise
        output[..., 0] = np.take_along_axis(frame[..., 0], blueColumns, axis=1) + noise
        return self._roundedBytes(output)

    # :: ANY, ARRAY<STRING, ANY> -> ANY
    # Applies Glitchstation barrel curvature, palette crush, mask, and scanlines
    def _arcade(self, frame: np.ndarray, operation: Dict[str, Any]) -> np.ndarray:
        curvature = min(max(float(operation.get("curvature", 0.0)), 0.0), 0.5)
        output = frame.copy()
        if curvature > 0.0:
            centerX = self._width / 2.0
            centerY = self._height / 2.0
            maximum = math.hypot(centerX, centerY) or 1.0
            yValues, xValues = np.mgrid[:self._height, :self._width]
            deltaX = (xValues - centerX) / maximum
            deltaY = (yValues - centerY) / maximum
            scale = 1.0 + curvature * (deltaX * deltaX + deltaY * deltaY) * 2.2
            sourceX = np.clip(np.floor(centerX + (xValues - centerX) / scale + 0.5), 0, self._width - 1).astype(np.int64)
            sourceY = np.clip(np.floor(centerY + (yValues - centerY) / scale + 0.5), 0, self._height - 1).astype(np.int64)
            output = frame[sourceY, sourceX]
        levels = max(2, int(operation.get("paletteLevels", 4)))
        step = 255.0 / float(levels - 1)
        values = output.astype(np.float32)
        values = np.floor(np.floor(values / step + 0.5) * step + 0.5)
        maskStrength = min(max(float(operation.get("maskStrength", 0.0)), 0.0), 1.0)
        scanStrength = min(max(float(operation.get("scanStrength", 0.0)), 0.0), 1.0)
        yValues, xValues = np.mgrid[:self._height, :self._width]
        grid = np.where((xValues % 3 == 0) | (yValues % 3 == 0), 1.0 - maskStrength, 1.0)
        scan = np.where(yValues % 2 == 0, 1.0 - scanStrength, 1.0)
        return self._roundedBytes(values * (grid * scan)[..., None])

    # :: ANY, ARRAY<STRING, ANY>, INT, ARRAY<STRING, FLOAT> -> ANY
    # Applies Glitch Maker's audio-scaled horizontal, vertical, or circular aberration
    def _chromatic(
        self,
        frame: np.ndarray,
        operation: Dict[str, Any],
        frameIndex: int,
        signals: Dict[str, float],
    ) -> np.ndarray:
        amount = max(0.0, float(operation.get("amount", 16.0)))
        audioScale = min(max(float(operation.get("audio_scale", 0.75)), 0.0), 1.0)
        bass = min(max(float(signals.get("bass", 0.0)), 0.0), 1.0)
        treble = min(max(float(signals.get("treble", signals.get("high", 0.0))), 0.0), 1.0)
        rms = min(max(float(signals.get("rms", self._rms(signals))), 0.0), 1.0)
        audio = treble * 0.6 + rms * 0.4
        amount *= (1.0 - audioScale) + audioScale * audio
        direction = str(operation.get("direction", "circular"))
        phase = float(signals.get("chromatic_phase", (frameIndex + 1) * (0.12 + bass * 0.35)))
        sign = float(signals.get("chromatic_sign", -1.0 if bool(signals.get("transient", False)) else 1.0))
        if direction == "horizontal":
            shiftX = int(sign * amount * math.cos(phase))
            shiftY = 0
        elif direction == "vertical":
            shiftX = 0
            shiftY = int(sign * amount * math.cos(phase))
        else:
            shiftX = int(sign * amount * math.cos(phase))
            shiftY = int(sign * amount * math.sin(phase) * 0.5)
        output = frame.copy()
        output[..., 2] = np.roll(frame[..., 2], shift=(shiftY, shiftX), axis=(0, 1))
        output[..., 0] = np.roll(frame[..., 0], shift=(-shiftY, -shiftX), axis=(0, 1))
        return output

    # :: ANY, ARRAY<STRING, ANY>, ARRAY<STRING, FLOAT> -> ANY
    # Sorts Glitch Maker-style contiguous pixel runs within audio-scaled thresholds
    def _pixelSort(self, frame: np.ndarray, operation: Dict[str, Any], signals: Dict[str, float]) -> np.ndarray:
        audioScale = min(max(float(operation.get("audio_scale", 0.5)), 0.0), 1.0)
        activity = self._glitchActivity(signals)
        if activity == 0.0 and audioScale > 0.0:
            return frame.copy()
        lower = min(max(float(operation.get("lower_threshold", 0.25)), 0.0), 1.0)
        upper = min(max(float(operation.get("upper_threshold", 0.8)), lower), 1.0)
        if audioScale > 0.0:
            middle = (lower + upper) * 0.5
            shrink = 1.0 - audioScale * (1.0 - activity)
            half = (upper - lower) * 0.5 * shrink
            lower = max(0.0, middle - half)
            upper = min(1.0, middle + half)
        angle = int(operation.get("angle", 0)) % 360
        work = frame[..., ::-1].copy()
        if angle:
            work = np.asarray(Image.fromarray(work, mode="RGB").rotate(angle, expand=True, fillcolor=(0, 0, 0)))
        direction = str(operation.get("direction", "horizontal"))
        if direction in ("horizontal", "both"):
            transposed = work.transpose(1, 0, 2)
            work = self._sortPixelRuns(transposed, lower, upper, operation).transpose(1, 0, 2)
        if direction in ("vertical", "both"):
            work = self._sortPixelRuns(work, lower, upper, operation)
        if angle:
            rotated = Image.fromarray(work, mode="RGB").rotate(-angle, expand=True, fillcolor=(0, 0, 0))
            rotatedWidth, rotatedHeight = rotated.size
            top = (rotatedHeight - self._height) // 2
            left = (rotatedWidth - self._width) // 2
            work = np.asarray(rotated.crop((left, top, left + self._width, top + self._height)))
        return work[..., ::-1].copy()

    # :: ANY, FLOAT, FLOAT, ARRAY<STRING, ANY> -> ANY
    # Sorts contiguous qualifying runs along the first axis of every pixel column
    def _sortPixelRuns(
        self,
        pixels: np.ndarray,
        lower: float,
        upper: float,
        operation: Dict[str, Any],
    ) -> np.ndarray:
        values = self._pixelValues(pixels, str(operation.get("sort_by", "brightness")))
        mask = (values >= lower) & (values <= upper)
        output = pixels.copy()
        length, columnCount = pixels.shape[:2]
        reverse = bool(operation.get("reverse", False))
        for column in range(columnCount):
            columnMask = mask[:, column]
            if not columnMask.any():
                continue
            index = 0
            while index < length:
                if not columnMask[index]:
                    index += 1
                    continue
                end = index
                while end < length and columnMask[end]:
                    end += 1
                if end - index > 1:
                    order = np.argsort(values[index:end, column])
                    if reverse:
                        order = order[::-1]
                    output[index:end, column] = output[index:end, column][order]
                index = end
        return output

    # :: ANY, STRING -> ANY
    # Computes Glitch Maker brightness, hue, or saturation keys for RGB pixels
    def _pixelValues(self, pixels: np.ndarray, sortBy: str) -> np.ndarray:
        if sortBy == "brightness":
            red = pixels[..., 0].astype(np.float32)
            green = pixels[..., 1].astype(np.float32)
            blue = pixels[..., 2].astype(np.float32)
            return (red * 0.299 + green * 0.587 + blue * 0.114) / 255.0
        hsv = np.asarray(Image.fromarray(pixels, mode="RGB").convert("HSV"), dtype=np.float32) / 255.0
        return hsv[..., 0] if sortBy == "hue" else hsv[..., 1]

    # :: ANY, ARRAY<STRING, ANY>, INT, ARRAY<STRING, FLOAT>, (INT, INT) -> ANY
    # Recreates Glitch Maker slitscan from a bounded rolling frame history
    def _slitscan(
        self,
        frame: np.ndarray,
        operation: Dict[str, Any],
        frameIndex: int,
        signals: Dict[str, float],
        stateKey: Tuple[int, int],
    ) -> np.ndarray:
        maximumDelay = max(1, int(operation.get("max_delay_frames", 30)))
        state = self._operationState.setdefault(stateKey, {})
        buffer = state.get("buffer")
        if not isinstance(buffer, deque) or buffer.maxlen != maximumDelay + 1:
            buffer = deque(maxlen=maximumDelay + 1)
            state["buffer"] = buffer
        previousFrame = state.get("frame_index")
        if previousFrame is not None and frameIndex != int(previousFrame) + 1:
            buffer.clear()
        state["frame_index"] = frameIndex
        typedBuffer = buffer
        typedBuffer.append(frame.copy())
        audioScale = min(max(float(operation.get("audio_scale", 0.5)), 0.0), 1.0)
        intensity = (1.0 - audioScale) + audioScale * self._glitchActivity(signals)
        effectiveDelay = min(int(maximumDelay * intensity), len(typedBuffer) - 1)
        if effectiveDelay <= 0:
            return frame.copy()
        history = list(typedBuffer)
        output = frame.copy()
        if str(operation.get("direction", "horizontal")) == "horizontal":
            for row in range(self._height):
                delay = int(effectiveDelay * row / max(1, self._height - 1))
                output[row] = history[-1 - delay][row]
        else:
            for column in range(self._width):
                delay = int(effectiveDelay * column / max(1, self._width - 1))
                output[:, column] = history[-1 - delay][:, column]
        return output

    # :: ANY, ARRAY<STRING, ANY>, INT, ANY, ARRAY<STRING, FLOAT> -> ANY
    # Recreates Glitzle's full-width scan tear plus horizontal chromatic recipe
    def _scanlineCorrupt(
        self,
        frame: np.ndarray,
        operation: Dict[str, Any],
        frameIndex: int,
        random: np.random.Generator,
        signals: Dict[str, float],
    ) -> np.ndarray:
        audioScale = min(max(float(operation.get("audio_scale", 0.65)), 0.0), 1.0)
        intensity = (1.0 - audioScale) + audioScale * self._audioActivity(signals)
        bandCount = max(1, int(round(int(operation.get("band_count", 16)) * intensity)))
        thickness = max(1, int(operation.get("thickness", 3)))
        displacement = max(0, int(round(int(operation.get("displacement", 48)) * intensity)))
        output = frame.copy()
        for index in range(bandCount):
            del index
            start = int(random.integers(0, self._height))
            end = min(self._height, start + thickness)
            shift = int(random.integers(-displacement, displacement + 1)) if displacement else 0
            output[start:end] = np.roll(frame[start:end], shift, axis=1)
        chromatic = {
            "amount": float(operation.get("chroma_amount", 10.0)),
            "direction": "horizontal",
            "speed": 0.12,
            "audio_scale": audioScale,
        }
        return self._chromatic(output, chromatic, frameIndex, signals)

    # :: ARRAY<STRING, FLOAT> -> FLOAT
    # Reduces renderer bass, mid, high, and onset signals to bounded activity
    def _audioActivity(self, signals: Dict[str, float]) -> float:
        bass = min(max(float(signals.get("bass", 0.0)), 0.0), 1.0)
        mid = min(max(float(signals.get("mid", 0.0)), 0.0), 1.0)
        high = min(max(float(signals.get("high", 0.0)), 0.0), 1.0)
        onset = min(max(float(signals.get("onset", 0.0)), 0.0), 1.0)
        value = high * 0.4 + mid * 0.2 + bass * 0.2 + onset * 0.2
        return min(max(value, 0.0), 1.0)

    # :: ARRAY<STRING, FLOAT> -> FLOAT
    # Recreates Glitch Maker's shared RMS, bass, onset, and transient activity mix
    def _glitchActivity(self, signals: Dict[str, float]) -> float:
        if bool(signals.get("section_change", False)):
            return 1.0
        bass = min(max(float(signals.get("bass", 0.0)), 0.0), 1.0)
        onset = min(max(float(signals.get("onset", 0.0)), 0.0), 1.0)
        rms = min(max(float(signals.get("rms", self._rms(signals))), 0.0), 1.0)
        value = rms * 0.5 + bass * 0.3 + onset * 0.2
        if bool(signals.get("transient", False)):
            value += 0.3
        return min(max(value, 0.0), 1.0)

    # :: ARRAY<STRING, FLOAT> -> FLOAT
    # Derives a bounded full-band level when the caller has no explicit RMS signal
    def _rms(self, signals: Dict[str, float]) -> float:
        bass = min(max(float(signals.get("bass", 0.0)), 0.0), 1.0)
        mid = min(max(float(signals.get("mid", 0.0)), 0.0), 1.0)
        high = min(max(float(signals.get("high", 0.0)), 0.0), 1.0)
        return bass * 0.5 + mid * 0.3 + high * 0.2

    # :: NUMBER -> FLOAT
    # Reproduces Glitchstation's stable unsigned 32-bit pseudo-random hash
    def _glitchRandom(self, seed: float) -> float:
        value = (int(math.floor(seed * 1000.0)) ^ 0x9E3779B9) & 0xFFFFFFFF
        value = (value * 0x85EBCA6B) & 0xFFFFFFFF
        value ^= value >> 13
        value = (value * 0xC2B2AE35) & 0xFFFFFFFF
        value ^= value >> 16
        return float(value & 0xFFFFFFFF) / 4294967296.0

    # :: NUMBER, INT, INT, INT -> INT
    # Reproduces Glitchstation's inclusive deterministic random integer helper
    def _glitchRandomInt(self, seed: float, index: int, minimum: int, maximum: int) -> int:
        if maximum <= minimum:
            return minimum
        random = self._glitchRandom(seed * 97 + index * 131)
        return minimum + int(math.floor(random * (maximum - minimum + 1)))

    # :: NUMBER, INT, FLOAT -> ANY
    # Builds Glitchstation's signed per-pixel VHS noise sequence
    def _lcgNoise(self, frameIndex: float, seed: int, amount: float) -> np.ndarray:
        count = self._height * self._width
        values = np.empty(count, dtype=np.float32)
        state = int((frameIndex + 1) * 1103515245 + (seed + 1) * 12345) & 0xFFFFFFFF
        for index in range(count):
            state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
            values[index] = ((state / 2147483648.0) - 1.0) * amount
        return values.reshape((self._height, self._width))

    # :: INT, INT, INT -> ANY
    # Creates one stable random generator independent of process scheduling
    def _random(self, frameIndex: int, effectIndex: int, operationIndex: int) -> np.random.Generator:
        payload = "{0}:{1}:{2}:{3}".format(self._seed, frameIndex, effectIndex, operationIndex).encode("utf-8")
        digest = hashlib.sha256(payload).digest()
        randomSeed = int.from_bytes(digest[:8], byteorder="big", signed=False)
        return np.random.default_rng(randomSeed)

    # :: ANY -> ANY
    # Clamps float pixel data to BGR bytes
    def _bytes(self, value: np.ndarray) -> np.ndarray:
        return np.clip(value, 0.0, 255.0).astype(np.uint8)

    # :: ANY -> ANY
    # Matches Glitchstation's rounded channel clamping for color operations
    def _roundedBytes(self, value: np.ndarray) -> np.ndarray:
        return np.clip(np.floor(value + 0.5), 0.0, 255.0).astype(np.uint8)

    #
    # Class Methods
    #

    # Class Factory Method :: [ARRAY<STRING, ANY>], INT, INT, INT, INT -> effectChain
    # Creates a deterministic ordered effect processor
    @classmethod
    def init(cls, effects: List[Dict[str, Any]], width: int, height: int, fps: int, seed: int) -> EffectChain:
        return cls(effects, width, height, fps, seed)
