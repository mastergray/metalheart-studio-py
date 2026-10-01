# Versioned offline option-thumbnail generation and manifest validation

from __future__ import annotations  # Preserve forward-compatible annotations on Python 3.8

import copy  # Build isolated fixed-fixture scenes
import hashlib  # Fingerprint catalogs and generated thumbnail bytes
import json  # Read and write portable deterministic manifests
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


THUMBNAIL_SCHEMA_VERSION = 1
THUMBNAIL_VERSION = "2026-10-01-v1"
THUMBNAIL_WIDTH = 128
THUMBNAIL_HEIGHT = 72
THUMBNAIL_FPS = 12
THUMBNAIL_SEED = 23
THUMBNAIL_TIME_SEC = 1.75
THUMBNAIL_EFFECT_FRAMES = 32
THUMBNAIL_ROOT = (
    Path(__file__).resolve().parent / "assets" / "thumbnails" / "v1"
)
THUMBNAIL_CATALOGS: Dict[str, List[str]] = {
    "forms": list(FORMS),
    "cameras": list(CAMERAS),
    "palettes": list(PALETTES),
    "effects": effectIds(),
}


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
        path = (self._root / str(entry.get("file", ""))).resolve()
        try:
            path.relative_to(self._root)
        except ValueError:
            return None
        return path if path.is_file() else None

    # :: VOID -> [STRING]
    # Validates every declared file and content hash without changing assets
    def validate(self) -> List[str]:
        if self._manifest is None:
            return ["thumbnail manifest is missing or stale"]
        errors: List[str] = []
        for catalog, identifiers in THUMBNAIL_CATALOGS.items():
            for optionId in identifiers:
                entry = self._manifest["catalogs"][catalog][optionId]
                path = self.path(catalog, optionId)
                if path is None:
                    errors.append("missing thumbnail: {0}/{1}".format(catalog, optionId))
                    continue
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest != entry.get("sha256"):
                    errors.append("thumbnail hash mismatch: {0}/{1}".format(catalog, optionId))
        return errors

    #
    # Protected Methods
    #

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
        catalogs = manifest.get("catalogs")
        if not isinstance(catalogs, dict):
            return False
        for catalog, identifiers in THUMBNAIL_CATALOGS.items():
            entries = catalogs.get(catalog)
            if not isinstance(entries, dict) or list(entries) != identifiers:
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
        catalogs: Dict[str, Dict[str, Dict[str, str]]] = {
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
            frame = self._renderScene("radial", cameraId, "jungle")
            catalogs["cameras"][cameraId] = self._write(
                outputRoot,
                "cameras",
                cameraId,
                cameraId.replace("_", " ").title(),
                frame,
            )
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
            frame = self._effectThumbnail(effectBase, effectId)
            catalogs["effects"][effectId] = self._write(
                outputRoot,
                "effects",
                effectId,
                labels[effectId],
                frame,
            )
        manifest: Dict[str, Any] = {
            "schema_version": THUMBNAIL_SCHEMA_VERSION,
            "thumbnail_version": THUMBNAIL_VERSION,
            "renderer_version": REFERENCE_VERSION,
            "catalog_fingerprint": catalogFingerprint(),
            "width": THUMBNAIL_WIDTH,
            "height": THUMBNAIL_HEIGHT,
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

    # :: ANY, STRING -> ANY
    # Applies one catalog effect after deterministic temporal preroll
    def _effectThumbnail(self, base: np.ndarray, effectId: str) -> np.ndarray:
        chain = EffectChain.init(
            [{"id": effectId}],
            THUMBNAIL_WIDTH,
            THUMBNAIL_HEIGHT,
            THUMBNAIL_FPS,
            THUMBNAIL_SEED,
        )
        output = base
        signals = self._effectSignals()
        for frameIndex in range(THUMBNAIL_EFFECT_FRAMES):
            source = np.roll(base, frameIndex - THUMBNAIL_EFFECT_FRAMES + 1, axis=1)
            output = chain.apply(
                source,
                frameIndex / float(THUMBNAIL_FPS),
                frameIndex,
                signals,
            )
        return output

    # :: VOID -> ARRAY<STRING, FLOAT>
    # Supplies fixed high-information audio values to audio-aware effects
    def _effectSignals(self) -> Dict[str, float]:
        return {
            "bass": 0.68,
            "mid": 0.52,
            "high": 0.61,
            "treble": 0.61,
            "rms": 0.62,
            "onset": 0.42,
            "transient": 1.0,
            "chromatic_phase": 0.67,
            "chromatic_sign": 1.0,
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

    #
    # Class Methods
    #

    # Class Factory Method :: referenceBackend? -> thumbnailGenerator
    # Creates a deterministic offline thumbnail generator
    @classmethod
    def init(cls, backend: Optional[ReferenceBackend] = None) -> ThumbnailGenerator:
        return cls(backend)
