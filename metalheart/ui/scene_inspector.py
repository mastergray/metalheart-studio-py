# Structured per-scene form, background, ribbon, and effect controls

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import copy  # Build isolated authored scene updates
from pathlib import Path  # Choose image skins relative to the active project
from typing import Any, Dict, Optional  # Python 3.8-compatible collection annotations

from PySide6.QtCore import Signal  # Publish complete authored scene changes
from PySide6.QtWidgets import QCheckBox  # Toggle ribbon and ripple systems
from PySide6.QtWidgets import QComboBox  # Select renderer catalog identifiers
from PySide6.QtWidgets import QDoubleSpinBox  # Edit bounded visual properties
from PySide6.QtWidgets import QFileDialog  # Select per-layer image skins
from PySide6.QtWidgets import QFormLayout  # Align scene properties
from PySide6.QtWidgets import QHBoxLayout  # Pair file fields with browse actions
from PySide6.QtWidgets import QLabel  # Display immutable scene timing
from PySide6.QtWidgets import QLineEdit  # Edit scene names and image paths
from PySide6.QtWidgets import QPushButton  # Open native image selectors
from PySide6.QtWidgets import QSpinBox  # Edit ribbon counts and geometry steps
from PySide6.QtWidgets import QTabWidget  # Separate layer-specific controls
from PySide6.QtWidgets import QVBoxLayout  # Stack inspector sections
from PySide6.QtWidgets import QWidget  # Host native inspector controls

from metalheart.catalog import CAMERAS  # Populate supported camera modes
from metalheart.catalog import FORMS  # Populate supported form geometries
from metalheart.catalog import PALETTES  # Populate supported form palettes
from metalheart.catalog import REACTIVITY_PRESETS  # Populate explicit audio mappings
from metalheart.ui.animated_thumbnail_widget import AnimatedThumbnailWidget  # Play camera studies without rendering
from metalheart.ui.effect_stack_widget import EffectStackWidget  # Edit scoped post chains
from metalheart.ui.thumbnail_icons import applyComboThumbnails  # Decorate catalog selectors from packaged assets


IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff);;All Files (*)"


