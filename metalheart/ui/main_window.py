# Native audio-led Metalheart scene authoring application

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import copy  # Snapshot canonical projects before background preview work
import json  # Preserve an optional advanced canonical JSON view
import math  # Convert bounded preview durations into normalized slider spans
import os  # Create and terminate task-specific process groups on POSIX
import signal  # Cancel analysis and rendering process groups safely
import sys  # Launch project services with the active Python environment
from pathlib import Path  # Track project, audio, cache, and output paths
from typing import Any, Dict, List, Optional, Tuple  # Python 3.8-compatible annotations

import numpy as np  # Load cached audio energy for the native waveform
from PySide6.QtCore import QProcess  # Run analysis and exports outside the GUI thread
from PySide6.QtCore import QThread  # Run still rendering outside the GUI thread
from PySide6.QtCore import QTimer  # Escalate cooperative process cancellation safely
from PySide6.QtCore import Qt  # Configure native docks, widgets, and splitters
from PySide6.QtGui import QAction  # Define menu and toolbar commands
from PySide6.QtGui import QCloseEvent  # Type the native close override
from PySide6.QtGui import QKeySequence  # Assign platform-standard shortcuts
from PySide6.QtGui import QUndoStack  # Maintain canonical authored-project history
from PySide6.QtWidgets import QDockWidget  # Hide JSON behind an advanced view
from PySide6.QtWidgets import QFileDialog  # Select audio, projects, and outputs
from PySide6.QtWidgets import QHBoxLayout  # Arrange compact horizontal controls
from PySide6.QtWidgets import QInputDialog  # Choose automatic scene duration bounds
from PySide6.QtWidgets import QLabel  # Display project, timing, and validation state
from PySide6.QtWidgets import QListWidget  # Select analyzed scenes directly
from PySide6.QtWidgets import QMainWindow  # Host the complete native application
from PySide6.QtWidgets import QMessageBox  # Confirm navigation and report failures
from PySide6.QtWidgets import QPlainTextEdit  # Offer JSON as an advanced tool
from PySide6.QtWidgets import QProgressBar  # Show analysis and render activity
from PySide6.QtWidgets import QPushButton  # Trigger explicit bounded previews
from PySide6.QtWidgets import QScrollArea  # Support the inspector on small screens
from PySide6.QtWidgets import QSlider  # Select time inside the active scene
from PySide6.QtWidgets import QSplitter  # Resize scene, preview, and inspector areas
from PySide6.QtWidgets import QToolBar  # Surface the audio-led workflow
from PySide6.QtWidgets import QVBoxLayout  # Stack application sections vertically
from PySide6.QtWidgets import QWidget  # Build native panel containers

from metalheart.config import ConfigResolver  # Resolve and validate canonical projects
from metalheart.preview import PREVIEW_DEFAULT_RANGE_SEC  # Choose a useful initial motion study
from metalheart.preview import PREVIEW_MAX_FPS  # Match selected-range frame boundaries
from metalheart.preview import PREVIEW_MAX_RANGE_SEC  # Bound memory and render cost on older machines
from metalheart.preview import PreviewClipResult  # Display completed renderer-backed ranges
from metalheart.preview import PreviewResult  # Display completed renderer-backed stills
from metalheart.planner import AUTO_SCENE_MAX_SEC  # Share the CLI automatic-scene default
from metalheart.progress import formatDuration  # Format elapsed and remaining task time
from metalheart.progress import parseProgressLine  # Consume machine-readable CLI progress
from metalheart.ui.project_command import ProjectEditCommand  # Snapshot reversible edits
from metalheart.ui.preview_widget import PreviewWidget  # Present copied RGB preview frames
from metalheart.ui.preview_worker import PreviewWorker  # Render bounded stills off-thread
from metalheart.ui.scene_inspector import SceneInspector  # Edit per-scene layers
from metalheart.ui.waveform_widget import WaveformTimelineWidget  # Navigate audio scenes


PROJECT_FILTER = "Metalheart Projects (*.json);;JSON (*.json)"
AUDIO_FILTER = "Audio (*.wav *.mp3 *.flac *.ogg *.m4a *.aac *.aiff *.aif);;All Files (*)"
VIDEO_FILTER = "MPEG-4 Video (*.mp4)"


