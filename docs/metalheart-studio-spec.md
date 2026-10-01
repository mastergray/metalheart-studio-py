# Metalheart Studio — Product and Technical Specification

Status: Draft for discussion  
Date: 2026-09-26  
Working name: **Metalheart Studio**

## 1. Summary

Metalheart Studio is a local audio-reactive video authoring application backed by a headless rendering pipeline. It keeps the useful parts of Glitzle Studio—audio analysis, scene-based composition, declarative JSON files, reusable templates, effect chains, validation, and reproducible rendering—but replaces Dazzle as the base visual generator with the Metalheart/Depthcore renderer currently prototyped in `ref/metalheart.py` and `ref/liquid3d.py`.

The first version should let an author:

1. analyze a song into continuous audio features and suggested scene boundaries;
2. choose a Metalheart form, camera, palette, and renderer options for each scene;
3. map audio features to renderer parameters without writing Python;
4. stack glitch, post-filter, and FFmpeg effects per scene or globally; and
5. preview scenes and effects in a native desktop application; and
6. render a deterministic final video plus a portable render profile from either the desktop application or CLI.

The first version is an evolution of Glitzle's workflow, not a line-for-line fork. JSON remains the canonical project and interchange format, while a native PySide6/Qt desktop application provides the primary visual authoring surface. The rendering engine and CLI remain independently usable for automation and testing. The project must not introduce a browser frontend, embedded webview, JavaScript UI, or local web server.

## 2. Source systems and current capabilities

### 2.1 Glitzle Studio concepts to retain

The reference Glitzle project already demonstrates these useful patterns:

- two-phase `analyze` then `render` CLI workflow;
- JSON timelines with global settings and ordered scenes;
- audio-derived scene boundaries and objective timing/event metadata;
- strict up-front validation of all named effects and presets;
- independent scene renders, optionally in parallel;
- ordered per-scene and global post-processing chains;
- render profiles that preserve the exact authored configuration;
- managed catalogs for glitch effects, Python post-filter presets, and FFmpeg recipes;
- content-addressed intermediate preservation for failure recovery and repeat-render reuse.

### 2.2 Metalheart renderer capabilities to expose

The current reference renderer is deterministic for a given time, seed, renderer configuration, and `Params` value. It produces BGR frames and already exposes an audio-oriented per-frame control structure:

- `bass`: low-frequency energy;
- `mid`: mid-frequency energy;
- `high`: high-frequency energy;
- `onset`: transient/beat impulse;
- `spectrum`: optional N-band magnitude array used by the HUD.

The current selectable visual vocabulary is:

- palettes: native `steel`, `acid`, `ember`, and `jungle`, plus Dazzle-derived `rainbow`, `ice`, `electric`, `neon`, and `grayscale`;
- cores: `3d`, `2d`;
- forms (called `looks` by the reference backend): `mercury`, `wring`, `ferro`, `drip`, `split`, `fold`, `morph`, `gyro`, `chaos`, plus the production-owned abstract `resonance` and `radial` geometries;
- cameras: `orbit`, `crane`, `dolly`, `low`, `top`, `macro`, `dutch`, `drift`;
- toggles/quality controls: scanlines, decor, anti-aliasing, and 3D core render scale;
- choreography controls: one or more forms and cameras, form duration, camera duration, crossfade behavior, and independent camera speed, phase, and signature intensity.

The authoring concepts map to Glitzle/Dazzle as follows:

| Glitzle/Dazzle | Metalheart | Meaning |
| --- | --- | --- |
| Dazzle shape `effects` | scene forms (`renderer.forms`) | generated subject or deformation treatment |
| Dazzle `palette` | Metalheart palette (`renderer.palette`) | material and lighting color family |
| no direct equivalent | `renderer.core` | 2D or 3D rendering foundation |
| no direct equivalent | `renderer.cameras` | viewpoint and camera motion, independent of the form |
| audio-reactive behavior | scene `reactivity` bindings | mapping analyzed signals onto renderer inputs |

The public authoring vocabulary uses **form** and **palette**. Legacy `look`, `looks`, `look_len_sec`, and `preset` inputs are accepted as migration aliases, but resolved profiles contain only the public names. Cameras remain independent because changing the viewpoint is not the same operation as changing the generated form.

Dazzle's eight indexed color ramps were audited for adaptation into Metalheart's environment-lighting vocabulary. `rainbow`, `ice`, `electric`, `neon`, and `grayscale` sample their source ramp identities into stable sky, ground, key, rim, accent, HUD, and background roles. They are owned static palettes rather than indexed or cycling palettes. `fire` and `lava` are excluded because the existing `ember` palette already covers their warm progression, while `ocean` is redundant with `steel` and `ice`. This keeps palette selection visually meaningful and avoids a runtime dependency on Dazzle.

The owned `jungle` palette fills the remaining green/yellow range with deep foliage backgrounds, yellow-green environment reflections, and warm gold accents. It is intentionally less fluorescent and more two-toned than `acid` or `neon`.

The renderer already uses the audio-oriented parameters in meaningful places, including core size and deformation, spike response, surface ripple, ribbon motion, beat shake, HUD flicker/readouts, and spectrum bars. The clip CLI currently feeds synthetic signals; replacing those signals with analyzed audio is the central integration task.

### 2.3 Audio-reactive reference prototype

`ref/audioReactive/` is a second reference snapshot that already demonstrates audio decoding, band/onset/spectrum analysis, tempo and beat-grid estimation, phrase-aligned look planning, multi-process chunk rendering, concatenation, and final audio muxing. It is evidence and regression material, not the production architecture.

The production implementation should reuse validated behavior and algorithms from this prototype where they satisfy the new config contract, but should not copy its monolithic CLI structure or treat its current output as automatically correct. Its synthetic track generator and sample video are useful inputs for deterministic integration and visual-regression fixtures.

## 3. Product goals

### 3.1 Goals

- Make compelling audio-reactive Metalheart videos without code changes.
- Provide a native desktop workflow for previewing, authoring, and producing those videos.
- Make JSON composition templates concise enough for experimentation and iteration.
- Keep timelines human-readable, versioned, deterministic, and validatable.
- Separate audio analysis, authored intent, rendering, and post-processing.
- Preserve exact audio/video duration and synchronization.
- Support fast drafts and high-quality final renders from the same timeline.
- Make renderer options and effect catalogs inspectable through CLI commands and generated schema documentation.
- Allow the Metalheart renderer to gain new controls without redesigning the timeline format.

