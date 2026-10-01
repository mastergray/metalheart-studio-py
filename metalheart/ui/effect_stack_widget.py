# Ordered per-layer effect stack editor generated from the owned effect catalog

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import copy  # Isolate widget state from the canonical authored document
from typing import Any, Dict, List, Optional  # Python 3.8-compatible collection annotations

from PySide6.QtCore import Qt  # Store stable effect identifiers on native list items
from PySide6.QtCore import Signal  # Publish authored stack changes
from PySide6.QtWidgets import QCheckBox  # Edit boolean parameters and effect bypass
from PySide6.QtWidgets import QComboBox  # Select effects and enumerated parameters
from PySide6.QtWidgets import QDoubleSpinBox  # Edit bounded floating-point properties
from PySide6.QtWidgets import QFormLayout  # Align dynamic parameter labels and controls
from PySide6.QtWidgets import QHBoxLayout  # Arrange stack actions compactly
from PySide6.QtWidgets import QLabel  # Label empty parameter state
from PySide6.QtWidgets import QLineEdit  # Edit uncommon free-form string parameters
from PySide6.QtWidgets import QListWidget  # Display ordered effect instances
from PySide6.QtWidgets import QListWidgetItem  # Attach effect identifiers to stack rows
from PySide6.QtWidgets import QPushButton  # Add, remove, and reorder effects
from PySide6.QtWidgets import QSpinBox  # Edit bounded integer properties
from PySide6.QtWidgets import QVBoxLayout  # Stack the editor sections
from PySide6.QtWidgets import QWidget  # Host the reusable native editor

from metalheart.effect_catalog import publicEffectCatalog  # Build controls from renderer metadata


