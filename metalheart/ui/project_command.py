# Undoable canonical project replacement command for native authoring

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import copy  # Isolate command snapshots from later widget mutations
from typing import Any, Callable, Dict  # Type the canonical project callback on Python 3.8

from PySide6.QtGui import QUndoCommand  # Integrate authored edits with Qt Undo and Redo


# Restores complete canonical project snapshots through one application callback
class ProjectEditCommand(QUndoCommand):

    # CONSTRUCTOR :: STRING, ARRAY<STRING, ANY>, ARRAY<STRING, ANY>, INT, (ARRAY<STRING, ANY>, INT, BOOL -> NONE), BOOL -> projectEditCommand
    # Creates one reversible authored project change
    def __init__(
        self,
        label: str,
        before: Dict[str, Any],
        after: Dict[str, Any],
        selectedScene: int,
        applyProject: Callable[[Dict[str, Any], int, bool], None],
        reloadOnFirst: bool = False,
    ) -> None:
        super().__init__(label)
        self._before = copy.deepcopy(before)
        self._after = copy.deepcopy(after)
        self._selectedScene = selectedScene
        self._applyProject = applyProject
        self._reloadOnFirst = reloadOnFirst
        self._firstRedo = True

    #
    # Instance Methods
    #

    # :: VOID -> NONE
    # Restores the project state before this authored edit
    # NOTE: The name is fixed by the Qt undo-command contract
    def undo(self) -> None:
        self._applyProject(copy.deepcopy(self._before), self._selectedScene, True)

    # :: VOID -> NONE
    # Applies or reapplies the project state after this authored edit
    # NOTE: The name is fixed by the Qt undo-command contract
    def redo(self) -> None:
        reloadControls = self._reloadOnFirst if self._firstRedo else True
        self._firstRedo = False
        self._applyProject(
            copy.deepcopy(self._after),
            self._selectedScene,
            reloadControls,
        )
