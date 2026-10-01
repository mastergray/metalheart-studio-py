# Command-line interface for JSON validation, resolution, catalogs, and rendering

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import argparse  # Define the headless command-line interface
import json  # Emit machine-readable command output
import subprocess  # Classify child-process failures for concise CLI errors
import sys  # Return command status and write errors
from pathlib import Path  # Derive default resolved-config paths
from typing import Any, Dict, List, Optional, Tuple  # Python 3.8-compatible type annotations

from metalheart.analysis import AudioAnalysisCache  # Cache full-track analysis used for scene planning
from metalheart.catalog import CAMERAS  # List supported cameras
from metalheart.catalog import FORMS  # List supported forms
from metalheart.catalog import PALETTES  # List supported palettes
from metalheart.catalog import QUALITY_PROFILES  # Resolve CLI quality defaults
from metalheart.catalog import REACTIVITY_PRESETS  # List supported reactivity presets
from metalheart.catalog import TEMPLATES  # List built-in scene templates
from metalheart.config import ConfigError  # Report authored config failures
from metalheart.config import ConfigResolver  # Load, resolve, validate, and write configs
from metalheart.effect_catalog import effectIds  # List stable owned effect identifiers
from metalheart.effect_catalog import publicEffectCatalog  # Expose typed effect metadata for the desktop UI
from metalheart.planner import ScenePlanner  # Convert audio analysis into scene-based configs
from metalheart.reference_backend import ReferenceBackend  # Analyze audio through the pinned backend
from metalheart.render import RenderPipeline  # Execute resolved render configs


# :: configResolver, STRING -> ARRAY<STRING, ANY>
# Loads and resolves one authored config path
def _loadResolved(resolver: ConfigResolver, path: str) -> Dict[str, Any]:
    return resolver.resolve(resolver.load(path), path)


# :: validationReport, BOOL -> NONE
# Prints validation results as JSON or readable text
def _printReport(report: Any, asJson: bool) -> None:
    if asJson:
        print(json.dumps(report.toDict(), indent=2, sort_keys=True))
        return
    for warning in report.warnings:
        print("warning: {0}".format(warning), file=sys.stderr)
    if report.isValid:
        print("valid")
    else:
        print("invalid", file=sys.stderr)
        for error in report.errors:
            print("- {0}".format(error), file=sys.stderr)


# :: argumentParser -> NONE
# Adds a consistent machine-readable output switch
def _addJsonFlag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


# :: STRING -> (INT, INT)
# Parses an even WIDTHxHEIGHT command-line value
def _parseSize(value: str) -> Tuple[int, int]:
    try:
        widthText, heightText = value.lower().split("x", 1)
        width, height = int(widthText), int(heightText)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("size must use WIDTHxHEIGHT")
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise argparse.ArgumentTypeError("size dimensions must be positive even integers")
    return width, height


# :: STRING -> ANY
# Parses an automatic or positive integer worker count
def _parseWorkers(value: str) -> Any:
    if value == "auto":
        return value
    try:
        workers = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("workers must be 'auto' or a positive integer")
    if workers <= 0:
        raise argparse.ArgumentTypeError("workers must be 'auto' or a positive integer")
    return workers


