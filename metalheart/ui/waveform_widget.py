# Audio-energy waveform and hard-cut scene timeline

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

from typing import Any, Dict, List, Optional, Tuple  # Python 3.8-compatible collection annotations

import numpy as np  # Store and normalize cached audio-energy samples
from PySide6.QtCore import QPointF  # Build waveform drawing points
from PySide6.QtCore import QRectF  # Define scene and waveform drawing regions
from PySide6.QtCore import Qt  # Interpret mouse buttons and widget orientation
from PySide6.QtCore import Signal  # Publish scene, playhead, and range selections
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
    rangeChanged = Signal(float, float, str)

    # CONSTRUCTOR :: widget? -> waveformTimelineWidget
    # Creates an empty low-cost scene timeline
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scenes: List[Dict[str, Any]] = []
        self._samples = np.zeros(0, dtype=np.float32)
        self._selectedScene = -1
        self._position = 0.5
        self._rangeStart = 0.0
        self._rangeEnd = 1.0
        self._dragTarget: Optional[str] = None
        self.setObjectName("sceneTimeline")
        self.setMinimumHeight(118)
        self.setMouseTracking(True)
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

    # PROPERTY :: VOID -> FLOAT
    # Returns the normalized selected-range in point
    @property
    def rangeStart(self) -> float:
        return self._rangeStart

    # PROPERTY :: VOID -> FLOAT
    # Returns the normalized selected-range out point
    @property
    def rangeEnd(self) -> float:
        return self._rangeEnd

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

    # :: FLOAT, FLOAT -> NONE
    # Moves the visual in and out handles without emitting a user edit
    def setPreviewRange(self, start: float, end: float) -> None:
        safeStart = min(max(float(start), 0.0), 1.0)
        safeEnd = min(max(float(end), 0.0), 1.0)
        if safeEnd <= safeStart:
            safeEnd = min(safeStart + 0.001, 1.0)
            safeStart = min(safeStart, safeEnd - 0.001)
        self._rangeStart = safeStart
        self._rangeEnd = safeEnd
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
        timeline = self._timelineRect()
        duration = self._duration()
        self._drawScenes(painter, timeline, duration)
        self._drawRangeSelection(painter, timeline, duration)
        self._drawWaveform(painter, timeline)
        self._drawRangeHandles(painter, timeline, duration)
        self._drawPlayhead(painter, timeline, duration)
        painter.end()

    # :: qMouseEvent -> NONE
    # Selects a scene and playhead from a native pointer press
    # NOTE: The name is fixed by the Qt override contract
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            x = float(event.position().x())
            self._dragTarget = self._rangeHandleAtX(x) or "playhead"
            if self._dragTarget == "playhead":
                self._selectAtX(x)
            else:
                self._moveRangeAtX(x)

    # :: qMouseEvent -> NONE
    # Scrubs the playhead while the primary pointer button is held
    # NOTE: The name is fixed by the Qt override contract
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        x = float(event.position().x())
        if self._dragTarget == "playhead":
            self._selectAtX(x)
        elif self._dragTarget is not None:
            self._moveRangeAtX(x)
        elif self._rangeHandleAtX(x) is not None:
            self.setCursor(Qt.CursorShape.SplitHCursor)
        else:
            self.unsetCursor()

    # :: qMouseEvent -> NONE
    # Ends native playhead scrubbing
    # NOTE: The name is fixed by the Qt override contract
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragTarget = None
            if self._rangeHandleAtX(float(event.position().x())) is None:
                self.unsetCursor()

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
    # Shades the scene-local source interval selected for range preview
    def _drawRangeSelection(
        self,
        painter: QPainter,
        timeline: QRectF,
        duration: float,
    ) -> None:
        coordinates = self._rangeCoordinates(timeline, duration)
        if coordinates is None:
            return
        startX, endX = coordinates
        painter.fillRect(
            QRectF(startX, timeline.top(), max(endX - startX, 1.0), timeline.height()),
            QColor(39, 138, 145, 72),
        )

    # :: qPainter, qRectF, FLOAT -> NONE
    # Paints distinct draggable source-time handles over the waveform
    def _drawRangeHandles(
        self,
        painter: QPainter,
        timeline: QRectF,
        duration: float,
    ) -> None:
        coordinates = self._rangeCoordinates(timeline, duration)
        if coordinates is None:
            return
        startX, endX = coordinates
        handles = [
            (startX, QColor("#63e6be"), "IN"),
            (endX, QColor("#ff8fb3"), "OUT"),
        ]
        for x, color, label in handles:
            painter.setPen(QPen(color, 2.0))
            painter.drawLine(int(x), int(timeline.top()), int(x), int(timeline.bottom()))
            painter.fillRect(QRectF(x - 3.0, timeline.bottom() - 18.0, 7.0, 18.0), color)
            painter.setPen(color)
            labelLeft = min(
                max(x - 18.0, timeline.left()),
                timeline.right() - 36.0,
            )
            painter.drawText(
                QRectF(labelLeft, timeline.bottom() - 36.0, 36.0, 16.0),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )

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

    # :: FLOAT -> STRING?
    # Returns the nearest range handle when the pointer is close enough to drag it
    def _rangeHandleAtX(self, x: float) -> Optional[str]:
        coordinates = self._rangeCoordinates(self._timelineRect(), self._duration())
        if coordinates is None:
            return None
        startX, endX = coordinates
        startDistance = abs(x - startX)
        endDistance = abs(x - endX)
        if min(startDistance, endDistance) > 9.0:
            return None
        return "start" if startDistance <= endDistance else "end"

    # :: FLOAT -> NONE
    # Moves the active in or out handle within the selected scene
    def _moveRangeAtX(self, x: float) -> None:
        if self._dragTarget not in ("start", "end"):
            return
        position = self._scenePositionAtX(x)
        if position is None:
            return
        minimumSpan = 0.001
        if self._dragTarget == "start":
            self._rangeStart = min(position, self._rangeEnd - minimumSpan)
        else:
            self._rangeEnd = max(position, self._rangeStart + minimumSpan)
        self.update()
        self.rangeChanged.emit(
            self._rangeStart,
            self._rangeEnd,
            self._dragTarget,
        )

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

    # :: FLOAT -> FLOAT?
    # Converts an absolute widget location to a clamped selected-scene position
    def _scenePositionAtX(self, x: float) -> Optional[float]:
        if self._selectedScene < 0 or self._selectedScene >= len(self._scenes):
            return None
        timeline = self._timelineRect()
        absolute = min(
            max((x - timeline.left()) / timeline.width(), 0.0),
            1.0,
        ) * self._duration()
        scene = self._scenes[self._selectedScene]
        start = float(scene.get("start_sec", 0.0))
        end = float(scene.get("end_sec", start + 1.0))
        return min(max((absolute - start) / max(end - start, 1e-9), 0.0), 1.0)

    # :: qRectF, FLOAT -> (FLOAT, FLOAT)?
    # Maps the selected scene's normalized range onto the full audio timeline
    def _rangeCoordinates(
        self,
        timeline: QRectF,
        duration: float,
    ) -> Optional[Tuple[float, float]]:
        if self._selectedScene < 0 or self._selectedScene >= len(self._scenes):
            return None
        scene = self._scenes[self._selectedScene]
        sceneStart = float(scene.get("start_sec", 0.0))
        sceneEnd = float(scene.get("end_sec", sceneStart))
        sceneDuration = max(sceneEnd - sceneStart, 0.0)
        startTime = sceneStart + sceneDuration * self._rangeStart
        endTime = sceneStart + sceneDuration * self._rangeEnd
        return (
            timeline.left() + timeline.width() * startTime / duration,
            timeline.left() + timeline.width() * endTime / duration,
        )

    # :: VOID -> qRectF
    # Returns the shared inset used for drawing and pointer mapping
    def _timelineRect(self) -> QRectF:
        return QRectF(
            8.0,
            8.0,
            max(float(self.width() - 16), 1.0),
            max(float(self.height() - 16), 1.0),
        )

    # :: VOID -> FLOAT
    # Returns a safe total timeline duration
    def _duration(self) -> float:
        if not self._scenes:
            return 1.0
        return max(float(self._scenes[-1].get("end_sec", 1.0)), 1e-9)
