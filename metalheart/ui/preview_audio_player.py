# Isolated preview-audio playback that cannot block the Qt GUI event loop

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import shutil  # Locate the optional FFplay executable beside the required FFmpeg tools
from pathlib import Path  # Reject missing audio inputs before launching a child process
from typing import Optional  # Preserve Python 3.8-compatible optional process state

from PySide6.QtCore import QObject  # Own playback within the preview widget lifecycle
from PySide6.QtCore import QProcess  # Isolate audio-backend failures from the GUI process


# Plays bounded source-audio intervals in a disposable child process
class PreviewAudioPlayer(QObject):

    # CONSTRUCTOR :: qObject?, STRING? -> previewAudioPlayer
    # Creates an optional FFplay-backed controller with no active child process
    def __init__(
        self,
        parent: Optional[QObject] = None,
        executable: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self._executable = executable or shutil.which("ffplay")
        self._process: Optional[QProcess] = None

    #
    # Properties
    #

    # PROPERTY :: VOID -> BOOL
    # Reports whether isolated audio playback is available on this machine
    @property
    def available(self) -> bool:
        return self._executable is not None

    # PROPERTY :: VOID -> BOOL
    # Reports whether a child player is starting or actively playing
    @property
    def isPlaying(self) -> bool:
        return (
            self._process is not None
            and self._process.state() != QProcess.ProcessState.NotRunning
        )

    #
    # Instance Methods
    #

    # :: STRING, INT, INT -> NONE
    # Starts one bounded interval without exposing backend stalls to the GUI
    def play(self, audioPath: str, startMs: int, endMs: int) -> None:
        self.stop()
        if (
            self._executable is None
            or not Path(audioPath).is_file()
            or endMs <= startMs
        ):
            return
        process = QProcess(self)
        process.setProgram(self._executable)
        process.setArguments(
            [
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "quiet",
                "-ss",
                "{0:.3f}".format(startMs / 1000.0),
                "-t",
                "{0:.3f}".format((endMs - startMs) / 1000.0),
                audioPath,
            ]
        )
        process.setStandardOutputFile(QProcess.nullDevice())
        process.setStandardErrorFile(QProcess.nullDevice())
        process.finished.connect(
            lambda _exitCode, _exitStatus, active=process: self._finished(active)
        )
        self._process = process
        process.start()

    # :: VOID -> NONE
    # Stops and releases the current disposable player without waiting on its backend
    def stop(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.state() != QProcess.ProcessState.NotRunning:
            process.kill()
        else:
            process.deleteLater()

    #
    # Protected Methods
    #

    # :: qProcess -> NONE
    # Releases a naturally completed player only if it is still the active child
    def _finished(self, process: QProcess) -> None:
        if self._process is process:
            self._process = None
        process.deleteLater()

    #
    # Class Methods
    #

    # Class Factory Method :: qObject?, STRING? -> previewAudioPlayer
    # Creates an isolated preview-audio controller
    @classmethod
    def init(
        cls,
        parent: Optional[QObject] = None,
        executable: Optional[str] = None,
    ) -> PreviewAudioPlayer:
        return cls(parent, executable)
