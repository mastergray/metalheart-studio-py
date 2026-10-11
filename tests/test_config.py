# Unit tests for JSON config resolution and validation

from pathlib import Path  # Type temporary test paths and create audio placeholders
from typing import Any, Dict  # Python 3.8-compatible config annotations

from metalheart.catalog import PALETTES  # Verify every stable palette reaches the public schema
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
    assert resolved["scenes"][0]["renderer"]["decor"]["enabled"]
    assert resolved["scenes"][0]["background"]["palette"] == "steel"
    assert resolved["scenes"][0]["renderer"]["decor"]["ribbons"]["palette"] == "steel"
    authored["scenes"][0]["renderer"]["decor"] = False
    resolved = resolver.resolve(authored, str(configPath))
    assert not resolved["scenes"][0]["renderer"]["decor"]["enabled"]
    assert not resolved["scenes"][0]["renderer"]["decor"]["ribbons"]["enabled"]
    assert not resolved["scenes"][0]["renderer"]["decor"]["plates"]["enabled"]
    assert resolved["scenes"][0]["overlay"] == {"enabled": False, "reference_hud": False, "items": []}
    assert resolved["settings"]["crf"] == 23
    assert resolved["scenes"][0]["finish"]["psx"] == {
        "preset": "custom",
        "render_scale": 1.0,
        "color_levels": 0,
        "dither": "none",
        "dither_strength": 1.0,
    }


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
    assert scene["background"]["palette"] == "ember"
    assert scene["renderer"]["decor"]["ribbons"]["palette"] == "ember"
    assert scene["renderer"]["forms"] == ["ferro"]
    assert scene["renderer"]["form_len_sec"] == 3.0
    assert "preset" not in scene["renderer"]
    assert "looks" not in scene["renderer"]
    assert "hud" not in scene["renderer"]
    assert scene["finish"]["scanlines"]
    assert not scene["overlay"]["enabled"]