# Edits the selected scene without exposing JSON as the primary workflow
class SceneInspector(QWidget):

    sceneEdited = Signal(object)

    # CONSTRUCTOR :: widget? -> sceneInspector
    # Creates empty structured controls for the three authored visual layers
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._authoredScene: Dict[str, Any] = {}
        self._resolvedScene: Dict[str, Any] = {}
        self._baseDirectory = Path.cwd()
        self._decorEnabled = True
        self._loading = False
        self.setObjectName("sceneInspector")
        self.setEnabled(False)
        self._buildUi()

    #
    # Properties
    #

    # PROPERTY :: VOID -> ARRAY<STRING, ANY>
    # Returns the scene represented by the current native controls
    @property
    def editedScene(self) -> Dict[str, Any]:
        return self._collectScene()

    #
    # Instance Methods
    #

    # :: ARRAY<STRING, ANY>, ARRAY<STRING, ANY>, PATH -> NONE
    # Loads one canonical authored scene with its resolved defaults
    def loadScene(
        self,
        authoredScene: Dict[str, Any],
        resolvedScene: Dict[str, Any],
        baseDirectory: Path,
    ) -> None:
        self._loading = True
        self._authoredScene = copy.deepcopy(authoredScene)
        self._resolvedScene = copy.deepcopy(resolvedScene)
        self._baseDirectory = baseDirectory
        renderer = resolvedScene["renderer"]
        surface = renderer["surface"]
        style = renderer["form_style"]
        background = resolvedScene["background"]
        ripple = background["ripple"]
        decor = renderer["decor"]
        ribbons = decor["ribbons"]
        ribbonSurface = ribbons["surface"]
        self._decorEnabled = bool(decor.get("enabled", True))

        self._name.setText(str(resolvedScene.get("name", resolvedScene["id"])))
        self._timing.setText(
            "{0:.2f}s – {1:.2f}s".format(
                float(resolvedScene["start_sec"]),
                float(resolvedScene["end_sec"]),
            )
        )
        self._reactivity.setCurrentText(str(resolvedScene["reactivity"]["preset"]))
        self._form.setCurrentText(str(renderer["forms"][0]))
        self._palette.setCurrentText(str(renderer["palette"]))
        self._camera.setCurrentText(str(renderer["cameras"][0]))
        self._formMaterial.setCurrentText(str(surface["material"]))
        self._formSampling.setCurrentText(str(surface["sampling"]))
        self._formImage.setText(str(surface.get("image") or ""))
        self._faceting.setValue(float(style["faceting"]))
        self._jaggedness.setValue(float(style["jaggedness"]))
        self._jaggedScale.setValue(float(style["jagged_scale"]))
        self._geometrySteps.setValue(int(style["geometry_steps"]))
        self._formEffects.setEffects(surface.get("post", []))

        self._backgroundSource.setCurrentText(str(background["source"]))
        self._backgroundPalette.setCurrentText(str(background["palette"]))
        self._backgroundIntensity.setValue(float(background["intensity"]))
        self._backgroundMaterial.setCurrentText(str(background["material"]))
        self._backgroundFit.setCurrentText(str(background["fit"]))
        self._backgroundImage.setText(str(background.get("image") or ""))
        self._rippleEnabled.setChecked(bool(ripple["enabled"]))
        self._rippleAmount.setValue(float(ripple["amount"]))
        self._rippleScale.setValue(float(ripple["scale"]))
        self._rippleSpeed.setValue(float(ripple["travel_speed"]))
        self._backgroundEffects.setEffects(background.get("post", []))

        self._ribbonEnabled.setChecked(bool(ribbons["enabled"]))
        self._ribbonCount.setValue(int(ribbons["count"]))
        self._ribbonPalette.setCurrentText(str(ribbons["palette"]))
        self._ribbonMaterial.setCurrentText(str(ribbons["material"]))
        self._ribbonSampling.setCurrentText(str(ribbonSurface["sampling"]))
        self._ribbonImage.setText(str(ribbonSurface.get("image") or ""))
        self._ribbonEffects.setEffects(ribbons.get("post", []))
        self._loading = False
        self.setEnabled(True)

    # :: VOID -> NONE
    # Clears and disables the inspector when no scene is active
    def clear(self) -> None:
        self._authoredScene = {}
        self._resolvedScene = {}
        self.setEnabled(False)

    #
    # Protected Methods
    #

    # :: VOID -> NONE
    # Builds scene identity and the three layer-specific editor tabs
    def _buildUi(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)
        title = QLabel("SCENE INSPECTOR")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        sceneForm = QFormLayout()
        self._name = QLineEdit()
        self._name.editingFinished.connect(self._publishScene)
        sceneForm.addRow("Name", self._name)
        self._timing = QLabel("No scene selected")
        sceneForm.addRow("Range", self._timing)
        self._reactivity = self._combo(sorted(REACTIVITY_PRESETS))
        sceneForm.addRow("Audio response", self._reactivity)
        layout.addLayout(sceneForm)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("layerTabs")
        self._tabs.addTab(self._buildFormTab(), "Form")
        self._tabs.addTab(self._buildBackgroundTab(), "Background")
        self._tabs.addTab(self._buildRibbonTab(), "Ribbons")
        layout.addWidget(self._tabs, 1)

    # :: VOID -> widget
    # Builds form geometry, skin, material, and scoped effects controls
    def _buildFormTab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()
        self._form = self._combo(FORMS, "forms")
        form.addRow("Geometry", self._form)
        self._palette = self._combo(PALETTES, "palettes")
        form.addRow("Palette", self._palette)
        self._camera = self._combo(CAMERAS, "cameras")
        form.addRow("Camera", self._camera)
        self._cameraPreview = AnimatedThumbnailWidget.init()
        self._camera.currentTextChanged.connect(self._cameraPreviewSelected)
        self._cameraPreview.setOption("cameras", self._camera.currentText())
        form.addRow("Motion preview", self._cameraPreview)
        self._formMaterial = self._combo(["metallic", "matte"])
        form.addRow("Material", self._formMaterial)
        self._formSampling = self._combo(["bilinear", "nearest"])
        form.addRow("Texture", self._formSampling)
        self._formImage = QLineEdit()
        form.addRow("Image skin", self._pathField(self._formImage, "Select Form Skin"))
        self._faceting = self._number(0.0, 1.0, 0.01)
        form.addRow("Faceting", self._faceting)
        self._jaggedness = self._number(0.0, 1.0, 0.01)
        form.addRow("Jaggedness", self._jaggedness)
        self._jaggedScale = self._number(0.25, 24.0, 0.25)
        form.addRow("Jagged scale", self._jaggedScale)
        self._geometrySteps = QSpinBox()
        self._geometrySteps.setRange(0, 128)
        self._geometrySteps.valueChanged.connect(self._publishScene)
        form.addRow("Geometry steps", self._geometrySteps)
        layout.addLayout(form)
        layout.addWidget(QLabel("FORM EFFECT STACK"))
        self._formEffects = EffectStackWidget()
        self._formEffects.changed.connect(self._publishScene)
        layout.addWidget(self._formEffects)
        layout.addStretch(1)
        return tab

    # :: VOID -> widget
    # Builds background source, ripple surface, and scoped effects controls
    def _buildBackgroundTab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()
        self._backgroundSource = self._combo(["palette", "image"])
        form.addRow("Source", self._backgroundSource)
        self._backgroundPalette = self._combo(PALETTES, "palettes")
        form.addRow("Palette", self._backgroundPalette)
        self._backgroundIntensity = self._number(0.0, 4.0, 0.05)
        form.addRow("Palette intensity", self._backgroundIntensity)
        self._backgroundMaterial = self._combo(["flat", "matte", "metallic"])
        form.addRow("Material", self._backgroundMaterial)
        self._backgroundFit = self._combo(["cover", "contain", "tile"])
        form.addRow("Image fit", self._backgroundFit)
        self._backgroundImage = QLineEdit()
        form.addRow("Image skin", self._pathField(self._backgroundImage, "Select Background Skin"))
        self._rippleEnabled = QCheckBox("Audio-reactive surface")
        self._rippleEnabled.toggled.connect(self._publishScene)
        form.addRow("Ripple", self._rippleEnabled)
        self._rippleAmount = self._number(0.0, 0.5, 0.005, 3)
        form.addRow("Ripple amount", self._rippleAmount)
        self._rippleScale = self._number(0.25, 24.0, 0.25)
        form.addRow("Ripple scale", self._rippleScale)
        self._rippleSpeed = self._number(0.0, 4.0, 0.05)
        form.addRow("Travel speed", self._rippleSpeed)
        layout.addLayout(form)
        layout.addWidget(QLabel("BACKGROUND EFFECT STACK"))
        self._backgroundEffects = EffectStackWidget()
        self._backgroundEffects.changed.connect(self._publishScene)
        layout.addWidget(self._backgroundEffects)
        layout.addStretch(1)
        return tab

    # :: VOID -> widget
    # Builds ribbon geometry, skin, material, and scoped effects controls
    def _buildRibbonTab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()
        self._ribbonEnabled = QCheckBox("Render ribbons")
        self._ribbonEnabled.toggled.connect(self._publishScene)
        form.addRow("Enabled", self._ribbonEnabled)
        self._ribbonCount = QSpinBox()
        self._ribbonCount.setRange(0, 8)
        self._ribbonCount.valueChanged.connect(self._publishScene)
        form.addRow("Count", self._ribbonCount)
        self._ribbonPalette = self._combo(PALETTES, "palettes")
        form.addRow("Palette", self._ribbonPalette)
        self._ribbonMaterial = self._combo(["metallic", "matte"])
        form.addRow("Material", self._ribbonMaterial)
        self._ribbonSampling = self._combo(["bilinear", "nearest"])
        form.addRow("Texture", self._ribbonSampling)
        self._ribbonImage = QLineEdit()
        form.addRow("Image skin", self._pathField(self._ribbonImage, "Select Ribbon Skin"))
        layout.addLayout(form)
        layout.addWidget(QLabel("RIBBON EFFECT STACK"))
        self._ribbonEffects = EffectStackWidget()
        self._ribbonEffects.changed.connect(self._publishScene)
        layout.addWidget(self._ribbonEffects)
        layout.addStretch(1)
        return tab

    # :: [STRING], STRING? -> qComboBox
    # Creates a catalog selector that publishes structured changes
    def _combo(self, values: Any, thumbnailCatalog: Optional[str] = None) -> QComboBox:
        control = QComboBox()
        control.addItems([str(value) for value in values])
        if thumbnailCatalog is not None:
            applyComboThumbnails(control, thumbnailCatalog)
        control.currentTextChanged.connect(self._publishScene)
        return control

    # :: STRING -> NONE
    # Updates the packaged camera motion study without invoking the renderer
    def _cameraPreviewSelected(self, cameraId: str) -> None:
        self._cameraPreview.setOption("cameras", cameraId)

    # :: FLOAT, FLOAT, FLOAT, INT -> qDoubleSpinBox
    # Creates a bounded floating-point scene property control
    def _number(
        self,
        minimum: float,
        maximum: float,
        step: float,
        decimals: int = 2,
    ) -> QDoubleSpinBox:
        control = QDoubleSpinBox()
        control.setRange(minimum, maximum)
        control.setSingleStep(step)
        control.setDecimals(decimals)
        control.valueChanged.connect(self._publishScene)
        return control

    # :: qLineEdit, STRING -> widget
    # Pairs an image path field with a native file chooser
    def _pathField(self, field: QLineEdit, title: str) -> QWidget:
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        field.editingFinished.connect(self._publishScene)
        button = QPushButton("Browse…")
        button.clicked.connect(lambda: self._browseImage(field, title))
        layout.addWidget(field, 1)
        layout.addWidget(button)
        return host

    # :: qLineEdit, STRING -> NONE
    # Chooses a layer image and publishes its absolute canonical path
    def _browseImage(self, field: QLineEdit, title: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            str(self._baseDirectory),
            IMAGE_FILTER,
        )
        if path:
            field.setText(path)
            self._publishScene()

    # :: VOID -> NONE
    # Emits the complete selected scene after one native control changes
    def _publishScene(self) -> None:
        if not self._loading and self._authoredScene:
            self.sceneEdited.emit(self._collectScene())

    # :: VOID -> ARRAY<STRING, ANY>
    # Projects structured controls back into the canonical authored scene format
    def _collectScene(self) -> Dict[str, Any]:
        if not self._authoredScene:
            return {}
        scene = copy.deepcopy(self._authoredScene)
        scene["name"] = self._name.text().strip() or str(scene.get("id", "Scene"))
        reactivity = scene.setdefault("reactivity", {})
        reactivity["preset"] = self._reactivity.currentText()

        renderer = scene.setdefault("renderer", {})
        renderer["forms"] = [self._form.currentText()]
        renderer["cameras"] = [self._camera.currentText()]
        renderer["palette"] = self._palette.currentText()
        surface = renderer.setdefault("surface", {})
        surface["material"] = self._formMaterial.currentText()
        surface["sampling"] = self._formSampling.currentText()
        surface["image"] = self._optionalPath(self._formImage.text())
        surface["post"] = self._formEffects.effects
        style = renderer.setdefault("form_style", {})
        style["faceting"] = self._faceting.value()
        style["jaggedness"] = self._jaggedness.value()
        style["jagged_scale"] = self._jaggedScale.value()
        style["geometry_steps"] = self._geometrySteps.value()

        background = scene.setdefault("background", {})
        background["source"] = self._backgroundSource.currentText()
        background["palette"] = self._backgroundPalette.currentText()
        background["intensity"] = self._backgroundIntensity.value()
        background["material"] = self._backgroundMaterial.currentText()
        background["fit"] = self._backgroundFit.currentText()
        background["image"] = self._optionalPath(self._backgroundImage.text())
        background["post"] = self._backgroundEffects.effects
        ripple = background.setdefault("ripple", {})
        ripple["enabled"] = self._rippleEnabled.isChecked()
        ripple["amount"] = self._rippleAmount.value()
        ripple["scale"] = self._rippleScale.value()
        ripple["travel_speed"] = self._rippleSpeed.value()

        decor = renderer.setdefault("decor", {})
        decor["enabled"] = self._decorEnabled or self._ribbonEnabled.isChecked()
        ribbons = decor.setdefault("ribbons", {})
        ribbons["enabled"] = self._ribbonEnabled.isChecked()
        ribbons["count"] = self._ribbonCount.value()
        ribbons["palette"] = self._ribbonPalette.currentText()
        ribbons["material"] = self._ribbonMaterial.currentText()
        ribbons["post"] = self._ribbonEffects.effects
        ribbonSurface = ribbons.setdefault("surface", {})
        ribbonSurface["mapping"] = "ribbon"
        ribbonSurface["sampling"] = self._ribbonSampling.currentText()
        ribbonSurface["image"] = self._optionalPath(self._ribbonImage.text())
        return scene

    # :: STRING -> STRING?
    # Normalizes blank image fields to the renderer's null contract
    def _optionalPath(self, value: str) -> Optional[str]:
        stripped = value.strip()
        return stripped if stripped else None