### 3.2 Non-goals for version 1

- Real-time full-resolution playback of the CPU ray marcher.
- A general-purpose nonlinear video editor.
- Any browser frontend, embedded webview, JavaScript UI, or local web server.
- Real-time editing semantics that bypass the canonical JSON project model.
- Arbitrary keyframe curves for every internal renderer variable.
- Live microphone or performance/VJ input.
- GPU rendering or a rewrite of the renderer in WebGL.
- Multi-track audio mixing.
- Cross-platform distribution or cloud rendering.
- Backward compatibility with Dazzle-specific `video.visuals` blocks.

Glitch and post-filter compatibility is desirable, but should be implemented as copied, owned modules or clean package dependencies—not runtime coupling to sibling repositories.

## 4. JSON-backed workflow

### 4.1 Create or copy a config template

```bash
cp examples/metalheart-basic.json song.metalheart.json
```

Edit the JSON to select the audio file, output settings, scene ranges, Metalheart renderer settings, reactivity mappings, and post effects. A single-scene template should be enough to produce a complete audio-reactive render; scenes and advanced overrides are optional composition tools.

An explicit analysis command is available for inspecting a track or generating suggested scene boundaries:

```bash
python3 studio.py analyze song.wav -o song.analysis.json
```

Analysis produces or refreshes:

- track metadata and duration;
- a compact frame-addressable feature cache;
- detected beats, downbeats, transients, silence, peaks, and section changes;
- suggested scene boundaries with event counts and measured feature summaries;
- an optional timeline skeleton with default Metalheart settings and suggested scenes.

Analysis must not infer aesthetic intent such as mood, sentiment, “calm,” or “intense,” and it must not automatically choose forms, palettes, cameras, or reactivity presets from such labels. Those are authored scene decisions. Feature summaries such as mean energy may be retained as factual diagnostics, while the skeleton uses an explicitly selected default template until the author assigns each scene.

The feature cache should be stored beside the source audio or in the render cache and referenced by content fingerprint. Large per-frame arrays should not be embedded in config JSON. Running `render` automatically performs analysis when a valid cache is not already available, so `analyze` is an optional diagnostic/preparation step rather than a required phase.

### 4.2 Validate the JSON

```bash
python3 studio.py validate song.metalheart.json
```

Validation resolves templates and defaults, then reports all problems before rendering. Supporting CLI commands should expose legal values without requiring source inspection:

```bash
python3 studio.py list forms
python3 studio.py list cameras
python3 studio.py list effects
python3 studio.py schema
```

For each scene, the JSON selects:

- palette and seed policy;
- core type and quality settings;
- one or more forms and camera moves;
- choreography timing or a fixed form/camera;
- audio-reactivity preset and optional binding overrides;
- per-scene post-processing;
- optional notes and a human-friendly scene name.

### 4.3 Render

```bash
python3 studio.py render song.metalheart.json \
  --output song.mp4 \
  --quality final \
  --workers auto \
  --chunk-sec 4
```

`render` always runs validation before expensive work. It analyzes or loads audio features once, renders independent scene segments, applies ordered post chains, concatenates segments in timeline order, muxes the original audio, applies global post-processing, and writes a resolved render profile.

Optional `--quality preview` and `--range START:END` flags provide fast, low-resolution test renders for automation and use by the desktop application's preview workflow.

### 4.4 Author in the desktop application

The PySide6/Qt application opens and saves the same versioned JSON documents accepted by the CLI. It presents the audio waveform and hard-cut scene timeline, scene renderer and reactivity controls, ordered scene/global effect stacks, still-frame previews, short range previews, and final or per-scene export actions. It calls the same resolver, validator, analyzer, renderer, and effect registry used by the CLI; UI-only project state must not become a second rendering contract.

The implemented first shell exposes the canonical authored JSON directly, resolved scene selection, effect counts for form, ribbon, background, scene, and global scopes, persistent validation feedback, and a normalized scene-time control. Still previews run in a worker thread through the production resolver, analysis cache, renderer adapter, and effect-history calculation. They are capped at 480×270, 12 fps, 0.2 core scale, and disabled antialiasing; these preview-only cost settings never mutate the authored export profile. Full video export runs as a cancellable child CLI process so the Qt event loop remains responsive.

Preview is progressive rather than full-resolution real-time playback. A playhead change may request a low-cost still immediately, while an explicit preview action renders a selected range with the preview quality profile. Preview work must be cancellable and must never replace a valid final output.

## 5. Architecture

```text
audio file
   │
   ├── analyzer ──> feature cache + events
   │                         │
JSON config template ──> template/default resolver
                             │
                      validated timeline
                             │
                    scene render workers
                             │
 feature sampler ──> Metalheart frame renderer
                             │
                    per-scene post chain
                             │
                    concat + audio mux
                             │
                      global post chain
                             │
                final video + resolved profile
```

Recommended modules:

| Module | Responsibility |
|---|---|
| `studio.py` | CLI and high-level orchestration |
| `timeline.py` | schema loading, migration, defaults, and validation |
| `analysis.py` | audio decoding, features, events, and feature-cache I/O |
| `signals.py` | feature sampling, envelopes, binding evaluation, and scene reset behavior |
| `templates.py` | template catalog loading, inheritance resolution, and expansion |
| `renderers/metalheart.py` | adapter between timeline scene settings and the reference renderer |
| `metalheart/` | production-owned frame renderer derived from `ref/` |
| `post/` | effect registries and ordered post-chain execution |
| `profiles.py` | quality profiles and resolved render-manifest output |

The production renderer should be moved or copied out of `ref/`; `ref/` should remain an immutable visual and behavioral reference once implementation begins.

## 6. Audio analysis and signal model

### 6.1 Feature cache

Analysis should decode audio to mono PCM and compute features at a fixed analysis hop independent of render FPS. Recommended initial hop: 10 ms or 20 ms. The cache contains:

- timestamps;
- normalized `bass`, `mid`, and `high` band energy;
- broadband RMS/energy;
- onset envelope;
- beat and downbeat impulses;
- 24-band normalized spectrum for the HUD;
- optional brightness and tension descriptors for scene suggestions.

Use a compact NumPy format (`.npz`) with metadata including source audio fingerprint, analyzer version, sample rate, hop size, normalization method, and band definitions. Re-analysis is required if the fingerprint or analyzer version changes.

### 6.2 Frequency bands

Initial defaults:

