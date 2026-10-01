# JSON config loading, template resolution, defaults, and validation

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import copy  # Copy nested config values without shared mutable state
import json  # Read and write the JSON authoring format
from pathlib import Path  # Resolve config-relative filesystem paths
from typing import Any, Dict, List, Optional, Tuple  # Python 3.8-compatible type annotations

from metalheart.catalog import CAMERAS  # Supported camera identifiers
from metalheart.catalog import CORES  # Supported renderer core identifiers
from metalheart.catalog import CONFIG_SCHEMA  # Public JSON Schema document
from metalheart.catalog import CURVES  # Supported binding curve identifiers
from metalheart.catalog import DEFAULT_BACKGROUND  # Typed background defaults
from metalheart.catalog import DEFAULT_DECOR  # First-class ribbon and plate defaults
from metalheart.catalog import DEFAULT_FINISH  # Owned finishing-pass defaults
from metalheart.catalog import DEFAULT_OVERLAY  # Text-overlay defaults
from metalheart.catalog import DEFAULT_RENDERER  # Renderer defaults
from metalheart.catalog import DEFAULT_SETTINGS  # Project render defaults
from metalheart.catalog import DESTINATIONS  # Supported renderer signal destinations
from metalheart.catalog import FORMS  # Supported Metalheart form identifiers
from metalheart.catalog import MODULATORS  # Supported frame-space audio destinations
from metalheart.catalog import PALETTES  # Supported Metalheart palettes
from metalheart.catalog import QUALITY_PROFILES  # Concrete render-quality settings
from metalheart.catalog import QUALITY_RENDERER_PROFILES  # Concrete renderer-quality settings
from metalheart.catalog import REACTIVITY_PRESETS  # Built-in audio binding presets
from metalheart.catalog import SOURCES  # Supported audio feature sources
from metalheart.catalog import TEMPLATES  # Built-in scene templates
from metalheart.effect_catalog import effectDefinition  # Expand owned effects into reproducible operations


# Raised when a config cannot be parsed or resolved
class ConfigError(Exception):
    pass


# Stores validation errors and non-blocking warnings
class ValidationReport:

    # CONSTRUCTOR :: [STRING]?, [STRING]? -> validationReport
    # Creates a validation report from optional error and warning lists
    def __init__(self, errors: Optional[List[str]] = None, warnings: Optional[List[str]] = None) -> None:
        self._errors: List[str] = list(errors or [])
        self._warnings: List[str] = list(warnings or [])

    #
    # Properties
    #

    # PROPERTY :: VOID -> [STRING]
    # Returns a copy of blocking validation errors
    @property
    def errors(self) -> List[str]:
        return list(self._errors)

    # PROPERTY :: VOID -> [STRING]
    # Returns a copy of non-blocking validation warnings
    @property
    def warnings(self) -> List[str]:
        return list(self._warnings)

    # PROPERTY :: VOID -> BOOL
    # Reports whether the config has no blocking errors
    @property
    def isValid(self) -> bool:
        return not self._errors

    #
    # Instance Methods
    #

    # :: STRING -> NONE
    # Adds a blocking validation error
    def addError(self, message: str) -> None:
        self._errors.append(message)

    # :: STRING -> NONE
    # Adds a non-blocking validation warning
    def addWarning(self, message: str) -> None:
        self._warnings.append(message)

    # :: VOID -> ARRAY<STRING, ANY>
    # Serializes the report for CLI JSON output
    def toDict(self) -> Dict[str, Any]:
        return {"valid": self.isValid, "errors": self.errors, "warnings": self.warnings}


