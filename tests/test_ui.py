# Optional offscreen smoke tests for the native PySide6 editor shell

import json  # Build portable temporary canonical projects
import os  # Select Qt's headless platform before importing PySide6
from pathlib import Path  # Locate a real canonical example project

import pytest  # Skip cleanly when the optional UI dependency is absent


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # Toggle native effect-row checkboxes  # noqa: E402
from PySide6.QtWidgets import QApplication  # Create the Qt event loop after headless setup  # noqa: E402
from PySide6.QtWidgets import QTabWidget  # Find the structured layer inspector  # noqa: E402

from metalheart.ui.effect_stack_widget import EffectStackWidget  # Verify authored stacks  # noqa: E402
from metalheart.ui.main_window import MainWindow  # Exercise the native shell  # noqa: E402
from metalheart.ui.numeric_parameter_widget import NumericParameterWidget  # Verify slider-number controls  # noqa: E402
from metalheart.ui.waveform_widget import WaveformTimelineWidget  # Verify audio-led navigation  # noqa: E402


# :: VOID -> NONE
# Verifies the audio-led application constructs without background work
def testMainWindowBuildsLightweightEmptyShell() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow.init()
    window.show()
    application.processEvents()
    assert window.projectPath is None
    assert not window.dirty
    assert "Create a project from audio" in window.preview.text()
    assert window.findChild(WaveformTimelineWidget, "sceneTimeline") is not None
    window.close()
    window.deleteLater()
    application.processEvents()


# :: VOID -> NONE
# Verifies each layer can own an independently ordered typed effect chain
def testEffectStackBuildsCanonicalCatalogEntries() -> None:
    application = QApplication.instance() or QApplication([])
    stack = EffectStackWidget()
    stack.addEffect("posterize")
    stack.addEffect("tear")
    application.processEvents()
    assert [effect["id"] for effect in stack.effects] == ["posterize", "tear"]
    assert stack.effects[0]["parameters"]["levels"] == 5
    assert stack.effects[1]["parameters"]["direction"] == "horizontal"
    stack._list.item(0).setCheckState(Qt.CheckState.Unchecked)
    application.processEvents()
    assert not stack.effects[0]["enabled"]
    assert stack.effects[0]["parameters"]["levels"] == 5
    assert stack._list.item(0).foreground().color().name() == "#596568"
    stack._list.item(0).setCheckState(Qt.CheckState.Checked)
    application.processEvents()
    assert stack.effects[0]["enabled"]
    assert stack.effects[0]["parameters"]["levels"] == 5
    stack.close()
    stack.deleteLater()
    application.processEvents()


# :: VOID -> NONE
# Verifies sliders and direct number entry publish one precise committed value
def testNumericParameterPairsSliderAndEditableNumber() -> None:
    application = QApplication.instance() or QApplication([])
    control = NumericParameterWidget.init(2.0, 12.0, 1.0, 5, True)
    committed = []
    control.valueCommitted.connect(committed.append)
    control.slider.setValue(control.slider.maximum())
    control.slider.sliderReleased.emit()
    application.processEvents()
    assert control.value == 12
    assert committed == [12]
    control.numberField.setValue(7)
    control.numberField.editingFinished.emit()
    application.processEvents()
    assert control.value == 7
    assert committed == [12, 7]
    control.close()
    control.deleteLater()
    application.processEvents()