# :: VOID -> argumentParser
# Builds the complete CLI parser
def buildParser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="studio.py", description="Native and headless JSON-driven Metalheart renderer")
    commands = parser.add_subparsers(dest="command", required=True)

    analyzeParser = commands.add_parser("analyze", help="analyze audio and write a scene-based JSON config")
    analyzeParser.add_argument("audio")
    analyzeParser.add_argument("-o", "--output", required=True)
    analyzeParser.add_argument("--quality", choices=sorted(QUALITY_PROFILES), default="preview")
    analyzeParser.add_argument("--size", type=_parseSize)
    analyzeParser.add_argument("--fps", type=int)
    analyzeParser.add_argument("--crf", type=int)
    analyzeParser.add_argument("--seed", type=int, default=3)
    analyzeParser.add_argument("--bpm", type=float)
    analyzeParser.add_argument("--bars-per-scene", type=int, default=8)
    analyzeParser.add_argument("--max-scene-sec", type=float)
    analyzeParser.add_argument("--template", choices=sorted(TEMPLATES), default="builtins/mercury-intro", help="explicit default for every generated scene skeleton")
    _addJsonFlag(analyzeParser)

    validateParser = commands.add_parser("validate", help="resolve and validate a JSON config")
    validateParser.add_argument("config")
    _addJsonFlag(validateParser)

    resolveParser = commands.add_parser("resolve", help="write a fully expanded JSON config")
    resolveParser.add_argument("config")
    resolveParser.add_argument("-o", "--output")

    renderParser = commands.add_parser("render", help="render a JSON config to video")
    renderParser.add_argument("config")
    renderOutput = renderParser.add_mutually_exclusive_group(required=True)
    renderOutput.add_argument("-o", "--output", help="write one assembled timeline video")
    renderOutput.add_argument("--scene-clips", metavar="DIRECTORY", help="write each scene as an independent clip")
    renderParser.add_argument("--ffmpeg", default="ffmpeg")
    renderParser.add_argument("--ffprobe", default="ffprobe")
    renderParser.add_argument("--workers", type=_parseWorkers)
    renderParser.add_argument("--chunk-sec", type=float)
    renderParser.add_argument("--no-resume", action="store_true")
    _addJsonFlag(renderParser)

    listParser = commands.add_parser("list", help="list stable catalog identifiers")
    listParser.add_argument("catalog", choices=["templates", "forms", "looks", "cameras", "palettes", "effects", "reactivity"])
    _addJsonFlag(listParser)

    schemaParser = commands.add_parser("schema", help="emit the config JSON Schema")
    schemaParser.add_argument("-o", "--output")

    uiParser = commands.add_parser("ui", help="open the native PySide6 authoring interface")
    uiParser.add_argument("config", nargs="?", help="optional JSON project to open")
    return parser


# :: argumentNamespace, configResolver -> INT
# Executes the validate command
def _validateCommand(args: argparse.Namespace, resolver: ConfigResolver) -> int:
    resolved = _loadResolved(resolver, args.config)
    report = resolver.validate(resolved)
    _printReport(report, args.json)
    return 0 if report.isValid else 2


# :: argumentNamespace, configResolver -> INT
# Analyzes a complete audio source and writes a renderable multi-scene config
def _analyzeCommand(args: argparse.Namespace, resolver: ConfigResolver) -> int:
    audioPath = Path(args.audio).resolve()
    if not audioPath.is_file():
        raise ConfigError("audio file not found: {0}".format(audioPath))
    qualityProfile = QUALITY_PROFILES[args.quality]
    fps = args.fps if args.fps is not None else qualityProfile["fps"]
    crf = args.crf if args.crf is not None else qualityProfile["crf"]
    width, height = args.size if args.size is not None else (qualityProfile["width"], qualityProfile["height"])
    if fps <= 0 or args.bars_per_scene <= 0:
        raise ConfigError("fps and bars-per-scene must be positive")
    outputPath = Path(args.output).resolve()
    outputPath.parent.mkdir(parents=True, exist_ok=True)
    backend = ReferenceBackend.init()
    cache = AudioAnalysisCache.init(backend, outputPath.parent / ".metalheart-cache")
    print("[analyze] decoding and analyzing {0}".format(audioPath), file=sys.stderr, flush=True)
    analysisResult = cache.get(str(audioPath), float(fps), 0.0, None, args.bpm)
    planner = ScenePlanner.init(
        width=width,
        height=height,
        fps=fps,
        crf=crf,
        seed=args.seed,
        quality=args.quality,
        template=args.template,
        maxSceneSec=args.max_scene_sec,
    )
    authored = planner.plan(analysisResult.analysis, str(audioPath), str(outputPath), args.bars_per_scene, analysisResult.cachePath)
    resolved = resolver.resolve(authored, str(outputPath))
    report = resolver.validate(resolved)
    if not report.isValid:
        raise ConfigError("generated config is invalid:\n- " + "\n- ".join(report.errors))
    resolver.write(authored, str(outputPath))
    summary = {
        "output": str(outputPath),
        "audio": str(audioPath),
        "duration_sec": float(analysisResult.analysis.duration),
        "render_duration_sec": authored["scenes"][-1]["end_sec"],
        "bpm": float(analysisResult.analysis.bpm),
        "scenes": len(authored["scenes"]),
        "analysis_cache": analysisResult.cachePath,
        "analysis_cache_hit": analysisResult.cacheHit,
    }
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print("wrote {0}: {1} scenes, {2:.2f} BPM, {3:.2f}s".format(outputPath, summary["scenes"], summary["bpm"], summary["render_duration_sec"]))
    return 0


