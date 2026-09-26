# Unit tests for JSON config resolution and validation

from pathlib import Path  # Type temporary test paths and create audio placeholders
from typing import Any, Dict  # Python 3.8-compatible config annotations

from metalheart.config import ConfigResolver  # Resolve and validate authored configs


# :: PATH -> ARRAY<STRING, ANY>
# Creates a minimal valid authored config with an existing audio placeholder
def _validConfig(tmpPath: Path) -> Dict[str, Any]:
    audioPath = tmpPath / "audio.wav"
    audioPath.write_bytes(b"placeholder")
    return {
        "version": 1,
        "audio": str(audioPath),
        "settings": {"width": 64, "height": 64, "fps": 4, "quality": "preview", "seed": 7},
        "scenes": [
            {
                "id": "one",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "template": "builtins/mercury-intro",
                "renderer": {"core": "2d", "hud": False},
                "reactivity": {"preset": "balanced"},
            }
        ],
    }


# :: PATH -> NONE
# Verifies templates and reactivity presets expand into a valid config
def testResolvesTemplateAndPreset(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    configPath = tmp_path / "project.json"
    resolved = resolver.resolve(authored, str(configPath))
    report = resolver.validate(resolved)
    assert report.isValid, report.errors
    assert resolved["scenes"][0]["renderer"]["forms"] == ["mercury", "wring"]
    assert resolved["scenes"][0]["renderer"]["core"] == "2d"
    assert resolved["scenes"][0]["reactivity"]["bindings"]["bass"]["source"] == "bass"
    assert resolved["scenes"][0]["reactivity"]["modulators"]["pulse"]["source"] == "bass"
    assert resolved["scenes"][0]["overlay"] == {"enabled": False, "reference_hud": False, "items": []}
    assert resolved["settings"]["crf"] == 23


# :: PATH -> NONE
# Verifies authored text overlays resolve and validate independently of the reference HUD
def testValidatesConfigurableTextOverlay(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["overlay"] = {
        "enabled": True,
        "items": [
            {
                "text": "MASTERGRAY",
                "position": [0.5, 0.92],
                "anchor": "bottom_center",
                "size": 0.04,
                "color": "#FF8030",
                "opacity": 0.8,
            }
        ],
    }
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert report.isValid, report.errors
    assert resolved["scenes"][0]["overlay"]["items"][0]["text"] == "MASTERGRAY"


# :: PATH -> NONE
# Verifies named quality profiles supply concrete defaults while permitting overrides
def testResolvesNamedQualityProfile(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["settings"] = {"quality": "draft", "seed": 7}
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    assert resolved["settings"]["width"] == 960
    assert resolved["settings"]["height"] == 540
    assert resolved["settings"]["fps"] == 24
    assert resolved["settings"]["crf"] == 20
    assert resolved["scenes"][0]["renderer"]["core_scale"] == 0.5
    assert resolved["scenes"][0]["renderer"]["anti_alias"]
    assert resolved["scenes"][0]["renderer"]["camera_speed"] == 1.0
    assert resolved["scenes"][0]["renderer"]["camera_phase_sec"] == 0.0
    assert resolved["scenes"][0]["renderer"]["camera_intensity"] == 1.0


# :: PATH -> NONE
# Verifies legacy backend names migrate without leaking into resolved profiles
def testMigratesLegacyRendererAliases(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["renderer"].update(
        {
            "preset": "ember",
            "looks": ["ferro"],
            "look_len_sec": 3.0,
            "scanlines": True,
            "hud": True,
        }
    )
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    scene = resolved["scenes"][0]
    assert scene["renderer"]["palette"] == "ember"
    assert scene["renderer"]["forms"] == ["ferro"]
    assert scene["renderer"]["form_len_sec"] == 3.0
    assert "preset" not in scene["renderer"]
    assert "looks" not in scene["renderer"]
    assert "hud" not in scene["renderer"]
    assert scene["finish"]["scanlines"]
    assert not scene["overlay"]["enabled"]


# :: PATH -> NONE
# Verifies unsafe finishing values fail before rendering
def testRejectsInvalidFinishControls(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["finish"] = {"grain": 0.5, "slice_glitch": "yes"}
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert not report.isValid
    assert any("finish.grain" in error for error in report.errors)
    assert any("finish.slice_glitch" in error for error in report.errors)


# :: VOID -> NONE
# Verifies generated schema documents the stable public vocabulary
def testSchemaPublishesFormsFinishAndOverlay() -> None:
    schema = ConfigResolver.init().schema()
    renderer = schema["$defs"]["renderer"]["properties"]
    scene = schema["$defs"]["scene"]["properties"]
    assert "forms" in renderer
    assert "palette" in renderer
    assert "looks" not in renderer
    assert "preset" not in renderer
    assert "camera_speed" in renderer
    assert "camera_phase_sec" in renderer
    assert "camera_intensity" in renderer
    modulators = schema["$defs"]["scene"]["properties"]["reactivity"]["properties"]["modulators"]["additionalProperties"]
    assert modulators == {"$ref": "#/$defs/binding"}
    assert "resonance" in renderer["forms"]["items"]["enum"]
    assert "stretch" in renderer["forms"]["items"]["enum"]
    assert "heart" not in renderer["forms"]["items"]["enum"]
    assert "finish" in scene
    assert "overlay" in scene


# :: PATH -> NONE
# Verifies validation rejects odd H.264 dimensions and unknown form IDs
def testRejectsInvalidRendererSettings(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["settings"]["width"] = 65
    authored["scenes"][0]["renderer"]["forms"] = ["not-a-form"]
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert not report.isValid
    assert any("settings.width" in error for error in report.errors)
    assert any("renderer.forms[0]" in error for error in report.errors)


# :: PATH -> NONE
# Verifies camera timing and signature controls reject unsafe authored ranges
def testRejectsInvalidCameraControls(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["renderer"].update(
        {"camera_speed": 9.0, "camera_phase_sec": -1.0, "camera_intensity": 3.1}
    )
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert not report.isValid
    assert any("renderer.camera_speed" in error for error in report.errors)
    assert any("renderer.camera_phase_sec" in error for error in report.errors)
    assert any("renderer.camera_intensity" in error for error in report.errors)


# :: PATH -> NONE
# Verifies the camera-driven preset expands into supported camera destinations
def testResolvesCameraDrivenPreset(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["reactivity"] = {"preset": "camera-driven"}
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    modulators = resolved["scenes"][0]["reactivity"]["modulators"]
    assert report.isValid, report.errors
    assert set(modulators) == {
        "camera_distance",
        "camera_elevation",
        "camera_roll",
        "camera_kick",
    }


# :: PATH -> NONE
# Verifies the owned resonance form and preset resolve only on the 3D core
def testResolvesSpectralResonancePreset(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["renderer"] = {"core": "3d", "forms": ["resonance"]}
    authored["scenes"][0]["reactivity"] = {"preset": "spectral-resonance"}
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert report.isValid, report.errors
    assert set(resolved["scenes"][0]["reactivity"]["modulators"]) == {
        "form_scale",
        "form_deformation",
        "form_ripple",
    }
    authored["scenes"][0]["renderer"]["core"] = "2d"
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert any("resonance requires the 3d core" in error for error in report.errors)


# :: PATH -> NONE
# Verifies spectral stretch publishes every geometry-composition destination
def testResolvesSpectralStretchPreset(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["renderer"] = {"core": "3d", "forms": ["stretch"]}
    authored["scenes"][0]["reactivity"] = {"preset": "spectral-stretch"}
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert report.isValid, report.errors
    assert set(resolved["scenes"][0]["reactivity"]["modulators"]) == {
        "form_length",
        "form_curvature",
        "form_direction",
        "form_twist",
        "form_snap",
    }


# :: PATH -> NONE
# Verifies frame-precision gaps between scenes are rejected
def testRejectsSceneGapAtFramePrecision(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"].append(
        {
            "id": "two",
            "start_sec": 1.5,
            "end_sec": 2.0,
            "renderer": {"core": "2d"},
            "reactivity": {"preset": "balanced"},
        }
    )
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert not report.isValid
    assert any("scenes must be contiguous" in error for error in report.errors)
