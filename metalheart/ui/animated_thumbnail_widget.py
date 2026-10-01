# Native dependency-free playback for packaged option-preview spritesheets

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import math  # Derive spritesheet rows from manifest dimensions
from typing import List, Optional  # Store decoded frames and accept an optional parent

from PySide6.QtCore import QTimer  # Advance packaged preview frames without media codecs
from PySide6.QtCore import Qt  # Align and smoothly scale preview frames
from PySide6.QtGui import QPixmap  # Decode packaged PNG spritesheets
from PySide6.QtWidgets import QLabel  # Present one animated native preview surface
from PySide6.QtWidgets import QWidget  # Type the optional widget parent

from metalheart.ui.thumbnail_icons import thumbnailCatalog  # Share the validated manifest cache


PREVIEW_WIDTH = 256
PREVIEW_HEIGHT = 144


# Plays one packaged spritesheet without rendering or multimedia dependencies
class AnimatedThumbnailWidget(QLabel):

    # CONSTRUCTOR :: widget? -> animatedThumbnailWidget
    # Creates a hidden preview surface that becomes active for animated options
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._frames: List[QPixmap] = []
        self._frameIndex = 0
        self._frameDirection = 1
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advanceFrame)
        self.setObjectName("animatedOptionPreview")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self.setVisible(False)

    #
    # Properties
    #

    # PROPERTY :: VOID -> INT
    # Returns the decoded frame count for diagnostics and UI tests
    @property
    def frameCount(self) -> int:
        return len(self._frames)

    # PROPERTY :: VOID -> INT
    # Returns the frame currently displayed by the native timer
    @property
    def frameIndex(self) -> int:
        return self._frameIndex

    #
    # Instance Methods
    #

    # :: STRING, STRING -> NONE
    # Loads one current packaged animation or hides cleanly when unavailable
    def setOption(self, catalog: str, optionId: str) -> None:
        self._timer.stop()
        self._frames = []
        self._frameIndex = 0
        self._frameDirection = 1
        animation = thumbnailCatalog().animation(catalog, optionId)
        if animation is None:
            self.clear()
            self.setVisible(False)
            return
        sheet = QPixmap(str(animation["path"]))
        width = int(animation["width"])
        height = int(animation["height"])
        frameCount = int(animation["frame_count"])
        columns = int(animation["columns"])
        rows = int(math.ceil(frameCount / float(columns)))
        if sheet.isNull() or sheet.width() < columns * width or sheet.height() < rows * height:
            self.clear()
            self.setVisible(False)
            return
        for frameIndex in range(frameCount):
            row = frameIndex // columns
            column = frameIndex % columns
            frame = sheet.copy(column * width, row * height, width, height)
            self._frames.append(
                frame.scaled(
                    PREVIEW_WIDTH,
                    PREVIEW_HEIGHT,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self.setPixmap(self._frames[0])
        self.setVisible(True)
        interval = max(1, int(round(1000.0 / float(animation["fps"]))))
        self._timer.start(interval)

    #
    # Protected Methods
    #

    # :: VOID -> NONE
    # Advances one decoded frame and ping-pongs without disk or renderer work
    def _advanceFrame(self) -> None:
        if len(self._frames) < 2:
            return
        nextFrame = self._frameIndex + self._frameDirection
        if nextFrame >= len(self._frames):
            self._frameDirection = -1
            nextFrame = len(self._frames) - 2
        elif nextFrame < 0:
            self._frameDirection = 1
            nextFrame = 1
        self._frameIndex = nextFrame
        self.setPixmap(self._frames[self._frameIndex])

    #
    # Class Methods
    #

    # Class Factory Method :: widget? -> animatedThumbnailWidget
    # Creates a native packaged-animation surface
    @classmethod
    def init(cls, parent: Optional[QWidget] = None) -> AnimatedThumbnailWidget:
        return cls(parent)