# :: argumentNamespace, configResolver -> INT
# Executes the resolve command after validation
def _resolveCommand(args: argparse.Namespace, resolver: ConfigResolver) -> int:
    resolved = _loadResolved(resolver, args.config)
    report = resolver.validate(resolved)
    if not report.isValid:
        _printReport(report, False)
        return 2
    output = args.output or str(Path(args.config).with_suffix(".resolved.json"))
    resolver.write(resolved, output)
    print(str(Path(output).resolve()))
    return 0


# :: argumentNamespace, configResolver -> INT
# Executes a complete config-to-video render
def _renderCommand(args: argparse.Namespace, resolver: ConfigResolver) -> int:
    resolved = _loadResolved(resolver, args.config)
    if args.workers is not None:
        resolved["settings"]["workers"] = args.workers
    if args.chunk_sec is not None:
        resolved["settings"]["chunk_sec"] = args.chunk_sec
    if args.no_resume:
        resolved["settings"]["resume"] = False
    report = resolver.validate(resolved)
    if not report.isValid:
        _printReport(report, args.json)
        return 2
    pipeline = RenderPipeline.init(args.ffmpeg, args.ffprobe)
    if args.scene_clips:
        results = pipeline.renderScenes(resolved, args.scene_clips)
        clips = []
        for scene, result in zip(resolved["scenes"], results):
            clip = result.toDict()
            clip["scene_id"] = scene["id"]
            clips.append(clip)
        summary = {
            "output_directory": str(Path(args.scene_clips).resolve()),
            "clips": clips,
        }
        if args.json:
            print(json.dumps(summary, indent=2, sort_keys=True))
        else:
            for clip in clips:
                print("wrote {0}: {1} frames ({2})".format(clip["output"], clip["frames"], clip["scene_id"]))
        return 0
    result = pipeline.render(resolved, args.output)
    if args.json:
        print(json.dumps(result.toDict(), indent=2, sort_keys=True))
    else:
        print("wrote {0}: {1} frames in {2:.2f}s".format(result.outputPath, result.frameCount, result.elapsedSec))
        print("profile: {0}".format(result.profilePath))
        print("manifest: {0}".format(result.manifestPath))
    return 0


# :: argumentNamespace -> INT
# Lists identifiers from one built-in catalog
def _listCommand(args: argparse.Namespace) -> int:
    catalogs: Dict[str, List[str]] = {
        "templates": sorted(TEMPLATES),
        "forms": list(FORMS),
        "looks": list(FORMS),
        "cameras": list(CAMERAS),
        "palettes": list(PALETTES),
        "effects": effectIds(),
        "reactivity": sorted(REACTIVITY_PRESETS),
    }
    values = catalogs[args.catalog]
    if args.json:
        payload: Dict[str, Any] = {"catalog": args.catalog, "values": values}
        if args.catalog == "effects":
            payload["entries"] = publicEffectCatalog()
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for value in values:
            print(value)
    return 0


# :: argumentNamespace, configResolver -> INT
# Writes the public JSON Schema to stdout or a file
def _schemaCommand(args: argparse.Namespace, resolver: ConfigResolver) -> int:
    value = json.dumps(resolver.schema(), indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(value, encoding="utf-8")
    else:
        print(value, end="")
    return 0


# :: argumentNamespace -> INT
# Starts the optional native desktop authoring interface
def _uiCommand(args: argparse.Namespace) -> int:
    try:
        from metalheart.ui.application import runGui  # Load Qt only for the explicit UI command
    except ModuleNotFoundError as error:
        if error.name == "PySide6":
            raise ConfigError(
                "PySide6 is not installed; install the 'ui' optional dependency before running the native editor"
            )
        raise
    return runGui(args.config)


# :: [STRING]? -> INT
# Runs one CLI command and converts expected failures to concise messages
def main(arguments: Optional[List[str]] = None) -> int:
    parser = buildParser()
    args = parser.parse_args(arguments)
    resolver = ConfigResolver.init()
    try:
        if args.command == "validate":
            return _validateCommand(args, resolver)
        if args.command == "analyze":
            return _analyzeCommand(args, resolver)
        if args.command == "resolve":
            return _resolveCommand(args, resolver)
        if args.command == "render":
            return _renderCommand(args, resolver)
        if args.command == "list":
            return _listCommand(args)
        if args.command == "schema":
            return _schemaCommand(args, resolver)
        if args.command == "ui":
            return _uiCommand(args)
    except (ConfigError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        print("error: {0}".format(error), file=sys.stderr)
        return 2
    parser.error("unknown command")
    return 2
