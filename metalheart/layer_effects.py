# Material-isolated post effects for reference-rendered 3D foregrounds

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

from typing import Any, Optional, Tuple  # Type captured material masks and processed layers

import cv2  # Expand internal trace masks to output resolution
import numpy as np  # Classify ray hits and composite transparent effect layers

from metalheart.effects import EffectChain  # Reuse the public deterministic effect engine


# Captures visible form and ribbon materials and applies their independent chains
class LayerEffects:

    # CONSTRUCTOR :: ANY, effectChain?, effectChain? -> layerEffects
    # Wraps immutable ray tracing without altering reference source files
    def __init__(
        self,
        coreRenderer: Any,
        formEffects: Optional[EffectChain],
        ribbonEffects: Optional[EffectChain],
    ) -> None:
        self._renderer = coreRenderer
        self._formEffects = formEffects
        self._ribbonEffects = ribbonEffects
        self._baseTrace = coreRenderer._trace
        self._formMask: Optional[np.ndarray] = None
        self._ribbonMask: Optional[np.ndarray] = None
        coreRenderer._trace = self._captureTrace

    #
    # Properties
    #

    # PROPERTY :: VOID -> (ANY?, ANY?)
    # Exposes the latest visible masks for renderer verification
    @property
    def visibleMasks(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        return self._formMask, self._ribbonMask

    #
    # Instance Methods
    #

    # :: ANY, ANY, FLOAT, INT?, ARRAY<STRING, FLOAT> -> (ANY, ANY)
    # Rebuilds the foreground from independently processed transparent materials
    def apply(
        self,
        foreground: np.ndarray,
        alpha: np.ndarray,
        timeSec: float,
        frameIndex: Optional[int],
        signals: Any,
    ) -> Tuple[np.ndarray, np.ndarray]:
        if self._formMask is None or self._ribbonMask is None:
            return foreground, alpha
        formAlpha = np.clip(alpha * self._formMask, 0.0, 1.0)
        ribbonAlpha = np.clip(alpha * self._ribbonMask, 0.0, 1.0)
        restAlpha = np.clip(alpha - formAlpha - ribbonAlpha, 0.0, 1.0)
        restPremultiplied = foreground * restAlpha[..., None]
        outputPremultiplied = restPremultiplied
        outputAlpha = restAlpha
        for chain, layerAlpha in (
            (self._formEffects, formAlpha),
            (self._ribbonEffects, ribbonAlpha),
        ):
            if chain is None or not np.any(layerAlpha > 0.0):
                layerColor = foreground
                processedAlpha = layerAlpha
            else:
                layerRgb = np.clip(foreground * 255.0, 0.0, 255.0).astype(np.uint8)
                layerBgr = cv2.cvtColor(layerRgb, cv2.COLOR_RGB2BGR)
                layerBgr[layerAlpha <= 0.0] = 0
                processedBgr, processedAlpha = chain.applyLayer(
                    layerBgr,
                    layerAlpha,
                    timeSec,
                    frameIndex,
                    signals,
                )
                layerColor = cv2.cvtColor(processedBgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            outputPremultiplied = (
                layerColor * processedAlpha[..., None]
                + outputPremultiplied * (1.0 - processedAlpha[..., None])
            )
            outputAlpha = processedAlpha + outputAlpha * (1.0 - processedAlpha)
        output = outputPremultiplied / np.maximum(outputAlpha[..., None], 1e-6)
        return output.astype(np.float32), np.clip(outputAlpha, 0.0, 1.0).astype(np.float32)

    #
    # Protected Methods
    #

    # :: *ANY, **ANY -> ANY
    # Captures the frontmost material for the primary ray pass only
    def _captureTrace(self, *arguments: Any, **keywords: Any) -> Any:
        result = self._baseTrace(*arguments, **keywords)
        if len(arguments) < 7:
            return result
        eye, rayX, rayY, rayZ, coreFrame, decorFrame, _ = arguments[:7]
        if np.asarray(rayX).size != self._renderer.w * self._renderer.h:
            return result
        hit = result[1]
        distance = result[2]
        material = np.zeros(hit.shape, np.uint8)
        hitIndex = np.nonzero(hit)[0]
        if hitIndex.size and decorFrame is not None and self._renderer.decor is not None:
            pointX = eye[0] + rayX[hitIndex] * distance[hitIndex]
            pointY = eye[1] + rayY[hitIndex] * distance[hitIndex]
            pointZ = eye[2] + rayZ[hitIndex] * distance[hitIndex]
            coreDistance = self._renderer.core.sdf(pointX, pointY, pointZ, coreFrame)
            ribbonDistance, plateDistance = self._renderer.decor.sdf_parts(
                pointX,
                pointY,
                pointZ,
                decorFrame,
            )
            material[hitIndex] = np.argmin(
                np.stack([coreDistance, ribbonDistance, plateDistance]),
                axis=0,
            ).astype(np.uint8)
        materialImage = material.reshape(self._renderer.h, self._renderer.w)
        hitImage = hit.reshape(self._renderer.h, self._renderer.w)
        form = ((materialImage == 0) & hitImage).astype(np.float32)
        ribbon = ((materialImage == 1) & hitImage).astype(np.float32)
        outputSize = (self._renderer.W, self._renderer.H)
        self._formMask = cv2.resize(form, outputSize, interpolation=cv2.INTER_NEAREST)
        self._ribbonMask = cv2.resize(ribbon, outputSize, interpolation=cv2.INTER_NEAREST)
        return result

    #
    # Class Methods
    #

    # Class Factory Method :: ANY, effectChain?, effectChain? -> layerEffects
    # Creates a material-aware foreground effect compositor
    @classmethod
    def init(
        cls,
        coreRenderer: Any,
        formEffects: Optional[EffectChain],
        ribbonEffects: Optional[EffectChain],
    ) -> LayerEffects:
        return cls(coreRenderer, formEffects, ribbonEffects)