| Signal | Frequency range |
|---|---:|
| `bass` | 20–180 Hz |
| `mid` | 180–2,000 Hz |
| `high` | 2,000–12,000 Hz |

These ranges must be stored in cache metadata and may later become project settings. Values presented to the renderer are normalized to `[0, 1]` using robust track-level percentiles rather than per-frame min/max. Silence should remain near zero.

### 6.3 Frame sampling and envelopes

For output frame `n` at FPS `f`, sample signals at the center timestamp `(n + 0.5) / f`. Continuous features use linear interpolation. Beat, downbeat, and transient impulses use peak-preserving sampling so events are not lost between analysis hops.

Each signal passes through independently configurable attack and release smoothing. The onset path should default to a fast attack and short release; energy bands should default to slower release values to avoid jitter.

### 6.4 Bindings

A binding maps one analyzed source to one public renderer parameter:

```json
{
  "source": "bass",
  "amount": 0.85,
  "bias": 0.05,
  "curve": "ease_out",
  "attack_ms": 20,
  "release_ms": 180,
  "clamp": [0.0, 1.0]
}
```

Version 1 supports sources `bass`, `mid`, `high`, `amplitude`, `energy`, `spectral_centroid`, `onset`, `beat`, `downbeat`, and `tension`; curves `linear`, `ease_in`, `ease_out`, `smoothstep`, and `square`; and scalar destinations declared by the renderer adapter.

The adapter exposes the existing `Params` destinations `bass`, `mid`, `high`, and `onset`, and passes the analyzed 24-band spectrum directly to `Params.spectrum`. Because those native inputs are intentionally subtle, scenes may also map signals onto owned frame-space modulators: `pulse`, `shake`, `flash`, and `chroma`. Camera-space destinations `camera_distance`, `camera_elevation`, `camera_roll`, and `camera_kick` apply bounded transforms to the selected base-camera pose; the `camera-driven` preset provides a curated mapping. Form-space destinations `form_scale`, `form_deformation`, and `form_ripple` drive the abstract `resonance` mass from fast amplitude, normalized spectral centroid, and onset envelopes. The `radial` form adds `form_extent` and `form_rotation`; amplitude controls overall reach, the individual 24 spectrum bands control extensions distributed across the sphere, spectral centroid rotates the field, and onsets propagate surface waves. An optional `renderer.form_style` block adds bounded faceting, deterministic object-space jagged displacement, jagged detail scale, and continuous geometric plateaus to Radial. The `form_jaggedness` and `form_jagged_scale` destinations make the first two properties audio-reactive; `spectral-radial-jagged` maps amplitude and spectral centroid onto them. A modulator uses the same amount, bias, curve, threshold, and clamp model as a native binding. Future renderer controls should be added through a typed parameter registry rather than arbitrary dotted access into Python objects.

### 6.5 Reactivity presets

The template catalog should ship with named binding presets such as:

- `balanced`: direct, smoothed low/mid/high with transient onset;
- `sub-heavy`: exaggerated bass and restrained high-frequency motion;
- `percussive`: strong onset and beat response with quicker envelopes;
- `ambient`: slow envelopes and minimal camera shake;
- `ferro-impact`: onset-forward response suited to the `ferro` look;
- `manual`: explicit per-binding settings.

Presets expand to ordinary bindings in the resolved render profile so renders remain reproducible if preset definitions later change.

### 6.6 Visible modulation

Audio-reactive behavior is authored per scene. Time-based form or camera choreography must not be presented as audio response. For evaluation, a fixed form and fixed camera can isolate whether detected beats and transients visibly alter the frame. Presets may supply conservative defaults, while an author can explicitly bind beat or downbeat impulses when a pronounced synchronized response is wanted.

### 6.7 Image surface skins

An optional `renderer.surface` block may assign a config-relative image to any 3D core. Version 1 uses object-space `triplanar` mapping so animated or topologically changing forms do not require authored UV coordinates. `scale` controls repetition, and `rotation_deg` rotates the projection around the vertical axis. The image replaces the core palette color rather than tinting it. `material` selects `metallic`, which adds neutral reflections and highlights, or `matte`, which applies diffuse lighting without reflective highlights. `sampling` selects smooth `bilinear` or hard-edged `nearest` texture sampling. A nonzero `texel_steps` value snaps each repeating projection to a stable object-space grid, while a nonzero `lighting_steps` value reduces smooth illumination to a fixed number of bands. Zero disables either quantizer and preserves the original output. The palette continues to control the environment and unskinned geometry. The skin applies only to core hits; ribbons and plates retain their reference materials. Resolved paths and image-content digests participate in render fingerprints so editing an image invalidates resumable chunks.

### 6.8 First-class backgrounds

A 3D scene may define a `background` block whose `source` is either the existing procedural `palette` or a config-relative `image`. `background.palette` selects the procedural gradient, dot field, and ghost tint independently from `renderer.palette`; omission inherits the renderer palette. Procedural backgrounds rebalance the reference renderer's near-black center and edge stops into a visible but still subordinate color wash. `background.intensity` ranges from `0.0` through `4.0`, defaults to `1.0`, and scales only that procedural wash so image skins retain their authored colors. Image backgrounds support `cover`, `contain`, and repeating `tile` fit modes. `scale`, `rotation_deg`, normalized `offset`, and `opacity` control image placement without changing the foreground form. The dot field, blurred foreground ghosts, and drop shadow are independently enabled by `dots`, `ghosts`, and `shadow`.

The `background_pulse` modulator is a bounded zero-to-one control. It scales the background around `pulse_center` by at most `pulse_scale` and raises its brightness by at most `pulse_brightness`. The optional `ripple` object instead treats the background as a displaced 2.5D sheet. Its traveling height field combines directional weights reduced from the live spectrum, a broad bass wave, and an onset-accented radial wave. Reconstructed normals displace the source-image coordinates and provide neutral `matte` or `metallic` lighting without replacing the image's colors. `amount`, `scale`, `travel_speed`, `warp`, `specular`, and `roughness` bound the authored treatment. The typed `background_ripple`, `background_ripple_scale`, and `background_ripple_impact` modulators control deformation strength, spectral scale, and transient radial impact.

Both background effects are composed before ghosts, shadow, and foreground geometry, so they do not resize, warp, or relight fully opaque foreground pixels. Whole-frame finishing still follows composition, and overlays remain last. Background image paths and content digests participate in render fingerprints. Version 1 background customization is limited to the 3D core because that renderer provides the isolated foreground alpha needed to preserve this layer contract.

