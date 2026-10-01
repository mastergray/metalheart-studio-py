# Native desktop application entry point

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import sys  # Supply Qt with a minimal process argument vector
from typing import Optional  # Type the optional startup project

from PySide6.QtCore import QCoreApplication  # Publish native application metadata
from PySide6.QtWidgets import QApplication  # Own the native event loop

from metalheart.ui.main_window import MainWindow  # Construct the primary editor window


# :: STRING? -> INT
# Starts the native authoring application and returns its exit status
def runGui(projectPath: Optional[str] = None) -> int:
    application = QApplication.instance() or QApplication(sys.argv[:1])
    QCoreApplication.setOrganizationName("mastergray")
    QCoreApplication.setApplicationName("Metalheart Studio")
    window = MainWindow.init(projectPath)
    window.show()
    return application.exec()