# Hosts audio-led project creation, scene authoring, previews, and export
class MainWindow(QMainWindow):

    # CONSTRUCTOR :: STRING? -> mainWindow
    # Creates the native Metalheart scene-authoring workspace
    def __init__(self, projectPath: Optional[str] = None) -> None:
        super().__init__()
        self._resolver = ConfigResolver.init()
        self._undoStack = QUndoStack(self)
        self._undoStack.cleanChanged.connect(self._undoCleanChanged)
        self._projectPath: Optional[Path] = None
        self._authored: Optional[Dict[str, Any]] = None
        self._resolved: Optional[Dict[str, Any]] = None
        self._dirty = False
        self._advancedDirty = False
        self._loadingUi = False
        self._selectedScene = 0
        self._projectRevision = 0
        self._previewThread: Optional[QThread] = None
        self._previewWorker: Optional[PreviewWorker] = None
        self._pendingPreview: Optional[
            Tuple[Dict[str, Any], str, int, float, Optional[float], int]
        ] = None
        self._activePreviewRevision = 0
        self._activePreviewRange: Optional[Tuple[float, float]] = None
        self._previewKind: Optional[str] = None
        self._previewSceneIndex = -1
        self._previewDetails = "Explicit preview • max 480×270 • AA off"
        self._renderProcess: Optional[QProcess] = None
        self._analysisProcess: Optional[QProcess] = None
        self._analysisProjectPath: Optional[Path] = None
        self._analysisOutputBuffer = ""
        self._renderOutputBuffer = ""
        self.resize(1500, 850)
        self.setMinimumSize(1020, 650)
        self._buildUi()
        self._buildActions()
        self._buildMenus()
        self._buildToolbar()
        self._applyTheme()
        self._updateTitle()
        if projectPath:
            self._openPath(Path(projectPath))

    #
    # Properties
    #

    # PROPERTY :: VOID -> PATH?
    # Returns the active canonical project path
    @property
    def projectPath(self) -> Optional[Path]:
        return self._projectPath

    # PROPERTY :: VOID -> BOOL
    # Reports whether structured or advanced edits are unsaved
    @property
    def dirty(self) -> bool:
        return self._dirty

    # PROPERTY :: VOID -> previewWidget
    # Returns the central renderer-backed preview surface
    @property
    def preview(self) -> PreviewWidget:
        return self._preview

    # PROPERTY :: VOID -> qUndoStack
    # Returns the canonical authored-project history
    @property
    def undoStack(self) -> QUndoStack:
        return self._undoStack

    #
    # Instance Methods
    #

    # :: qCloseEvent -> NONE
    # Confirms edits and stops every task owned by this application
    # NOTE: The name is fixed by the Qt override contract
    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirmUnsavedChanges():
            event.ignore()
            return
        self._preview.pause()
        self._pendingPreview = None
        if self._previewWorker is not None:
            self._previewWorker.requestCancel()
        if self._previewThread is not None:
            self._previewThread.quit()
            if not self._previewThread.wait(10000):
                event.ignore()
                return
        self._terminateProcess(self._analysisProcess, signal.SIGKILL)
        self._terminateProcess(self._renderProcess, signal.SIGKILL)
        if self._analysisProcess is not None:
            self._analysisProcess.waitForFinished(3000)
        if self._renderProcess is not None:
            self._renderProcess.waitForFinished(3000)
        event.accept()

    #
    # Protected Methods
    #

    # :: VOID -> NONE
    # Builds audio identity, scenes, preview timeline, and structured inspector
    def _buildUi(self) -> None:
        root = QWidget()
        rootLayout = QVBoxLayout(root)
        rootLayout.setContentsMargins(10, 10, 10, 6)
        audioRow = QHBoxLayout()
        audioTitle = QLabel("AUDIO")
        audioTitle.setObjectName("panelTitle")
        self._audioSummary = QLabel("Create a project from audio or open an existing project")
        self._audioSummary.setObjectName("audioSummary")
        audioRow.addWidget(audioTitle)
        audioRow.addWidget(self._audioSummary, 1)
        rootLayout.addLayout(audioRow)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._buildScenePanel())
        splitter.addWidget(self._buildPreviewPanel())
        splitter.addWidget(self._buildInspectorPanel())
        splitter.setSizes([220, 700, 500])
        splitter.setStretchFactor(1, 1)
        rootLayout.addWidget(splitter, 1)
        statusRow = QHBoxLayout()
        self._diagnostics = QLabel("Choose New from Audio to begin")
        self._diagnostics.setObjectName("diagnostics")
        self._diagnostics.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setMaximumWidth(180)
        self._progress.setVisible(False)
        self._progressText = QLabel()
        self._progressText.setObjectName("progressText")
        self._progressText.setMinimumWidth(260)
        self._progressText.setMaximumWidth(560)
        self._progressText.setVisible(False)
        statusRow.addWidget(self._diagnostics, 1)
        statusRow.addWidget(self._progressText)
        statusRow.addWidget(self._progress)
        rootLayout.addLayout(statusRow)
        self.setCentralWidget(root)
        self._buildAdvancedDock()
        self._preview.setMessage("Create a project from audio or open an existing project")
        self.statusBar().showMessage("Ready")

    # :: VOID -> widget
    # Builds the analyzed hard-cut scene navigator
    def _buildScenePanel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("sidePanel")
        panel.setMinimumWidth(205)
        panel.setMaximumWidth(310)
        layout = QVBoxLayout(panel)
        title = QLabel("SCENES")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        self._sceneList = QListWidget()
        self._sceneList.setObjectName("sceneList")
        self._sceneList.currentRowChanged.connect(self._sceneChanged)
        layout.addWidget(self._sceneList, 1)
        hint = QLabel("Select a musical scene to configure its visual layers.")
        hint.setObjectName("summary")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return panel

    # :: VOID -> widget
    # Builds explicit bounded preview controls and the audio scene timeline
    def _buildPreviewPanel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 8, 0)
        self._preview = PreviewWidget()
        layout.addWidget(self._preview, 1)
        timeControls = QHBoxLayout()
        timeControls.addWidget(QLabel("Scene time"))
        self._timeSlider = QSlider(Qt.Orientation.Horizontal)
        self._timeSlider.setRange(0, 1000)
        self._timeSlider.setValue(500)
        self._timeSlider.valueChanged.connect(self._timeChanged)
        timeControls.addWidget(self._timeSlider, 1)
        self._timeLabel = QLabel("50.0%")
        timeControls.addWidget(self._timeLabel)
        layout.addLayout(timeControls)
        rangeControls = QHBoxLayout()
        rangeControls.addWidget(QLabel("Range in"))
        self._rangeStartSlider = QSlider(Qt.Orientation.Horizontal)
        self._rangeStartSlider.setRange(0, 999)
        self._rangeStartSlider.setValue(0)
        self._rangeStartSlider.valueChanged.connect(self._previewRangeStartChanged)
        rangeControls.addWidget(self._rangeStartSlider, 1)
        self._rangeStartLabel = QLabel("0.00s")
        rangeControls.addWidget(self._rangeStartLabel)
        rangeControls.addWidget(QLabel("Out"))
        self._rangeEndSlider = QSlider(Qt.Orientation.Horizontal)
        self._rangeEndSlider.setRange(1, 1000)
        self._rangeEndSlider.setValue(1000)
        self._rangeEndSlider.valueChanged.connect(self._previewRangeEndChanged)
        rangeControls.addWidget(self._rangeEndSlider, 1)
        self._rangeEndLabel = QLabel("0.00s")
        rangeControls.addWidget(self._rangeEndLabel)
        layout.addLayout(rangeControls)
        actions = QHBoxLayout()
        self._previewButton = QPushButton("Render Still")
        self._previewButton.setObjectName("primaryButton")
        self._previewButton.clicked.connect(self._requestPreview)
        self._rangePreviewButton = QPushButton("Render Range")
        self._rangePreviewButton.setObjectName("primaryButton")
        self._rangePreviewButton.clicked.connect(self._requestRangePreview)
        self._playPreviewButton = QPushButton("Play")
        self._playPreviewButton.setEnabled(False)
        self._playPreviewButton.clicked.connect(self._preview.play)
        self._preview.playbackChanged.connect(self._previewPlaybackChanged)
        self._stopPreviewButton = QPushButton("Stop")
        self._stopPreviewButton.setEnabled(False)
        self._stopPreviewButton.clicked.connect(self._stopPreview)
        self._mutePreviewButton = QPushButton("Mute")
        self._mutePreviewButton.setCheckable(True)
        self._mutePreviewButton.setEnabled(False)
        self._mutePreviewButton.toggled.connect(self._previewMutedChanged)
        actions.addWidget(self._previewButton)
        actions.addWidget(self._rangePreviewButton)
        actions.addWidget(self._playPreviewButton)
        actions.addWidget(self._stopPreviewButton)
        actions.addWidget(self._mutePreviewButton)
        actions.addStretch(1)
        self._restorePreviewButton = QPushButton("Restore Preview")
        self._restorePreviewButton.setEnabled(False)
        self._restorePreviewButton.clicked.connect(self._restorePreview)
        actions.addWidget(self._restorePreviewButton)
        layout.addLayout(actions)
        self._timeline = WaveformTimelineWidget()
        self._timeline.sceneSelected.connect(self._timelineSelected)
        self._timeline.rangeChanged.connect(self._timelineRangeChanged)
        layout.addWidget(self._timeline)
        return panel

    # :: VOID -> widget
    # Builds a scrollable structured per-scene layer inspector
    def _buildInspectorPanel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("inspectorScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(440)
        self._inspector = SceneInspector()
        self._inspector.sceneEdited.connect(self._sceneEdited)
        scroll.setWidget(self._inspector)
        return scroll

    # :: VOID -> NONE
    # Builds optional canonical JSON editing outside the primary workflow
    def _buildAdvancedDock(self) -> None:
        self._advancedDock = QDockWidget("Advanced Project JSON", self)
        self._advancedDock.setObjectName("advancedJsonDock")
        host = QWidget()
        layout = QVBoxLayout(host)
        notice = QLabel("Advanced view of the same canonical project used by the controls.")
        layout.addWidget(notice)
        self._jsonEditor = QPlainTextEdit()
        self._jsonEditor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._jsonEditor.textChanged.connect(self._advancedEditorChanged)
        layout.addWidget(self._jsonEditor, 1)
        applyButton = QPushButton("Apply Advanced JSON")
        applyButton.clicked.connect(self._applyAdvancedEditor)
        layout.addWidget(applyButton)
        self._advancedDock.setWidget(host)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._advancedDock)
        self._advancedDock.hide()

    # :: VOID -> NONE
    # Creates project, preview, analysis, and export commands
    def _buildActions(self) -> None:
        self._newAction = QAction("&New from Audio…", self)
        self._newAction.setShortcut(QKeySequence.StandardKey.New)
        self._newAction.triggered.connect(self._newFromAudio)
        self._openAction = QAction("&Open Project…", self)
        self._openAction.setShortcut(QKeySequence.StandardKey.Open)
        self._openAction.triggered.connect(self._openProject)
        self._saveAction = QAction("&Save", self)
        self._saveAction.setShortcut(QKeySequence.StandardKey.Save)
        self._saveAction.triggered.connect(self._saveProject)
        self._saveAsAction = QAction("Save &As…", self)
        self._saveAsAction.setShortcut(QKeySequence.StandardKey.SaveAs)
        self._saveAsAction.triggered.connect(self._saveProjectAs)
        self._cancelAnalysisAction = QAction("Cancel Audio Analysis", self)
        self._cancelAnalysisAction.setEnabled(False)
        self._cancelAnalysisAction.triggered.connect(self._cancelAnalysis)
        self._undoAction = self._undoStack.createUndoAction(self, "&Undo")
        self._undoAction.setShortcut(QKeySequence.StandardKey.Undo)
        self._redoAction = self._undoStack.createRedoAction(self, "&Redo")
        self._redoAction.setShortcut(QKeySequence.StandardKey.Redo)
        self._previewAction = QAction("Render &Still", self)
        self._previewAction.setShortcut("Ctrl+R")
        self._previewAction.triggered.connect(self._requestPreview)
        self._rangePreviewAction = QAction("Render Selected &Range", self)
        self._rangePreviewAction.setShortcut("Ctrl+Alt+R")
        self._rangePreviewAction.triggered.connect(self._requestRangePreview)
        self._renderAction = QAction("Render &Video…", self)
        self._renderAction.setShortcut("Ctrl+Shift+R")
        self._renderAction.triggered.connect(self._chooseRenderPath)
        self._cancelRenderAction = QAction("Cancel Video Render", self)
        self._cancelRenderAction.setEnabled(False)
        self._cancelRenderAction.triggered.connect(self._cancelRender)

    # :: VOID -> NONE
    # Adds workflow-oriented native menus and the advanced view toggle
    def _buildMenus(self) -> None:
        fileMenu = self.menuBar().addMenu("&File")
        fileMenu.addActions((self._newAction, self._openAction, self._saveAction, self._saveAsAction))
        fileMenu.addAction(self._cancelAnalysisAction)
        fileMenu.addSeparator()
        quitAction = QAction("&Quit", self)
        quitAction.setShortcut(QKeySequence.StandardKey.Quit)
        quitAction.triggered.connect(self.close)
        fileMenu.addAction(quitAction)
        editMenu = self.menuBar().addMenu("&Edit")
        editMenu.addActions((self._undoAction, self._redoAction))
        previewMenu = self.menuBar().addMenu("&Preview")
        previewMenu.addActions((self._previewAction, self._rangePreviewAction))
        renderMenu = self.menuBar().addMenu("&Render")
        renderMenu.addActions((self._renderAction, self._cancelRenderAction))
        self.menuBar().addMenu("&View").addAction(self._advancedDock.toggleViewAction())

    # :: VOID -> NONE
    # Surfaces the normal audio-to-scenes-to-render workflow
    def _buildToolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setMovable(False)
        toolbar.addActions((self._newAction, self._openAction, self._saveAction))
        toolbar.addSeparator()
        toolbar.addActions((self._undoAction, self._redoAction))
        toolbar.addSeparator()
        toolbar.addAction(self._previewAction)
        toolbar.addAction(self._rangePreviewAction)
        toolbar.addAction(self._renderAction)
        self.addToolBar(toolbar)

    # :: VOID -> NONE
    # Applies a lightweight native theme suitable for the target machine
    def _applyTheme(self) -> None:
        self.setStyleSheet(
            "QMainWindow, QWidget { background: #0d1011; color: #ccd5d6; }"
            "QMenuBar, QMenu, QToolBar, QStatusBar { background: #141819; color: #ccd5d6; }"
            "QListWidget, QPlainTextEdit, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { "
            "background: #090c0d; border: 1px solid #30383a; selection-background-color: #245b60; }"
            "QListWidget, QPlainTextEdit { font-family: monospace; }"
            "QPushButton { background: #1d2425; border: 1px solid #344043; "
            "border-radius: 4px; padding: 6px 10px; }"
            "QPushButton:hover { border-color: #4ccbd1; } QPushButton:disabled { color: #586365; }"
            "QPushButton:checked { background: #744b16; border-color: #d89b3c; color: #fff0c2; }"
            "#primaryButton { background: #245b60; color: #e7ffff; }"
            "QTabWidget::pane { border: 1px solid #293638; }"
            "QTabBar::tab { background: #171d1f; padding: 7px 10px; }"
            "QTabBar::tab:selected { background: #245b60; }"
            "QSlider::groove:horizontal { height: 4px; background: #30383a; }"
            "QSlider::handle:horizontal { background: #4ccbd1; width: 12px; margin: -5px 0; }"
            "#panelTitle { color: #7fe4e7; font-weight: bold; letter-spacing: 1px; }"
            "#summary, #audioSummary { color: #9aa7a9; }"
            "#animatedOptionPreview { background: #050708; border: 1px solid #30383a; }"
            "#diagnostics { background: #131718; border-top: 1px solid #293133; padding: 6px; }"
        )

    # :: VOID -> NONE
    # Starts a project by choosing audio and a canonical project destination
    def _newFromAudio(self) -> None:
        if not self._confirmUnsavedChanges():
            return
        audioPath, _ = QFileDialog.getOpenFileName(
            self, "Choose Audio for Metalheart Project", str(Path.cwd()), AUDIO_FILTER
        )
        if not audioPath:
            return
        sceneChoice = self._chooseSceneMode()
        if sceneChoice is None:
            return
        sceneMode, maxSceneSec = sceneChoice
        suggested = Path(audioPath).with_suffix(".metalheart.json")
        projectPath, _ = QFileDialog.getSaveFileName(
            self, "Save New Metalheart Project", str(suggested), PROJECT_FILTER
        )
        if projectPath:
            self._startAnalysis(
                Path(audioPath),
                Path(projectPath),
                sceneMode,
                maxSceneSec,
            )

    # :: VOID -> (STRING, FLOAT?)?
    # Asks whether a new audio project should remain whole or gain phrase scenes
    def _chooseSceneMode(self) -> Optional[Tuple[str, Optional[float]]]:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("New Audio Project")
        dialog.setText("How should Metalheart organize this audio?")
        dialog.setInformativeText(
            "Full Track creates one uninterrupted composition. Auto Scenes creates "
            "phrase-aligned sections that can be styled independently."
        )
        fullTrackButton = dialog.addButton("Full Track", QMessageBox.ButtonRole.AcceptRole)
        autoScenesButton = dialog.addButton("Auto Scenes", QMessageBox.ButtonRole.ActionRole)
        dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(fullTrackButton)
        dialog.exec()
        if dialog.clickedButton() is fullTrackButton:
            return "single", None
        if dialog.clickedButton() is autoScenesButton:
            maximum, accepted = QInputDialog.getDouble(
                self,
                "Auto Scene Length",
                "Maximum scene length in seconds:",
                AUTO_SCENE_MAX_SEC,
                1.0,
                60.0,
                1,
            )
            return ("phrases", maximum) if accepted else None
        return None

    # :: PATH, PATH, STRING, FLOAT? -> NONE
    # Runs the established analyzer and scene planner outside the GUI thread
    def _startAnalysis(
        self,
        audioPath: Path,
        projectPath: Path,
        sceneMode: str,
        maxSceneSec: Optional[float] = None,
    ) -> None:
        if self._analysisProcess is not None:
            return
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._readAnalysisOutput)
        process.finished.connect(self._analysisFinished)
        process.errorOccurred.connect(self._analysisFailed)
        arguments = self._analysisArguments(
            audioPath,
            projectPath,
            sceneMode,
            maxSceneSec,
        )
        if os.name == "posix":
            process.start("setsid", [sys.executable] + arguments)
        else:
            process.start(sys.executable, arguments)
        self._analysisProcess = process
        self._analysisProjectPath = projectPath.resolve()
        self._analysisOutputBuffer = ""
        self._newAction.setEnabled(False)
        self._cancelAnalysisAction.setEnabled(True)
        self._showBusyProgress("Starting audio analysis…")
        if sceneMode == "single":
            self._diagnostics.setText("Analyzing audio and creating one full-track composition…")
        else:
            self._diagnostics.setText("Analyzing audio and creating phrase-aligned scenes…")
        self.statusBar().showMessage("Analyzing {0}…".format(audioPath.name))

    # :: PATH, PATH, STRING, FLOAT? -> [STRING]
    # Builds the shared CLI invocation for one audio-led project creation mode
    def _analysisArguments(
        self,
        audioPath: Path,
        projectPath: Path,
        sceneMode: str,
        maxSceneSec: Optional[float] = None,
    ) -> List[str]:
        studioPath = Path(__file__).resolve().parents[2] / "studio.py"
        arguments = [
            str(studioPath),
            "analyze",
            str(audioPath.resolve()),
            "-o",
            str(projectPath.resolve()),
            "--quality",
            "final",
            "--scene-mode",
            sceneMode,
            "--progress",
        ]
        if sceneMode == "phrases":
            maximum = AUTO_SCENE_MAX_SEC if maxSceneSec is None else maxSceneSec
            arguments.extend(["--max-scene-sec", "{0:g}".format(maximum)])
        return arguments

    # :: VOID -> NONE
    # Shows the newest analyzer message without blocking the event loop
    def _readAnalysisOutput(self) -> None:
        if self._analysisProcess is None:
            return
        output = bytes(self._analysisProcess.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        self._analysisOutputBuffer = self._consumeProcessOutput(
            self._analysisOutputBuffer, output
        )

    # :: INT, ANY -> NONE
    # Opens the newly analyzed project after successful scene planning
    def _analysisFinished(self, exitCode: int, exitStatus: Any) -> None:
        del exitStatus
        self._readAnalysisOutput()
        if self._analysisOutputBuffer.strip():
            self._handleProcessLine(self._analysisOutputBuffer.strip())
        self._analysisOutputBuffer = ""
        projectPath = self._analysisProjectPath
        self._finishAnalysisUi()
        if exitCode == 0 and projectPath is not None and projectPath.is_file():
            self._openPath(projectPath)
            self.statusBar().showMessage("Audio analysis complete", 5000)
        elif exitCode != 0:
            self._showValidationErrors(
                ["audio analysis failed with status {0}".format(exitCode)]
            )

    # :: ANY -> NONE
    # Reports failure to start or execute the audio analyzer
    def _analysisFailed(self, error: Any) -> None:
        self._finishAnalysisUi()
        self._showValidationErrors(["audio analysis process failed: {0}".format(error)])

    # :: VOID -> NONE
    # Cancels the analyzer and its task-specific child processes
    def _cancelAnalysis(self) -> None:
        if self._analysisProcess is None:
            return
        self._terminateProcess(self._analysisProcess, signal.SIGTERM)
        QTimer.singleShot(2000, self._killAnalysisIfRunning)
        self.statusBar().showMessage("Cancelling audio analysis…")

    # :: VOID -> NONE
    # Escalates analysis cancellation if it remains active
    def _killAnalysisIfRunning(self) -> None:
        self._terminateProcess(self._analysisProcess, signal.SIGKILL)

    # :: VOID -> NONE
    # Restores controls after any terminal analysis outcome
    def _finishAnalysisUi(self) -> None:
        if self._analysisProcess is not None:
            self._analysisProcess.deleteLater()
        self._analysisProcess = None
        self._analysisProjectPath = None
        self._newAction.setEnabled(True)
        self._cancelAnalysisAction.setEnabled(False)
        if self._previewThread is None and self._renderProcess is None:
            self._hideProgress()

    # :: VOID -> NONE
    # Selects and opens an existing project after protecting edits
    def _openProject(self) -> None:
        if not self._confirmUnsavedChanges():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Metalheart Project",
            str(self._projectPath.parent if self._projectPath else Path.cwd()),
            PROJECT_FILTER,
        )
        if path:
            self._openPath(Path(path))

    # :: PATH -> NONE
    # Loads one project into scenes, timeline, and structured controls
    def _openPath(self, path: Path) -> None:
        try:
            authored = self._resolver.load(str(path))
            resolved = self._resolver.resolve(authored, str(path))
            report = self._resolver.validate(resolved)
        except Exception as error:
            self._showError("Unable to Open Project", str(error))
            return
        if not report.isValid:
            self._showError("Invalid Project", "\n".join(report.errors))
            return
        self._projectPath = path.resolve()
        self._authored = authored
        self._resolved = resolved
        self._selectedScene = 0
        self._projectRevision += 1
        self._previewKind = None
        self._previewSceneIndex = -1
        self._previewDetails = "Explicit preview • max 480×270 • AA off"
        self._preview.setMessage("Scene selected — render a still or range when ready")
        self._setPreviewDetails(self._previewDetails, False)
        self._playPreviewButton.setEnabled(False)
        self._stopPreviewButton.setEnabled(False)
        self._mutePreviewButton.setChecked(False)
        self._mutePreviewButton.setEnabled(False)
        self._undoStack.clear()
        self._syncAdvancedEditor()
        self._setDirty(False)
        self._populateProject()
        self._showValidation(report.warnings)
        self.statusBar().showMessage("Opened {0}".format(self._projectPath.name), 4000)

    # :: VOID -> NONE
    # Populates audio identity, waveform, scenes, and selected inspector
    def _populateProject(self) -> None:
        if self._resolved is None:
            return
        samples, bpm = self._loadWaveform()
        scenes = self._resolved["scenes"]
        duration = float(scenes[-1]["end_sec"])
        audioName = Path(str(self._resolved["audio"])).name
        bpmText = " • {0:.2f} BPM".format(bpm) if bpm is not None else ""
        self._audioSummary.setText(
            "{0} • {1:.2f}s • {2} scenes{3}".format(
                audioName, duration, len(scenes), bpmText
            )
        )
        self._timeline.setTimeline(scenes, samples)
        self._populateScenes(self._selectedScene)

    # :: VOID -> (ANY, FLOAT?)
    # Loads cached energy and tempo without reanalyzing audio
    def _loadWaveform(self) -> Tuple[Any, Optional[float]]:
        if self._resolved is None:
            return np.zeros(0, dtype=np.float32), None
        analysis = self._resolved.get("analysis", {})
        cachePath = analysis.get("cache") if isinstance(analysis, dict) else None
        if isinstance(cachePath, str) and Path(cachePath).is_file():
            try:
                with np.load(cachePath) as cache:
                    energy = np.asarray(cache["energy"], dtype=np.float32)
                    bpm = float(cache["bpm"])
                return energy, bpm
            except (OSError, KeyError, ValueError):
                pass
        samples: List[float] = []
        for scene in self._resolved.get("scenes", []):
            meanEnergy = float(scene.get("analysis", {}).get("mean_energy", 0.25))
            samples.extend([meanEnergy] * 24)
        detectedBpm = analysis.get("detected_bpm") if isinstance(analysis, dict) else None
        bpm = float(detectedBpm) if isinstance(detectedBpm, (int, float)) else None
        return np.asarray(samples, dtype=np.float32), bpm

    # :: INT? -> NONE
    # Rebuilds the analyzed scene list and restores its selection
    def _populateScenes(self, selected: Optional[int] = None) -> None:
        self._loadingUi = True
        self._sceneList.clear()
        if self._resolved is not None:
            for index, scene in enumerate(self._resolved["scenes"]):
                self._sceneList.addItem(
                    "{0:02d}  {1}\n{2:.2f}s – {3:.2f}s".format(
                        index + 1,
                        scene.get("name", scene["id"]),
                        float(scene["start_sec"]),
                        float(scene["end_sec"]),
                    )
                )
            target = self._selectedScene if selected is None else selected
            self._sceneList.setCurrentRow(min(max(target, 0), self._sceneList.count() - 1))
        self._loadingUi = False
        self._sceneChanged(self._sceneList.currentRow())

    # :: INT -> NONE
    # Loads a scene's layer controls without triggering a render
    def _sceneChanged(self, index: int) -> None:
        if self._loadingUi or self._resolved is None or self._authored is None or index < 0:
            return
        self._selectedScene = index
        position = self._timeSlider.value() / 1000.0
        self._timeline.selectScene(index, position)
        self._inspector.loadScene(
            self._authored["scenes"][index],
            self._resolved["scenes"][index],
            self._projectPath.parent if self._projectPath else Path.cwd(),
        )
        self._updateTimeLabel()
        self._resetPreviewRange()
        if self._preview.hasPreview:
            if self._previewSceneIndex != index:
                self._markPreviewStale()
        else:
            self._preview.setMessage("Scene selected — render a still or range when ready")

    # :: INT, FLOAT -> NONE
    # Selects a scene and relative time from the waveform
    def _timelineSelected(self, index: int, position: float) -> None:
        self._timeSlider.blockSignals(True)
        self._timeSlider.setValue(int(round(position * 1000.0)))
        self._timeSlider.blockSignals(False)
        if self._sceneList.currentRow() != index:
            self._sceneList.setCurrentRow(index)
        else:
            self._timeline.selectScene(index, position)
            self._updateTimeLabel()

    # :: INT -> NONE
    # Moves the playhead without starting expensive preview work
    def _timeChanged(self, value: int) -> None:
        self._timeline.selectScene(self._sceneList.currentRow(), value / 1000.0)
        self._updateTimeLabel()
        if self._previewKind == "still":
            self._markPreviewStale()

    # :: VOID -> NONE
    # Updates the selected absolute audio time
    def _updateTimeLabel(self) -> None:
        position = self._timeSlider.value() / 1000.0
        if self._resolved is None or self._sceneList.currentRow() < 0:
            self._timeLabel.setText("{0:.1f}%".format(position * 100.0))
            return
        scene = self._resolved["scenes"][self._sceneList.currentRow()]
        timeSec = float(scene["start_sec"]) + (
            float(scene["end_sec"]) - float(scene["start_sec"])
        ) * position
        self._timeLabel.setText("{0:.2f}s".format(timeSec))

    # :: VOID -> NONE
    # Places an inexpensive default range around the current scene playhead
    def _resetPreviewRange(self) -> None:
        if self._resolved is None or self._sceneList.currentRow() < 0:
            return
        scene = self._resolved["scenes"][self._sceneList.currentRow()]
        durationSec = max(
            float(scene["end_sec"]) - float(scene["start_sec"]),
            1e-9,
        )
        minimumSpan, maximumSpan = self._previewRangeSpans()
        defaultSpan = min(
            maximumSpan,
            max(
                minimumSpan,
                int(round(PREVIEW_DEFAULT_RANGE_SEC / durationSec * 1000.0)),
            ),
        )
        center = self._timeSlider.value()
        start = min(max(center - defaultSpan // 2, 0), 1000 - defaultSpan)
        end = start + defaultSpan
        self._rangeStartSlider.blockSignals(True)
        self._rangeEndSlider.blockSignals(True)
        self._rangeStartSlider.setValue(start)
        self._rangeEndSlider.setValue(end)
        self._rangeStartSlider.blockSignals(False)
        self._rangeEndSlider.blockSignals(False)
        self._updatePreviewRangeLabels()
        self._syncTimelineRange()

    # :: INT -> NONE
    # Keeps the range start before the end and within the bounded memory budget
    def _previewRangeStartChanged(self, value: int) -> None:
        minimumSpan, maximumSpan = self._previewRangeSpans()
        start = min(max(value, 0), 1000 - minimumSpan)
        end = self._rangeEndSlider.value()
        end = max(end, start + minimumSpan)
        end = min(end, start + maximumSpan, 1000)
        self._rangeStartSlider.blockSignals(True)
        self._rangeEndSlider.blockSignals(True)
        self._rangeStartSlider.setValue(start)
        self._rangeEndSlider.setValue(end)
        self._rangeStartSlider.blockSignals(False)
        self._rangeEndSlider.blockSignals(False)
        self._updatePreviewRangeLabels()
        self._syncTimelineRange()
        if self._previewKind == "range":
            self._markPreviewStale()

    # :: INT -> NONE
    # Keeps the range end after the start and within the bounded memory budget
    def _previewRangeEndChanged(self, value: int) -> None:
        minimumSpan, maximumSpan = self._previewRangeSpans()
        end = min(max(value, minimumSpan), 1000)
        start = self._rangeStartSlider.value()
        start = min(start, end - minimumSpan)
        start = max(start, end - maximumSpan, 0)
        self._rangeStartSlider.blockSignals(True)
        self._rangeEndSlider.blockSignals(True)
        self._rangeStartSlider.setValue(start)
        self._rangeEndSlider.setValue(end)
        self._rangeStartSlider.blockSignals(False)
        self._rangeEndSlider.blockSignals(False)
        self._updatePreviewRangeLabels()
        self._syncTimelineRange()
        if self._previewKind == "range":
            self._markPreviewStale()

    # :: FLOAT, FLOAT, STRING -> NONE
    # Synchronizes a waveform handle drag through the bounded slider controls
    def _timelineRangeChanged(self, start: float, end: float, target: str) -> None:
        startValue = min(max(int(round(start * 1000.0)), 0), 999)
        endValue = min(max(int(round(end * 1000.0)), 1), 1000)
        if target == "start":
            self._rangeStartSlider.blockSignals(True)
            self._rangeStartSlider.setValue(startValue)
            self._rangeStartSlider.blockSignals(False)
            self._previewRangeStartChanged(startValue)
        else:
            self._rangeEndSlider.blockSignals(True)
            self._rangeEndSlider.setValue(endValue)
            self._rangeEndSlider.blockSignals(False)
            self._previewRangeEndChanged(endValue)

    # :: VOID -> NONE
    # Copies the canonical slider interval onto the waveform selection
    def _syncTimelineRange(self) -> None:
        start, end = self._previewRangePositions()
        self._timeline.setPreviewRange(start, end)

    # :: VOID -> (INT, INT)
    # Returns normalized minimum-frame and maximum-duration slider spans
    def _previewRangeSpans(self) -> Tuple[int, int]:
        if self._resolved is None or self._sceneList.currentRow() < 0:
            return 1, 1000
        scene = self._resolved["scenes"][self._sceneList.currentRow()]
        durationSec = max(
            float(scene["end_sec"]) - float(scene["start_sec"]),
            1e-9,
        )
        fps = min(int(self._resolved["settings"]["fps"]), PREVIEW_MAX_FPS)
        minimumSpan = min(
            1000,
            max(1, int(math.ceil(1000.0 / (durationSec * max(fps, 1))))),
        )
        maximumSpan = min(
            1000,
            max(
                minimumSpan,
                int(math.floor(PREVIEW_MAX_RANGE_SEC / durationSec * 1000.0)),
            ),
        )
        return minimumSpan, maximumSpan

    # :: VOID -> (FLOAT, FLOAT)
    # Returns the selected normalized in and out points
    def _previewRangePositions(self) -> Tuple[float, float]:
        return (
            self._rangeStartSlider.value() / 1000.0,
            self._rangeEndSlider.value() / 1000.0,
        )

    # :: VOID -> NONE
    # Displays exact global source times for both selected range handles
    def _updatePreviewRangeLabels(self) -> None:
        if self._resolved is None or self._sceneList.currentRow() < 0:
            return
        scene = self._resolved["scenes"][self._sceneList.currentRow()]
        sceneStart = float(scene["start_sec"])
        durationSec = float(scene["end_sec"]) - sceneStart
        startPosition, endPosition = self._previewRangePositions()
        self._rangeStartLabel.setText(
            "{0:.2f}s".format(sceneStart + durationSec * startPosition)
        )
        self._rangeEndLabel.setText(
            "{0:.2f}s".format(sceneStart + durationSec * endPosition)
        )

    # :: STRING, BOOL -> NONE
    # Stores internal preview metadata and controls the stale-result restore action
    def _setPreviewDetails(self, details: str, stale: bool) -> None:
        self._previewDetails = details
        self._restorePreviewButton.setEnabled(
            stale
            and self._preview.hasPreview
            and self._previewThread is None
        )

    # :: VOID -> NONE
    # Retains the last successful result while marking it older than current state
    def _markPreviewStale(self) -> None:
        if not self._preview.hasPreview:
            return
        self._preview.setStale(True)
        self._setPreviewDetails(self._previewDetails, True)

    # :: VOID -> NONE
    # Regenerates the retained preview type from the current authored state
    def _restorePreview(self) -> None:
        if not self._preview.isStale or self._previewThread is not None:
            return
        if self._previewKind == "range":
            self._requestRangePreview()
        else:
            self._requestPreview()

    # :: BOOL -> NONE
    # Enables explicit playback controls from native range playback state
    def _previewPlaybackChanged(self, playing: bool) -> None:
        self._playPreviewButton.setEnabled(
            self._preview.isClip
            and not playing
            and self._previewThread is None
        )
        self._stopPreviewButton.setEnabled(
            self._preview.isClip or self._previewThread is not None
        )

    # :: BOOL -> NONE
    # Applies an explicit audio-only mute without pausing visual playback
    def _previewMutedChanged(self, muted: bool) -> None:
        self._preview.setMuted(muted)
        self._mutePreviewButton.setText("Unmute" if muted else "Mute")

    # :: VOID -> NONE
    # Stops range playback and cancels an active preview render when necessary
    def _stopPreview(self) -> None:
        self._preview.stop()
        if self._previewWorker is not None:
            self._cancelPreview()

    # :: ARRAY<STRING, ANY> -> NONE
    # Adds a structured scene edit to the canonical project history
    def _sceneEdited(self, scene: Dict[str, Any]) -> None:
        if self._authored is None or self._projectPath is None:
            return
        authored = copy.deepcopy(self._authored)
        if authored["scenes"][self._selectedScene] == scene:
            return
        authored["scenes"][self._selectedScene] = scene
        command = ProjectEditCommand(
            "Edit Scene",
            self._authored,
            authored,
            self._selectedScene,
            self._applyAuthoredCommand,
        )
        self._undoStack.push(command)

    # :: ARRAY<STRING, ANY>, INT, BOOL -> NONE
    # Applies one command snapshot and synchronizes every project representation
    def _applyAuthoredCommand(
        self,
        authored: Dict[str, Any],
        selectedScene: int,
        reloadControls: bool,
    ) -> None:
        if self._projectPath is None:
            return
        resolved = self._resolver.resolve(authored, str(self._projectPath))
        report = self._resolver.validate(resolved)
        self._authored = copy.deepcopy(authored)
        self._resolved = resolved
        self._projectRevision += 1
        self._selectedScene = min(
            max(selectedScene, 0),
            max(len(resolved.get("scenes", [])) - 1, 0),
        )
        self._pendingPreview = None
        if self._previewWorker is not None:
            self._previewWorker.requestCancel()
        self._syncAdvancedEditor()
        if reloadControls:
            self._populateProject()
        else:
            self._updateSceneRow(self._selectedScene)
            samples, _ = self._loadWaveform()
            self._timeline.setTimeline(resolved["scenes"], samples)
            self._timeline.selectScene(
                self._selectedScene,
                self._timeSlider.value() / 1000.0,
            )
        self._markPreviewStale()
        if report.isValid:
            self._showValidation(report.warnings)
        else:
            self._showValidationErrors(report.errors)

    # :: INT -> NONE
    # Updates one scene label without rebuilding its inspector
    def _updateSceneRow(self, index: int) -> None:
        if self._resolved is None or index < 0 or index >= self._sceneList.count():
            return
        scene = self._resolved["scenes"][index]
        self._sceneList.item(index).setText(
            "{0:02d}  {1}\n{2:.2f}s – {3:.2f}s".format(
                index + 1,
                scene.get("name", scene["id"]),
                float(scene["start_sec"]),
                float(scene["end_sec"]),
            )
        )

    # :: VOID -> NONE
    # Marks direct advanced JSON edits without parsing every keystroke
    def _advancedEditorChanged(self) -> None:
        if not self._loadingUi:
            self._advancedDirty = True
            self._setDirty(True)

    # :: VOID -> BOOL
    # Validates and applies optional advanced JSON edits
    def _applyAdvancedEditor(self) -> bool:
        if self._projectPath is None or self._authored is None:
            self._showError("No Project", "Create or open a project before editing JSON.")
            return False
        try:
            authored = json.loads(self._jsonEditor.toPlainText())
        except json.JSONDecodeError as error:
            self._showValidationErrors(
                ["JSON line {0}: {1}".format(error.lineno, error.msg)]
            )
            return False
        if not isinstance(authored, dict):
            self._showValidationErrors(["project root must be a JSON object"])
            return False
        resolved = self._resolver.resolve(authored, str(self._projectPath))
        report = self._resolver.validate(resolved)
        if not report.isValid:
            self._showValidationErrors(report.errors)
            return False
        if self._authored == authored:
            self._syncAdvancedEditor()
            return True
        self._advancedDirty = False
        command = ProjectEditCommand(
            "Apply Advanced JSON",
            self._authored,
            authored,
            self._selectedScene,
            self._applyAuthoredCommand,
            reloadOnFirst=True,
        )
        self._undoStack.push(command)
        self.statusBar().showMessage("Advanced JSON applied", 3000)
        return True

    # :: VOID -> NONE
    # Mirrors canonical state into the optional advanced view
    def _syncAdvancedEditor(self) -> None:
        if self._authored is None:
            return
        self._loadingUi = True
        self._jsonEditor.setPlainText(
            json.dumps(self._authored, indent=2, sort_keys=True) + "\n"
        )
        self._loadingUi = False
        self._advancedDirty = False

    # :: VOID -> BOOL
    # Writes the valid canonical document to its current path
    def _saveProject(self) -> bool:
        if self._projectPath is None:
            return self._saveProjectAs()
        if self._advancedDirty and not self._applyAdvancedEditor():
            return False
        if self._authored is None:
            return False
        resolved = self._resolver.resolve(self._authored, str(self._projectPath))
        report = self._resolver.validate(resolved)
        if not report.isValid:
            self._showValidationErrors(report.errors)
            return False
        try:
            self._resolver.write(self._authored, str(self._projectPath))
        except OSError as error:
            self._showError("Unable to Save Project", str(error))
            return False
        self._resolved = resolved
        self._syncAdvancedEditor()
        self._undoStack.setClean()
        self._setDirty(False)
        self._showValidation(report.warnings)
        self.statusBar().showMessage("Saved {0}".format(self._projectPath.name), 4000)
        return True

    # :: VOID -> BOOL
    # Selects a destination and writes the canonical project
    def _saveProjectAs(self) -> bool:
        if self._authored is None:
            self._showError("No Project", "Create a project from audio before saving.")
            return False
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Metalheart Project",
            str(self._projectPath or (Path.cwd() / "metalheart-project.json")),
            PROJECT_FILTER,
        )
        if not path:
            return False
        previousPath = self._projectPath
        self._projectPath = Path(path).resolve()
        if self._saveProject():
            return True
        self._projectPath = previousPath
        return False

    # :: BOOL -> NONE
    # Updates unsaved state and the native title bar
    def _setDirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._updateTitle()

    # :: BOOL -> NONE
    # Synchronizes the title marker with the Qt history clean point
    def _undoCleanChanged(self, clean: bool) -> None:
        self._setDirty((not clean) or self._advancedDirty)

    # :: VOID -> NONE
    # Reflects the active project and unsaved state in the title
    def _updateTitle(self) -> None:
        name = self._projectPath.name if self._projectPath else "No Project"
        marker = " *" if self._dirty else ""
        self.setWindowTitle("Metalheart Studio — {0}{1}".format(name, marker))

    # :: VOID -> NONE
    # Queues an explicit bounded still from current valid controls
    def _requestPreview(self) -> None:
        if self._projectPath is None or self._authored is None:
            self._showError("No Project", "Create or open a project before rendering a still.")
            return
        if self._advancedDirty and not self._applyAdvancedEditor():
            return
        resolved = self._resolver.resolve(self._authored, str(self._projectPath))
        report = self._resolver.validate(resolved)
        if not report.isValid:
            self._showValidationErrors(report.errors)
            return
        request = (
            copy.deepcopy(self._authored),
            str(self._projectPath),
            self._sceneList.currentRow(),
            self._timeSlider.value() / 1000.0,
            None,
            self._projectRevision,
        )
        if self._previewThread is not None:
            self._pendingPreview = request
            if self._previewWorker is not None:
                self._previewWorker.requestCancel()
            return
        self._startPreview(request)

    # :: VOID -> NONE
    # Queues the selected bounded scene range from current valid controls
    def _requestRangePreview(self) -> None:
        if self._projectPath is None or self._authored is None:
            self._showError(
                "No Project",
                "Create or open a project before rendering a selected range.",
            )
            return
        if self._advancedDirty and not self._applyAdvancedEditor():
            return
        resolved = self._resolver.resolve(self._authored, str(self._projectPath))
        report = self._resolver.validate(resolved)
        if not report.isValid:
            self._showValidationErrors(report.errors)
            return
        startPosition, endPosition = self._previewRangePositions()
        request = (
            copy.deepcopy(self._authored),
            str(self._projectPath),
            self._sceneList.currentRow(),
            startPosition,
            endPosition,
            self._projectRevision,
        )
        if self._previewThread is not None:
            self._pendingPreview = request
            if self._previewWorker is not None:
                self._previewWorker.requestCancel()
            return
        self._startPreview(request)

    # :: (ARRAY<STRING, ANY>, STRING, INT, FLOAT, FLOAT?, INT) -> NONE
    # Starts one bounded still or range worker and connects cleanup
    def _startPreview(
        self,
        request: Tuple[
            Dict[str, Any],
            str,
            int,
            float,
            Optional[float],
            int,
        ],
    ) -> None:
        authored, configPath, sceneIndex, startPosition, endPosition, revision = request
        if sceneIndex < 0:
            return
        rangePreview = endPosition is not None
        message = (
            "Rendering selected range preview…"
            if rangePreview
            else "Rendering still preview…"
        )
        if not self._preview.hasPreview:
            self._preview.setMessage(message)
        self._showBusyProgress(message)
        self._previewButton.setEnabled(False)
        self._rangePreviewButton.setEnabled(False)
        self._restorePreviewButton.setEnabled(False)
        self._playPreviewButton.setEnabled(False)
        self._mutePreviewButton.setEnabled(False)
        self._stopPreviewButton.setEnabled(True)
        thread = QThread(self)
        worker = PreviewWorker(
            authored,
            configPath,
            sceneIndex,
            startPosition,
            endPosition,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._previewCompleted)
        worker.failed.connect(self._previewFailed)
        worker.cancelled.connect(self._previewCancelled)
        worker.progress.connect(self._previewProgress)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._previewThreadFinished)
        thread.finished.connect(thread.deleteLater)
        self._previewThread = thread
        self._previewWorker = worker
        self._activePreviewRevision = revision
        self._activePreviewRange = (
            (startPosition, endPosition)
            if endPosition is not None
            else (startPosition, startPosition)
        )
        thread.start()

    # :: VOID -> NONE
    # Cooperatively cancels active and queued still previews
    def _cancelPreview(self) -> None:
        self._pendingPreview = None
        if self._previewWorker is not None:
            self._previewWorker.requestCancel()
            self.statusBar().showMessage("Cancelling preview…")

    # :: previewResult|previewClipResult -> NONE
    # Displays the newest successful result and marks mismatched context as stale
    def _previewCompleted(self, result: Any) -> None:
        if isinstance(result, PreviewClipResult):
            self._preview.setClip(
                result.frames,
                result.fps,
                result.audioPath,
                result.startSec,
                result.endSec,
            )
            self._previewKind = "range"
            self._previewSceneIndex = result.sceneIndex
            details = "{0}×{1} • {2} • {3:.2f}s–{4:.2f}s • {5} frames".format(
                result.width,
                result.height,
                result.sceneId,
                result.startSec,
                result.endSec,
                len(result.frames),
            )
        elif isinstance(result, PreviewResult):
            self._preview.setFrame(result.frame)
            self._previewKind = "still"
            self._previewSceneIndex = result.sceneIndex
            self._playPreviewButton.setEnabled(False)
            self._stopPreviewButton.setEnabled(False)
            self._mutePreviewButton.setEnabled(False)
            details = "{0}×{1} • {2} • {3:.2f}s".format(
                result.width,
                result.height,
                result.sceneId,
                result.timeSec,
            )
        else:
            self._previewFailed("preview worker returned an unsupported result")
            return
        self._previewDetails = details
        stale = (
            self._activePreviewRevision != self._projectRevision
            or result.sceneIndex != self._sceneList.currentRow()
        )
        if isinstance(result, PreviewClipResult) and self._activePreviewRange is not None:
            stale = stale or any(
                abs(current - rendered) > 0.0005
                for current, rendered in zip(
                    self._previewRangePositions(),
                    self._activePreviewRange,
                )
            )
            self._playPreviewButton.setEnabled(not self._preview.isPlaying)
            self._stopPreviewButton.setEnabled(True)
            self._mutePreviewButton.setEnabled(True)
        elif isinstance(result, PreviewResult) and self._activePreviewRange is not None:
            stale = stale or abs(
                self._timeSlider.value() / 1000.0 - self._activePreviewRange[0]
            ) > 0.0005
        self._preview.setStale(stale)
        self._setPreviewDetails(details, stale)
        self.statusBar().showMessage(
            "Preview ready" if not stale else "Preview ready but stale",
            3000,
        )

    # :: INT, INT -> NONE
    # Shows determinate selected-range frame progress
    def _previewProgress(self, completed: int, total: int) -> None:
        self._progress.setRange(0, max(total, 1))
        self._progress.setValue(min(max(completed, 0), max(total, 1)))
        self._progress.setFormat("%p%")
        message = "Rendering preview frames • {0}/{1}".format(completed, total)
        self._progressText.setText(message)
        self._progressText.setToolTip(message)
        self._progressText.setVisible(True)
        self._progress.setVisible(True)

    # :: STRING -> NONE
    # Reports preview failure without discarding scene edits
    def _previewFailed(self, message: str) -> None:
        if self._preview.hasPreview:
            self._markPreviewStale()
        else:
            self._preview.setMessage("Preview failed")
        self._showValidationErrors([message])

    # :: VOID -> NONE
    # Reports cooperative still-preview cancellation
    def _previewCancelled(self) -> None:
        self.statusBar().showMessage("Preview cancelled", 2000)

    # :: VOID -> NONE
    # Releases the worker and starts only the newest queued request
    def _previewThreadFinished(self) -> None:
        self._previewThread = None
        self._previewWorker = None
        if self._analysisProcess is None and self._renderProcess is None:
            self._hideProgress()
        self._previewButton.setEnabled(True)
        self._rangePreviewButton.setEnabled(True)
        pending = self._pendingPreview
        self._pendingPreview = None
        if pending is not None:
            self._startPreview(pending)
        else:
            self._restorePreviewButton.setEnabled(self._preview.isStale)
            self._playPreviewButton.setEnabled(
                self._preview.isClip and not self._preview.isPlaying
            )
            self._stopPreviewButton.setEnabled(self._preview.isClip)
            self._mutePreviewButton.setEnabled(self._preview.isClip)

    # :: VOID -> NONE
    # Chooses an MP4 destination and starts the tested render pipeline
    def _chooseRenderPath(self) -> None:
        if not self._saveProject() or self._projectPath is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Render Metalheart Video",
            str(self._projectPath.with_suffix(".mp4")),
            VIDEO_FILTER,
        )
        if path:
            self._startRender(Path(path))

    # :: PATH -> NONE
    # Runs full export asynchronously in a task-specific process group
    def _startRender(self, outputPath: Path) -> None:
        if self._projectPath is None or self._renderProcess is not None:
            return
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._readRenderOutput)
        process.finished.connect(self._renderFinished)
        process.errorOccurred.connect(self._renderFailed)
        studioPath = Path(__file__).resolve().parents[2] / "studio.py"
        arguments = [
            str(studioPath),
            "render",
            str(self._projectPath),
            "-o",
            str(outputPath),
            "--progress",
        ]
        if os.name == "posix":
            process.start("setsid", [sys.executable] + arguments)
        else:
            process.start(sys.executable, arguments)
        self._renderProcess = process
        self._renderOutputBuffer = ""
        self._renderAction.setEnabled(False)
        self._cancelRenderAction.setEnabled(True)
        self._showBusyProgress("Starting video render…")
        self.statusBar().showMessage("Rendering {0}…".format(outputPath.name))

    # :: VOID -> NONE
    # Shows the newest full-render pipeline message
    def _readRenderOutput(self) -> None:
        if self._renderProcess is None:
            return
        output = bytes(self._renderProcess.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        self._renderOutputBuffer = self._consumeProcessOutput(
            self._renderOutputBuffer, output
        )

    # :: INT, ANY -> NONE
    # Reports export completion and restores actions
    def _renderFinished(self, exitCode: int, exitStatus: Any) -> None:
        del exitStatus
        self._readRenderOutput()
        if self._renderOutputBuffer.strip():
            self._handleProcessLine(self._renderOutputBuffer.strip())
        self._renderOutputBuffer = ""
        message = (
            "Video render complete"
            if exitCode == 0
            else "Video render failed with status {0}".format(exitCode)
        )
        self.statusBar().showMessage(message, 6000)
        self._finishRenderUi()

    # :: ANY -> NONE
    # Reports a render process startup or execution error
    def _renderFailed(self, error: Any) -> None:
        self.statusBar().showMessage("Video render process failed: {0}".format(error), 6000)
        self._finishRenderUi()

    # :: VOID -> NONE
    # Terminates full export without blocking the event loop
    def _cancelRender(self) -> None:
        if self._renderProcess is None:
            return
        self._terminateProcess(self._renderProcess, signal.SIGTERM)
        QTimer.singleShot(2000, self._killRenderIfRunning)
        self.statusBar().showMessage("Cancelling video render…")

    # :: VOID -> NONE
    # Escalates export cancellation if it remains active
    def _killRenderIfRunning(self) -> None:
        self._terminateProcess(self._renderProcess, signal.SIGKILL)

    # :: VOID -> NONE
    # Restores controls after a terminal render outcome
    def _finishRenderUi(self) -> None:
        if self._renderProcess is not None:
            self._renderProcess.deleteLater()
        self._renderProcess = None
        self._renderAction.setEnabled(True)
        self._cancelRenderAction.setEnabled(False)
        if self._previewThread is None and self._analysisProcess is None:
            self._hideProgress()

    # :: STRING, STRING -> STRING
    # Consumes complete child-process lines while preserving a fragmented tail
    def _consumeProcessOutput(self, buffered: str, output: str) -> str:
        lines = (buffered + output).split("\n")
        remainder = lines.pop()
        for line in lines:
            cleaned = line.strip()
            if cleaned:
                self._handleProcessLine(cleaned)
        return remainder

    # :: STRING -> NONE
    # Routes structured progress records and preserves ordinary diagnostic output
    def _handleProcessLine(self, line: str) -> None:
        event = parseProgressLine(line)
        if event is None:
            self.statusBar().showMessage(line)
            return
        self._applyProgressEvent(event)

    # :: ARRAY<STRING, ANY> -> NONE
    # Displays determinate stage or frame progress with elapsed time and ETA
    def _applyProgressEvent(self, event: Dict[str, Any]) -> None:
        completed = max(0, int(event["completed"]))
        total = max(0, int(event["total"]))
        if total:
            self._progress.setRange(0, total)
            self._progress.setValue(min(completed, total))
            self._progress.setFormat("%p%")
        else:
            self._progress.setRange(0, 0)
        values = [str(event["message"])]
        if total:
            values.append(
                "{0}/{1} {2}".format(completed, total, event["unit"])
            )
        values.append("{0} elapsed".format(formatDuration(float(event["elapsed_sec"]))))
        if "remaining_sec" in event:
            values.append(
                "~{0} left".format(formatDuration(float(event["remaining_sec"])))
            )
        message = " • ".join(values)
        self._progressText.setText(message)
        self._progressText.setToolTip(message)
        self._progressText.setVisible(True)
        self._progress.setVisible(True)
        self.statusBar().showMessage(message)

    # :: STRING -> NONE
    # Shows an indeterminate task before its first structured progress record
    def _showBusyProgress(self, message: str) -> None:
        self._progress.setRange(0, 0)
        self._progress.setVisible(True)
        self._progressText.setText(message)
        self._progressText.setToolTip(message)
        self._progressText.setVisible(True)

    # :: VOID -> NONE
    # Hides shared task status after analysis, preview, and render work is idle
    def _hideProgress(self) -> None:
        self._progress.setVisible(False)
        self._progressText.setVisible(False)

    # :: qProcess?, INT -> NONE
    # Signals one application-owned process or POSIX process group
    def _terminateProcess(self, process: Optional[QProcess], signalValue: int) -> None:
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            return
        processId = int(process.processId())
        if os.name == "posix" and processId > 0:
            try:
                os.killpg(processId, signalValue)
            except ProcessLookupError:
                pass
        elif signalValue == signal.SIGKILL:
            process.kill()
        else:
            process.terminate()

    # :: [STRING] -> NONE
    # Displays successful validation with optional warnings
    def _showValidation(self, warnings: Any) -> None:
        if warnings:
            self._diagnostics.setText(
                "Valid with warnings: " + " • ".join(str(item) for item in warnings)
            )
            self._diagnostics.setStyleSheet("color: #edc56e;")
        else:
            self._diagnostics.setText("✓ Project is valid")
            self._diagnostics.setStyleSheet("color: #78d9a2;")

    # :: [STRING] -> NONE
    # Displays exact errors before preview, save, or render work
    def _showValidationErrors(self, errors: Any) -> None:
        self._diagnostics.setText("Invalid: " + " • ".join(str(item) for item in errors))
        self._diagnostics.setStyleSheet("color: #ff7b72;")
        self.statusBar().showMessage("Project validation failed", 5000)

    # :: STRING, STRING -> NONE
    # Shows a blocking native error dialog for project I/O failures
    def _showError(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    # :: VOID -> BOOL
    # Offers Save, Discard, and Cancel before replacing work
    def _confirmUnsavedChanges(self) -> bool:
        if not self._dirty:
            return True
        response = QMessageBox.question(
            self,
            "Unsaved Changes",
            "Save changes to the current Metalheart project?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if response == QMessageBox.StandardButton.Save:
            return self._saveProject()
        return response == QMessageBox.StandardButton.Discard

    #
    # Class Methods
    #

    # Class Factory Method :: STRING? -> mainWindow
    # Creates the native audio-led authoring application
    @classmethod
    def init(cls, projectPath: Optional[str] = None) -> MainWindow:
        return cls(projectPath)