### 6.9 First-class 3D decor

`renderer.decor` accepts the legacy boolean or a resolved object containing an overall enable switch, optional seed, and independent `ribbons` and `plates` objects. Each family provides its own enable switch, deterministic count from zero through eight, `metallic` or `matte` material, and optional image surface. `renderer.decor.ribbons.palette` selects independent environment and rim colors for unskinned ribbons; omission inherits `renderer.palette`, while an image skin continues to supply the ribbon's base color. When the overall switch or both families are disabled, the renderer omits the decor SDFs and their additional tracing steps.

Ribbon images use local longitudinal and twisted-width coordinates derived from the animated ribbon frame. The image therefore bends, waves, and twists with the blade rather than sliding through it in world space. Plate images use local planar coordinates derived from the animated plate transform. Both surfaces support scale, rotation, bilinear or nearest sampling, texture-coordinate steps, and lighting steps. Decor images are resolved relative to the config and included in render fingerprints independently from core and background images. A core image skin never propagates to ribbon or plate hits.

The typed destinations `ribbon_width`, `ribbon_twist`, `ribbon_wave`, and `ribbon_speed` control blade width, twist-rate response, path amplitude, and longitudinal wave speed. `plate_orbit` and `plate_displacement` control orbital speed and radial distance. If none of these explicit destinations is authored, bass continues to widen ribbons and displace plates while mid energy changes ribbon twist speed, preserving legacy output. The first-class decor object and its explicit destinations are version 1 3D features; legacy booleans continue to operate for both cores.

## 7. Timeline format

### 7.1 Design rules

- JSON is the sole v1 authoring and interchange format.
- Paths may be relative to the timeline file; the resolved profile records normalized absolute paths and fingerprints.
- Omitted values inherit typed defaults during validation.
- Unknown keys produce warnings; unknown enum values or effect IDs produce errors.
- Scene ranges must be ordered, non-overlapping, and cover the intended render range.
- The schema is versioned independently from renderer and analyzer versions.
- Authoring-time shorthand is allowed, but the saved render profile is fully resolved.

### 7.2 Proposed schema

```json
{
  "version": 1,
  "audio": "./audio/song.wav",
  "analysis": {
    "cache": "./audio/song.features.npz"
  },
  "settings": {
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "crf": 18,
    "seed": 3,
    "quality": "final",
    "time_mode": "global"
  },
  "scenes": [
    {
      "id": "intro",
      "name": "Cold open",
      "start_sec": 0.0,
      "end_sec": 12.4,
      "template": "builtins/mercury-intro",
      "renderer": {
        "id": "metalheart",
        "palette": "steel",
        "core": "3d",
        "forms": ["mercury", "wring"],
        "cameras": ["orbit", "crane"],
        "form_len_sec": 6.0,
        "camera_len_sec": 9.0,
        "camera_speed": 1.0,
        "camera_phase_sec": 0.0,
        "camera_intensity": 1.0,
        "crossfade_sec": 1.8,
        "decor": true,
        "anti_alias": true,
        "core_scale": 0.5,
        "surface": {
          "image": "./assets/surface.png",
          "mapping": "triplanar",
          "scale": 1.0,
          "rotation_deg": 0.0,
          "material": "metallic",
          "sampling": "nearest",
          "texel_steps": 48,
          "lighting_steps": 6
        },
        "hud": false
      },
      "reactivity": {
        "preset": "balanced",
        "bindings": {
          "bass": {"source": "bass", "amount": 1.0},
          "mid": {"source": "mid", "amount": 0.8},
          "high": {"source": "high", "amount": 0.7},
          "onset": {
            "source": "onset",
            "amount": 1.0,
            "attack_ms": 0,
            "release_ms": 100
          }
        },
        "modulators": {
          "pulse": {"source": "beat", "amount": 0.1, "clamp": [0.0, 0.1]},
          "shake": {"source": "onset", "amount": 0.02, "threshold": 0.3},
          "flash": {"source": "downbeat", "amount": 0.2},
          "chroma": {"source": "high", "amount": 0.008, "threshold": 0.5},
          "background_ripple": {"source": "amplitude", "amount": 1.0, "clamp": [0.0, 1.0]},
          "background_ripple_scale": {"source": "spectral_centroid", "amount": 1.0, "clamp": [0.0, 1.0]},
          "background_ripple_impact": {"source": "onset", "amount": 1.0, "clamp": [0.0, 1.0]}
        }
      },
      "background": {
        "source": "image",
        "image": "./assets/background.png",
        "fit": "cover",
        "scale": 1.0,
        "rotation_deg": 0.0,
        "offset": [0.0, 0.0],
        "opacity": 1.0,
        "material": "metallic",
        "ripple": {
          "enabled": true,
          "amount": 0.035,
          "scale": 5.0,
          "travel_speed": 0.4,
          "warp": 0.012,
          "specular": 0.45,
          "roughness": 0.65
        },
        "pulse_brightness": 0.35,
        "pulse_scale": 0.08,
        "pulse_center": [0.5, 0.5],
        "dots": false,
        "ghosts": true,
        "shadow": true
      },
      "overlay": {
        "enabled": true,
        "items": [
          {
            "text": "METALHEART",
            "position": [0.05, 0.08],
            "anchor": "top_left",
            "size": 0.05,
            "color": "#D8ECFF",
            "opacity": 0.95
          }
        ]
      },
      "finish": {
        "bloom": 0.65,
        "wide_bloom": 0.35,
        "streaks": 0.7,
        "onset_streaks": 1.5,
        "flash": 0.04,
        "chroma": 0.0005,
        "chroma_onset": 0.002,
        "slice_glitch": false,
        "slice_threshold": 0.7,
        "vignette": 0.5,
        "scanlines": false,
        "grain": 0.006,
        "grain_high": 0.006
      },
      "post": [
        {
          "type": "glitch",
          "id": "chromatic",
          "props": {"amount": 12}
        },
        {
          "type": "post_filter",
          "id": "bloom"
        }
      ]
    }
  ],
  "post": [
    {
      "type": "ffmpeg",
      "id": "film_grain"
    }
  ]
}
```

### 7.3 Time semantics

`settings.time_mode` controls the time passed to the renderer:

- `global` (default): animation time equals the timestamp in the complete song, preserving motion phase across adjacent scenes that share settings;
- `scene`: animation time restarts at zero for each scene, useful when choreography should begin at a specific look or camera.

