# Unit tests for render-input fingerprinting

from pathlib import Path  # Create mutable image-input fixtures

import pytest  # Verify mutually exclusive CLI render modes

from metalheart.cli import buildParser  # Parse assembled and per-scene render requests
from metalheart.render import RenderPipeline  # Hash complete render dependencies


# :: PATH -> NONE
# Verifies editing a surface image invalidates resumable render chunks
def testSurfaceImageContentsAffectFingerprint(tmp_path: Path) -> None:
    imagePath = tmp_path / "skin.png"
    imagePath.write_bytes(b"first-image")
    config = {
        "scenes": [
            {
                "renderer": {
                    "surface": {"image": str(imagePath)},
                }
            }
        ]
    }
    pipeline = RenderPipeline.init()
    first = pipeline._renderFingerprint(config, str(tmp_path / "analysis.npz"))
    imagePath.write_bytes(b"second-image")
    second = pipeline._renderFingerprint(config, str(tmp_path / "analysis.npz"))
    assert first != second


# :: PATH -> NONE
# Verifies editing a background image invalidates resumable render chunks
def testBackgroundImageContentsAffectFingerprint(tmp_path: Path) -> None:
    imagePath = tmp_path / "background.png"
    imagePath.write_bytes(b"first-image")
    config = {
        "scenes": [
            {
                "renderer": {"surface": {"image": None}},
                "background": {"image": str(imagePath)},
            }
        ]
    }
    pipeline = RenderPipeline.init()
    first = pipeline._renderFingerprint(config, str(tmp_path / "analysis.npz"))
    imagePath.write_bytes(b"second-image")
    second = pipeline._renderFingerprint(config, str(tmp_path / "analysis.npz"))
    assert first != second


# :: PATH -> NONE
# Verifies editing ribbon or plate images invalidates resumable render chunks
def testDecorImageContentsAffectFingerprint(tmp_path: Path) -> None:
    imagePath = tmp_path / "ribbon.png"
    imagePath.write_bytes(b"first-image")
    config = {
        "scenes": [
            {
                "renderer": {
                    "surface": {"image": None},
                    "decor": {
                        "ribbons": {"surface": {"image": str(imagePath)}},
                        "plates": {"surface": {"image": None}},
                    },
                },
                "background": {"image": None},
            }
        ]
    }
    pipeline = RenderPipeline.init()
    first = pipeline._renderFingerprint(config, str(tmp_path / "analysis.npz"))
    imagePath.write_bytes(b"second-image")
    second = pipeline._renderFingerprint(config, str(tmp_path / "analysis.npz"))
    assert first != second


# :: PATH -> NONE
# Verifies scene identifiers become ordered traversal-safe clip paths
def testBuildsSafeSceneClipPaths(tmp_path: Path) -> None:
    pipeline = RenderPipeline.init()
    first = pipeline._sceneClipPath(tmp_path, 0, {"id": "Opening / Form"})
    second = pipeline._sceneClipPath(tmp_path, 1, {"id": "../"})
    assert first == tmp_path / "001-opening-form.mp4"
    assert second == tmp_path / "002-scene.mp4"


# :: VOID -> NONE
# Verifies render selects exactly one assembled-output or scene-clip mode
def testRenderCliOutputModesAreExclusive() -> None:
    parser = buildParser()
    clipArgs = parser.parse_args(["render", "project.json", "--scene-clips", "clips"])
    assert clipArgs.output is None
    assert clipArgs.scene_clips == "clips"
    with pytest.raises(SystemExit):
        parser.parse_args(["render", "project.json"])
    with pytest.raises(SystemExit):
        parser.parse_args(["render", "project.json", "-o", "movie.mp4", "--scene-clips", "clips"])
