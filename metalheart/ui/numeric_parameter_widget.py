# Combined slider and editable number field for catalog-driven parameters

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

from typing import Any, Optional  # Type numeric values and optional native parents

from PySide6.QtCore import Qt  # Configure the horizontal native slider
from PySide6.QtCore import Signal  # Publish one committed authored value
from PySide6.QtWidgets import QDoubleSpinBox  # Preserve precise decimal keyboard entry
from PySide6.QtWidgets import QHBoxLayout  # Pair the slider with its number field
from PySide6.QtWidgets import QSlider  # Provide fast bounded parameter adjustment
from PySide6.QtWidgets import QSpinBox  # Preserve exact integer keyboard entry
from PySide6.QtWidgets import QWidget  # Host the reusable compound control


MAX_SLIDER_POSITIONS = 10000


# Couples fast slider adjustment with precise directly editable numeric input
class NumericParameterWidget(QWidget):

    valueCommitted = Signal(object)

    # CONSTRUCTOR :: FLOAT, FLOAT, FLOAT, INT|FLOAT, BOOL, widget? -> numericParameterWidget
    # Creates a bounded slider and number field with one commit signal
    def __init__(
        self,
        minimum: float,
        maximum: float,
        step: float,
        value: Any,
        isInteger: bool,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._minimum = float(minimum)
        self._maximum = max(float(maximum), self._minimum)
        self._step = max(float(step), 1.0 if isInteger else 1e-6)
        self._isInteger = isInteger
        span = self._maximum - self._minimum
        requestedPositions = int(round(span / self._step)) if span > 0.0 else 1
        self._positions = min(max(requestedPositions, 1), MAX_SLIDER_POSITIONS)
        self._loading = False
        self._lastCommitted: Any = None
        self.setObjectName("numericParameter")
        self._buildUi(value)

    #
    # Properties
    #

    # PROPERTY :: VOID -> INT|FLOAT
    # Returns the exact value in the directly editable number field
    @property
    def value(self) -> Any:
        current = self._numberField.value()
        return int(current) if self._isInteger else float(current)

    # PROPERTY :: VOID -> qSlider
    # Returns the native slider for focused UI tests and accessibility
    @property
    def slider(self) -> QSlider:
        return self._slider

    # PROPERTY :: VOID -> widget
    # Returns the directly editable native number field
    @property
    def numberField(self) -> QWidget:
        return self._numberField

    #
    # Instance Methods
    #

    # :: INT|FLOAT -> NONE
    # Replaces the displayed value without publishing an authored edit
    def setValue(self, value: Any) -> None:
        bounded = self._boundedValue(value)
        self._loading = True
        self._numberField.setValue(bounded)
        self._slider.setValue(self._positionForValue(float(bounded)))
        self._loading = False
        self._lastCommitted = self.value

    #
    # Protected Methods
    #

    # :: INT|FLOAT -> NONE
    # Builds and connects the paired native inputs
    def _buildUi(self, value: Any) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setObjectName("numericSlider")
        self._slider.setRange(0, self._positions)
        self._slider.setPageStep(max(1, self._positions // 10))
        self._slider.valueChanged.connect(self._sliderChanged)
        self._slider.sliderReleased.connect(self._commitValue)
        if self._isInteger:
            integer = QSpinBox()
            integer.setRange(int(round(self._minimum)), int(round(self._maximum)))
            integer.setSingleStep(max(1, int(round(self._step))))
            self._numberField = integer
        else:
            number = QDoubleSpinBox()
            number.setRange(self._minimum, self._maximum)
            number.setSingleStep(self._step)
            number.setDecimals(self._decimalPlaces(self._step))
            self._numberField = number
        self._numberField.setObjectName("numericValue")
        self._numberField.setKeyboardTracking(False)
        self._numberField.setMinimumWidth(88)
        self._numberField.valueChanged.connect(self._numberChanged)
        self._numberField.editingFinished.connect(self._commitValue)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._numberField)
        self.setToolTip(
            "Range {0} to {1}; step {2}".format(
                self._minimum,
                self._maximum,
                self._step,
            )
        )
        self.setValue(value)

    # :: INT -> NONE
    # Synchronizes the number field while the slider moves
    def _sliderChanged(self, position: int) -> None:
        if self._loading:
            return
        value = self._valueForPosition(position)
        self._loading = True
        self._numberField.setValue(value)
        self._loading = False
        if not self._slider.isSliderDown():
            self._commitValue()

    # :: INT|FLOAT -> NONE
    # Synchronizes the slider while preserving exact number-field input
    def _numberChanged(self, value: Any) -> None:
        if self._loading:
            return
        self._loading = True
        self._slider.setValue(self._positionForValue(float(value)))
        self._loading = False

    # :: VOID -> NONE
    # Publishes a changed value once at the end of one user interaction
    def _commitValue(self) -> None:
        if self._loading:
            return
        value = self.value
        if value == self._lastCommitted:
            return
        self._lastCommitted = value
        self.valueCommitted.emit(value)

    # :: FLOAT -> INT
    # Maps an exact numeric value onto the bounded slider domain
    def _positionForValue(self, value: float) -> int:
        span = self._maximum - self._minimum
        if span <= 0.0:
            return 0
        normalized = (min(max(value, self._minimum), self._maximum) - self._minimum) / span
        return int(round(normalized * self._positions))

    # :: INT -> INT|FLOAT
    # Maps one slider position back to the catalog numeric domain
    def _valueForPosition(self, position: int) -> Any:
        if self._positions <= 0:
            value = self._minimum
        else:
            value = self._minimum + (
                self._maximum - self._minimum
            ) * position / float(self._positions)
        return int(round(value)) if self._isInteger else round(
            value,
            self._decimalPlaces(self._step),
        )

    # :: INT|FLOAT -> INT|FLOAT
    # Clamps an incoming value to the native field range
    def _boundedValue(self, value: Any) -> Any:
        bounded = min(max(float(value), self._minimum), self._maximum)
        return int(round(bounded)) if self._isInteger else bounded

    # :: FLOAT -> INT
    # Derives enough decimal places to preserve the catalog step
    def _decimalPlaces(self, step: float) -> int:
        rendered = "{0:.8f}".format(step).rstrip("0").rstrip(".")
        return min(8, len(rendered.split(".")[1]) if "." in rendered else 0)

    #
    # Class Methods
    #

    # Class Factory Method :: FLOAT, FLOAT, FLOAT, INT|FLOAT, BOOL, widget? -> numericParameterWidget
    # Creates a combined numeric parameter control
    @classmethod
    def init(
        cls,
        minimum: float,
        maximum: float,
        step: float,
        value: Any,
        isInteger: bool,
        parent: Optional[QWidget] = None,
    ) -> NumericParameterWidget:
        return cls(minimum, maximum, step, value, isInteger, parent)
