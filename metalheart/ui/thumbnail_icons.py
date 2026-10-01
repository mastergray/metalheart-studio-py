# Native Qt icon wiring for packaged versioned option thumbnails

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

from typing import Optional  # Cache an optional current thumbnail catalog

from PySide6.QtCore import QSize  # Keep selector icons compact on older displays
from PySide6.QtCore import Qt  # Read stable identifiers from combo item data
from PySide6.QtGui import QIcon  # Load packaged PNGs without renderer work
from PySide6.QtWidgets import QComboBox  # Decorate existing native selectors

from metalheart.thumbnails import ThumbnailCatalog  # Validate assets before exposing icons


ICON_SIZE = QSize(64, 36)
_CATALOG: Optional[ThumbnailCatalog] = None


# :: VOID -> thumbnailCatalog
# Returns one process-local read-only manifest cache
def _thumbnailCatalog() -> ThumbnailCatalog:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = ThumbnailCatalog.init()
    return _CATALOG


# :: qComboBox, STRING, BOOL -> NONE
# Adds packaged icons to a combo without generating or rendering anything
def applyComboThumbnails(
    control: QComboBox,
    catalog: str,
    identifiersInData: bool = False,
) -> None:
    thumbnails = _thumbnailCatalog()
    if not thumbnails.available:
        return
    loaded = False
    for index in range(control.count()):
        if identifiersInData:
            value = control.itemData(index, Qt.ItemDataRole.UserRole)
        else:
            value = control.itemText(index)
        if not isinstance(value, str):
            continue
        path = thumbnails.path(catalog, value)
        if path is None:
            continue
        control.setItemIcon(index, QIcon(str(path)))
        loaded = True
    if loaded:
        control.setIconSize(ICON_SIZE)