Audio sampling always uses global song time. A scene may override `time_mode`. Scene rendering must derive frame counts from exact timeline frame boundaries, not independent rounded durations, to prevent cumulative drift.

### 7.4 Quality profiles

Named quality profiles resolve to concrete settings before rendering:

| Profile | Resolution | FPS | CRF |
| --- | ---: | ---: | ---: |
| `preview` | 320×180 | 12 | 23 |
| `draft` | 960×540 | 24 | 20 |
| `final` | 1920×1080 | 30 | 18 |

The `draft` dimensions and frame rate match the checked-in reference videos. Explicit `width`, `height`, `fps`, or `crf` values override their profile defaults. The resolved profile always records the effective numeric values.

Profiles also resolve renderer sampling defaults: preview uses a 0.35 internal 3D scale without antialiasing, draft uses the reference 0.5 scale with antialiasing, and final uses 0.75 with antialiasing. Scene renderer values may override these defaults.

### 7.5 Overlay semantics

`overlay.enabled` is the master switch for every text-bearing layer. When false, neither custom items nor the reference technical HUD may be drawn. When true, `overlay.items` supplies author text and `overlay.reference_hud` explicitly opts into the reference HUD. Custom positions and sizes use normalized frame coordinates so the same scene remains stable across quality profiles.

### 7.6 Seed semantics

`settings.seed` is required for final-quality renders. A scene may override it. A null seed is allowed only for exploratory renders; the CLI resolves and records the generated integer before rendering.

The same resolved timeline, audio fingerprint, analysis cache, renderer revision, and tool versions must reproduce the same frame sequence, except for explicitly documented nondeterministic post effects.

### 7.7 Scene templates

Templates make combinations of renderer settings, reactivity, and effects reusable. A template may provide:

- a Metalheart renderer block;
- a reactivity preset and binding overrides;
- an ordered scene post chain;
- authoring metadata such as name, description, tags, and a preview image.

Templates never own scene identity, start/end time, analysis labels, or source audio. A scene references a template by stable namespaced ID and may override any supplied value. Object values deep-merge; lists replace rather than concatenate unless the author explicitly edits the resulting list. This rule keeps effect order predictable.

Template catalogs are versioned JSON files. Version 1 permits built-in and project-local catalogs; user-library catalogs can follow later. A template may extend at most one other template. Resolution must reject cycles and missing parents.

The authoring timeline may retain compact template references. Before validation and rendering, the resolver expands every reference into a complete scene configuration. The resolved render profile contains both the original template ID/version and the fully expanded settings, so later catalog edits cannot change an existing render.

CLI commands support listing templates, printing a fully resolved template, and materializing a template as standalone JSON. Project-local templates are ordinary version-controlled files. Interactive template browsing and editing are deferred with the rest of the UI.

## 8. Renderer adapter contract

The orchestration layer should not construct `MetalheartRenderer` directly. It calls a renderer adapter with a stable interface:

```python
renderer = adapter.create(output_spec, scene_config, resolved_seed, quality)
frame = renderer.render(time_sec, signals)
```

The adapter is responsible for:

- declaring supported parameters and enum values;
- applying quality-profile overrides;
- constructing `Params` from evaluated bindings;
- converting the renderer's BGR output to the encoder's expected pixel format;
- reporting renderer/version metadata for profiles and caches;
- rejecting unsupported combinations before rendering;
- keeping scene settings independent from internal class names where practical.

Renderer instances are not shared between workers. Within a scene, one instance is reused for all frames so precomputed textures and geometry remain efficient.

## 9. Render pipeline

### 9.1 Preflight

Before producing frames:

1. load and migrate the timeline;
2. resolve relative paths and defaults;
3. validate audio, analysis cache, scene coverage, renderer settings, bindings, and post effects;
4. fingerprint source inputs and record tool versions;
5. calculate exact output-frame ranges for every scene;
6. estimate work and disk usage.

### 9.2 Scene render

For each scene:

1. create a renderer instance from the resolved scene configuration;
2. iterate its exact global frame range;
3. sample and smooth audio features at each frame time;
4. evaluate bindings and construct `Params`;
5. render BGR frames;
6. stream raw frames directly to FFmpeg rather than storing individual PNGs;
7. encode an audio-free, frame-accurate scene segment;
8. apply the ordered scene post chain.

The validated frame range is divided into deterministic fixed-duration chunks, including chunks that cross no more than the ordinary scene scheduler permits. Chunks render independently and concatenate in exact frame order without video re-encoding. The default automatic worker count is capped conservatively because the 3D ray marcher is CPU- and memory-intensive; `--workers` is user-overridable.

Each completed chunk is atomically published with a marker containing the render fingerprint and exact frame interval. Identical reruns reuse matching chunks. Failed or interrupted renders retain completed chunks under `.metalheart-work/`, while configuration, analysis, backend, or chunk-setting changes naturally select a different content-addressed work directory.

### 9.3 Assembly

Scene segments are concatenated losslessly when codec/container settings permit. The original audio is trimmed to the render range, muxed once after concatenation, and never repeatedly re-encoded between scene stages. Global post-processing runs after assembly.

The pipeline writes final output atomically through a temporary path. On success it writes:

- final video;
- resolved profile JSON;
- a render manifest with hashes, versions, elapsed time, warnings, and output metadata.

On failure it preserves intermediates and reports their location.

### 9.4 Quality profiles

Initial profiles:

| Profile | Intended use | Suggested defaults |
|---|---|---|
| `preview` | short CLI test renders | ≤640×360, 15 fps, low core scale, AA off, fast encode |
| `draft` | composition review | 1280×720, 24/30 fps, moderate core scale, AA optional |
| `final` | delivery | timeline resolution/FPS, authored core scale and AA, CRF 18 |

Quality profiles change render cost settings only. They must not change scene selection, animation timing, seed, audio bindings, or post-chain order.

## 10. Post-processing system

Retain Glitzle's ordered chain concept with explicit effect types:

- `glitch`: frame/video effects derived from glitch-maker;
- `post_filter`: owned Python frame filters and managed presets;
- `ffmpeg`: managed FFmpeg recipes.

Every effect registry entry must declare:

- stable ID, display name, category, and description;
- typed properties with defaults, ranges, and schema/documentation hints;
- whether it needs audio, previous frames, or the full clip;
- whether it is deterministic;
- supported pixel formats and resolutions;
- quality-profile support and estimated cost.

