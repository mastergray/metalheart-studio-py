# Tests for versioned offline option-thumbnail assets

import copy  # Build isolated stale-manifest fixtures
import json  # Write temporary manifest fixtures
from pathlib import Path  # Inspect packaged and temporary thumbnail catalogs

import cv2  # Verify packaged thumbnail dimensions
import pytest  # Mark the production-renderer regeneration check

from metalheart.thumbnails import THUMBNAIL_CATALOGS  # Verify complete option coverage
from metalheart.thumbnails import THUMBNAIL_HEIGHT  # Verify generated asset dimensions
from metalheart.thumbnails import THUMBNAIL_SCHEMA_VERSION  # Verify manifest compatibility
from metalheart.thumbnails import THUMBNAIL_VERSION  # Verify reviewed asset revision
from metalheart.thumbnails import THUMBNAIL_WIDTH  # Verify generated asset dimensions
from metalheart.thumbnails import ThumbnailCatalog  # Read packaged assets without rendering
from metalheart.thumbnails import ThumbnailGenerator  # Verify deterministic offline generation


# :: VOID -> NONE
# Verifies every current stable option has one valid packaged thumbnail
def testPackagedThumbnailCatalogIsCurrentAndComplete() -> None:
    catalog = ThumbnailCatalog.init()
    manifest = catalog.manifest
    assert catalog.available
    assert manifest is not None
    assert manifest["schema_version"] == THUMBNAIL_SCHEMA_VERSION
    assert manifest["thumbnail_version"] == THUMBNAIL_VERSION
    assert manifest["width"] == THUMBNAIL_WIDTH
    assert manifest["height"] == THUMBNAIL_HEIGHT
    assert catalog.validate() == []
    assert sum(len(entries) for entries in THUMBNAIL_CATALOGS.values()) == 92
    for catalogId, identifiers in THUMBNAIL_CATALOGS.items():
        assert list(manifest["catalogs"][catalogId]) == identifiers
        for optionId in identifiers:
            path = catalog.path(catalogId, optionId)
            assert path is not None
            frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
            assert frame is not None
            assert frame.shape == (THUMBNAIL_HEIGHT, THUMBNAIL_WIDTH, 3)


# :: PATH -> NONE
# Verifies stale renderer metadata produces a safe text-only catalog fallback
def testThumbnailCatalogRejectsStaleManifest(tmp_path: Path) -> None:
    packaged = ThumbnailCatalog.init()
    manifest = packaged.manifest
    assert manifest is not None
    stale = copy.deepcopy(manifest)
    stale["renderer_version"] = "stale-renderer"
    (tmp_path / "manifest.json").write_text(
        json.dumps(stale),
        encoding="utf-8",
    )
    catalog = ThumbnailCatalog.init(tmp_path)
    assert not catalog.available
    assert catalog.path("forms", "mercury") is None
    assert catalog.validate() == ["thumbnail manifest is missing or stale"]


# :: PATH -> NONE
# Verifies the production renderer reproduces the reviewed complete asset set
@pytest.mark.integration
def testThumbnailGenerationReproducesPackagedManifest(tmp_path: Path) -> None:
    packaged = ThumbnailCatalog.init().manifest
    assert packaged is not None
    generator = ThumbnailGenerator.init()
    generated = generator.generate(tmp_path)
    assert generated["renderer_version"] == packaged["renderer_version"]
    assert generated["catalog_fingerprint"] == packaged["catalog_fingerprint"]
    assert generated["fixture"] == packaged["fixture"]
    assert generated["catalogs"] == packaged["catalogs"]
    assert ThumbnailCatalog.init(tmp_path).validate() == []
