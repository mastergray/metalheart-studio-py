# Cancellable Qt worker for production-backed still previews

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import threading  # Share cooperative cancellation state across Qt threads
from typing import Any, Dict  # Type the authored project snapshot

from PySide6.QtCore import QObject  # Move preview work off the GUI thread
from PySide6.QtCore import Signal  # Report worker results safely to Qt
from PySide6.QtCore import Slot  # Mark the thread entry point

from metalheart.preview import PreviewService  # Execute bounded analysis and rendering


# Resolves and renders one immutable project snapshot outside the GUI thread
class PreviewWorker(QObject):

    # Class Variables
    completed = Signal(object)
    cancelled = Signal()
    failed = Signal(str)

    # CONSTRUCTOR :: ARRAY<STRING, ANY>, STRING, INT, FLOAT -> previewWorker
    # Creates one cooperative preview job
    def __init__(
        self,
        authored: Dict[str, Any],
        configPath: str,
        sceneIndex: int,
        position: float,
    ) -> None:
        super().__init__()
        self._authored = authored
        self._configPath = configPath
        self._sceneIndex = sceneIndex
        self._position = position
        self._cancelEvent = threading.Event()

    #
    # Instance Methods
    #

    # :: VOID -> NONE
    # Requests cancellation before the next bounded render step
    def requestCancel(self) -> None:
        self._cancelEvent.set()

    # :: VOID -> NONE
    # Resolves and renders the selected still and emits one terminal signal
    @Slot()
    def run(self) -> None:
        try:
            result = PreviewService.init().render(
                self._authored,
                self._configPath,
                self._sceneIndex,
                self._position,
                self._cancelEvent.is_set,
            )
        except InterruptedError:
            self.cancelled.emit()
        except Exception as error:
            self.failed.emit(str(error))
        else:
            self.completed.emit(result)