# Resolves authored JSON into complete renderer-ready configuration
class ConfigResolver:

    # CONSTRUCTOR :: ARRAY<STRING, ANY>? -> configResolver
    # Creates a resolver with built-in or caller-supplied scene templates
    def __init__(self, templates: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self._templates: Dict[str, Dict[str, Any]] = copy.deepcopy(templates or TEMPLATES)

    #
    # Instance Methods
    #

    # :: STRING -> ARRAY<STRING, ANY>
    # Loads a JSON config file and reports parse failures with its path
    def load(self, path: str) -> Dict[str, Any]:
        configPath = Path(path).resolve()
        try:
            with configPath.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            raise ConfigError("unable to load config {0}: {1}".format(configPath, error))
        if not isinstance(value, dict):
            raise ConfigError("config root must be a JSON object: {0}".format(configPath))
        return value

    # :: ARRAY<STRING, ANY>, STRING -> ARRAY<STRING, ANY>
    # Expands templates and defaults and resolves filesystem paths
    def resolve(self, authored: Dict[str, Any], configPath: str) -> Dict[str, Any]:
        basePath = Path(configPath).resolve().parent
        resolved: Dict[str, Any] = copy.deepcopy(authored)
        resolved["version"] = authored.get("version", 1)
        resolved["audio"] = self._resolvePath(authored.get("audio"), basePath)
        authoredSettings = authored.get("settings", {})
        quality = authoredSettings.get("quality", DEFAULT_SETTINGS["quality"]) if isinstance(authoredSettings, dict) else DEFAULT_SETTINGS["quality"]
        profile = QUALITY_PROFILES.get(quality, QUALITY_PROFILES["final"])
        resolved["settings"] = self._deepMerge(self._deepMerge(DEFAULT_SETTINGS, profile), authoredSettings)
        analysis = copy.deepcopy(authored.get("analysis", {}))
        if analysis.get("cache"):
            analysis["cache"] = self._resolvePath(analysis["cache"], basePath)
        resolved["analysis"] = analysis
        scenes = authored.get("scenes", [])
        resolved["scenes"] = [self._resolveScene(scene, index, quality, basePath) for index, scene in enumerate(scenes)] if isinstance(scenes, list) else scenes
        resolved["post"] = self._resolvePost(authored.get("post", []))
        resolved["_meta"] = {
            "config_path": str(Path(configPath).resolve()),
            "schema_version": 1,
        }
        return resolved

    # :: ARRAY<STRING, ANY> -> validationReport
    # Validates a resolved config without performing expensive audio analysis
    def validate(self, config: Dict[str, Any]) -> ValidationReport:
        report = ValidationReport()
        if config.get("version") != 1:
            report.addError("$.version: expected 1")
        audio = config.get("audio")
        if not isinstance(audio, str) or not audio:
            report.addError("$.audio: expected a non-empty path")
        elif not Path(audio).is_file():
            report.addError("$.audio: file not found: {0}".format(audio))
        settings = config.get("settings")
        if not isinstance(settings, dict):
            report.addError("$.settings: expected an object")
            settings = {}
        self._validateSettings(settings, report)
        scenes = config.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            report.addError("$.scenes: expected at least one scene")
            return report
        for index, scene in enumerate(scenes):
            self._validateScene(scene, index, report)
        self._validateSceneOrder(scenes, settings, report)
        self._validatePost(config.get("post"), "$.post", report)
        return report

    # :: ARRAY<STRING, ANY>, STRING -> NONE
    # Writes a resolved config or render profile as stable formatted JSON
    def write(self, config: Dict[str, Any], path: str) -> None:
        outputPath = Path(path)
        outputPath.parent.mkdir(parents=True, exist_ok=True)
        with outputPath.open("w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2, sort_keys=True)
            handle.write("\n")

    #
    # Protected Methods
    #

    # :: ANY, PATH -> ANY
    # Resolves a string path relative to the config directory
    def _resolvePath(self, value: Any, basePath: Path) -> Any:
        if not isinstance(value, str) or not value:
            return value
        path = Path(value).expanduser()
        return str((basePath / path).resolve()) if not path.is_absolute() else str(path.resolve())

    # :: ARRAY<STRING, ANY>, INT, STRING, PATH -> ARRAY<STRING, ANY>
    # Resolves one scene template, renderer defaults, and reactivity preset
    def _resolveScene(self, authored: Any, index: int, quality: str, basePath: Path) -> Any:
        if not isinstance(authored, dict):
            return authored
        templateId = authored.get("template")
        template = copy.deepcopy(self._templates.get(templateId, {})) if isinstance(templateId, str) else {}
        authoredScene = copy.deepcopy(authored)
        templateRenderer, templateFinish = self._normalizeRenderer(template.get("renderer", {}))
        authoredRenderer, authoredFinish = self._normalizeRenderer(authoredScene.get("renderer", {}))
        template["renderer"] = templateRenderer
        authoredScene["renderer"] = authoredRenderer
        scene = self._deepMerge(template, authoredScene)
        scene["id"] = scene.get("id", "scene-{0}".format(index + 1))
        scene["name"] = scene.get("name", str(scene["id"]))
        rendererDefaults = self._deepMerge(DEFAULT_RENDERER, QUALITY_RENDERER_PROFILES.get(quality, QUALITY_RENDERER_PROFILES["final"]))
        scene["renderer"] = self._deepMerge(rendererDefaults, scene.get("renderer", {}))
        scene["renderer"]["decor"] = self._resolveDecor(scene["renderer"].get("decor"))
        decor = scene["renderer"]["decor"]
        if isinstance(decor, dict):
            for element in ("ribbons", "plates"):
                elementConfig = decor.get(element)
                surfaceConfig = elementConfig.get("surface") if isinstance(elementConfig, dict) else None
                if isinstance(surfaceConfig, dict) and surfaceConfig.get("image"):
                    surfaceConfig["image"] = self._resolvePath(surfaceConfig["image"], basePath)
            ribbons = decor.get("ribbons")
            if isinstance(ribbons, dict):
                if ribbons.get("palette") is None:
                    ribbons["palette"] = scene["renderer"]["palette"]
                ribbons["post"] = self._resolvePost(ribbons.get("post", []))
        surface = scene["renderer"].get("surface")
        if isinstance(surface, dict):
            if surface.get("image"):
                surface["image"] = self._resolvePath(surface["image"], basePath)
            surface["post"] = self._resolvePost(surface.get("post", []))
        scene["background"] = self._deepMerge(DEFAULT_BACKGROUND, scene.get("background", {}))
        background = scene["background"]
        if isinstance(background, dict):
            if background.get("palette") is None:
                background["palette"] = scene["renderer"]["palette"]
            if background.get("image"):
                background["image"] = self._resolvePath(background["image"], basePath)
            background["post"] = self._resolvePost(background.get("post", []))
        legacyFinish = self._deepMerge(templateFinish, authoredFinish)
        scene["finish"] = self._deepMerge(DEFAULT_FINISH, self._deepMerge(legacyFinish, scene.get("finish", {})))
        reactivity = copy.deepcopy(scene.get("reactivity", {}))
        presetId = reactivity.get("preset", "balanced")
        preset = REACTIVITY_PRESETS.get(presetId, {"bindings": {}})
        scene["reactivity"] = self._deepMerge(preset, reactivity)
        scene["reactivity"]["preset"] = presetId
        scene["overlay"] = self._deepMerge(DEFAULT_OVERLAY, scene.get("overlay", {}))
        scene["post"] = self._resolvePost(scene.get("post", []))
        return scene

    # :: ANY -> ANY
    # Expands one authored effect chain while preserving invalid values for validation
    def _resolvePost(self, value: Any) -> Any:
        if not isinstance(value, list):
            return copy.deepcopy(value)
        return [self._resolveEffect(entry) for entry in value]

    # :: ANY -> ANY
    # Expands one catalog reference into deterministic render-profile operations
    def _resolveEffect(self, value: Any) -> Any:
        if not isinstance(value, dict):
            return copy.deepcopy(value)
        effectId = value.get("id")
        definition = effectDefinition(effectId) if isinstance(effectId, str) else None
        resolved = copy.deepcopy(value)
        resolved["type"] = value.get("type", "post_filter")
        resolved["enabled"] = value.get("enabled", True)
        resolved["mix"] = value.get("mix", 1.0)
        authoredParameters = value.get("parameters", value.get("props", {}))
        parameters: Dict[str, Any] = {}
        if definition is not None:
            for name, metadata in definition["parameters"].items():
                parameters[name] = copy.deepcopy(metadata["default"])
        if isinstance(authoredParameters, dict):
            parameters.update(copy.deepcopy(authoredParameters))
        else:
            parameters = copy.deepcopy(authoredParameters)
        resolved["parameters"] = parameters
        resolved.pop("props", None)
        if definition is not None:
            authoredOperations = value.get("operations")
            operations = copy.deepcopy(authoredOperations) if isinstance(authoredOperations, list) else copy.deepcopy(definition["operations"])
            if len(operations) == 1 and isinstance(parameters, dict):
                operations[0].update(parameters)
            resolved["operations"] = operations
        return resolved

    # :: ANY -> (ARRAY<STRING, ANY>, ARRAY<STRING, ANY>)
    # Migrates legacy backend renderer keys into the public authoring vocabulary
    def _normalizeRenderer(self, value: Any) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        renderer = copy.deepcopy(value) if isinstance(value, dict) else {}
        aliases = (("preset", "palette"), ("looks", "forms"), ("look_len_sec", "form_len_sec"))
        for legacy, public in aliases:
            if public not in renderer and legacy in renderer:
                renderer[public] = renderer[legacy]
            renderer.pop(legacy, None)
        finish: Dict[str, Any] = {}
        if "scanlines" in renderer:
            finish["scanlines"] = renderer.pop("scanlines")
        renderer.pop("hud", None)
        return renderer, finish

    # :: ARRAY<STRING, ANY>, ARRAY<STRING, ANY> -> ARRAY<STRING, ANY>
    # Deep-merges objects while replacing lists and scalar values
    def _deepMerge(self, base: Dict[str, Any], override: Any) -> Dict[str, Any]:
        result = copy.deepcopy(base)
        if not isinstance(override, dict):
            return result
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._deepMerge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    # :: ANY -> ANY
    # Expands the legacy decor boolean into independent ribbon and plate settings
    def _resolveDecor(self, value: Any) -> Any:
        if isinstance(value, bool):
            return self._deepMerge(
                DEFAULT_DECOR,
                {
                    "enabled": value,
                    "ribbons": {"enabled": value},
                    "plates": {"enabled": value},
                },
            )
        if not isinstance(value, dict):
            return value
        return self._deepMerge(DEFAULT_DECOR, value)

    # :: ARRAY<STRING, ANY>, validationReport -> NONE
    # Validates global output settings
    def _validateSettings(self, settings: Dict[str, Any], report: ValidationReport) -> None:
        for key in ("width", "height", "fps"):
            value = settings.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                report.addError("$.settings.{0}: expected a positive integer".format(key))
        for key in ("width", "height"):
            value = settings.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value % 2:
                report.addError("$.settings.{0}: libx264 requires an even value".format(key))
        crf = settings.get("crf")
        if isinstance(crf, bool) or not isinstance(crf, int) or not 0 <= crf <= 51:
            report.addError("$.settings.crf: expected an integer from 0 through 51")
        seed = settings.get("seed")
        if settings.get("quality") == "final" and (isinstance(seed, bool) or not isinstance(seed, int)):
            report.addError("$.settings.seed: final renders require an integer seed")
        if settings.get("quality") not in ("preview", "draft", "final"):
            report.addError("$.settings.quality: expected preview, draft, or final")
        if settings.get("time_mode") not in ("global", "scene"):
            report.addError("$.settings.time_mode: expected global or scene")
        workers = settings.get("workers")
        if workers != "auto" and (isinstance(workers, bool) or not isinstance(workers, int) or workers <= 0):
            report.addError("$.settings.workers: expected 'auto' or a positive integer")
        chunkSec = settings.get("chunk_sec")
        if isinstance(chunkSec, bool) or not isinstance(chunkSec, (int, float)) or chunkSec <= 0.0:
            report.addError("$.settings.chunk_sec: expected a positive number")
        if not isinstance(settings.get("resume"), bool):
            report.addError("$.settings.resume: expected a boolean")

    # :: ANY, INT, validationReport -> NONE
    # Validates one resolved scene and its renderer and reactivity blocks
    def _validateScene(self, scene: Any, index: int, report: ValidationReport) -> None:
        prefix = "$.scenes[{0}]".format(index)
        if not isinstance(scene, dict):
            report.addError("{0}: expected an object".format(prefix))
            return
        if scene.get("template") and scene.get("template") not in self._templates:
            report.addError("{0}.template: unknown template {1!r}".format(prefix, scene.get("template")))
        for key in ("start_sec", "end_sec"):
            value = scene.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                report.addError("{0}.{1}: expected a number".format(prefix, key))
        start = scene.get("start_sec")
        end = scene.get("end_sec")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end <= start:
            report.addError("{0}.end_sec: must be greater than start_sec".format(prefix))
        renderer = scene.get("renderer")
        if not isinstance(renderer, dict):
            report.addError("{0}.renderer: expected an object".format(prefix))
        else:
            self._validateRenderer(renderer, prefix, report)
        reactivity = scene.get("reactivity")
        if not isinstance(reactivity, dict):
            report.addError("{0}.reactivity: expected an object".format(prefix))
        else:
            self._validateReactivity(reactivity, prefix, report)
        background = scene.get("background")
        if not isinstance(background, dict):
            report.addError("{0}.background: expected an object".format(prefix))
        else:
            core = renderer.get("core") if isinstance(renderer, dict) else None
            rendererPalette = renderer.get("palette") if isinstance(renderer, dict) else None
            self._validateBackground(background, core, rendererPalette, prefix, report)
            defaultBackground = copy.deepcopy(DEFAULT_BACKGROUND)
            defaultBackground["palette"] = rendererPalette
            if core != "3d" and background != defaultBackground:
                report.addError(
                    "{0}.background: customized backgrounds require the 3d core".format(prefix)
                )
        if (
            isinstance(renderer, dict)
            and renderer.get("core") != "3d"
            and isinstance(reactivity, dict)
            and {
                "background_pulse",
                "background_ripple",
                "background_ripple_scale",
                "background_ripple_impact",
            }.intersection(reactivity.get("modulators", {}))
        ):
            report.addError(
                "{0}.reactivity.modulators: background modulation requires the 3d core".format(prefix)
            )
        if (
            isinstance(renderer, dict)
            and renderer.get("core") != "3d"
            and isinstance(reactivity, dict)
            and {
                "ribbon_width",
                "ribbon_twist",
                "ribbon_wave",
                "ribbon_speed",
                "plate_orbit",
                "plate_displacement",
            }.intersection(reactivity.get("modulators", {}))
        ):
            report.addError(
                "{0}.reactivity.modulators: decor modulation requires the 3d core".format(prefix)
            )
        overlay = scene.get("overlay")
        if not isinstance(overlay, dict):
            report.addError("{0}.overlay: expected an object".format(prefix))
        else:
            self._validateOverlay(overlay, prefix, report)
        finish = scene.get("finish")
        if not isinstance(finish, dict):
            report.addError("{0}.finish: expected an object".format(prefix))
        else:
            self._validateFinish(finish, prefix, report)
        self._validatePost(scene.get("post"), prefix + ".post", report)

    # :: ANY, STRING, validationReport -> NONE
    # Validates an ordered scene or global effect chain
    def _validatePost(self, value: Any, path: str, report: ValidationReport) -> None:
        if not isinstance(value, list):
            report.addError("{0}: expected an array".format(path))
            return
        for index, entry in enumerate(value):
            self._validateEffect(entry, "{0}[{1}]".format(path, index), report)

    # :: ANY, STRING, validationReport -> NONE
    # Validates one resolved catalog effect and its typed parameters
    def _validateEffect(self, value: Any, path: str, report: ValidationReport) -> None:
        if not isinstance(value, dict):
            report.addError("{0}: expected an object".format(path))
            return
        if value.get("type") != "post_filter":
            report.addError("{0}.type: expected 'post_filter'".format(path))
        effectId = value.get("id")
        definition = effectDefinition(effectId) if isinstance(effectId, str) else None
        if definition is None:
            report.addError("{0}.id: unknown effect {1!r}".format(path, effectId))
            return
        if not isinstance(value.get("enabled"), bool):
            report.addError("{0}.enabled: expected a boolean".format(path))
        mix = value.get("mix")
        if isinstance(mix, bool) or not isinstance(mix, (int, float)) or not 0.0 <= mix <= 1.0:
            report.addError("{0}.mix: expected 0.0 through 1.0".format(path))
        parameters = value.get("parameters")
        if not isinstance(parameters, dict):
            report.addError("{0}.parameters: expected an object".format(path))
            return
        parameterDefinitions = definition["parameters"]
        for name in parameters:
            if name not in parameterDefinitions:
                report.addError("{0}.parameters.{1}: unknown parameter".format(path, name))
        for name, metadata in parameterDefinitions.items():
            parameterPath = "{0}.parameters.{1}".format(path, name)
            parameterValue = parameters.get(name)
            expectedType = metadata["type"]
            if expectedType == "integer":
                validType = isinstance(parameterValue, int) and not isinstance(parameterValue, bool)
            elif expectedType == "boolean":
                validType = isinstance(parameterValue, bool)
            elif expectedType == "string":
                validType = isinstance(parameterValue, str)
            else:
                validType = isinstance(parameterValue, (int, float)) and not isinstance(parameterValue, bool)
            if not validType:
                report.addError("{0}: expected a {1}".format(parameterPath, expectedType))
                continue
            allowed = metadata.get("enum")
            if allowed is not None and parameterValue not in allowed:
                report.addError("{0}: expected one of {1}".format(parameterPath, ", ".join(allowed)))
                continue
            minimum = metadata.get("minimum")
            maximum = metadata.get("maximum")
            if (minimum is not None and parameterValue < minimum) or (maximum is not None and parameterValue > maximum):
                report.addError("{0}: expected {1} through {2}".format(parameterPath, minimum, maximum))

    # :: ARRAY<STRING, ANY>, ANY, ANY, STRING, validationReport -> NONE
    # Validates configurable palette or image backgrounds and bounded pulse behavior
    def _validateBackground(
        self,
        background: Dict[str, Any],
        core: Any,
        rendererPalette: Any,
        prefix: str,
        report: ValidationReport,
    ) -> None:
        backgroundPath = prefix + ".background"
        source = background.get("source")
        image = background.get("image")
        self._validateEnum(source, ["palette", "image"], backgroundPath + ".source", report)
        self._validateEnum(background.get("palette"), PALETTES, backgroundPath + ".palette", report)
        self._validateEnum(background.get("fit"), ["cover", "contain", "tile"], backgroundPath + ".fit", report)
        self._validateEnum(
            background.get("material"),
            ["flat", "matte", "metallic"],
            backgroundPath + ".material",
            report,
        )
        if image is not None and (not isinstance(image, str) or not image):
            report.addError("{0}.image: expected a non-empty path or null".format(backgroundPath))
        elif isinstance(image, str) and not Path(image).is_file():
            report.addError("{0}.image: file not found: {1}".format(backgroundPath, image))
        if source == "image" and not image:
            report.addError("{0}.image: image source requires a file".format(backgroundPath))
        if source == "image" and core != "3d":
            report.addError("{0}: image backgrounds require the 3d core".format(backgroundPath))
        if core != "3d" and background.get("palette") != rendererPalette:
            report.addError(
                "{0}.palette: independent background palettes require the 3d core".format(
                    backgroundPath
                )
            )
        ranges = {
            "intensity": (0.0, 4.0),
            "scale": (0.1, 10.0),
            "rotation_deg": (-3600.0, 3600.0),
            "opacity": (0.0, 1.0),
            "pulse_brightness": (0.0, 2.0),
            "pulse_scale": (0.0, 1.0),
        }
        for key, limits in ranges.items():
            value = background.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not limits[0] <= value <= limits[1]:
                report.addError("{0}.{1}: expected {2} through {3}".format(backgroundPath, key, limits[0], limits[1]))
        points = {
            "offset": (-2.0, 2.0),
            "pulse_center": (0.0, 1.0),
        }
        for key, limits in points.items():
            value = background.get(key)
            valid = isinstance(value, list) and len(value) == 2 and all(
                isinstance(item, (int, float))
                and not isinstance(item, bool)
                and limits[0] <= item <= limits[1]
                for item in value
            )
            if not valid:
                report.addError("{0}.{1}: expected two numbers from {2} through {3}".format(
                    backgroundPath, key, limits[0], limits[1]
                ))
        for key in ("dots", "ghosts", "shadow"):
            if not isinstance(background.get(key), bool):
                report.addError("{0}.{1}: expected a boolean".format(backgroundPath, key))
        self._validatePost(background.get("post"), backgroundPath + ".post", report)
        if core != "3d" and background.get("post"):
            report.addError("{0}.post: scoped effects require the 3d core".format(backgroundPath))
        ripple = background.get("ripple")
        if not isinstance(ripple, dict):
            report.addError("{0}.ripple: expected an object".format(backgroundPath))
            return
        if not isinstance(ripple.get("enabled"), bool):
            report.addError("{0}.ripple.enabled: expected a boolean".format(backgroundPath))
        rippleRanges = {
            "amount": (0.0, 0.5),
            "scale": (0.25, 24.0),
            "travel_speed": (0.0, 4.0),
            "warp": (0.0, 0.2),
            "specular": (0.0, 2.0),
            "roughness": (0.0, 1.0),
        }
        for key, limits in rippleRanges.items():
            value = ripple.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not limits[0] <= value <= limits[1]:
                report.addError(
                    "{0}.ripple.{1}: expected {2} through {3}".format(
                        backgroundPath,
                        key,
                        limits[0],
                        limits[1],
                    )
                )

    # :: ARRAY<STRING, ANY>, STRING, validationReport -> NONE
    # Validates renderer enums, booleans, and numeric controls
    def _validateRenderer(self, renderer: Dict[str, Any], prefix: str, report: ValidationReport) -> None:
        if renderer.get("id") != "metalheart":
            report.addError("{0}.renderer.id: expected 'metalheart'".format(prefix))
        self._validateEnum(renderer.get("palette"), PALETTES, "{0}.renderer.palette".format(prefix), report)
        self._validateEnum(renderer.get("core"), CORES, "{0}.renderer.core".format(prefix), report)
        self._validateEnumList(renderer.get("forms"), FORMS, "{0}.renderer.forms".format(prefix), report)
        self._validateEnumList(renderer.get("cameras"), CAMERAS, "{0}.renderer.cameras".format(prefix), report)
        ownedForms = {"resonance", "radial"}.intersection(renderer.get("forms", []))
        if renderer.get("core") != "3d" and ownedForms:
            report.addError("{0}.renderer.forms: {1} requires the 3d core".format(prefix, sorted(ownedForms)[0]))
        for key in ("anti_alias",):
            if not isinstance(renderer.get(key), bool):
                report.addError("{0}.renderer.{1}: expected a boolean".format(prefix, key))
        for key in ("form_len_sec", "camera_len_sec", "crossfade_sec", "core_scale"):
            value = renderer.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                report.addError("{0}.renderer.{1}: expected a positive number".format(prefix, key))
        cameraRanges = {
            "camera_speed": (0.0, 8.0),
            "camera_phase_sec": (0.0, 120.0),
            "camera_intensity": (0.0, 3.0),
        }
        for key, limits in cameraRanges.items():
            value = renderer.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not limits[0] <= value <= limits[1]:
                report.addError("{0}.renderer.{1}: expected {2} through {3}".format(prefix, key, limits[0], limits[1]))
        coreScale = renderer.get("core_scale")
        if isinstance(coreScale, (int, float)) and not 0.1 <= coreScale <= 1.0:
            report.addError("{0}.renderer.core_scale: expected 0.1 through 1.0".format(prefix))
        surface = renderer.get("surface")
        if not isinstance(surface, dict):
            report.addError("{0}.renderer.surface: expected an object".format(prefix))
        else:
            self._validateSurface(surface, renderer.get("core"), prefix, report)
        decor = renderer.get("decor")
        if not isinstance(decor, dict):
            report.addError("{0}.renderer.decor: expected an object".format(prefix))
        else:
            self._validateDecor(
                decor,
                renderer.get("core"),
                renderer.get("palette"),
                prefix,
                report,
            )
        formStyle = renderer.get("form_style")
        if not isinstance(formStyle, dict):
            report.addError("{0}.renderer.form_style: expected an object".format(prefix))
        else:
            self._validateFormStyle(formStyle, renderer, prefix, report)

    # :: ARRAY<STRING, ANY>, ARRAY<STRING, ANY>, STRING, validationReport -> NONE
    # Validates the first radial faceting, jaggedness, and geometry-step controls
    def _validateFormStyle(
        self,
        formStyle: Dict[str, Any],
        renderer: Dict[str, Any],
        prefix: str,
        report: ValidationReport,
    ) -> None:
        stylePath = prefix + ".renderer.form_style"
        ranges = {
            "faceting": (0.0, 1.0),
            "jaggedness": (0.0, 0.12),
            "jagged_scale": (1.0, 16.0),
        }
        for key, limits in ranges.items():
            value = formStyle.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not limits[0] <= value <= limits[1]:
                report.addError("{0}.{1}: expected {2} through {3}".format(stylePath, key, limits[0], limits[1]))
        geometrySteps = formStyle.get("geometry_steps")
        if isinstance(geometrySteps, bool) or not isinstance(geometrySteps, int) or (
            geometrySteps != 0 and not 2 <= geometrySteps <= 32
        ):
            report.addError("{0}.geometry_steps: expected 0 or an integer from 2 through 32".format(stylePath))
        enabled = bool(formStyle.get("faceting") or formStyle.get("jaggedness") or geometrySteps)
        if enabled and renderer.get("core") != "3d":
            report.addError("{0}: form styling requires the 3d core".format(stylePath))
        if enabled and "radial" not in renderer.get("forms", []):
            report.addError("{0}: form styling currently requires the radial form".format(stylePath))

    # :: ARRAY<STRING, ANY>, ANY, STRING, validationReport -> NONE
    # Validates optional object-space image skinning controls
    def _validateSurface(self, surface: Dict[str, Any], core: Any, prefix: str, report: ValidationReport) -> None:
        surfacePath = prefix + ".renderer.surface"
        image = surface.get("image")
        if image is not None and (not isinstance(image, str) or not image):
            report.addError("{0}.image: expected a non-empty path or null".format(surfacePath))
        elif isinstance(image, str) and not Path(image).is_file():
            report.addError("{0}.image: file not found: {1}".format(surfacePath, image))
        if image and core != "3d":
            report.addError("{0}.image: image skins require the 3d core".format(surfacePath))
        self._validateEnum(surface.get("mapping"), ["triplanar"], surfacePath + ".mapping", report)
        self._validateEnum(surface.get("material"), ["metallic", "matte"], surfacePath + ".material", report)
        self._validateEnum(surface.get("sampling"), ["bilinear", "nearest"], surfacePath + ".sampling", report)
        ranges = {
            "scale": (0.05, 100.0),
            "rotation_deg": (-3600.0, 3600.0),
        }
        for key, limits in ranges.items():
            value = surface.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not limits[0] <= value <= limits[1]:
                report.addError("{0}.{1}: expected {2} through {3}".format(surfacePath, key, limits[0], limits[1]))
        stepRanges = {"texel_steps": (2, 1024), "lighting_steps": (2, 64)}
        for key, limits in stepRanges.items():
            value = surface.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or (
                value != 0 and not limits[0] <= value <= limits[1]
            ):
                report.addError(
                    "{0}.{1}: expected 0 or an integer from {2} through {3}".format(
                        surfacePath, key, limits[0], limits[1]
                    )
                )
        self._validatePost(surface.get("post"), surfacePath + ".post", report)
        if core != "3d" and surface.get("post"):
            report.addError("{0}.post: scoped effects require the 3d core".format(surfacePath))

    # :: ARRAY<STRING, ANY>, ANY, ANY, STRING, validationReport -> NONE
    # Validates independently authored 3D ribbon and plate geometry and skins
    def _validateDecor(
        self,
        decor: Dict[str, Any],
        core: Any,
        rendererPalette: Any,
        prefix: str,
        report: ValidationReport,
    ) -> None:
        decorPath = prefix + ".renderer.decor"
        if not isinstance(decor.get("enabled"), bool):
            report.addError("{0}.enabled: expected a boolean".format(decorPath))
        seed = decor.get("seed")
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
            report.addError("{0}.seed: expected an integer or null".format(decorPath))
        for element, mapping in (("ribbons", "ribbon"), ("plates", "planar")):
            value = decor.get(element)
            elementPath = "{0}.{1}".format(decorPath, element)
            if not isinstance(value, dict):
                report.addError("{0}: expected an object".format(elementPath))
                continue
            if not isinstance(value.get("enabled"), bool):
                report.addError("{0}.enabled: expected a boolean".format(elementPath))
            count = value.get("count")
            if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 8:
                report.addError("{0}.count: expected an integer from 0 through 8".format(elementPath))
            self._validateEnum(
                value.get("material"),
                ["metallic", "matte"],
                elementPath + ".material",
                report,
            )
            if element == "ribbons":
                self._validateEnum(
                    value.get("palette"),
                    PALETTES,
                    elementPath + ".palette",
                    report,
                )
            surface = value.get("surface")
            if not isinstance(surface, dict):
                report.addError("{0}.surface: expected an object".format(elementPath))
            else:
                self._validateDecorSurface(surface, mapping, core, elementPath, report)
            if element == "ribbons":
                self._validatePost(value.get("post"), elementPath + ".post", report)
                if core != "3d" and value.get("post"):
                    report.addError("{0}.post: scoped effects require the 3d core".format(elementPath))
        if core != "3d" and self._hasAdvancedDecorControls(decor, rendererPalette):
            report.addError("{0}: first-class decor controls require the 3d core".format(decorPath))

    # :: ARRAY<STRING, ANY>, ANY -> BOOL
    # Distinguishes legacy all-on/all-off booleans from first-class decor authoring
    def _hasAdvancedDecorControls(
        self,
        decor: Dict[str, Any],
        rendererPalette: Any,
    ) -> bool:
        ribbons = decor.get("ribbons", {})
        plates = decor.get("plates", {})
        legacyEnabled = bool(decor.get("enabled"))
        if decor.get("seed") is not None:
            return True
        if ribbons.get("palette") != rendererPalette:
            return True
        if ribbons.get("enabled") != legacyEnabled or plates.get("enabled") != legacyEnabled:
            return True
        for value, default in (
            (ribbons, DEFAULT_DECOR["ribbons"]),
            (plates, DEFAULT_DECOR["plates"]),
        ):
            if value.get("count") != default["count"] or value.get("material") != "metallic":
                return True
            if value.get("post"):
                return True
            surface = value.get("surface", {})
            if surface != default["surface"]:
                return True
        return False

    # :: ARRAY<STRING, ANY>, STRING, ANY, STRING, validationReport -> NONE
    # Validates one ribbon-local or plate-planar image surface
    def _validateDecorSurface(
        self,
        surface: Dict[str, Any],
        mapping: str,
        core: Any,
        prefix: str,
        report: ValidationReport,
    ) -> None:
        surfacePath = prefix + ".surface"
        image = surface.get("image")
        if image is not None and (not isinstance(image, str) or not image):
            report.addError("{0}.image: expected a non-empty path or null".format(surfacePath))
        elif isinstance(image, str) and not Path(image).is_file():
            report.addError("{0}.image: file not found: {1}".format(surfacePath, image))
        if image and core != "3d":
            report.addError("{0}.image: decor image skins require the 3d core".format(surfacePath))
        self._validateEnum(surface.get("mapping"), [mapping], surfacePath + ".mapping", report)
        self._validateEnum(surface.get("sampling"), ["bilinear", "nearest"], surfacePath + ".sampling", report)
        for key, limits in {"scale": (0.05, 100.0), "rotation_deg": (-3600.0, 3600.0)}.items():
            value = surface.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not limits[0] <= value <= limits[1]:
                report.addError("{0}.{1}: expected {2} through {3}".format(surfacePath, key, limits[0], limits[1]))
        for key, limits in {"texel_steps": (2, 1024), "lighting_steps": (2, 64)}.items():
            value = surface.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or (
                value != 0 and not limits[0] <= value <= limits[1]
            ):
                report.addError(
                    "{0}.{1}: expected 0 or an integer from {2} through {3}".format(
                        surfacePath,
                        key,
                        limits[0],
                        limits[1],
                    )
                )

    # :: ARRAY<STRING, ANY>, STRING, validationReport -> NONE
    # Validates the owned finishing controls and their safe numeric ranges
    def _validateFinish(self, finish: Dict[str, Any], prefix: str, report: ValidationReport) -> None:
        finishPath = prefix + ".finish"
        for key in ("slice_glitch", "scanlines"):
            if not isinstance(finish.get(key), bool):
                report.addError("{0}.{1}: expected a boolean".format(finishPath, key))
        ranges = {
            "bloom": (0.0, 5.0),
            "wide_bloom": (0.0, 5.0),
            "streaks": (0.0, 5.0),
            "onset_streaks": (0.0, 10.0),
            "flash": (0.0, 1.0),
            "chroma": (0.0, 0.05),
            "chroma_onset": (0.0, 0.05),
            "slice_threshold": (0.0, 10.0),
            "vignette": (0.0, 1.0),
            "grain": (0.0, 0.2),
            "grain_high": (0.0, 0.2),
        }
        for key, limits in ranges.items():
            value = finish.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not limits[0] <= value <= limits[1]:
                report.addError("{0}.{1}: expected {2} through {3}".format(finishPath, key, limits[0], limits[1]))

    # :: ARRAY<STRING, ANY>, STRING, validationReport -> NONE
    # Validates a reactivity preset and its expanded binding map
    def _validateReactivity(self, reactivity: Dict[str, Any], prefix: str, report: ValidationReport) -> None:
        presetId = reactivity.get("preset")
        if presetId not in REACTIVITY_PRESETS:
            report.addError("{0}.reactivity.preset: unknown preset {1!r}".format(prefix, presetId))
        bindings = reactivity.get("bindings")
        if not isinstance(bindings, dict):
            report.addError("{0}.reactivity.bindings: expected an object".format(prefix))
        else:
            for destination, binding in bindings.items():
                bindingPath = "{0}.reactivity.bindings.{1}".format(prefix, destination)
                self._validateBinding(destination, binding, DESTINATIONS, bindingPath, report)
        modulators = reactivity.get("modulators")
        if not isinstance(modulators, dict):
            report.addError("{0}.reactivity.modulators: expected an object".format(prefix))
        else:
            for destination, binding in modulators.items():
                bindingPath = "{0}.reactivity.modulators.{1}".format(prefix, destination)
                self._validateBinding(destination, binding, MODULATORS, bindingPath, report)

    # :: STRING, ANY, [STRING], STRING, validationReport -> NONE
    # Validates one analyzed-signal mapping for a renderer or frame destination
    def _validateBinding(self, destination: str, binding: Any, destinations: List[str], bindingPath: str, report: ValidationReport) -> None:
        if destination not in destinations:
            report.addError("{0}: unknown destination".format(bindingPath))
            return
        if not isinstance(binding, dict):
            report.addError("{0}: expected an object".format(bindingPath))
            return
        self._validateEnum(binding.get("source"), SOURCES, bindingPath + ".source", report)
        self._validateEnum(binding.get("curve", "linear"), CURVES, bindingPath + ".curve", report)
        for key in ("amount", "bias"):
            value = binding.get(key, 0.0)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                report.addError("{0}.{1}: expected a number".format(bindingPath, key))
        threshold = binding.get("threshold", 0.0)
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0.0 <= threshold < 1.0:
            report.addError("{0}.threshold: expected a number from 0 up to but not including 1".format(bindingPath))
        clamp = binding.get("clamp", [0.0, 1.0])
        if not isinstance(clamp, list) or len(clamp) != 2 or not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in clamp):
            report.addError("{0}.clamp: expected [minimum, maximum]".format(bindingPath))
        elif clamp[1] < clamp[0]:
            report.addError("{0}.clamp: maximum must be at least minimum".format(bindingPath))

    # :: ARRAY<STRING, ANY>, STRING, validationReport -> NONE
    # Validates resolution-independent author text items
    def _validateOverlay(self, overlay: Dict[str, Any], prefix: str, report: ValidationReport) -> None:
        overlayPath = prefix + ".overlay"
        if not isinstance(overlay.get("enabled"), bool):
            report.addError("{0}.enabled: expected a boolean".format(overlayPath))
        if not isinstance(overlay.get("reference_hud"), bool):
            report.addError("{0}.reference_hud: expected a boolean".format(overlayPath))
        items = overlay.get("items")
        if not isinstance(items, list):
            report.addError("{0}.items: expected a list".format(overlayPath))
            return
        anchors = ["top_left", "top_center", "top_right", "center", "bottom_left", "bottom_center", "bottom_right"]
        for index, item in enumerate(items):
            itemPath = "{0}.items[{1}]".format(overlayPath, index)
            if not isinstance(item, dict):
                report.addError("{0}: expected an object".format(itemPath))
                continue
            if not isinstance(item.get("text"), str) or not item.get("text"):
                report.addError("{0}.text: expected a non-empty string".format(itemPath))
            position = item.get("position", [0.05, 0.05])
            if not isinstance(position, list) or len(position) != 2 or not all(isinstance(value, (int, float)) and not isinstance(value, bool) and 0.0 <= value <= 1.0 for value in position):
                report.addError("{0}.position: expected two normalized numbers".format(itemPath))
            size = item.get("size", 0.035)
            if isinstance(size, bool) or not isinstance(size, (int, float)) or not 0.005 <= size <= 0.25:
                report.addError("{0}.size: expected 0.005 through 0.25".format(itemPath))
            color = item.get("color", "#D8ECFF")
            if not isinstance(color, str) or len(color) != 7 or not color.startswith("#"):
                report.addError("{0}.color: expected #RRGGBB".format(itemPath))
            elif any(character not in "0123456789abcdefABCDEF" for character in color[1:]):
                report.addError("{0}.color: expected #RRGGBB".format(itemPath))
            opacity = item.get("opacity", 1.0)
            if isinstance(opacity, bool) or not isinstance(opacity, (int, float)) or not 0.0 <= opacity <= 1.0:
                report.addError("{0}.opacity: expected 0 through 1".format(itemPath))
            self._validateEnum(item.get("anchor", "top_left"), anchors, itemPath + ".anchor", report)

    # :: [ARRAY<STRING, ANY>], ARRAY<STRING, ANY>, validationReport -> NONE
    # Validates scene continuity after mapping boundaries to output frames
    def _validateSceneOrder(self, scenes: List[Any], settings: Dict[str, Any], report: ValidationReport) -> None:
        fps = settings.get("fps")
        if isinstance(fps, bool) or not isinstance(fps, int) or fps <= 0:
            return
        previousEnd: Optional[int] = None
        for index, scene in enumerate(scenes):
            if not isinstance(scene, dict):
                continue
            start = scene.get("start_sec")
            end = scene.get("end_sec")
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                continue
            startFrame = int(round(float(start) * fps))
            endFrame = int(round(float(end) * fps))
            if endFrame <= startFrame:
                report.addError("$.scenes[{0}]: scene is empty at {1} fps".format(index, fps))
            if previousEnd is not None and startFrame != previousEnd:
                report.addError("$.scenes[{0}].start_sec: scenes must be contiguous at output-frame precision".format(index))
            previousEnd = endFrame

    # :: ANY, [STRING], STRING, validationReport -> NONE
    # Validates one scalar enum value
    def _validateEnum(self, value: Any, values: List[str], path: str, report: ValidationReport) -> None:
        if value not in values:
            report.addError("{0}: expected one of {1}".format(path, ", ".join(values)))

    # :: ANY, [STRING], STRING, validationReport -> NONE
    # Validates a non-empty list of enum values
    def _validateEnumList(self, value: Any, values: List[str], path: str, report: ValidationReport) -> None:
        if not isinstance(value, list) or not value:
            report.addError("{0}: expected a non-empty list".format(path))
            return
        for index, item in enumerate(value):
            self._validateEnum(item, values, "{0}[{1}]".format(path, index), report)

    #
    # Class Methods
    #

    # Class Factory Method :: ARRAY<STRING, ANY>? -> configResolver
    # Creates a config resolver with optional templates
    @classmethod
    def init(cls, templates: Optional[Dict[str, Dict[str, Any]]] = None) -> ConfigResolver:
        return cls(templates)

    #
    # Static Methods
    #

    # :: VOID -> ARRAY<STRING, ANY>
    # Returns a copy of the public JSON Schema document
    @staticmethod
    def schema() -> Dict[str, Any]:
        return copy.deepcopy(CONFIG_SCHEMA)
