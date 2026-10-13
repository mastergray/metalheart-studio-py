# Optional offscreen smoke tests for the native PySide6 editor shell

import copy  # Preserve target scene context for clipboard assertions
import json  # Build portable temporary canonical projects
import os  # Select Qt's headless platform before importing PySide6
from pathlib import Path  # Locate a real canonical example project

import numpy as np  # Build deterministic native preview frames
import pytest  # Skip cleanly when the optional UI dependency is absent


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint  # Place native waveform drag events  # noqa: E402
from PySide6.QtCore import Qt  # Toggle native effect-row checkboxes  # noqa: E402
from PySide6.QtTest import QTest  # Exercise draggable waveform range handles  # noqa: E402
from PySide6.QtWidgets import QApplication  # Create the Qt event loop after headless setup  # noqa: E402
from PySide6.QtWidgets import QScrollArea  # Verify responsive inspector sizing  # noqa: E402
from PySide6.QtWidgets import QSizePolicy  # Verify long effect labels may shrink  # noqa: E402
from PySide6.QtWidgets import QTabWidget  # Find the structured layer inspector  # noqa: E402

from metalheart.catalog import PALETTES  # Verify every stable palette reaches each layer selector  # noqa: E402
from metalheart.ui.effect_stack_widget import EffectStackWidget  # Verify authored stacks  # noqa: E402
from metalheart.ui.main_window import MainWindow  # Exercise the native shell  # noqa: E402
from metalheart.ui.numeric_parameter_widget import NumericParameterWidget  # Verify slider-number controls  # noqa: E402
from metalheart.ui.waveform_widget import WaveformTimelineWidget  # Verify audio-led navigation  # noqa: E402
from metalheart.progress import PROGRESS_PREFIX  # Build child-process progress lines  # noqa: E402
from metalheart.progress import buildProgressEvent  # Build deterministic UI progress  # noqa: E402


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
    assert [
        window._playPreviewButton.text(),
        window._stopPreviewButton.text(),
        window._mutePreviewButton.text(),
    ] == ["Play", "Stop", "Mute"]
    assert not hasattr(window, "_previewInfo")
    window.close()
    window.deleteLater()
    application.processEvents()


# :: VOID -> NONE
# Verifies fragmented child output becomes determinate frame, timing, and ETA status
def testMainWindowDisplaysStructuredProgress() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow.init()
    event = buildProgressEvent(
        "render",
        "rendering",
        48,
        120,
        "frames",
        10.0,
        "Completed chunk 2/5 · scene impact",
        18.0,
        {"chunk": 2, "chunks": 5, "scene": "impact"},
        22.0,
    )
    line = PROGRESS_PREFIX + json.dumps(event) + "\n"
    remainder = window._consumeProcessOutput("", line[:31])
    assert not window._progress.isVisible()
    remainder = window._consumeProcessOutput(remainder, line[31:])
    application.processEvents()
    assert remainder == ""
    assert window._progress.minimum() == 0
    assert window._progress.maximum() == 120
    assert window._progress.value() == 48
    assert "48/120 frames" in window._progressText.text()
    assert "00:12 elapsed" in window._progressText.text()
    assert "~00:18 left" in window._progressText.text()
    window.close()
    window.deleteLater()
    application.processEvents()


# :: VOID -> NONE
# Verifies retained multi-frame playback remains visible when marked stale
def testPreviewClipRetainsPlaybackWithStaleIndicator() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow.init()
    window.show()
    audioPath = (
        Path(__file__).resolve().parents[1]
        / "ref"
        / "audioReactive"
        / "metalheart_audio_test_small.mp4"
    )
    frames = [
        np.full((18, 32, 3), value, dtype=np.uint8)
        for value in (0, 96, 192)
    ]
    window.preview.setClip(frames, 12, str(audioPath), 1.0, 1.25)
    assert window.preview.hasPreview
    assert window.preview.isClip
    assert window.preview.isPlaying
    assert window.preview.frameCount == 3
    assert window.preview._audioPlayback is not None
    if window.preview._audioPlayback.available:
        assert window.preview._audioPlayback._process is not None
    window.preview.setStale(True)
    application.processEvents()
    assert window.preview.hasPreview
    assert window.preview.isStale
    assert window.preview.isPlaying
    assert not window.preview._staleBadge.isHidden()
    window._mutePreviewButton.setEnabled(True)
    window._mutePreviewButton.click()
    assert window.preview.isMuted
    assert window.preview.isPlaying
    assert window._mutePreviewButton.text() == "Unmute"
    QTest.qWait(50)
    assert not window.preview._audioPlayback.isPlaying
    window._stopPreviewButton.setEnabled(True)
    window._stopPreviewButton.click()
    assert not window.preview.isPlaying
    assert window.preview.frameCount == 3
    window.close()
    window.deleteLater()
    application.processEvents()


