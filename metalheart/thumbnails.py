# Versioned offline option-thumbnail generation and manifest validation

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import copy  # Build isolated fixed-fixture scenes
import hashlib  # Fingerprint catalogs and generated thumbnail bytes
import json  # Read and write portable deterministic manifests
import math  # Sample camera spans and animated effect signals
from pathlib import Path  # Locate packaged assets and caller-selected outputs
from types import SimpleNamespace  # Build fixed renderer parameters without audio decoding
from typing import Any, Dict, List, Optional  # Python 3.8-compatible collection annotations

import cv2  # Encode generated BGR frames and draw asymmetric calibration marks
import numpy as np  # Build fixed spectrum signals and temporal effect inputs

from metalheart.catalog import CAMERAS  # Enumerate stable camera identifiers
from metalheart.catalog import DEFAULT_BACKGROUND  # Build fixed background settings
from metalheart.catalog import DEFAULT_FINISH  # Build fixed finishing settings
from metalheart.catalog import DEFAULT_RENDERER  # Build fixed renderer settings
from metalheart.catalog import FORMS  # Enumerate stable form identifiers
from metalheart.catalog import PALETTES  # Enumerate stable palette identifiers
from metalheart.catalog import REACTIVITY_PRESETS  # Supply the resolved fixture contract
from metalheart.effect_catalog import effectDefinition  # Fingerprint complete effect recipes
from metalheart.effect_catalog import effectIds  # Enumerate stable effect identifiers
from metalheart.effect_catalog import publicEffectCatalog  # Publish effect labels in the manifest
from metalheart.effects import EffectChain  # Render deterministic effect thumbnails
from metalheart.reference_backend import REFERENCE_VERSION  # Reject assets from stale renderers
from metalheart.reference_backend import ReferenceBackend  # Render fixed form, camera, and palette frames


THUMBNAIL_SCHEMA_VERSION = 2
THUMBNAIL_VERSION = "2026-10-01-v2"
THUMBNAIL_WIDTH = 128
THUMBNAIL_HEIGHT = 72
THUMBNAIL_FPS = 12
THUMBNAIL_SEED = 23
THUMBNAIL_TIME_SEC = 1.75
THUMBNAIL_EFFECT_FRAMES = 32
THUMBNAIL_ANIMATION_FPS = 8
THUMBNAIL_ANIMATION_FRAMES = 16
THUMBNAIL_ANIMATION_COLUMNS = 4
THUMBNAIL_CAMERA_SPAN_SEC = 10.0
THUMBNAIL_ROOT = (
    Path(__file__).resolve().parent / "assets" / "thumbnails" / "v2"
)
THUMBNAIL_CATALOGS: Dict[str, List[str]] = {
    "forms": list(FORMS),
    "cameras": list(CAMERAS),
    "palettes": list(PALETTES),
    "effects": effectIds(),
}
THUMBNAIL_ANIMATED_CATALOGS = ("cameras", "effects")


