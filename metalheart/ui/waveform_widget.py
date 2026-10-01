# Audio-energy waveform and hard-cut scene timeline

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

from typing import Any, Dict, List, Optional  # Python 3.8-compatible collection annotations

import numpy as np  # Store and normalize cached audio-energy samples
from PySide6.QtCore import QPointF  # Build waveform drawing points
from PySide6.QtCore import QRectF  # Define scene and waveform drawing regions
from PySide6.QtCore import Qt  # Interpret mouse buttons and widget orientation
from PySide6.QtCore import Signal  # Publish scene and playhead selections
from PySide6.QtGui import QColor  # Color timeline regions and waveform traces
from PySide6.QtGui import QMouseEvent  # Type native pointer events
from PySide6.QtGui import QPainter  # Draw the lightweight timeline without a web view
from PySide6.QtGui import QPaintEvent  # Type native paint events
from PySide6.QtGui import QPen  # Configure waveform and playhead strokes
from PySide6.QtWidgets import QSizePolicy  # Let the timeline expand horizontally
from PySide6.QtWidgets import QWidget  # Host the custom native timeline


# Displays analyzed audio energy beneath selectable hard-cut scene regions
class WaveformTimelineWidget(QWidget):

    sceneSelected = Signal(int, float)

    # CONSTRUCTOR :: widget? -> waveformTimelineWidget
    # Creates an empty low-cost scene timeline
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scenes: List[Dict[str, Any]] = []
        self._samples = np.zeros(0, dtype=np.float32)
        self._selectedScene = -1
        self._position = 0.5
        self._dragging = False
        self.setObjectName("sceneTimeline")
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    #
    # Properties
    #

    # PROPERTY :: VOID -> INT
    # Returns the selected scene index
    @property
    def selectedScene(self) -> int:
        return self._selectedScene

    # PROPERTY :: VOID -> FLOAT
    # Returns the normalized playhead position inside the selected scene
    @property
    def position(self) -> float:
        return self._position

    #
    # Instance Methods
    #

    # :: [ARRAY<STRING, ANY>], ANY -> NONE
    # Loads scene ranges and optional normalized analysis samples
    def setTimeline(self, scenes: List[Dict[str, Any]], samples: Any) -> None:
        self._scenes = list(scenes)
        values = np.asarray(samples if samples is not None else [], dtype=np.float32).reshape(-1)
        if values.size:
            maximum = float(np.max(np.abs(values)))
            self._samples = values / maximum if maximum > 1e-9 else values
        else:
            self._samples = values
        if not self._scenes:
            self._selectedScene = -1
        elif self._selectedScene < 0 or self._selectedScene >= len(self._scenes):
            self._selectedScene = 0
        self.update()

    # :: INT, FLOAT -> NONE
    # Moves the visual playhead without emitting a user selection
    def selectScene(self, index: int, position: float = 0.5) -> None:
        if not self._scenes:
            self._selectedScene = -1
            self.update()
            return
        self._selectedScene = min(max(index, 0), len(self._scenes) - 1)
        self._position = min(max(float(position), 0.0), 1.0)
        self.update()

    # :: qPaintEvent -> NONE
    # Draws scene blocks, the energy envelope, labels, and playhead
    # NOTE: The name is fixed by the Qt override contract
    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), QColor("#090c0d"))
        if not self._scenes:
            painter.setPen(QColor("#758184"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Load audio to create a scene timeline")
            painter.end()
            return
        timeline = QRectF(8.0, 8.0, max(float(self.width() - 16), 1.0), max(float(self.height() - 16), 1.0))
        duration = self._duration()
        self._drawScenes(painter, timeline, duration)
        self._drawWaveform(painter, timeline)
        self._drawPlayhead(painter, timeline, duration)
        painter.end()

    # :: qMouseEvent -> NONE
    # Selects a scene and playhead from a native pointer press
    # NOTE: The name is fixed by the Qt override contract
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._selectAtX(float(event.position().x()))

    # :: qMouseEvent -> NONE
    # Scrubs the playhead while the primary pointer button is held
    # NOTE: The name is fixed by the Qt override contract
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._selectAtX(float(event.position().x()))

    # :: qMouseEvent -> NONE
    # Ends native playhead scrubbing
    # NOTE: The name is fixed by the Qt override contract
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

    #
    # Protected Methods
    #

    # :: qPainter, qRectF, FLOAT -> NONE
    # Paints alternating scene regions and compact identifiers
    def _drawScenes(self, painter: QPainter, timeline: QRectF, duration: float) -> None:
        for index, scene in enumerate(self._scenes):
            start = float(scene.get("start_sec", 0.0)) / duration
            end = float(scene.get("end_sec", duration)) / duration
            left = timeline.left() + timeline.width() * start
            width = max(1.0, timeline.width() * (end - start))
            color = QColor("#17383b") if index == self._selectedScene else QColor(
                "#10191b" if index % 2 == 0 else "#131e20"
            )
            painter.fillRect(QRectF(left, timeline.top(), width, timeline.height()), color)
            painter.setPen(QColor("#34484b"))
            painter.drawLine(int(left), int(timeline.top()), int(left), int(timeline.bottom()))
            if width > 42.0:
                painter.setPen(QColor("#9fb1b3"))
                label = str(scene.get("name", scene.get("id", index + 1)))
                painter.drawText(
                    QRectF(left + 5.0, timeline.top() + 4.0, width - 10.0, 18.0),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    label,
                )

    # :: qPainter, qRectF -> NONE
    # Paints a downsampled symmetric energy envelope
    def _drawWaveform(self, painter: QPainter, timeline: QRectF) -> None:
        center = timeline.center().y() + 8.0
        amplitude = max(8.0, timeline.height() * 0.31)
        painter.setPen(QPen(QColor("#51d2d7"), 1.0))
        if not self._samples.size:
            painter.drawLine(int(timeline.left()), int(center), int(timeline.right()), int(center))
            return
        width = max(1, int(timeline.width()))
        step = max(1, int(np.ceil(self._samples.size / float(width))))
        pointsTop: List[QPointF] = []
        pointsBottom: List[QPointF] = []
        for pixel in range(width):
            first = min(pixel * step, self._samples.size - 1)
            last = min(first + step, self._samples.size)
            value = float(np.max(np.abs(self._samples[first:last])))
            x = timeline.left() + pixel
            pointsTop.append(QPointF(x, center - value * amplitude))
            pointsBottom.append(QPointF(x, center + value * amplitude))
        if len(pointsTop) > 1:
            painter.drawPolyline(pointsTop)
            painter.drawPolyline(pointsBottom)

    # :: qPainter, qRectF, FLOAT -> NONE
    # Paints the selected absolute scene time as a high-contrast playhead
    def _drawPlayhead(self, painter: QPainter, timeline: QRectF, duration: float) -> None:
        if self._selectedScene < 0 or self._selectedScene >= len(self._scenes):
            return
        scene = self._scenes[self._selectedScene]
        start = float(scene.get("start_sec", 0.0))
        end = float(scene.get("end_sec", start))
        timeSec = start + (end - start) * self._position
        x = timeline.left() + timeline.width() * timeSec / duration
        painter.setPen(QPen(QColor("#ffcf66"), 2.0))
        painter.drawLine(int(x), int(timeline.top()), int(x), int(timeline.bottom()))

    # :: FLOAT -> NONE
    # Converts a horizontal pointer location into scene and relative position
    def _selectAtX(self, x: float) -> None:
        if not self._scenes:
            return
        width = max(float(self.width() - 16), 1.0)
        absolute = min(max((x - 8.0) / width, 0.0), 1.0) * self._duration()
        index = len(self._scenes) - 1
        for candidate, scene in enumerate(self._scenes):
            if absolute < float(scene.get("end_sec", 0.0)):
                index = candidate
                break
        scene = self._scenes[index]
        start = float(scene.get("start_sec", 0.0))
        end = float(scene.get("end_sec", start + 1.0))
        position = (absolute - start) / max(end - start, 1e-9)
        self._selectedScene = index
        self._position = min(max(position, 0.0), 1.0)
        self.update()
        self.sceneSelected.emit(index, self._position)

    # :: VOID -> FLOAT
    # Returns a safe total timeline duration
    def _duration(self) -> float:
        if not self._scenes:
            return 1.0
        return max(float(self._scenes[-1].get("end_sec", 1.0)), 1e-9)