# Edits an ordered effect chain including bypass, mix, order, and typed properties
class EffectStackWidget(QWidget):

    changed = Signal()

    # CONSTRUCTOR :: widget? -> effectStackWidget
    # Creates a reusable catalog-driven stack editor
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        catalog = publicEffectCatalog()
        self._catalog: List[Dict[str, Any]] = catalog
        self._definitions: Dict[str, Dict[str, Any]] = {
            str(entry["id"]): entry for entry in catalog
        }
        self._effects: List[Dict[str, Any]] = []
        self._parameterControls: Dict[str, QWidget] = {}
        self._loading = False
        self.setObjectName("effectStack")
        self._buildUi()

    #
    # Properties
    #

    # PROPERTY :: VOID -> [ARRAY<STRING, ANY>]
    # Returns an isolated canonical effect chain
    @property
    def effects(self) -> List[Dict[str, Any]]:
        return copy.deepcopy(self._effects)

    #
    # Instance Methods
    #

    # :: [ARRAY<STRING, ANY>] -> NONE
    # Replaces the visible chain with normalized editable effect instances
    def setEffects(self, effects: List[Dict[str, Any]]) -> None:
        self._loading = True
        self._effects = [self._normalizeEffect(effect) for effect in effects]
        self._refreshList(0 if self._effects else -1)
        self._loading = False

    # :: STRING -> NONE
    # Adds a catalog effect with its declared parameter defaults
    def addEffect(self, effectId: str) -> None:
        definition = self._definitions.get(effectId)
        if definition is None:
            return
        effect = self._normalizeEffect({"id": effectId})
        self._effects.append(effect)
        self._refreshList(len(self._effects) - 1)
        self._publishChange()

    #
    # Protected Methods
    #

    # :: VOID -> NONE
    # Builds the effect picker, ordered list, and dynamic parameter form
    def _buildUi(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        picker = QHBoxLayout()
        self._effectPicker = QComboBox()
        for entry in sorted(self._catalog, key=lambda item: (str(item["category"]), str(item["label"]))):
            self._effectPicker.addItem(
                "{0} — {1}".format(entry["category"], entry["label"]),
                entry["id"],
            )
        addButton = QPushButton("Add")
        addButton.clicked.connect(self._addSelected)
        picker.addWidget(self._effectPicker, 1)
        picker.addWidget(addButton)
        layout.addLayout(picker)

        self._list = QListWidget()
        self._list.setObjectName("effectStackList")
        self._list.setMinimumHeight(105)
        self._list.currentRowChanged.connect(self._effectSelected)
        layout.addWidget(self._list)

        actions = QHBoxLayout()
        removeButton = QPushButton("Remove")
        removeButton.clicked.connect(self._removeSelected)
        upButton = QPushButton("Up")
        upButton.clicked.connect(lambda: self._moveSelected(-1))
        downButton = QPushButton("Down")
        downButton.clicked.connect(lambda: self._moveSelected(1))
        actions.addWidget(removeButton)
        actions.addWidget(upButton)
        actions.addWidget(downButton)
        actions.addStretch(1)
        layout.addLayout(actions)

        self._parameterHost = QWidget()
        self._parameterForm = QFormLayout(self._parameterHost)
        self._parameterForm.setContentsMargins(0, 6, 0, 0)
        self._parameterForm.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.addWidget(self._parameterHost)
        self._showEmptyParameters()

    # :: ARRAY<STRING, ANY> -> ARRAY<STRING, ANY>
    # Expands one authored instance with catalog defaults for direct editing
    def _normalizeEffect(self, effect: Dict[str, Any]) -> Dict[str, Any]:
        effectId = str(effect.get("id", ""))
        definition = self._definitions.get(effectId, {"parameters": {}})
        parameters = {
            name: copy.deepcopy(metadata.get("default"))
            for name, metadata in definition.get("parameters", {}).items()
        }
        authoredParameters = effect.get("parameters", effect.get("props", {}))
        if isinstance(authoredParameters, dict):
            parameters.update(copy.deepcopy(authoredParameters))
        return {
            "id": effectId,
            "enabled": bool(effect.get("enabled", True)),
            "mix": float(effect.get("mix", 1.0)),
            "parameters": parameters,
        }

    # :: INT -> NONE
    # Rebuilds stable numbered list rows and selects one instance
    def _refreshList(self, selected: int) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for index, effect in enumerate(self._effects):
            definition = self._definitions.get(effect["id"], {})
            label = definition.get("label", effect["id"])
            prefix = "" if effect.get("enabled", True) else "[off] "
            item = QListWidgetItem("{0:02d}  {1}{2}".format(index + 1, prefix, label))
            item.setData(Qt.ItemDataRole.UserRole, effect["id"])
            self._list.addItem(item)
        self._list.setCurrentRow(selected)
        self._list.blockSignals(False)
        self._effectSelected(selected)

    # :: VOID -> NONE
    # Adds the effect selected in the catalog picker
    def _addSelected(self) -> None:
        effectId = self._effectPicker.currentData()
        if isinstance(effectId, str):
            self.addEffect(effectId)

    # :: VOID -> NONE
    # Removes the active effect instance from this layer only
    def _removeSelected(self) -> None:
        index = self._list.currentRow()
        if index < 0 or index >= len(self._effects):
            return
        self._effects.pop(index)
        self._refreshList(min(index, len(self._effects) - 1))
        self._publishChange()

    # :: INT -> NONE
    # Moves the active effect while preserving all instance parameters
    def _moveSelected(self, offset: int) -> None:
        index = self._list.currentRow()
        target = index + offset
        if index < 0 or target < 0 or target >= len(self._effects):
            return
        self._effects[index], self._effects[target] = self._effects[target], self._effects[index]
        self._refreshList(target)
        self._publishChange()

    # :: INT -> NONE
    # Builds typed controls for the selected effect instance
    def _effectSelected(self, index: int) -> None:
        self._clearParameterForm()
        self._parameterControls = {}
        if index < 0 or index >= len(self._effects):
            self._showEmptyParameters()
            return
        effect = self._effects[index]
        enabled = QCheckBox()
        enabled.setChecked(bool(effect["enabled"]))
        enabled.toggled.connect(lambda value: self._setEnabled(index, value))
        self._parameterForm.addRow("Enabled", enabled)
        mix = QDoubleSpinBox()
        mix.setRange(0.0, 1.0)
        mix.setSingleStep(0.01)
        mix.setDecimals(2)
        mix.setValue(float(effect["mix"]))
        mix.valueChanged.connect(lambda value: self._setMix(index, float(value)))
        self._parameterForm.addRow("Mix", mix)
        definition = self._definitions.get(effect["id"], {})
        for name, metadata in definition.get("parameters", {}).items():
            control = self._parameterControl(index, name, metadata, effect["parameters"].get(name))
            self._parameterControls[name] = control
            self._parameterForm.addRow(self._humanLabel(name), control)

    # :: INT, STRING, ARRAY<STRING, ANY>, ANY -> widget
    # Creates one native editor matching the catalog parameter type
    def _parameterControl(
        self,
        index: int,
        name: str,
        metadata: Dict[str, Any],
        value: Any,
    ) -> QWidget:
        valueType = metadata.get("type")
        allowed = metadata.get("enum")
        if allowed is not None:
            control = QComboBox()
            control.addItems([str(item) for item in allowed])
            control.setCurrentText(str(value))
            control.currentTextChanged.connect(
                lambda current: self._setParameter(index, name, current)
            )
            return control
        if valueType == "integer":
            integer = QSpinBox()
            integer.setRange(int(metadata.get("minimum", -100000)), int(metadata.get("maximum", 100000)))
            integer.setSingleStep(int(metadata.get("step", 1)))
            integer.setValue(int(value))
            integer.valueChanged.connect(
                lambda current: self._setParameter(index, name, int(current))
            )
            return integer
        if valueType == "number":
            number = QDoubleSpinBox()
            number.setRange(float(metadata.get("minimum", -100000.0)), float(metadata.get("maximum", 100000.0)))
            number.setSingleStep(float(metadata.get("step", 0.01)))
            number.setDecimals(4)
            number.setValue(float(value))
            number.valueChanged.connect(
                lambda current: self._setParameter(index, name, float(current))
            )
            return number
        if valueType == "boolean":
            boolean = QCheckBox()
            boolean.setChecked(bool(value))
            boolean.toggled.connect(
                lambda current: self._setParameter(index, name, bool(current))
            )
            return boolean
        text = QLineEdit(str(value))
        text.editingFinished.connect(
            lambda: self._setParameter(index, name, text.text())
        )
        return text

    # :: INT, BOOL -> NONE
    # Changes bypass state and refreshes its row marker
    def _setEnabled(self, index: int, enabled: bool) -> None:
        if self._loading or index >= len(self._effects):
            return
        self._effects[index]["enabled"] = enabled
        self._refreshList(index)
        self._publishChange()

    # :: INT, FLOAT -> NONE
    # Changes the selected effect output mix
    def _setMix(self, index: int, mix: float) -> None:
        if self._loading or index >= len(self._effects):
            return
        self._effects[index]["mix"] = mix
        self._publishChange()

    # :: INT, STRING, ANY -> NONE
    # Changes one catalog-typed effect parameter
    def _setParameter(self, index: int, name: str, value: Any) -> None:
        if self._loading or index >= len(self._effects):
            return
        self._effects[index]["parameters"][name] = value
        self._publishChange()

    # :: VOID -> NONE
    # Emits one consolidated authored-stack change outside load operations
    def _publishChange(self) -> None:
        if not self._loading:
            self.changed.emit()

    # :: VOID -> NONE
    # Removes every dynamic row and schedules its controls for deletion
    def _clearParameterForm(self) -> None:
        while self._parameterForm.rowCount():
            self._parameterForm.removeRow(0)

    # :: VOID -> NONE
    # Shows an unobtrusive prompt when no effect instance is selected
    def _showEmptyParameters(self) -> None:
        self._parameterForm.addRow(QLabel("Select an effect to edit its properties."))

    # :: STRING -> STRING
    # Converts JSON property names into compact native labels
    def _humanLabel(self, name: str) -> str:
        return name.replace("_", " ").replace("X", " X").replace("Y", " Y").title()
