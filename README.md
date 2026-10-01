# Metalheart Studio

Metalheart Studio is a local audio-reactive video authoring project built around the Metalheart/Depthcore renderer. It combines a headless JSON-driven rendering pipeline with a native PySide6/Qt desktop authoring shell. The project does not use a browser frontend, embedded webview, or local web server.

The implementation provides an audio-led native authoring workflow alongside JSON resolution, cached audio analysis, and direct rendering through the immutable audio-reactive reference backend.

## Quick start

```bash
uv sync
uv run python studio.py ui examples/layer-effects.json
python3 studio.py analyze /path/to/song.wav -o song.metalheart.json --quality preview
python3 studio.py validate examples/minimal.json
python3 studio.py resolve examples/minimal.json
python3 studio.py render examples/minimal.json -o renders/minimal.mp4 --workers auto
python3 studio.py render examples/multi-scene.json --scene-clips renders/scenes
```

The native editor begins with audio rather than JSON. **New from Audio** analyzes a track, creates phrase-aligned scenes, and opens a waveform timeline. Selecting a scene exposes structured Form, Background, and Ribbons tabs; each layer owns an independent ordered effect stack with catalog-driven property controls. Every effect row has a visible enable checkbox, and bypassed instances remain in place with dimmed labels and retained settings. Numeric effect parameters combine a fast slider with precise direct number entry. Image skins, materials, form geometry, camera, palette, background ripple, ribbon settings, and audio-response presets are editable per scene. Project-level Undo and Redo cover structured edits and applied Advanced JSON, while Save establishes the clean history point. Canonical JSON remains available only through the optional **View → Advanced Project JSON** dock.

Still previews are explicit and deliberately capped at 480×270, 12 fps, 0.2 core scale, and no antialiasing so authoring remains practical on older hardware. Analysis, preview, and full export run outside the UI thread and support cancellation. Full export continues to use the authored quality settings.

`analyze` detects tempo, downbeats, and energy, divides the track into contiguous phrase-aligned scenes, and writes a neutral config skeleton that can be edited or rendered directly. It does not infer sentiment or select aesthetics from audio. Use `--bars-per-scene` and `--max-scene-sec` to tune boundaries, and `--template` to choose the explicit default assigned to every generated scene.

Quality profiles now have concrete defaults: `preview` is 320×180 at 12 fps, `draft` matches the reference fixtures at 960×540 and 24 fps, and `final` is 1920×1080 at 30 fps. Explicit size, FPS, and CRF values override the selected profile.

Each scene may define resolution-independent `overlay.items` with text, position, anchor, size, color, and opacity. `overlay.enabled: false` is the master no-text switch and suppresses both custom items and the reference technical HUD. When overlays are enabled, `overlay.reference_hud` opts into that reference HUD. Reactivity presets expand both native renderer `bindings` and owned `modulators`: frame-space `pulse`, `shake`, `flash`, and `chroma`; camera-space `camera_distance`, `camera_elevation`, `camera_roll`, and `camera_kick`; and form-space controls for scale, deformation, ripple, multidirectional extent, and rotation. The `camera-driven`, `spectral-resonance`, and `spectral-radial` presets supply bounded musical mappings. See `examples/reactive-overlay.json` for explicit per-scene mappings.

The public renderer vocabulary is `palette`, `forms`, `form_len_sec`, and `cameras`. Forms include the reference catalog plus two production-owned abstract geometries: `resonance`, a spectrum-sculpted multi-lobed mass, and `radial`, whose 24 spectrum bands pull the surface along directions distributed around the whole form; see `examples/resonance.json` and `examples/radial.json`. Radial may opt into `form_style` faceting, deterministic object-space jaggedness, and continuous geometric steps. The `spectral-radial-jagged` preset maps amplitude to jaggedness and spectral centroid to detail scale; see `examples/jagged-radial.json`. Optional `renderer.surface` settings replace any 3D core's palette color with a config-relative image using seamless object-space triplanar projection. The `material` setting selects `metallic` reflections or `matte` diffuse lighting. PSX-inspired skins may opt into nearest sampling, stable texture-coordinate steps, and stepped lighting without changing existing renders; see `examples/image-skin.json` and `examples/psx-image-skin.json`.