Scalar effect properties may opt into audio bindings through declared typed destinations. Existing Glitzle filters must be audited before import; malformed, resolution-hardcoded, or unsupported FFmpeg recipes should not enter the initial catalog merely for numeric parity.

The implemented first slice owns Glitzle's NumPy-style frame operations rather than invoking Glitzle at runtime. It provides configurable building blocks and curated presets across Glitch, Chaos, Decay, Destructive, Retro/CRT, and Violent categories. Scene and global chains use the same ordered entry shape:

```json
{
  "type": "post_filter",
  "id": "rgb_shift",
  "enabled": true,
  "mix": 0.7,
  "parameters": {
    "rX": 7,
    "bX": -9
  }
}
```

Resolution-safe operations execute on BGR frames inside render workers. Randomized operations derive their state from the render seed and the appropriate scene-local or global frame index so chunk count, worker scheduling, resume, and scene-clip export do not change their pixels. Finite-history effects declare their maximum lookback; workers render and discard that preroll before encoding an assigned chunk. Resolution-hardcoded FFmpeg recipes, external glitch-maker processes, unbounded-history effects, and arbitrary source-to-effect-property bindings remain outside this slice pending separate audits and integration contracts.

Three-dimensional scenes may place the same ordered effect entries at `background.post`, `renderer.surface.post`, and `renderer.decor.ribbons.post`. The renderer captures the visible frontmost form and ribbon materials from the immutable ray marcher, expands those classifications to output resolution, and processes each as a transparent layer. Spatial primitives carry their alpha matte, so effects such as Tear, Block Jitter, mirrors, Tetrys, Ziti, Slitscan, RGB Shift, Chromatic, VHS tracking, and Arcade curvature can move layer pixels instead of being clipped to the original silhouette. Background effects run after background ripple, ghosts, and shadow but before foreground composition. Form and ribbon effects then composite independently, followed by finishing, scene post, global post, and finally text overlay. Scoped chains require the 3D core; plate-scoped chains are not part of version 1.

```json
{
  "background": {"post": [{"id": "vhs", "mix": 0.35}]},
  "renderer": {
    "surface": {"post": [{"id": "posterize", "parameters": {"levels": 4}}]},
    "decor": {
      "ribbons": {"post": [{"id": "tear", "parameters": {"direction": "vertical"}}]}
    }
  }
}
```

The next owned catalog slice ports Dazzle's horizontal, vertical, quad, and diamond mirrors; VidGlitch's byte-equivalent Tetrys column drops; Dazzle's Ziti cylindrical projection; and animated XOR interference. Tetrys extends its original downward column motion to upward columns and left/right row motion while retaining `down` as the compatible default. Ziti likewise supports right, left, down, and up: `right` preserves the original horizontal projection, `left` reverses its phase, and down/up transpose the cylinder vertically with matching phase direction. Spatial effects retain their source geometry on Metalheart BGR frames. XOR operates per BGR channel rather than on Dazzle palette indices, so it is an intentional Metalheart adaptation rather than pixel identity with the Dazzle output. The complete 19-preset Glitzle Glitch post-filter category is represented as exact ordered operation recipes; Datamosh Breakup, Stutter Tear, Bitplane Scramble, Channel Smear, Scanline Desync, and Glitch Warpfield carry featured catalog metadata. Glitchstation contributes a six-effect Color family: contrast, saturation, posterize, independent RGB channel gain, grayscale blending, and invert blending. Those controls retain Glitchstation's defaults, bounds, increments, semantic roles, Rec.601 luminance, and rounded byte behavior. Its selected utility pedals add wrapping or clamped RGB Shift, horizontal or vertical seeded Tear, seeded Block Jitter, deterministic rectangle swaps, configurable VHS tracking/chroma/noise/head-switch processing, and configurable Arcade curvature/mask/palette/scan processing. Legacy Glitzle compound recipes retain their prior RGB Shift and Block Jitter semantics because their owned operation definitions do not opt into the Glitchstation parameters. Blister, Randomize, and Handheld are intentionally excluded. Glitzle Studio's Glitch Maker stack separately contributes horizontal, vertical, or circular `chromatic` aberration, contiguous-run `pixel_sort`, and finite-history `slitscan`. `scanline_corrupt` remains a deterministic full-width tear-and-chromatic recipe distinct from the simpler alternating-row `scanlines` primitive. These audio-aware effects retain bounded `audio_scale` parameters; fully general effect-property bindings remain future work.

## 11. Desktop, CLI, and JSON authoring contract

The native PySide6/Qt desktop application is the interactive authoring interface. The CLI remains a complete automation and diagnostic interface, and version-controlled JSON remains authoritative. Both interfaces use the same application services and validation rules. A browser application, embedded webview, or local HTTP API is explicitly outside the architecture.

The implemented primary workflow begins with **New from Audio**, which runs the shared analyzer and phrase-aligned scene planner outside the UI thread. The workspace presents cached audio energy as a waveform/hard-cut timeline and edits the selected scene through structured Form, Background, and Ribbons inspectors. Each layer owns an independent palette selector and ordered effect stack generated from the effect catalog, including typed parameter, mix, add, remove, and reorder controls. A native checkbox on every stack row controls enable/bypass; bypassed rows remain ordered with retained properties and use a dimmed label. Numeric effect values use catalog-driven slider/number pairs that retain precise direct entry and commit slider drags once. Project-level Undo and Redo restore canonical authored snapshots across structured controls and applied Advanced JSON; Save marks the current history position as clean. JSON is available through an optional advanced dock rather than serving as the normal authoring surface. Still previews remain explicit and bounded for the target machine. Analysis reports named workflow stages, and full export reports current scene/chunk, completed and total frames, elapsed time, and measured ETA through an optional line-oriented CLI protocol consumed by the native task area.

### 11.1 Required commands

- `ui [CONFIG]`: open the native PySide6 authoring application, optionally with a project.
- `render CONFIG`: validate, analyze when needed, and produce the requested video.
- `validate CONFIG`: resolve and validate without rendering.
- `analyze AUDIO`: inspect audio features/events and optionally emit a scene skeleton.
- `list {templates|forms|cameras|palettes|effects|reactivity}`: enumerate stable IDs and concise descriptions. `looks` remains a compatibility CLI alias.
- `schema`: emit JSON Schema for validation support and external tooling.
- `resolve CONFIG`: write the fully expanded config without rendering.

