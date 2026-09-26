# Unit tests for render-input fingerprinting

from pathlib import Path  # Create mutable image-input fixtures

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