A 3D scene may also replace the procedural palette background with a config-relative image through `background.source: "image"`. Cover, contain, and tile fitting are supported along with scale, rotation, offset, opacity, dots, foreground ghosts, and shadow controls. The typed `background_pulse` destination changes only background brightness and scale. An optional `background.ripple` surface bends the image with spectrum-directed traveling waves and relights it as flat, matte, or metallic material. `background_ripple`, `background_ripple_scale`, and `background_ripple_impact` independently map overall amplitude, spectral detail, and transient rings while leaving fully opaque form pixels stable; see `examples/image-background.json`. Camera motion may be tuned independently from form animation with `camera_speed`, `camera_phase_sec`, and `camera_intensity`; defaults preserve the reference behavior. Legacy `preset`, `looks`, and `look_len_sec` inputs are accepted during resolution but never appear in resolved profiles. Per-scene `finish` controls own bloom, streaks, flash, chroma, slice glitches, vignette, scanlines, and grain without modifying `ref/`.

Ordered `post` chains provide an owned Glitzle-, Glitchstation-, and Dazzle-derived effect library at scene and global scope. On 3D scenes, the same catalog may also be scoped to `background.post`, `renderer.surface.post`, or `renderer.decor.ribbons.post`; transparent form and ribbon mattes preserve spatial effect movement without filtering the other layers or final text overlay. The catalog contains configurable Glitzle building blocks; a Glitchstation-aligned Color family with `contrast`, `saturation`, `posterize`, `channels`, `grayscale`, and `invert`; Glitchstation shift/block pedals for wrapping `rgb_shift`, directional `tear`, seeded `block_jitter`, and `rectangles`; configurable Glitchstation `vhs` and `arcade` screen processors; the complete 19-preset Glitzle Glitch category; curated Chaos, Decay, Destructive, and Violent presets; five of Glitzle's seven Retro/CRT presets; four Dazzle mirror modes; Dazzle XOR and four-direction Ziti transforms; four-direction VidGlitch-compatible Tetrys; and the Glitzle Studio Glitch Maker effects `chromatic`, `pixel_sort`, and `slitscan`. The catalog marks Datamosh Breakup, Stutter Tear, Bitplane Scramble, Channel Smear, Scanline Desync, and Glitch Warpfield as featured Glitch presets for native UI surfacing. Effects support stable order, enable/bypass, output mixing, typed parameters, deterministic seeded noise, and expansion into portable render profiles. Numeric parameters publish slider step and semantic-role metadata where their source controls define it. `scanlines` is the simple alternating-row treatment; `scanline_corrupt` adds audio-scaled displaced signal bands and chromatic fringing. Audio-aware Glitzle effects expose bounded `audio_scale` parameters. Slitscan declares its finite history requirement, and render workers preroll that history so chunk boundaries do not reset the image. Run `python3 studio.py list effects --json` for UI-ready metadata and see `examples/effects.json` and `examples/layer-effects.json` for authoring syntax. The sibling projects are not runtime dependencies.

Three-dimensional ribbons and plates are independently authorable through `renderer.decor`. Each family has its own enable switch, deterministic count, metallic or matte material, and optional image surface. Ribbon images use longitudinal/twisted-width coordinates that bend with the blade; plate images use planar object-local coordinates. The destinations `ribbon_width`, `ribbon_twist`, `ribbon_wave`, `ribbon_speed`, `plate_orbit`, and `plate_displacement` expose decor motion to ordinary audio bindings. Legacy `decor: true|false` remains valid and preserves the reference defaults; see `examples/decor.json`.

Renders split into deterministic chunks. `settings.workers` defaults conservatively to `auto`, `chunk_sec` defaults to four seconds, and completed chunks are retained under `.metalheart-work/` for automatic resume. CLI overrides are available through `--workers`, `--chunk-sec`, and `--no-resume`.

`render CONFIG --scene-clips DIRECTORY` skips assembled-timeline output and renders every scene as an independently playable, audio-synchronized clip. Files use stable ordered names such as `001-intro.mp4`; each receives its own resolved profile and render manifest. Scene-local form skins, background images, ribbon skins, and plate skins remain independent in the exported clips. Global animation time retains the scene's original timeline phase, while scene time still begins at zero.

The minimal example renders three seconds at preview quality. `examples/multi-scene.json` demonstrates an explicit hard cut from Mercury to an Ember/Ferro impact template. Both use the existing audio-reactive reference fixture.

## Documentation

- [Product and technical specification](docs/metalheart-studio-spec.md)
- [Development standards](docs/development-standards.md)

## Reference material

`ref/` contains renderer and audio-reactive prototypes plus visual fixtures. These files are reference inputs, not production modules, and are exempt from production style and coverage gates.
