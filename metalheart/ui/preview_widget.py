# Native still and bounded-range preview playback with a persistent stale indicator

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

from pathlib import Path  # Load source audio through a native file URL
from typing import List, Optional  # Preserve Python 3.8-compatible collections

import numpy as np  # Validate and retain RGB preview arrays
from PySide6.QtCore import QTimer  # Advance bounded preview frames without video codecs
from PySide6.QtCore import Qt  # Configure native alignment and scaling
from PySide6.QtCore import Signal  # Publish native playback state changes
from PySide6.QtGui import QCloseEvent  # Stop isolated playback when the widget closes
from PySide6.QtGui import QImage  # Copy NumPy frame storage into Qt
from PySide6.QtGui import QPixmap  # Display and scale copied images
from PySide6.QtGui import QResizeEvent  # Type the resize override
from PySide6.QtWidgets import QLabel  # Provide the lightweight image surface and badge
from PySide6.QtWidgets import QSizePolicy  # Allow the preview to expand with the window

from metalheart.ui.preview_audio_player import PreviewAudioPlayer  # Isolate backend stalls


# Displays copied RGB stills or short native frame sequences with synchronized audio
class PreviewWidget(QLabel):

    # Class Variables
    playbackChanged = Signal(bool)

    # CONSTRUCTOR :: VOID -> previewWidget
    # Creates an expandable dark preview surface and native audio player
    def __init__(self) -> None:
        super().__init__()
        self._image: Optional[QImage] = None
        self._frames: List[np.ndarray] = []
        self._frameIndex = 0
        self._fps = 1
        self._audioPath = ""
        self._audioStartMs = 0
        self._audioEndMs = 0
        self._stale = False
        self._muted = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advanceFrame)
        self._audioPlayback = PreviewAudioPlayer.init(self)
        self._staleBadge = QLabel("STALE PREVIEW", self)
        self._staleBadge.setObjectName("previewStaleBadge")
        self._staleBadge.setStyleSheet(
            "background: #7a4d0f; color: #fff0c2; border: 1px solid #d89b3c; "
            "border-radius: 3px; font-weight: bold; padding: 4px 7px;"
        )
        self._staleBadge.setVisible(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setText("Create a project from audio or open an existing project")
        self.setStyleSheet(
            "background: #07090a; border: 1px solid #303638; color: #687577;"
        )

    #
    # Properties
    #

    # PROPERTY :: VOID -> BOOL
    # Reports whether a rendered still or range remains available
    @property
    def hasPreview(self) -> bool:
        return self._image is not None

    # PROPERTY :: VOID -> BOOL
    # Reports whether the current rendered result contains multiple frames
    @property
    def isClip(self) -> bool:
        return len(self._frames) > 1

    # PROPERTY :: VOID -> BOOL
    # Reports whether the visible result predates the current selection or config
    @property
    def isStale(self) -> bool:
        return self._stale

    # PROPERTY :: VOID -> BOOL
    # Reports whether the native frame timer is active
    @property
    def isPlaying(self) -> bool:
        return self._timer.isActive()

    # PROPERTY :: VOID -> BOOL
    # Reports whether source-audio playback is muted
    @property
    def isMuted(self) -> bool:
        return self._muted

    # PROPERTY :: VOID -> INT
    # Returns the number of retained bounded preview frames
    @property
    def frameCount(self) -> int:
        return max(len(self._frames), 1 if self._image is not None else 0)

    #
    # Instance Methods
    #

    # :: ANY -> NONE
    # Replaces playback with one copied HxWx3 RGB byte frame
    def setFrame(self, frame: np.ndarray) -> None:
        self.pause()
        self._frames = []
        self._frameIndex = 0
        self._audioPath = ""
        self._displayFrame(frame)
        self.setStale(False)

    # :: [ANY], INT, STRING, FLOAT, FLOAT -> NONE
    # Replaces the result with a looping bounded frame sequence and source audio
    def setClip(
        self,
        frames: List[np.ndarray],
        fps: int,
        audioPath: str,
        startSec: float,
        endSec: float,
    ) -> None:
        if not frames:
            raise ValueError("preview clip requires at least one frame")
        for frame in frames:
            self._validateFrame(frame)
        self.pause()
        self._frames = list(frames)
        self._frameIndex = 0
        self._fps = max(1, int(fps))
        self._audioPath = str(Path(audioPath).resolve())
        self._audioStartMs = max(0, int(round(startSec * 1000.0)))
        self._audioEndMs = max(
            self._audioStartMs + 1,
            int(round(endSec * 1000.0)),
        )
        self._displayFrame(self._frames[0])
        self.setStale(False)
        if len(self._frames) > 1:
            self.play()

    # :: STRING -> NONE
    # Clears every rendered result and shows a centered status message
    def setMessage(self, message: str) -> None:
        self.pause()
        self._audioPath = ""
        self._frames = []
        self._frameIndex = 0
        self._image = None
        self._stale = False
        self._staleBadge.setVisible(False)
        self.clear()
        self.setText(message)

    # :: BOOL -> NONE
    # Marks the retained result as outdated without interrupting playback
    def setStale(self, stale: bool) -> None:
        self._stale = bool(stale) and self.hasPreview
        self._staleBadge.setVisible(self._stale)
        if self._stale:
            self._positionBadge()
            self._staleBadge.raise_()

    # :: VOID -> NONE
    # Starts or resumes looping frame and source-audio playback
    def play(self) -> None:
        if len(self._frames) < 2 or self._timer.isActive():
            return
        interval = max(1, int(round(1000.0 / float(self._fps))))
        self._timer.start(interval)
        if not self._muted:
            self._startAudio()
        self.playbackChanged.emit(True)

    # :: VOID -> NONE
    # Pauses frame and audio playback without discarding the result
    def pause(self) -> None:
        wasPlaying = self._timer.isActive()
        self._timer.stop()
        self._audioPlayback.stop()
        if wasPlaying:
            self.playbackChanged.emit(False)

    # :: VOID -> NONE
    # Stops playback and returns a retained range to its first frame
    def stop(self) -> None:
        wasPlaying = self._timer.isActive()
        self._timer.stop()
        self._audioPlayback.stop()
        if self._frames:
            self._frameIndex = 0
            self._displayFrame(self._frames[0])
        if wasPlaying:
            self.playbackChanged.emit(False)

    # :: BOOL -> NONE
    # Mutes or restores source audio without affecting visual playback
    def setMuted(self, muted: bool) -> None:
        self._muted = bool(muted)
        if self._muted:
            self._audioPlayback.stop()
        elif self._timer.isActive():
            self._startAudio()

    # :: VOID -> NONE
    # Toggles the current bounded clip between playing and paused
    def togglePlayback(self) -> None:
        if self.isPlaying:
            self.pause()
        else:
            self.play()

    # :: qResizeEvent -> NONE
    # Refreshes the scaled pixmap and stale badge after a native resize
    # NOTE: The name is fixed by the Qt override contract
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._updatePixmap()
        self._positionBadge()

    # :: qCloseEvent -> NONE
    # Stops disposable audio playback before the preview widget closes
    # NOTE: The name is fixed by the Qt override contract
    def closeEvent(self, event: QCloseEvent) -> None:
        self._audioPlayback.stop()
        super().closeEvent(event)

    #
    # Protected Methods
    #

    # :: VOID -> NONE
    # Advances one frame and loops both the image range and source audio
    def _advanceFrame(self) -> None:
        if len(self._frames) < 2:
            return
        self._frameIndex += 1
        if self._frameIndex >= len(self._frames):
            self._frameIndex = 0
            if not self._muted:
                self._startAudio()
        self._displayFrame(self._frames[self._frameIndex])

    # :: VOID -> NONE
    # Starts isolated audio at the visual frame's current source position
    def _startAudio(self) -> None:
        offsetMs = int(round(self._frameIndex * 1000.0 / self._fps))
        self._audioPlayback.play(
            self._audioPath,
            self._audioStartMs + offsetMs,
            self._audioEndMs,
        )

    # :: ANY -> NONE
    # Copies one worker-owned RGB frame into Qt-owned display memory
    def _displayFrame(self, frame: np.ndarray) -> None:
        self._validateFrame(frame)
        height, width, _ = frame.shape
        image = QImage(
            frame.data,
            width,
            height,
            int(frame.strides[0]),
            QImage.Format.Format_RGB888,
        )
        self._image = image.copy()
        self.setText("")
        self._updatePixmap()

    # :: ANY -> NONE
    # Rejects invalid frame storage before Qt reads its bytes
    def _validateFrame(self, frame: np.ndarray) -> None:
        if frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
            raise ValueError("preview frame must be an HxWx3 uint8 array")

    # :: VOID -> NONE
    # Uses fast scaling to keep interaction inexpensive on older hardware
    def _updatePixmap(self) -> None:
        if self._image is None:
            return
        pixmap = QPixmap.fromImage(self._image).scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.setPixmap(pixmap)

    # :: VOID -> NONE
    # Anchors the stale badge inside the visible preview surface
    def _positionBadge(self) -> None:
        self._staleBadge.adjustSize()
        self._staleBadge.move(
            max(8, self.width() - self._staleBadge.width() - 12),
            12,
        )