# :: VOID -> NONE
# Verifies an existing project opens into scenes and structured layer tabs
def testMainWindowLoadsStructuredSceneWorkflow() -> None:
    application = QApplication.instance() or QApplication([])
    projectPath = Path(__file__).resolve().parents[1] / "examples" / "layer-effects.json"
    window = MainWindow.init(str(projectPath))
    window.show()
    application.processEvents()
    tabs = window.findChild(QTabWidget, "layerTabs")
    assert tabs is not None
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "Form",
        "Background",
        "Ribbons",
    ]
    assert window.findChild(WaveformTimelineWidget, "sceneTimeline").selectedScene == 0
    assert "Scene selected" in window.preview.text()
    window._inspector._backgroundEffects.addEffect("invert")
    application.processEvents()
    assert window.dirty
    assert window.undoStack.canUndo()
    scene = window._authored["scenes"][0]
    assert [effect["id"] for effect in scene["background"]["post"]] == ["vhs", "invert"]
    assert [effect["id"] for effect in scene["renderer"]["surface"]["post"]] == [
        "posterize",
        "chromatic",
    ]
    assert scene["renderer"]["decor"]["ribbons"]["post"][0]["id"] == "tear"
    window.undoStack.undo()
    application.processEvents()
    assert [
        effect["id"] for effect in window._authored["scenes"][0]["background"]["post"]
    ] == ["vhs"]
    assert not window.dirty
    assert window.undoStack.canRedo()
    window.undoStack.redo()
    application.processEvents()
    assert [
        effect["id"] for effect in window._authored["scenes"][0]["background"]["post"]
    ] == ["vhs", "invert"]
    window.undoStack.undo()
    window.close()
    window.deleteLater()
    application.processEvents()


# :: VOID -> NONE
# Verifies row bypass is layer-local, parameter-preserving, and undoable
def testEffectRowBypassParticipatesInProjectHistory() -> None:
    application = QApplication.instance() or QApplication([])
    projectPath = Path(__file__).resolve().parents[1] / "examples" / "layer-effects.json"
    window = MainWindow.init(str(projectPath))
    formEffects = window._inspector._formEffects
    formEffects._list.item(0).setCheckState(Qt.CheckState.Unchecked)
    application.processEvents()
    effect = window._authored["scenes"][0]["renderer"]["surface"]["post"][0]
    assert not effect["enabled"]
    assert effect["parameters"]["levels"] == 4
    assert window._authored["scenes"][0]["background"]["post"][0]["enabled"]
    window.undoStack.undo()
    application.processEvents()
    restored = window._authored["scenes"][0]["renderer"]["surface"]["post"][0]
    assert restored.get("enabled", True)
    assert restored["parameters"]["levels"] == 4
    window.close()
    window.deleteLater()
    application.processEvents()


# :: PATH -> NONE
# Verifies Save establishes the clean history point across later edits
def testUndoHistoryTracksSavedProjectCleanPoint(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    repository = Path(__file__).resolve().parents[1]
    sourcePath = repository / "examples" / "layer-effects.json"
    authored = json.loads(sourcePath.read_text(encoding="utf-8"))
    authored["audio"] = str(
        (repository / "ref" / "audioReactive" / "metalheart_audio_test_small.mp4").resolve()
    )
    projectPath = tmp_path / "history.json"
    projectPath.write_text(json.dumps(authored), encoding="utf-8")
    window = MainWindow.init(str(projectPath))
    window._inspector._backgroundEffects.addEffect("invert")
    application.processEvents()
    assert window.dirty
    assert window._saveProject()
    assert not window.dirty
    window._inspector._backgroundEffects.addEffect("grayscale")
    application.processEvents()
    assert window.dirty
    window.undoStack.undo()
    application.processEvents()
    assert not window.dirty
    window.undoStack.undo()
    application.processEvents()
    assert window.dirty
    window.undoStack.redo()
    application.processEvents()
    assert not window.dirty
    advanced = json.loads(window._jsonEditor.toPlainText())
    originalName = advanced["scenes"][0].get("name")
    advanced["scenes"][0]["name"] = "Advanced History Edit"
    window._jsonEditor.setPlainText(json.dumps(advanced))
    assert window._applyAdvancedEditor()
    application.processEvents()
    assert window._authored["scenes"][0]["name"] == "Advanced History Edit"
    assert window.dirty
    window.undoStack.undo()
    application.processEvents()
    assert window._authored["scenes"][0].get("name") == originalName
    assert not window.dirty
    window.close()
    window.deleteLater()
    application.processEvents()
