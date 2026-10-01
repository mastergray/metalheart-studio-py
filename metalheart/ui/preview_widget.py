# Aspect-preserving Qt display surface for Metalheart preview frames

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import numpy as np  # Validate RGB preview arrays
from typing import Optional  # Preserve Python 3.8-compatible optional annotations
from PySide6.QtCore import Qt  # Configure native alignment and scaling
from PySide6.QtGui import QImage  # Copy NumPy frame storage into Qt
from PySide6.QtGui import QPixmap  # Display and scale copied images
from PySide6.QtGui import QResizeEvent  # Type the resize override
from PySide6.QtWidgets import QLabel  # Provide the lightweight image surface
from PySide6.QtWidgets import QSizePolicy  # Allow the preview to expand with the window


# Displays copied RGB frames without retaining worker-owned NumPy storage
class PreviewWidget(QLabel):

    # CONSTRUCTOR :: VOID -> previewWidget
    # Creates an expandable dark preview surface
    def __init__(self) -> None:
        super().__init__()
        self._image: Optional[QImage] = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setText("Create a project from audio or open an existing project")
        self.setStyleSheet("background: #07090a; border: 1px solid #303638; color: #687577;")

    #
    # Instance Methods
    #

    # :: ANY -> NONE
    # Copies one HxWx3 RGB byte frame into Qt-owned image memory
    def setFrame(self, frame: np.ndarray) -> None:
        if frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
            raise ValueError("preview frame must be an HxWx3 uint8 array")
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

    # :: STRING -> NONE
    # Shows a centered status message without discarding the last valid image
    def setMessage(self, message: str) -> None:
        self.clear()
        self.setText(message)

    # :: qResizeEvent -> NONE
    # Refreshes the scaled pixmap after a native resize
    # NOTE: The name is fixed by the Qt override contract
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._updatePixmap()

    #
    # Protected Methods
    #

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
