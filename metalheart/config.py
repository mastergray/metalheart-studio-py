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
        resolved["scenes"] = [self._resolveScene(scene, index, quality) for index, scene in enumerate(scenes)] if isinstance(scenes, list) else scenes
        resolved["post"] = copy.deepcopy(authored.get("post", []))
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
        if config.get("post"):
            report.addError("$.post: global post effects are not implemented in the first vertical slice")
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

    # :: ARRAY<STRING, ANY>, INT, STRING -> ARRAY<STRING, ANY>
    # Resolves one scene template, renderer defaults, and reactivity preset
    def _resolveScene(self, authored: Any, index: int, quality: str) -> Any:
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
        legacyFinish = self._deepMerge(templateFinish, authoredFinish)
        scene["finish"] = self._deepMerge(DEFAULT_FINISH, self._deepMerge(legacyFinish, scene.get("finish", {})))
        reactivity = copy.deepcopy(scene.get("reactivity", {}))
        presetId = reactivity.get("preset", "balanced")
        preset = REACTIVITY_PRESETS.get(presetId, {"bindings": {}})
        scene["reactivity"] = self._deepMerge(preset, reactivity)
        scene["reactivity"]["preset"] = presetId
        scene["overlay"] = self._deepMerge(DEFAULT_OVERLAY, scene.get("overlay", {}))
        scene["post"] = copy.deepcopy(scene.get("post", []))
        return scene

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
        if scene.get("post"):
            report.addError("{0}.post: scene post effects are not implemented in the first vertical slice".format(prefix))

    # :: ARRAY<STRING, ANY>, STRING, validationReport -> NONE
    # Validates renderer enums, booleans, and numeric controls
    def _validateRenderer(self, renderer: Dict[str, Any], prefix: str, report: ValidationReport) -> None:
        if renderer.get("id") != "metalheart":
            report.addError("{0}.renderer.id: expected 'metalheart'".format(prefix))
        self._validateEnum(renderer.get("palette"), PALETTES, "{0}.renderer.palette".format(prefix), report)
        self._validateEnum(renderer.get("core"), CORES, "{0}.renderer.core".format(prefix), report)
        self._validateEnumList(renderer.get("forms"), FORMS, "{0}.renderer.forms".format(prefix), report)
        self._validateEnumList(renderer.get("cameras"), CAMERAS, "{0}.renderer.cameras".format(prefix), report)
        for key in ("decor", "anti_alias"):
            if not isinstance(renderer.get(key), bool):
                report.addError("{0}.renderer.{1}: expected a boolean".format(prefix, key))
        for key in ("form_len_sec", "camera_len_sec", "crossfade_sec", "core_scale"):
            value = renderer.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                report.addError("{0}.renderer.{1}: expected a positive number".format(prefix, key))
        coreScale = renderer.get("core_scale")
        if isinstance(coreScale, (int, float)) and not 0.1 <= coreScale <= 1.0:
            report.addError("{0}.renderer.core_scale: expected 0.1 through 1.0".format(prefix))

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