All commands support `--json` for machine-readable output where applicable. Normal progress goes to stderr so stdout can safely carry JSON.

`render CONFIG --scene-clips DIRECTORY` is the non-assembly render mode. It writes every scene as an independently playable clip named with its timeline index and sanitized scene ID, trims and muxes the matching source-audio interval, and writes a resolved profile and manifest beside each clip. It does not add transition frames or change scene boundaries. Each isolated scene retains its own form image skin, background image, ribbon skin, and plate skin. Global time preserves the scene's position in the authored timeline; scene time restarts at zero as usual.

### 11.2 Config templates

The repository ships with small, commented-by-documentation example configs:

- a minimal one-scene audio-reactive render;
- a multi-scene look/camera composition;
- a render with scene and global post chains;
- preview, draft, and final quality examples.

Because strict JSON does not support comments, each example should remain self-explanatory through descriptive IDs and a nearby Markdown reference. JSON Schema supplies property descriptions, types, defaults, enums, and bounds.

### 11.3 CLI usability

- Validation errors identify the config file, scene ID, and JSON property path.
- `render` prints current scene/frame, throughput, elapsed time, and estimated remaining time.
- `--dry-run` prints the resolved plan, frame counts, estimated work, cache state, and output paths.
- `--quality`, `--range`, `--output`, `--workers`, `--chunk-sec`, and `--no-resume` may override operational settings without changing composition semantics.
- The resolved profile records all CLI overrides.
- SIGINT/cancellation terminates child processes cleanly and preserves useful intermediates.

## 12. Validation and error handling

Validation errors block rendering. Warnings require visibility but not confirmation in the CLI.

Errors include:

- missing/unreadable audio or cache;
- stale cache fingerprint;
- invalid or overlapping scene ranges;
- a gap when full-track coverage is required;
- unknown palette, core, form, camera, binding source/destination, effect, or preset;
- binding values outside supported ranges;
- non-positive dimensions/FPS/durations;
- output dimensions incompatible with the selected encoder;
- missing FFmpeg/ffprobe or required Python dependencies.

Warnings include:

- unusually expensive resolution/core-scale/AA combinations;
- very short scenes relative to camera/look crossfades;
- a post effect excluded from the selected quality profile;
- nondeterministic effects;
- hard cuts between visually unrelated adjacent scenes;
- ignored unknown metadata keys.

CLI failures must be actionable and identify the timeline path, scene ID, and property path involved.

## 13. Performance and operational requirements

- Target this machine's Python 3.8.10 runtime and retain compatibility with the Python 3.8 series.
- Stream frames to FFmpeg with bounded memory.
- Cache audio analysis by content hash.
- Print unbuffered progress at least once per second during long renders.
- Report current scene, frame, frames per second, elapsed time, and estimated remaining time.
- Support cancellation that terminates child FFmpeg processes and leaves recoverable intermediates.
- Avoid writing final output until the complete encode succeeds.
- Bound parallel workers based on detected RAM and a configurable maximum.
- Keep temporary paths unique per render to prevent concurrent jobs from overwriting one another.
- Never depend on the current working directory for resource discovery.

## 14. Testing and acceptance criteria

### 14.1 Test levels

Tests use `pytest` and are divided by cost and dependency:

| Level | Marker | Purpose | Default run |
|---|---|---|---|
| Unit | none | schema, math, bindings, envelopes, template resolution, pure helpers | yes |
| Integration | `integration` | FFmpeg/ffprobe, cache I/O, renderer adapter, post-chain assembly | yes when dependencies exist |
| Visual | `visual` | fixed-seed frame and short-clip regressions | no |
| Slow/end-to-end | `slow` | full config-to-video render, cancellation, parallel workers | no |

The normal local command is:

```bash
pytest
```

Release verification includes:

```bash
pytest -m "integration or visual"
pytest -m slow
```

Tests requiring optional binaries must skip with a precise reason when the dependency is absent; they must not silently pass. CI should install and exercise the supported FFmpeg version.

### 14.2 Automated coverage

- timeline schema/default/migration tests;
- invalid enum, path, scene range, binding, and effect validation tests;
- audio cache fingerprint and stale-cache tests;
- template inheritance, cycle detection, merge, and expansion tests;
- feature normalization, interpolation, impulse preservation, and envelope tests;
- renderer adapter tests using small frames and fixed seeds;
- exact frame-count and audio-duration tests at awkward scene boundaries;
- deterministic frame hash tests for a pinned environment;
- post-chain ordering tests;
- interrupted render and atomic-output tests;
- JSON load/resolve/write round-trip tests preserving unknown metadata where safe.

Use generated audio fixtures for most tests so the suite does not depend on licensed music or network access. Fixtures should include silence, isolated low/mid/high tones, impulses at frame boundaries, a tempo-stable synthetic song, odd durations, and malformed/empty inputs. `ref/audioReactive/make_test_track.py` is the starting reference for the synthetic song fixture.

Production modules should maintain at least 85% statement coverage overall. Critical deterministic modules—timeline resolution, validation, signal binding, frame scheduling, and template expansion—target 95% or higher. Coverage is a guardrail, not a substitute for behavioral assertions or visual review.

### 14.3 Visual regression set

Maintain small reference renders covering:

- each palette;
- each 3D look;
- each camera;
- 2D and 3D cores;
- zero, low, and peak values for each public audio parameter;
- representative combined signals;
- preview versus final quality at matching frame times.

Pixel-perfect thresholds may vary for OpenCV/FFmpeg version differences; use perceptual comparison where exact hashes are not portable.

Each visual fixture records the config, resolved seed, exact frame time/range, renderer revision, resolution, and dependency versions. Exact hashes are used inside the pinned CI environment. A perceptual image metric with an explicit threshold is used for supported environment variation. Updating a golden fixture requires an intentional review and a commit explaining the visual change; tests must never rewrite goldens automatically.

### 14.4 End-to-end and synchronization tests

At minimum, end-to-end tests verify:

- `render CONFIG` creates a playable file with the requested streams and dimensions;
- video frame count equals the resolved schedule exactly;
- muxed audio begins at the correct source timestamp and stays within one output frame of the video duration;
- awkward fractional scene boundaries do not create gaps, duplicate frames, or cumulative drift;
- one-worker and multi-worker renders produce the same ordered frame sequence;
- cache hit and cache miss renders produce equivalent signals and frames;
- a failed or cancelled render does not replace an existing valid output;
- resolved profiles can reproduce the render plan without the original template catalog.