# :: VOID -> STRING
# Fingerprints every option that determines the packaged thumbnail inventory
def catalogFingerprint() -> str:
    payload = {
        "forms": list(FORMS),
        "cameras": list(CAMERAS),
        "palettes": list(PALETTES),
        "effects": [effectDefinition(effectId) for effectId in effectIds()],
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# Reads only packaged thumbnail metadata and paths; never invokes a renderer
class ThumbnailCatalog:

    # CONSTRUCTOR :: PATH? -> thumbnailCatalog
    # Loads a current manifest when complete packaged assets are available
    def __init__(self, root: Optional[Path] = None) -> None:
        self._root = (root or THUMBNAIL_ROOT).resolve()
        self._manifest: Optional[Dict[str, Any]] = None
        self._load()

    #
    # Properties
    #

    # PROPERTY :: VOID -> BOOL
    # Reports whether the complete manifest matches the current renderer and catalogs
    @property
    def available(self) -> bool:
        return self._manifest is not None

    # PROPERTY :: VOID -> ARRAY<STRING, ANY>?
    # Returns isolated manifest metadata for diagnostics and tests
    @property
    def manifest(self) -> Optional[Dict[str, Any]]:
        return copy.deepcopy(self._manifest)

    #
    # Instance Methods
    #

    # :: STRING, STRING -> PATH?
    # Returns one current thumbnail path without generating missing assets
    def path(self, catalog: str, optionId: str) -> Optional[Path]:
        if self._manifest is None:
            return None
        entry = self._manifest["catalogs"].get(catalog, {}).get(optionId)
        if not isinstance(entry, dict):
            return None
        return self._entryPath(entry, "file")

    # :: STRING, STRING -> ARRAY<STRING, ANY>?
    # Returns one spritesheet contract and path without decoding its frames
    def animation(self, catalog: str, optionId: str) -> Optional[Dict[str, Any]]:
        if self._manifest is None:
            return None
        entry = self._manifest["catalogs"].get(catalog, {}).get(optionId)
        if not isinstance(entry, dict):
            return None
        path = self._entryPath(entry, "animation_file")
        metadata = self._manifest.get("animation")
        if path is None or not isinstance(metadata, dict):
            return None
        result = copy.deepcopy(metadata)
        result["path"] = path
        return result

    # :: VOID -> [STRING]
    # Validates every declared still, spritesheet, and content hash
    def validate(self) -> List[str]:
        if self._manifest is None:
            return ["thumbnail manifest is missing or stale"]
        errors: List[str] = []
        for catalog, identifiers in THUMBNAIL_CATALOGS.items():
            for optionId in identifiers:
                entry = self._manifest["catalogs"][catalog][optionId]
                self._validateFile(
                    errors,
                    catalog,
                    optionId,
                    entry,
                    "file",
                    "sha256",
                    "thumbnail",
                )
                if catalog in THUMBNAIL_ANIMATED_CATALOGS:
                    self._validateFile(
                        errors,
                        catalog,
                        optionId,
                        entry,
                        "animation_file",
                        "animation_sha256",
                        "animation",
                    )
        return errors

    #
    # Protected Methods
    #

    # :: ARRAY<STRING, ANY>, STRING -> PATH?
    # Resolves one manifest path while rejecting traversal outside the asset root
    def _entryPath(self, entry: Dict[str, Any], key: str) -> Optional[Path]:
        value = entry.get(key)
        if not isinstance(value, str) or not value:
            return None
        path = (self._root / value).resolve()
        try:
            path.relative_to(self._root)
        except ValueError:
            return None
        return path if path.is_file() else None

    # :: [STRING], STRING, STRING, ARRAY<STRING, ANY>, STRING, STRING, STRING -> NONE
    # Validates one declared asset path and digest with a precise diagnostic
    def _validateFile(
        self,
        errors: List[str],
        catalog: str,
        optionId: str,
        entry: Dict[str, Any],
        fileKey: str,
        hashKey: str,
        assetType: str,
    ) -> None:
        path = self._entryPath(entry, fileKey)
        if path is None:
            errors.append("missing {0}: {1}/{2}".format(assetType, catalog, optionId))
            return
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry.get(hashKey):
            errors.append(
                "{0} hash mismatch: {1}/{2}".format(assetType, catalog, optionId)
            )

    # :: VOID -> NONE
    # Reads and accepts only a complete current manifest
    def _load(self) -> None:
        path = self._root / "manifest.json"
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(manifest, dict) or not self._isCurrent(manifest):
            return
        self._manifest = manifest

    # :: ARRAY<STRING, ANY> -> BOOL
    # Rejects stale or incomplete manifests before the native UI uses them
    def _isCurrent(self, manifest: Dict[str, Any]) -> bool:
        if manifest.get("schema_version") != THUMBNAIL_SCHEMA_VERSION:
            return False
        if manifest.get("thumbnail_version") != THUMBNAIL_VERSION:
            return False
        if manifest.get("renderer_version") != REFERENCE_VERSION:
            return False
        if manifest.get("catalog_fingerprint") != catalogFingerprint():
            return False
        if manifest.get("width") != THUMBNAIL_WIDTH:
            return False
        if manifest.get("height") != THUMBNAIL_HEIGHT:
            return False
        expectedAnimation = {
            "width": THUMBNAIL_WIDTH,
            "height": THUMBNAIL_HEIGHT,
            "fps": THUMBNAIL_ANIMATION_FPS,
            "frame_count": THUMBNAIL_ANIMATION_FRAMES,
            "columns": THUMBNAIL_ANIMATION_COLUMNS,
            "camera_span_sec": THUMBNAIL_CAMERA_SPAN_SEC,
            "effect_preroll_frames": THUMBNAIL_EFFECT_FRAMES,
        }
        if manifest.get("animation") != expectedAnimation:
            return False
        catalogs = manifest.get("catalogs")
        if not isinstance(catalogs, dict):
            return False
        for catalog, identifiers in THUMBNAIL_CATALOGS.items():
            entries = catalogs.get(catalog)
            if not isinstance(entries, dict) or list(entries) != identifiers:
                return False
            if catalog in THUMBNAIL_ANIMATED_CATALOGS:
                for entry in entries.values():
                    if not isinstance(entry, dict):
                        return False
                    if not entry.get("animation_file") or not entry.get("animation_sha256"):
                        return False
        return True

    #
    # Class Methods
    #

    # Class Factory Method :: PATH? -> thumbnailCatalog
    # Creates a read-only packaged thumbnail catalog
    @classmethod
    def init(cls, root: Optional[Path] = None) -> ThumbnailCatalog:
        return cls(root)


# Generates reviewed offline assets from one deterministic fixed fixture
class ThumbnailGenerator:

    # CONSTRUCTOR :: referenceBackend? -> thumbnailGenerator
    # Creates a generator with an injectable production renderer adapter
    def __init__(self, backend: Optional[ReferenceBackend] = None) -> None:
        self._backend = backend or ReferenceBackend.init()
        self._settings: Dict[str, Any] = {
            "width": THUMBNAIL_WIDTH,
            "height": THUMBNAIL_HEIGHT,
            "fps": THUMBNAIL_FPS,
            "seed": THUMBNAIL_SEED,
        }
        self._params = SimpleNamespace(
            bass=0.68,
            mid=0.52,
            high=0.61,
            onset=0.42,
            spectrum=np.asarray(
                [
                    0.82, 0.55, 0.74, 0.41, 0.68, 0.36,
                    0.62, 0.48, 0.78, 0.39, 0.71, 0.44,
                    0.58, 0.66, 0.35, 0.73, 0.46, 0.64,
                    0.38, 0.69, 0.51, 0.76, 0.43, 0.60,
                ],
                np.float32,
            ),
        )
        self._modulators: Dict[str, float] = {
            "form_scale": 0.18,
            "form_deformation": 0.58,
            "form_ripple": 0.11,
            "form_extent": 0.72,
            "form_rotation": 1.35,
            "form_jaggedness": 0.16,
            "form_jagged_scale": 0.52,
            "camera_distance": 0.0,
            "camera_elevation": 0.0,
            "camera_roll": 0.0,
            "camera_kick": 0.0,
        }

    #
    # Instance Methods
    #

    # :: PATH -> ARRAY<STRING, ANY>
    # Regenerates every versioned thumbnail and writes its complete manifest
    def generate(self, root: Path) -> Dict[str, Any]:
        outputRoot = root.resolve()
        outputRoot.mkdir(parents=True, exist_ok=True)
        labels = {
            str(entry["id"]): str(entry["label"])
            for entry in publicEffectCatalog()
        }
        catalogs: Dict[str, Dict[str, Dict[str, Any]]] = {
            catalog: {} for catalog in THUMBNAIL_CATALOGS
        }
        for formId in FORMS:
            frame = self._renderScene(formId, "dutch", "steel")
            catalogs["forms"][formId] = self._write(
                outputRoot,
                "forms",
                formId,
                formId.replace("_", " ").title(),
                frame,
            )
        for cameraId in CAMERAS:
            frames = self._cameraFrames(cameraId)
            entry = self._write(
                outputRoot,
                "cameras",
                cameraId,
                cameraId.replace("_", " ").title(),
                frames[len(frames) // 2],
            )
            entry.update(self._writeAnimation(outputRoot, "cameras", cameraId, frames))
            catalogs["cameras"][cameraId] = entry
        for paletteId in PALETTES:
            frame = self._renderScene("mercury", "orbit", paletteId)
            catalogs["palettes"][paletteId] = self._write(
                outputRoot,
                "palettes",
                paletteId,
                paletteId.replace("_", " ").title(),
                frame,
            )
        effectBase = self._effectBase()
        for effectId in effectIds():
            frames = self._effectFrames(effectBase, effectId)
            entry = self._write(
                outputRoot,
                "effects",
                effectId,
                labels[effectId],
                frames[len(frames) // 2],
            )
            entry.update(self._writeAnimation(outputRoot, "effects", effectId, frames))
            catalogs["effects"][effectId] = entry
        manifest: Dict[str, Any] = {
            "schema_version": THUMBNAIL_SCHEMA_VERSION,
            "thumbnail_version": THUMBNAIL_VERSION,
            "renderer_version": REFERENCE_VERSION,
            "catalog_fingerprint": catalogFingerprint(),
            "width": THUMBNAIL_WIDTH,
            "height": THUMBNAIL_HEIGHT,
            "animation": {
                "width": THUMBNAIL_WIDTH,
                "height": THUMBNAIL_HEIGHT,
                "fps": THUMBNAIL_ANIMATION_FPS,
                "frame_count": THUMBNAIL_ANIMATION_FRAMES,
                "columns": THUMBNAIL_ANIMATION_COLUMNS,
                "camera_span_sec": THUMBNAIL_CAMERA_SPAN_SEC,
                "effect_preroll_frames": THUMBNAIL_EFFECT_FRAMES,
            },
            "fixture": {
                "fps": THUMBNAIL_FPS,
                "seed": THUMBNAIL_SEED,
                "time_sec": THUMBNAIL_TIME_SEC,
                "effect_frames": THUMBNAIL_EFFECT_FRAMES,
            },
            "catalogs": catalogs,
        }
        manifestPath = outputRoot / "manifest.json"
        manifestPath.write_text(
            json.dumps(manifest, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        return manifest

    #
    # Protected Methods
    #

    # :: STRING, STRING, STRING -> ANY
    # Renders one fixed low-cost production scene for an option thumbnail
    def _renderScene(self, formId: str, cameraId: str, paletteId: str) -> np.ndarray:
        scene = self._scene(formId, cameraId, paletteId)
        session = self._backend.createRenderer(self._settings, scene)
        return session.render(
            THUMBNAIL_TIME_SEC,
            self._params,
            self._modulators,
            int(round(THUMBNAIL_TIME_SEC * THUMBNAIL_FPS)),
            int(round(THUMBNAIL_TIME_SEC * THUMBNAIL_FPS)),
            self._effectSignals(),
        )

    # :: STRING -> [ANY]
    # Samples a broad camera path and compresses it into a concise looping study
    def _cameraFrames(self, cameraId: str) -> List[np.ndarray]:
        scene = self._scene("fold", cameraId, "jungle")
        scene["renderer"]["camera_speed"] = 1.0
        session = self._backend.createRenderer(self._settings, scene)
        frames: List[np.ndarray] = []
        for frameIndex in range(THUMBNAIL_ANIMATION_FRAMES):
            progress = frameIndex / float(THUMBNAIL_ANIMATION_FRAMES - 1)
            timeSec = 0.4 + progress * THUMBNAIL_CAMERA_SPAN_SEC
            frames.append(
                session.render(
                    timeSec,
                    self._params,
                    self._modulators,
                    frameIndex,
                    frameIndex,
                    self._effectSignals(frameIndex),
                )
            )
        return frames

    # :: STRING, STRING, STRING -> ARRAY<STRING, ANY>
    # Builds the complete fixed scene contract without audio or project I/O
    def _scene(self, formId: str, cameraId: str, paletteId: str) -> Dict[str, Any]:
        renderer = copy.deepcopy(DEFAULT_RENDERER)
        renderer.update(
            {
                "core": "3d",
                "forms": [formId],
                "cameras": [cameraId],
                "palette": paletteId,
                "camera_speed": 0.0,
                "camera_phase_sec": 0.0,
                "decor": False,
                "anti_alias": False,
                "core_scale": 0.24,
            }
        )
        background = copy.deepcopy(DEFAULT_BACKGROUND)
        background.update(
            {
                "palette": paletteId,
                "intensity": 1.25,
                "ghosts": False,
                "shadow": False,
            }
        )
        finish = copy.deepcopy(DEFAULT_FINISH)
        finish.update(
            {
                "grain": 0.0,
                "grain_high": 0.0,
                "chroma": 0.0,
                "chroma_onset": 0.0,
                "slice_glitch": False,
            }
        )
        return {
            "id": "thumbnail",
            "seed": THUMBNAIL_SEED,
            "renderer": renderer,
            "background": background,
            "reactivity": copy.deepcopy(REACTIVITY_PRESETS["balanced"]),
            "overlay": {"enabled": False, "reference_hud": False, "items": []},
            "finish": finish,
            "post": [],
        }

    # :: VOID -> ANY
    # Adds stable asymmetric marks to a real frame so spatial effects read clearly
    def _effectBase(self) -> np.ndarray:
        frame = self._renderScene("wring", "dutch", "rainbow")
        output = frame.copy()
        cv2.rectangle(output, (4, 5), (31, 19), (20, 220, 255), -1)
        cv2.circle(output, (108, 56), 10, (255, 190, 20), -1)
        cv2.line(output, (8, 64), (116, 8), (245, 245, 245), 2)
        cv2.putText(
            output,
            "MH",
            (47, 66),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        return output

    # :: ANY, STRING -> [ANY]
    # Applies one catalog effect through preroll and a changing audio/source loop
    def _effectFrames(self, base: np.ndarray, effectId: str) -> List[np.ndarray]:
        chain = EffectChain.init(
            [{"id": effectId}],
            THUMBNAIL_WIDTH,
            THUMBNAIL_HEIGHT,
            THUMBNAIL_FPS,
            THUMBNAIL_SEED,
        )
        frames: List[np.ndarray] = []
        totalFrames = THUMBNAIL_EFFECT_FRAMES + THUMBNAIL_ANIMATION_FRAMES
        for frameIndex in range(totalFrames):
            phase = frameIndex * math.tau / float(THUMBNAIL_ANIMATION_FRAMES)
            horizontal = int(round(math.sin(phase) * 11.0))
            vertical = int(round(math.cos(phase * 0.5) * 3.0))
            source = np.roll(base, (vertical, horizontal), axis=(0, 1))
            output = chain.apply(
                source,
                frameIndex / float(THUMBNAIL_FPS),
                frameIndex,
                self._effectSignals(frameIndex),
            )
            if frameIndex >= THUMBNAIL_EFFECT_FRAMES:
                frames.append(output)
        return frames

    # :: INT -> ARRAY<STRING, FLOAT>
    # Supplies changing high-information audio values to audio-aware effects
    def _effectSignals(self, frameIndex: int = 0) -> Dict[str, float]:
        phase = frameIndex * math.tau / float(THUMBNAIL_ANIMATION_FRAMES)
        pulse = 0.95 if frameIndex % 8 in (0, 1) else 0.18
        return {
            "bass": 0.58 + 0.30 * math.sin(phase),
            "mid": 0.52 + 0.24 * math.sin(phase * 1.5 + 0.8),
            "high": 0.55 + 0.32 * math.cos(phase * 2.0 + 0.4),
            "treble": 0.55 + 0.32 * math.cos(phase * 2.0 + 0.4),
            "rms": 0.60 + 0.22 * math.sin(phase + 1.2),
            "onset": pulse,
            "transient": 1.0 if frameIndex % 8 == 0 else 0.0,
            "chromatic_phase": phase,
            "chromatic_sign": -1.0 if frameIndex % 2 else 1.0,
        }

    # :: PATH, STRING, STRING, STRING, ANY -> ARRAY<STRING, STRING>
    # Encodes one PNG and returns portable manifest metadata
    def _write(
        self,
        root: Path,
        catalog: str,
        optionId: str,
        label: str,
        frame: np.ndarray,
    ) -> Dict[str, str]:
        directory = root / catalog
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "{0}.png".format(optionId)
        if not cv2.imwrite(str(path), frame):
            raise RuntimeError("unable to write thumbnail: {0}".format(path))
        relative = path.relative_to(root).as_posix()
        return {
            "label": label,
            "file": relative,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    # :: PATH, STRING, STRING, [ANY] -> ARRAY<STRING, STRING>
    # Packs one dependency-free animation into a deterministic PNG spritesheet
    def _writeAnimation(
        self,
        root: Path,
        catalog: str,
        optionId: str,
        frames: List[np.ndarray],
    ) -> Dict[str, str]:
        rows = int(math.ceil(len(frames) / float(THUMBNAIL_ANIMATION_COLUMNS)))
        sheet = np.zeros(
            (
                rows * THUMBNAIL_HEIGHT,
                THUMBNAIL_ANIMATION_COLUMNS * THUMBNAIL_WIDTH,
                3,
            ),
            dtype=np.uint8,
        )
        for frameIndex, frame in enumerate(frames):
            row = frameIndex // THUMBNAIL_ANIMATION_COLUMNS
            column = frameIndex % THUMBNAIL_ANIMATION_COLUMNS
            top = row * THUMBNAIL_HEIGHT
            left = column * THUMBNAIL_WIDTH
            sheet[
                top:top + THUMBNAIL_HEIGHT,
                left:left + THUMBNAIL_WIDTH,
            ] = frame
        directory = root / "previews" / catalog
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "{0}.png".format(optionId)
        if not cv2.imwrite(str(path), sheet):
            raise RuntimeError("unable to write thumbnail animation: {0}".format(path))
        return {
            "animation_file": path.relative_to(root).as_posix(),
            "animation_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    #
    # Class Methods
    #

    # Class Factory Method :: referenceBackend? -> thumbnailGenerator
    # Creates a deterministic offline thumbnail generator
    @classmethod
    def init(cls, backend: Optional[ReferenceBackend] = None) -> ThumbnailGenerator:
        return cls(backend)