# :: VOID -> NONE
# Verifies the waveform exposes a directly draggable scene-local range
def testWaveformRangeHandlesTrackAudioPosition() -> None:
    application = QApplication.instance() or QApplication([])
    timeline = WaveformTimelineWidget()
    timeline.resize(800, 118)
    timeline.setTimeline(
        [{"id": "scene-1", "start_sec": 0.0, "end_sec": 10.0}],
        np.linspace(0.0, 1.0, 64, dtype=np.float32),
    )
    timeline.setPreviewRange(0.25, 0.75)
    changes = []
    timeline.rangeChanged.connect(
        lambda start, end, target: changes.append((start, end, target))
    )
    timeline.show()
    application.processEvents()
    startX = int(round(8.0 + float(timeline.width() - 16) * 0.25))
    targetX = int(round(8.0 + float(timeline.width() - 16) * 0.4))
    QTest.mousePress(timeline, Qt.MouseButton.LeftButton, pos=QPoint(startX, 60))
    QTest.mouseMove(timeline, QPoint(targetX, 60))
    QTest.mouseRelease(timeline, Qt.MouseButton.LeftButton, pos=QPoint(targetX, 60))
    application.processEvents()
    assert changes
    assert changes[-1][2] == "start"
    assert timeline.rangeStart == pytest.approx(0.4, abs=0.003)
    assert timeline.rangeEnd == pytest.approx(0.75)
    timeline.close()
    timeline.deleteLater()
    application.processEvents()