# :: PATH -> NONE
# Verifies background and ribbon palettes resolve independently from the form
def testResolvesIndependentLayerPalettes(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["renderer"] = {
        "core": "3d",
        "palette": "rainbow",
        "decor": {"ribbons": {"palette": "electric"}},
    }
    authored["scenes"][0]["background"] = {"palette": "ice"}
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert report.isValid, report.errors
    scene = resolved["scenes"][0]
    assert scene["renderer"]["palette"] == "rainbow"
    assert scene["background"]["palette"] == "ice"
    assert scene["renderer"]["decor"]["ribbons"]["palette"] == "electric"
    authored["scenes"][0]["background"]["palette"] = "unknown"
    authored["scenes"][0]["background"]["intensity"] = 4.1
    authored["scenes"][0]["renderer"]["decor"]["ribbons"]["palette"] = "invalid"
    invalid = resolver.validate(
        resolver.resolve(authored, str(tmp_path / "project.json"))
    )
    assert any("background.palette" in error for error in invalid.errors)
    assert any("background.intensity" in error for error in invalid.errors)
    assert any("ribbons.palette" in error for error in invalid.errors)


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


# :: PATH -> NONE
# Verifies PSX finish controls reject unsafe scales, levels, and dither combinations
def testRejectsInvalidPsxFinishControls(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["finish"] = {
        "psx": {
            "preset": "missing",
            "render_scale": 0.1,
            "color_levels": 0,
            "dither": "bayer3",
            "dither_strength": 1.2,
        }
    }
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert not report.isValid
    assert any("finish.psx.preset" in error for error in report.errors)
    assert any("finish.psx.render_scale" in error for error in report.errors)
    assert any("finish.psx.dither" in error for error in report.errors)
    assert any("finish.psx.dither_strength" in error for error in report.errors)


# :: PATH -> NONE
# Verifies ordered dithering requires an explicit reduced-color target
def testRejectsDitherWithoutColorReduction(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["finish"] = {"psx": {"dither": "bayer4"}}
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert not report.isValid
    assert any("finish.psx.color_levels" in error for error in report.errors)


# :: PATH -> NONE
# Verifies the approved PSX recipe expands to ordinary reproducible values
def testResolvesPsxFinishPreset(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["finish"] = {"psx": {"preset": "combined"}}
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert report.isValid, report.errors
    assert resolved["scenes"][0]["finish"]["psx"] == {
        "preset": "combined",
        "render_scale": 0.5,
        "color_levels": 16,
        "dither": "bayer4",
        "dither_strength": 0.75,
    }


# :: PATH -> NONE
# Verifies authored values may override one constituent of a named PSX recipe
def testOverridesPsxFinishPresetValue(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["finish"] = {
        "psx": {"preset": "combined", "render_scale": 0.25}
    }
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    assert resolved["scenes"][0]["finish"]["psx"]["render_scale"] == 0.25
    assert resolved["scenes"][0]["finish"]["psx"]["color_levels"] == 16


# :: PATH -> NONE
# Verifies scene and global effect references expand to reproducible ordered operations
def testResolvesAndValidatesOrderedEffects(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["post"] = [
        {
            "type": "post_filter",
            "id": "rgb_shift",
            "parameters": {"rX": 9, "bX": -4},
        },
        {"id": "hyper_glitch_like", "enabled": False, "mix": 0.6},
    ]
    authored["post"] = [{"id": "retro_crt_like"}]
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert report.isValid, report.errors
    sceneEffects = resolved["scenes"][0]["post"]
    assert [effect["id"] for effect in sceneEffects] == ["rgb_shift", "hyper_glitch_like"]
    assert sceneEffects[0]["parameters"] == {"rX": 9, "bX": -4, "edge_mode": "wrap"}
    assert sceneEffects[0]["operations"] == [{"op": "rgbShift", "rX": 9, "bX": -4, "edge_mode": "wrap"}]
    assert not sceneEffects[1]["enabled"]
    assert resolved["post"][0]["operations"][0]["op"] == "pixelate"
    rerenderedProfile = resolver.resolve(resolved, str(tmp_path / "profile.json"))
    assert rerenderedProfile["scenes"][0]["post"] == resolved["scenes"][0]["post"]
    assert rerenderedProfile["post"] == resolved["post"]


# :: PATH -> NONE
# Verifies background, form, and ribbon chains share effect resolution and validation
def testResolvesLayerScopedEffects(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["renderer"] = {
        "core": "3d",
        "surface": {"post": [{"id": "posterize", "parameters": {"levels": 3}}]},
        "decor": {"ribbons": {"post": [{"id": "tear", "parameters": {"strength": 7}}]}},
    }
    authored["scenes"][0]["background"] = {"post": [{"id": "invert", "mix": 0.5}]}
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert report.isValid, report.errors
    scene = resolved["scenes"][0]
    assert scene["renderer"]["surface"]["post"][0]["operations"][0]["levels"] == 3
    assert scene["renderer"]["decor"]["ribbons"]["post"][0]["operations"][0]["strength"] == 7
    assert scene["background"]["post"][0]["mix"] == 0.5

    authored["scenes"][0]["renderer"]["core"] = "2d"
    invalid = resolver.resolve(authored, str(tmp_path / "project.json"))
    invalidReport = resolver.validate(invalid)
    assert any("surface.post: scoped effects require the 3d core" in error for error in invalidReport.errors)
    assert any("ribbons.post: scoped effects require the 3d core" in error for error in invalidReport.errors)
    assert any("background.post: scoped effects require the 3d core" in error for error in invalidReport.errors)


# :: PATH -> NONE
# Verifies invalid effect identifiers and typed parameters fail before rendering
def testRejectsInvalidEffects(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["post"] = [
        {"id": "not-an-effect"},
        {"id": "pixelate", "parameters": {"size": 0}},
        {"id": "contrast", "parameters": {"value": True}, "mix": 2.0},
        {"id": "chromatic", "parameters": {"direction": "diagonal"}},
    ]
    authored["post"] = "not-an-array"
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert not report.isValid
    assert any("unknown effect" in error for error in report.errors)
    assert any("parameters.size" in error for error in report.errors)
    assert any("parameters.value" in error for error in report.errors)
    assert any("parameters.direction" in error for error in report.errors)
    assert any(".mix" in error for error in report.errors)
    assert any("$.post: expected an array" == error for error in report.errors)


# :: VOID -> NONE
# Verifies generated schema documents the stable public vocabulary
def testSchemaPublishesFormsFinishAndOverlay() -> None:
    schema = ConfigResolver.init().schema()
    renderer = schema["$defs"]["renderer"]["properties"]
    scene = schema["$defs"]["scene"]["properties"]
    assert "forms" in renderer
    assert "palette" in renderer
    assert renderer["palette"]["enum"] == PALETTES
    assert "looks" not in renderer
    assert "preset" not in renderer
    assert "camera_speed" in renderer
    assert "camera_phase_sec" in renderer
    assert "camera_intensity" in renderer
    modulators = schema["$defs"]["scene"]["properties"]["reactivity"]["properties"]["modulators"]["additionalProperties"]
    assert modulators == {"$ref": "#/$defs/binding"}
    assert "resonance" in renderer["forms"]["items"]["enum"]
    assert "radial" in renderer["forms"]["items"]["enum"]
    assert "stretch" not in renderer["forms"]["items"]["enum"]
    assert "heart" not in renderer["forms"]["items"]["enum"]
    assert renderer["surface"] == {"$ref": "#/$defs/surface"}
    assert renderer["form_style"] == {"$ref": "#/$defs/formStyle"}
    assert {"$ref": "#/$defs/decor"} in renderer["decor"]["anyOf"]
    surface = schema["$defs"]["surface"]["properties"]
    assert surface["sampling"]["enum"] == ["bilinear", "nearest"]
    assert "texel_steps" in surface
    assert "lighting_steps" in surface
    assert surface["post"] == {"type": "array", "items": {"$ref": "#/$defs/effect"}}
    assert "finish" in scene
    assert scene["post"] == {"type": "array", "items": {"$ref": "#/$defs/effect"}}
    assert schema["properties"]["post"] == {"type": "array", "items": {"$ref": "#/$defs/effect"}}
    assert "hyper_glitch_like" in schema["$defs"]["effect"]["properties"]["id"]["enum"]
    assert "overlay" in scene
    assert scene["background"] == {"$ref": "#/$defs/background"}
    assert schema["$defs"]["background"]["properties"]["fit"]["enum"] == [
        "cover",
        "contain",
        "tile",
    ]
    background = schema["$defs"]["background"]["properties"]
    assert background["palette"]["enum"] == PALETTES
    assert background["intensity"] == {
        "type": "number",
        "minimum": 0.0,
        "maximum": 4.0,
    }
    assert background["post"] == {"type": "array", "items": {"$ref": "#/$defs/effect"}}
    ribbon = schema["$defs"]["ribbonElement"]["allOf"][1]["properties"]
    assert ribbon["palette"]["enum"] == PALETTES
    assert schema["$defs"]["ribbonElement"]["allOf"][1]["properties"]["post"] == {
        "type": "array",
        "items": {"$ref": "#/$defs/effect"},
    }
    assert background["material"]["enum"] == ["flat", "matte", "metallic"]
    assert "amount" in background["ripple"]["properties"]
    assert "roughness" in background["ripple"]["properties"]


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
# Verifies spectral radial publishes multidirectional geometry destinations
def testResolvesSpectralRadialPreset(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["renderer"] = {"core": "3d", "forms": ["radial"]}
    authored["scenes"][0]["reactivity"] = {"preset": "spectral-radial"}
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert report.isValid, report.errors
    assert set(resolved["scenes"][0]["reactivity"]["modulators"]) == {
        "form_extent",
        "form_rotation",
        "form_ripple",
    }


# :: PATH -> NONE
# Verifies jagged radial styles and their explicit audio destinations resolve safely
def testResolvesJaggedRadialStyle(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["renderer"] = {
        "core": "3d",
        "forms": ["radial"],
        "form_style": {
            "faceting": 0.55,
            "jaggedness": 0.02,
            "jagged_scale": 4.0,
            "geometry_steps": 6,
        },
    }
    authored["scenes"][0]["reactivity"] = {"preset": "spectral-radial-jagged"}
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert report.isValid, report.errors
    assert set(resolved["scenes"][0]["reactivity"]["modulators"]) == {
        "form_extent",
        "form_rotation",
        "form_ripple",
        "form_jaggedness",
        "form_jagged_scale",
    }
    authored["scenes"][0]["renderer"]["core"] = "2d"
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert any("form styling requires the 3d core" in error for error in report.errors)
    authored["scenes"][0]["renderer"].update({"core": "3d", "forms": ["mercury"]})
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert any("form styling currently requires the radial form" in error for error in report.errors)


# :: PATH -> NONE
# Verifies image skins resolve relative paths and require the 3D core
def testResolvesImageSurfacePath(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    skinPath = tmp_path / "skin.png"
    skinPath.write_bytes(b"placeholder")
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["renderer"] = {
        "core": "3d",
        "forms": ["radial"],
        "surface": {"image": "skin.png", "material": "matte"},
    }
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert report.isValid, report.errors
    assert resolved["scenes"][0]["renderer"]["surface"]["image"] == str(skinPath)
    assert resolved["scenes"][0]["renderer"]["surface"]["material"] == "matte"
    assert resolved["scenes"][0]["renderer"]["surface"]["sampling"] == "bilinear"
    assert resolved["scenes"][0]["renderer"]["surface"]["texel_steps"] == 0
    assert resolved["scenes"][0]["renderer"]["surface"]["lighting_steps"] == 0
    authored["scenes"][0]["renderer"]["core"] = "2d"
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert any("image skins require the 3d core" in error for error in report.errors)
    authored["scenes"][0]["renderer"]["surface"] = "invalid"
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert any("renderer.surface: expected an object" in error for error in report.errors)


# :: PATH -> NONE
# Verifies image backgrounds resolve paths and background pulse remains 3D-only
def testResolvesImageBackgroundPath(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    backgroundPath = tmp_path / "background.png"
    backgroundPath.write_bytes(b"placeholder")
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["renderer"] = {"core": "3d", "forms": ["radial"]}
    authored["scenes"][0]["background"] = {
        "source": "image",
        "image": "background.png",
        "fit": "contain",
        "pulse_scale": 0.2,
        "material": "metallic",
        "ripple": {
            "enabled": True,
            "amount": 0.1,
            "scale": 6.0,
            "travel_speed": 0.5,
            "warp": 0.03,
            "specular": 0.9,
            "roughness": 0.25,
        },
    }
    authored["scenes"][0]["reactivity"] = {
        "preset": "spectral-radial",
        "modulators": {
            "background_pulse": {
                "source": "bass",
                "amount": 1.0,
                "clamp": [0.0, 1.0],
            },
            "background_ripple": {
                "source": "amplitude",
                "amount": 1.0,
                "clamp": [0.0, 1.0],
            },
        },
    }
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert report.isValid, report.errors
    assert resolved["scenes"][0]["background"]["image"] == str(backgroundPath)
    assert resolved["scenes"][0]["background"]["fit"] == "contain"
    assert resolved["scenes"][0]["background"]["ripple"]["enabled"]
    authored["scenes"][0]["renderer"]["core"] = "2d"
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert any("customized backgrounds require the 3d core" in error for error in report.errors)
    assert any("background modulation requires the 3d core" in error for error in report.errors)


# :: PATH -> NONE
# Verifies unsafe background material and ripple values fail before rendering
def testRejectsInvalidBackgroundRippleControls(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["renderer"] = {"core": "3d"}
    authored["scenes"][0]["background"] = {
        "material": "glass",
        "ripple": {
            "enabled": "yes",
            "amount": 0.6,
            "scale": 0.0,
            "travel_speed": 5.0,
            "warp": 0.3,
            "specular": 3.0,
            "roughness": 1.5,
        },
    }
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert not report.isValid
    assert any("background.material" in error for error in report.errors)
    assert any("ripple.enabled" in error for error in report.errors)
    for key in ("amount", "scale", "travel_speed", "warp", "specular", "roughness"):
        assert any("ripple.{0}".format(key) in error for error in report.errors)


# :: PATH -> NONE
# Verifies independent decor counts, skins, mappings, and audio controls resolve on 3D
def testResolvesFirstClassDecorConfig(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    ribbonPath = tmp_path / "ribbon.png"
    platePath = tmp_path / "plate.png"
    ribbonPath.write_bytes(b"ribbon")
    platePath.write_bytes(b"plate")
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["renderer"] = {
        "core": "3d",
        "decor": {
            "enabled": True,
            "seed": 17,
            "ribbons": {
                "enabled": True,
                "count": 2,
                "material": "matte",
                "surface": {"image": "ribbon.png", "mapping": "ribbon"},
            },
            "plates": {
                "enabled": False,
                "count": 1,
                "surface": {"image": "plate.png", "mapping": "planar"},
            },
        },
    }
    authored["scenes"][0]["reactivity"] = {
        "preset": "spectral-radial",
        "modulators": {
            "ribbon_width": {"source": "bass", "amount": 0.5, "clamp": [0.0, 0.5]},
            "ribbon_twist": {"source": "mid", "amount": 1.2, "clamp": [0.0, 1.2]},
            "plate_orbit": {"source": "high", "amount": 1.0, "clamp": [0.0, 1.0]},
        },
    }
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert report.isValid, report.errors
    decor = resolved["scenes"][0]["renderer"]["decor"]
    assert decor["seed"] == 17
    assert decor["ribbons"]["count"] == 2
    assert decor["ribbons"]["surface"]["image"] == str(ribbonPath)
    assert decor["plates"]["surface"]["image"] == str(platePath)
    authored["scenes"][0]["renderer"]["core"] = "2d"
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert any("first-class decor controls require the 3d core" in error for error in report.errors)
    assert any("decor modulation requires the 3d core" in error for error in report.errors)


# :: PATH -> NONE
# Verifies unsafe decor counts, materials, mappings, and style values are rejected
def testRejectsInvalidDecorControls(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["renderer"] = {
        "core": "3d",
        "decor": {
            "enabled": "yes",
            "seed": True,
            "ribbons": {
                "enabled": 1,
                "count": 9,
                "material": "glass",
                "surface": {
                    "mapping": "planar",
                    "sampling": "cubic",
                    "scale": 0.0,
                    "texel_steps": 1,
                },
            },
            "plates": {"count": -1},
        },
    }
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert not report.isValid
    for fragment in (
        "decor.enabled",
        "decor.seed",
        "ribbons.enabled",
        "ribbons.count",
        "ribbons.material",
        "ribbons.surface.mapping",
        "ribbons.surface.sampling",
        "ribbons.surface.scale",
        "ribbons.surface.texel_steps",
        "plates.count",
    ):
        assert any(fragment in error for error in report.errors)
    authored["scenes"][0]["renderer"]["decor"] = "invalid"
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert any("renderer.decor: expected an object" in error for error in report.errors)


# :: PATH -> NONE
# Verifies PSX-style surface controls reject unsupported modes and unsafe steps
def testRejectsInvalidSurfaceStyleControls(tmp_path: Path) -> None:
    resolver = ConfigResolver.init()
    skinPath = tmp_path / "skin.png"
    skinPath.write_bytes(b"placeholder")
    authored = _validConfig(tmp_path)
    authored["scenes"][0]["renderer"] = {
        "core": "3d",
        "surface": {
            "image": "skin.png",
            "sampling": "cubic",
            "texel_steps": 1,
            "lighting_steps": 65,
        },
    }
    resolved = resolver.resolve(authored, str(tmp_path / "project.json"))
    report = resolver.validate(resolved)
    assert not report.isValid
    assert any("surface.sampling" in error for error in report.errors)
    assert any("surface.texel_steps" in error for error in report.errors)
    assert any("surface.lighting_steps" in error for error in report.errors)


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
