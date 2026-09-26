# Metalheart Studio

Metalheart Studio is a planned headless, JSON-driven pipeline for rendering audio-reactive video with the Metalheart/Depthcore renderer.

The first implementation slice provides JSON resolution and validation, cached audio analysis, and direct rendering through the immutable audio-reactive reference backend.

## Quick start

```bash
python3 studio.py analyze /path/to/song.wav -o song.metalheart.json --quality preview
python3 studio.py validate examples/minimal.json
python3 studio.py resolve examples/minimal.json
python3 studio.py render examples/minimal.json -o renders/minimal.mp4 --workers auto
```

`analyze` detects tempo, downbeats, and energy, divides the track into contiguous phrase-aligned scenes, and writes a neutral config skeleton that can be edited or rendered directly. It does not infer sentiment or select aesthetics from audio. Use `--bars-per-scene` and `--max-scene-sec` to tune boundaries, and `--template` to choose the explicit default assigned to every generated scene.

Quality profiles now have concrete defaults: `preview` is 320×180 at 12 fps, `draft` matches the reference fixtures at 960×540 and 24 fps, and `final` is 1920×1080 at 30 fps. Explicit size, FPS, and CRF values override the selected profile.

Each scene may define resolution-independent `overlay.items` with text, position, anchor, size, color, and opacity. `overlay.enabled: false` is the master no-text switch and suppresses both custom items and the reference technical HUD. When overlays are enabled, `overlay.reference_hud` opts into that reference HUD. Reactivity presets expand both native renderer `bindings` and owned `modulators`: frame-space `pulse`, `shake`, `flash`, and `chroma`; camera-space `camera_distance`, `camera_elevation`, `camera_roll`, and `camera_kick`; and form-space controls for scale, deformation, ripple, length, curvature, direction, twist, and snap. The `camera-driven`, `spectral-resonance`, and `spectral-stretch` presets supply bounded musical mappings. See `examples/reactive-overlay.json` for explicit per-scene mappings.

The public renderer vocabulary is `palette`, `forms`, `form_len_sec`, and `cameras`. Forms include the reference catalog plus two production-owned abstract geometries: `resonance`, a spectrum-sculpted multi-lobed mass, and `stretch`, an amplitude-lengthened body whose bend plane, curvature, twist, and recoil follow spectral content; see `examples/resonance.json` and `examples/stretch.json`. Camera motion may be tuned independently from form animation with `camera_speed`, `camera_phase_sec`, and `camera_intensity`; defaults preserve the reference behavior. Legacy `preset`, `looks`, and `look_len_sec` inputs are accepted during resolution but never appear in resolved profiles. Per-scene `finish` controls own bloom, streaks, flash, chroma, slice glitches, vignette, scanlines, and grain without modifying `ref/`.

Renders split into deterministic chunks. `settings.workers` defaults conservatively to `auto`, `chunk_sec` defaults to four seconds, and completed chunks are retained under `.metalheart-work/` for automatic resume. CLI overrides are available through `--workers`, `--chunk-sec`, and `--no-resume`.

The minimal example renders three seconds at preview quality. `examples/multi-scene.json` demonstrates an explicit hard cut from Mercury to an Ember/Ferro impact template. Both use the existing audio-reactive reference fixture.

## Documentation

- [Product and technical specification](docs/metalheart-studio-spec.md)
- [Development standards](docs/development-standards.md)

## Reference material

`ref/` contains renderer and audio-reactive prototypes plus visual fixtures. These files are reference inputs, not production modules, and are exempt from production style and coverage gates.