# :: PATH -> NONE
# Verifies native full-track creation delegates to the shared analyzer mode
def testMainWindowBuildsFullTrackAnalysisCommand(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow.init()
    audioPath = tmp_path / "song.wav"
    projectPath = tmp_path / "song.metalheart.json"
    arguments = window._analysisArguments(audioPath, projectPath, "single")
    assert arguments[1:5] == [
        "analyze",
        str(audioPath.resolve()),
        "-o",
        str(projectPath.resolve()),
    ]
    assert arguments[arguments.index("--scene-mode") + 1] == "single"
    assert "--max-scene-sec" not in arguments
    assert "--progress" in arguments
    window.close()
    window.deleteLater()
    application.processEvents()


# :: PATH -> NONE
# Verifies automatic scenes pass the selected hard duration cap to analysis
def testMainWindowBuildsBoundedAutoSceneCommand(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow.init()
    audioPath = tmp_path / "song.wav"
    projectPath = tmp_path / "song.metalheart.json"
    arguments = window._analysisArguments(audioPath, projectPath, "phrases", 5.0)
    assert arguments[arguments.index("--scene-mode") + 1] == "phrases"
    assert arguments[arguments.index("--max-scene-sec") + 1] == "5"
    window.close()
    window.deleteLater()
    application.processEvents()


# :: VOID -> NONE
# Verifies each layer can own an independently ordered typed effect chain
def testEffectStackBuildsCanonicalCatalogEntries() -> None:
    application = QApplication.instance() or QApplication([])
    stack = EffectStackWidget()
    stack.show()
    application.processEvents()
    posterizeIndex = stack._effectPicker.findData("posterize")
    assert posterizeIndex >= 0
    assert not stack._effectPicker.itemIcon(posterizeIndex).isNull()
    assert stack._effectPicker.iconSize().width() == 64
    assert stack._effectPicker.iconSize().height() == 36
    assert stack._effectPicker.minimumContentsLength() == 16
    assert stack._effectPicker.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored
    assert stack._addButton.isVisible()
    stack._effectPicker.setCurrentIndex(posterizeIndex)
    application.processEvents()
    assert not stack._effectPreview.isHidden()
    assert stack._effectPreview.frameCount == 16
    previousFrame = stack._effectPreview.frameIndex
    stack._effectPreview._advanceFrame()
    assert stack._effectPreview.frameIndex != previousFrame
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
    control.resize(420, 30)
    control.show()
    application.processEvents()
    slider = control.slider
    start = QPoint(8, slider.height() // 2)
    end = QPoint(slider.width() - 8, slider.height() // 2)
    QTest.mousePress(slider, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(slider, end)
    QTest.mouseRelease(slider, Qt.MouseButton.LeftButton, pos=end)
    application.processEvents()
    assert control.value == 12
    assert committed == [12, 7, 12]
    control.close()
    control.deleteLater()
    application.processEvents()


# :: VOID -> NONE
# Verifies every bounded scene number uses the shared slider-value interaction
def testSceneInspectorUsesSlidersForBoundedNumbers() -> None:
    application = QApplication.instance() or QApplication([])
    projectPath = Path(__file__).resolve().parents[1] / "examples" / "layer-effects.json"
    window = MainWindow.init(str(projectPath))
    inspector = window._inspector
    controls = (
        inspector._faceting,
        inspector._jaggedness,
        inspector._jaggedScale,
        inspector._geometrySteps,
        inspector._backgroundIntensity,
        inspector._rippleAmount,
        inspector._rippleScale,
        inspector._rippleSpeed,
        inspector._ribbonCount,
        inspector._psxRenderScale,
        inspector._psxColorLevels,
        inspector._psxDitherStrength,
    )
    assert all(isinstance(control, NumericParameterWidget) for control in controls)
    assert all(control.slider.maximum() > control.slider.minimum() for control in controls)
    assert inspector._geometrySteps.value == 0
    inspector._geometrySteps.slider.setValue(3)
    inspector._geometrySteps.slider.sliderReleased.emit()
    application.processEvents()
    assert inspector._geometrySteps.value == 6
    assert window._authored["scenes"][0]["renderer"]["form_style"]["geometry_steps"] == 6
    window.undoStack.undo()
    application.processEvents()
    assert inspector._geometrySteps.value == 0
    window.close()
    window.deleteLater()
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
    inspectorScroll = window.findChild(QScrollArea, "inspectorScroll")
    assert tabs is not None
    assert inspectorScroll is not None
    assert inspectorScroll.minimumWidth() == 440
    assert inspectorScroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "Form",
        "Background",
        "Ribbons",
        "Finish",
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


# :: PATH -> NONE
# Verifies scene copy/paste transfers authored visuals but retains audio context
def testSceneCopyPasteIsContextSafeAndUndoable(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    repository = Path(__file__).resolve().parents[1]
    sourcePath = repository / "examples" / "multi-scene.json"
    authored = json.loads(sourcePath.read_text(encoding="utf-8"))
    authored["audio"] = str(
        (repository / "ref" / "audioReactive" / "metalheart_audio_test_small.mp4").resolve()
    )
    authored["scenes"][0]["background"] = {
        "palette": "jungle",
        "intensity": 2.0,
    }
    authored["scenes"][0]["overlay"] = {"enabled": False}
    authored["scenes"][1]["beats"] = 8
    authored["scenes"][1]["downbeats"] = 2
    authored["scenes"][1]["analysis"] = {"mean_energy": 0.625}
    projectPath = tmp_path / "copy-paste.json"
    projectPath.write_text(json.dumps(authored), encoding="utf-8")
    window = MainWindow.init(str(projectPath))
    originalTarget = copy.deepcopy(window._authored["scenes"][1])
    assert window._copySceneButton.isEnabled()
    assert not window._pasteSceneButton.isEnabled()
    window._copySceneButton.click()
    assert window._pasteSceneButton.isEnabled()
    window._pasteSceneButton.click()
    assert not window.dirty
    assert not window.undoStack.canUndo()
    window._sceneList.setCurrentRow(1)
    window._pasteSceneButton.click()
    application.processEvents()
    pasted = window._authored["scenes"][1]
    source = window._authored["scenes"][0]
    for field in (
        "id",
        "name",
        "start_sec",
        "end_sec",
        "beats",
        "downbeats",
        "analysis",
    ):
        assert pasted[field] == originalTarget[field]
    for field in ("template", "renderer", "reactivity", "background", "overlay"):
        assert pasted[field] == source[field]
    assert window.dirty
    assert window.undoStack.undoText() == "Paste Scene"
    window.undoStack.undo()
    application.processEvents()
    assert window._authored["scenes"][1] == originalTarget
    window.undoStack.redo()
    application.processEvents()
    assert window._authored["scenes"][1]["background"] == source["background"]
    window.undoStack.undo()
    application.processEvents()
    assert not window.dirty
    window.close()
    window.deleteLater()
    application.processEvents()


# :: VOID -> NONE
# Verifies waveform range edits remain synchronized with the precise controls
def testMainWindowSynchronizesWaveformRangeHandles() -> None:
    application = QApplication.instance() or QApplication([])
    projectPath = Path(__file__).resolve().parents[1] / "examples" / "layer-effects.json"
    window = MainWindow.init(str(projectPath))
    window._rangeEndSlider.setValue(650)
    window._timeline.rangeChanged.emit(0.25, 0.65, "start")
    application.processEvents()
    assert window._rangeStartSlider.value() == 250
    assert window._rangeEndSlider.value() == 650
    assert window._timeline.rangeStart == pytest.approx(0.25)
    assert window._timeline.rangeEnd == pytest.approx(0.65)
    window.close()
    window.deleteLater()
    application.processEvents()


# :: VOID -> NONE
# Verifies edits retain the last preview and offer explicit regeneration
def testSceneEditRetainsRenderedPreviewAsStale() -> None:
    application = QApplication.instance() or QApplication([])
    projectPath = Path(__file__).resolve().parents[1] / "examples" / "layer-effects.json"
    window = MainWindow.init(str(projectPath))
    window.preview.setFrame(np.zeros((18, 32, 3), dtype=np.uint8))
    window._previewKind = "still"
    window._previewSceneIndex = 0
    window._previewDetails = "32×18 • layer-effects • 1.50s"
    window._inspector._backgroundEffects.addEffect("invert")
    application.processEvents()
    assert window.preview.hasPreview
    assert window.preview.isStale
    assert window.preview.pixmap() is not None
    assert window.preview._staleBadge.text() == "STALE PREVIEW"
    assert not hasattr(window, "_previewInfo")
    assert window._restorePreviewButton.isEnabled()
    requests = []
    window._requestPreview = lambda: requests.append("still")
    window._restorePreviewButton.click()
    assert requests == ["still"]
    window.undoStack.undo()
    application.processEvents()
    window.close()
    window.deleteLater()
    application.processEvents()


# :: VOID -> NONE
# Verifies the PSX preset and independent finish controls author through Undo
def testPsxFinishControlsExpandAndDetachPreset() -> None:
    application = QApplication.instance() or QApplication([])
    projectPath = Path(__file__).resolve().parents[1] / "examples" / "layer-effects.json"
    window = MainWindow.init(str(projectPath))
    inspector = window._inspector
    combinedIndex = inspector._psxPreset.findData("combined")
    inspector._psxPreset.setCurrentIndex(combinedIndex)
    application.processEvents()
    assert window._authored["scenes"][0]["finish"]["psx"] == {"preset": "combined"}
    assert inspector._psxRenderScale.value == 0.5
    assert inspector._psxColorLevels.value == 16
    assert inspector._psxDither.currentData() == "bayer4"
    assert inspector._psxDitherStrength.value == 0.75
    assert window._resolved["scenes"][0]["finish"]["psx"]["color_levels"] == 16
    window.undoStack.undo()
    application.processEvents()
    assert inspector._psxPreset.currentData() == "custom"
    window.undoStack.redo()
    application.processEvents()
    inspector._psxRenderScale.numberField.setValue(0.25)
    inspector._psxRenderScale.numberField.editingFinished.emit()
    application.processEvents()
    psx = window._authored["scenes"][0]["finish"]["psx"]
    assert "preset" not in psx
    assert psx["render_scale"] == 0.25
    assert psx["color_levels"] == 16
    assert psx["dither"] == "bayer4"
    window.undoStack.undo()
    window.undoStack.undo()
    application.processEvents()
    assert not window.dirty
    window.close()
    window.deleteLater()
    application.processEvents()


# :: VOID -> NONE
# Verifies Finish-tab channel and dither sliders support full-rail mouse dragging
def testPsxFinishSlidersSupportDirectTrackDragging() -> None:
    application = QApplication.instance() or QApplication([])
    projectPath = Path(__file__).resolve().parents[1] / "examples" / "layer-effects.json"
    window = MainWindow.init(str(projectPath))
    inspector = window._inspector
    inspector._psxPreset.setCurrentIndex(inspector._psxPreset.findData("combined"))
    window.show()
    application.processEvents()
    assert inspector._psxColorLevels.isEnabled()
    assert inspector._psxDitherStrength.isEnabled()
    levelsSlider = inspector._psxColorLevels.slider
    levelsTarget = QPoint(
        int(round(levelsSlider.width() * 0.75)),
        levelsSlider.height() // 2,
    )
    QTest.mousePress(
        levelsSlider,
        Qt.MouseButton.LeftButton,
        pos=QPoint(4, levelsSlider.height() // 2),
    )
    QTest.mouseMove(levelsSlider, levelsTarget)
    QTest.mouseRelease(
        levelsSlider,
        Qt.MouseButton.LeftButton,
        pos=levelsTarget,
    )
    application.processEvents()
    strengthSlider = inspector._psxDitherStrength.slider
    strengthTarget = QPoint(
        int(round(strengthSlider.width() * 0.35)),
        strengthSlider.height() // 2,
    )
    QTest.mousePress(
        strengthSlider,
        Qt.MouseButton.LeftButton,
        pos=QPoint(4, strengthSlider.height() // 2),
    )
    QTest.mouseMove(strengthSlider, strengthTarget)
    QTest.mouseRelease(
        strengthSlider,
        Qt.MouseButton.LeftButton,
        pos=strengthTarget,
    )
    application.processEvents()
    psx = window._authored["scenes"][0]["finish"]["psx"]
    assert psx["color_levels"] > 180
    assert psx["dither_strength"] == pytest.approx(0.35, abs=0.05)
    while window.undoStack.canUndo():
        window.undoStack.undo()
    application.processEvents()
    assert not window.dirty
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


# :: VOID -> NONE
# Verifies form, background, and ribbon palettes author independently with Undo
def testLayerPaletteControlsAreIndependentAndUndoable() -> None:
    application = QApplication.instance() or QApplication([])
    projectPath = Path(__file__).resolve().parents[1] / "examples" / "layer-effects.json"
    window = MainWindow.init(str(projectPath))
    inspector = window._inspector
    assert not inspector._form.itemIcon(inspector._form.findText("radial")).isNull()
    assert not inspector._camera.itemIcon(inspector._camera.findText("dutch")).isNull()
    assert not inspector._cameraPreview.isHidden()
    assert inspector._cameraPreview.frameCount == 16
    for selector in (
        inspector._palette,
        inspector._backgroundPalette,
        inspector._ribbonPalette,
    ):
        assert [selector.itemText(index) for index in range(selector.count())] == PALETTES
        assert not selector.itemIcon(selector.findText("jungle")).isNull()
    assert inspector._palette.currentText() == "steel"
    assert inspector._backgroundPalette.currentText() == "steel"
    assert inspector._backgroundIntensity.value == 1.0
    assert inspector._ribbonPalette.currentText() == "steel"
    inspector._backgroundIntensity.numberField.setValue(2.25)
    inspector._backgroundIntensity.numberField.editingFinished.emit()
    application.processEvents()
    assert window._authored["scenes"][0]["background"]["intensity"] == 2.25
    window.undoStack.undo()
    application.processEvents()
    assert inspector._backgroundIntensity.value == 1.0
    inspector._backgroundPalette.setCurrentText("ember")
    application.processEvents()
    scene = window._authored["scenes"][0]
    assert scene["background"]["palette"] == "ember"
    assert scene["renderer"].get("palette", "steel") == "steel"
    assert scene["renderer"]["decor"]["ribbons"].get("palette", "steel") == "steel"
    window.undoStack.undo()
    application.processEvents()
    assert inspector._backgroundPalette.currentText() == "steel"
    inspector._ribbonPalette.setCurrentText("acid")
    application.processEvents()
    scene = window._authored["scenes"][0]
    assert scene["renderer"]["decor"]["ribbons"]["palette"] == "acid"
    assert scene["background"].get("palette", "steel") == "steel"
    assert scene["renderer"].get("palette", "steel") == "steel"
    window.undoStack.undo()
    window.close()
    window.deleteLater()
    application.processEvents()


# :: VOID -> NONE
# Verifies leaving Radial removes inapplicable style state instead of invalidating the scene
def testFormSelectionOwnsRadialOnlyStyleControls() -> None:
    application = QApplication.instance() or QApplication([])
    projectPath = Path(__file__).resolve().parents[1] / "examples" / "layer-effects.json"
    window = MainWindow.init(str(projectPath))
    inspector = window._inspector
    assert inspector._jaggedness.numberField.maximum() == 0.12
    assert inspector._jaggedScale.numberField.minimum() == 1.0
    assert inspector._jaggedScale.numberField.maximum() == 16.0
    assert inspector._geometrySteps.numberField.maximum() == 32
    inspector._jaggedness.numberField.setValue(0.02)
    inspector._jaggedness.numberField.editingFinished.emit()
    application.processEvents()
    assert window._authored["scenes"][0]["renderer"]["form_style"]["jaggedness"] == 0.02
    inspector._form.setCurrentText("fold")
    application.processEvents()
    renderer = window._authored["scenes"][0]["renderer"]
    assert renderer["forms"] == ["fold"]
    assert "form_style" not in renderer
    assert not inspector._jaggedness.isEnabled()
    assert window._diagnostics.text() == "✓ Project is valid"
    window.undoStack.undo()
    application.processEvents()
    assert inspector._form.currentText() == "radial"
    assert inspector._jaggedness.isEnabled()
    assert inspector._jaggedness.value == 0.02
    window.undoStack.undo()
    application.processEvents()
    assert not window.dirty
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