The short generated track is the mandatory smoke test. A longer multi-scene render is a release test, not part of every local test run.

### 14.5 Static and style checks

All production Python is type-checked and linted in addition to runtime tests. The project should configure tools so they do not rewrite or reject the required mastergray/CTG conventions. In particular, PEP-8 naming rules must not override the required camelCase method convention.

A small repository-owned AST/style check should enforce conventions that general-purpose formatters do not understand:

- no module docstrings in production modules;
- an explanatory comment on each import;
- type annotations on every parameter and return value;
- the required signature comment immediately associated with every method;
- class member ordering and section headers;
- leading underscores on instance attributes;
- camelCase methods and `UPPERCASE_WITH_UNDERSCORES` constants.

`ref/` is immutable reference material and is excluded from production style, type, and coverage gates. Test code follows the same naming and typing rules where compatible with pytest discovery; test methods/functions use a `test...` camelCase prefix.

### 14.6 Version 1 acceptance criteria

Version 1 is complete when a user can:

1. copy a supplied JSON template, change its audio path, and render a complete audio-reactive video with one command;
2. validate, resolve, and inspect available template/look/camera/effect IDs entirely through the CLI;
3. configure palette, look, camera, and reactivity without changing Python;
4. render a multi-scene 1080p video with synchronized original audio;
5. use at least one scene-level and one global post effect;
6. reproduce the same render from the resolved profile and pinned inputs;
7. receive clear validation errors before expensive rendering begins.

## 15. Delivery phases

### Phase 0 — renderer extraction and baseline

- Move the reference renderer into an importable production package.
- Preserve `ref/` outputs as visual regression fixtures.
- Add version metadata, typed configuration, and a minimal adapter.
- Benchmark stills and clips across preview/draft/final settings.

Phases 0 through 3 constitute version 1. Phase 4 is explicitly outside the first release.

### Phase 1 — audio-reactive headless renderer

- Implement the feature cache and sampler.
- Map analyzed signals into `Params`.
- Define and validate timeline v1.
- Render one scene and then multiple hard-cut scenes from the CLI.
- Mux audio and write resolved profiles/manifests.
- Ship minimal and representative JSON config templates plus JSON Schema.

### Phase 2 — post ecosystem and robustness

- Port and audit selected Glitzle glitch/post/FFmpeg effects.
- Add range/preview renders, global post, cancellation, conservative parallel rendering, and recovery behavior.
- Complete visual regressions and duration/sync tests.

### Phase 3 — effects and native desktop authoring

- implement the typed, ordered scene and global effect registry;
- expose effect metadata and parameters to both CLI and desktop UI;
- build the PySide6/Qt project window, waveform, hard-cut scene timeline, and inspectors;
- add cancellable playhead stills and selected-range preview renders;
- launch final and per-scene exports through the shared render pipeline.

### Phase 4 — advanced authoring

- keyframes and automation lanes;
- audio-bound post-effect properties;
- user-defined reactivity presets;
- renderer plug-ins or additional base generators;

## 16. Initial implementation decisions

The following decisions are accepted for the initial build:

1. Use Python for orchestration, analysis, rendering, and the CLI.
2. Use PySide6/Qt for the native desktop authoring surface. Do not build a browser frontend, embedded webview, JavaScript UI, or local web server.
3. Use timeline JSON plus a separate NPZ audio-feature cache.
4. Default to 1920×1080 at 30 fps; preserve arbitrary even dimensions and common frame rates.
5. Default animation time to global song time, with a per-scene restart option.
6. Use hard cuts between scenes; transitions are not part of the authoring model.
7. Port a curated, tested subset of Glitzle's post catalog rather than all recipes at once.
8. Treat `ref/` as the baseline and create a production-owned renderer package.
9. Design the default templates for 16:9 landscape while continuing to accept arbitrary even dimensions.
10. Default to automatic look/camera choreography and allow explicit scene-level overrides.
11. Enable the HUD by default and expose a scene-level setting to disable it.
12. Begin with owned Python post filters and a small audited glitch subset; defer the broad FFmpeg recipe catalog.
13. Require a fixed seed for final renders and guarantee repeatability on the pinned local software stack. Cross-machine pixel identity is not a v1 requirement.
14. Make the first implementation checkpoint a deterministic 3–5 second low-resolution render from one JSON config with synchronized generated audio.
15. Keep JSON as the canonical project format and share resolver, validation, preview, render, and effect services between the desktop application and CLI.

## 17. Engineering and repository standards

### 17.1 Python code style

The canonical Python style is:

`/home/mastergray/claymoretechgroup/github/projects/ctg-spec-ops/code-styles/python-code-style.md`

It is binding for new production Python even though the project is personal rather than a CTG organization repository. Key nonstandard requirements include camelCase methods, underscore-prefixed camelCase instance attributes, class-section ordering, a class factory named `init` where applicable, no module docstrings, commented imports, complete Python type hints, and Hindley–Milner-inspired signature comments for every method.

The project's actual runtime target is Python 3.8.10. Where the canonical document specifies Python 3.10-only annotation syntax, Metalheart preserves the rule's intent with Python 3.8-compatible `typing.List`, `typing.Dict`, `typing.Optional`, `typing.Union`, and related forms. Runtime compatibility takes precedence over the guide's syntax examples; its naming, organization, documentation, and full-typing requirements still apply.

The repository keeps a short local enforcement guide and an `AGENTS.md` pointer, but does not fork the canonical rules. If the external canonical document changes, changes are reviewed before the project's tooling or code is updated.

### 17.2 Git and GitHub practices

Repository setup adapts:

`/home/mastergray/aleph-null-media/prompts/ctg-github-practices.md`

for the personal `mastergray` account:

- initialize locally with `main` as the default branch;
- set repository-local identity to `mastergray <me@mastergray.com>` without changing global Git configuration;
- use the baseline AI, OS, IDE, log, and Python exclusions in `.gitignore`;
- use short commit summaries, an optional blank line plus details, and no automated `Co-Authored-By` trailers;
- do not configure a remote until the GitHub repository exists;
- when it exists, use the personal SSH alias and URL form `git@github-mastergray:mastergray/<repo-name>.git`;
- verify local author identity, branch, status, and remote URL before the first push;
- push with `git push -u origin main` only after the remote is deliberately configured.

The project must not create a GitHub repository or infer its eventual remote name as part of local bootstrap.
