# Metalheart Studio Roadmap

Status: active implementation roadmap, 2026-09-28

This roadmap covers the visual system, ordered effects, and native authoring application. JSON remains canonical and the renderer remains headless-capable, but the product includes a PySide6/Qt desktop UI for previewing and producing visuals. Each visual milestone begins with a small study and an agreed configuration contract.

## Product direction

Metalheart should support rough, authored, audio-reactive imagery without converging on a polished Blender-like render. The intended direction is PSX-inspired rather than an exact emulation of PlayStation hardware: visible texels, stepped lighting, controlled projection instability, faceted or jagged forms, and deliberate color reduction should be available without forcing every scene into the same treatment.

The following rules apply across the roadmap:

- JSON remains the canonical project and interchange format, not the only authoring surface.
- The interactive interface is native PySide6/Qt. Browser frontends, embedded webviews, JavaScript UI stacks, and local web servers are excluded.
- The image is the base color for a skinned element. Palettes may light the surrounding scene but must not recolor the image.
- Visual roughness is opt-in and deterministic for a fixed seed.
- Audio sources remain factual signals such as amplitude, bands, centroid, beats, and onsets. No sentiment inference is introduced.
- New controls use the typed reactivity system rather than arbitrary access to renderer internals.
- `ref/` remains immutable. New behavior belongs in production-owned adapters and effects.
- Existing JSON continues to resolve with its present appearance unless a new style or control is selected.

## Current baseline

| Area | Current behavior | Important limitation |
| --- | --- | --- |
| Form skins | A config-relative image replaces the 3D core color through object-space triplanar projection. `metallic` and `matte` lighting plus optional nearest sampling, texture-coordinate steps, and lighting steps are supported. | The PSX treatment is surface-only. Skins do not apply to ribbons or plates, and faceted normals and color-depth reduction are not yet supported. |
| Forms | Reference forms plus the audio-driven `resonance` and `radial` forms are supported. Radial has opt-in faceting, object-space jaggedness, and continuous geometric steps. | Form styling currently targets Radial; it is not yet shared by reference forms or Resonance. |
| Background | A public per-scene block selects the procedural palette or a fitted image, controls dots/ghosts/shadow, and exposes isolated pulse and spectrum-directed ripple systems. Image backgrounds can behave as flat, matte, or metallic 2.5D sheets. | The first slice is 3D-only and does not yet include drift, color reduction, dithering, or general background warp/offset destinations. |
| Ribbons and plates | The 3D decor block independently controls ribbon and plate enablement, counts, seed, materials, local-coordinate skins, and six typed audio destinations. Legacy booleans retain the reference behavior. | The first-class object is 3D-only; topology beyond count and additional plate/ribbon shape controls are not yet public. |
| Retro finishing | Grain, scanlines, chroma offsets, slice glitches, bloom, streaks, flash, and vignette are configurable. | There is no coherent PSX-style preset, nearest-neighbor upscale, color quantization, or ordered dithering. |

## Milestone 1: PSX-inspired texture and finish language (in progress)

The first controlled study uses the same audio, form, camera, source image, and frame times to compare the smooth baseline with a deliberately rough surface treatment.

Implemented surface controls:

- nearest-neighbor texture sampling as an alternative to bilinear filtering;
- quantized texture coordinates, stable enough to avoid random shimmer;
- stepped rather than continuous lighting.

Remaining candidate surface controls:

- faceted normal shading independent of silhouette changes;
- configurable texture resolution or texel density;
- optional texture color-depth reduction.

Candidate whole-frame finishing controls:

- render at a lower internal resolution and upscale with nearest-neighbor sampling;
- RGB level reduction;
- ordered dithering, beginning with a stable Bayer pattern;
- optional frame-rate stepping that repeats rendered frames without changing audio synchronization.

The surface treatment and whole-frame finish should be separable. A scene may use a PSX-like image on a clean background, or apply a retro finish to the complete composition. A named preset may expand to ordinary resolved values, but every constituent control must remain directly authorable.

Acceptance criteria:

- the image remains recognizable and retains its own colors;
- texels and lighting steps remain visible at draft and final output sizes;
- effects are deterministic and do not create uncontrolled temporal noise;
- `metallic` and `matte` remain available outside the PSX treatment;
- a no-effect configuration is frame-equivalent to the current baseline;
- visual fixtures cover surface-only, finish-only, and combined treatments.

## Milestone 2: Configurable jagged and faceted forms (Radial slice implemented)

Add a form-style layer without creating a new explicit heart form. The first Radial study distinguishes three different ideas that are not collapsed into one slider:

1. **Faceting** quantizes normals or spatial directions, changing how broad planes catch light.
2. **Jaggedness** displaces the silhouette with deterministic object-space noise.
3. **Geometric stepping** quantizes portions of the deformation field for harder transitions.

Controls should include magnitude and scale, with conservative bounds that keep sphere tracing stable. Jaggedness must be anchored in object space so it follows the form rather than swimming across it. Audio-reactive destinations may then modulate the bounded amounts—for example, amplitude controlling jaggedness magnitude, centroid controlling roughness scale, and onsets briefly hardening facets.

Acceptance criteria:

- the completed first slice works on Radial; later generalization covers Mercury and Resonance;
- changes affect the form visibly at a fixed camera;
- audio modulation can be isolated from time-based motion in a test render;
- silhouettes do not develop persistent holes, missing ray hits, or explosive spikes;
- a fixed seed produces stable spatial detail and repeatable frames;
- performance cost is measured at preview, draft, and final quality.

## Milestone 3: First-class backgrounds (first slice implemented)

The implemented per-scene `background` object supports:

- `palette`, preserving the current procedural background;
- `image`, in which a config-relative image replaces the palette gradient;
- image fit modes such as `cover`, `contain`, and `tile`;
- scale, rotation, offset, and opacity;
- independent enabling of the dot field, foreground ghosts, and drop shadow;
- a bounded `background_pulse` that changes background brightness and scale without pulsing the foreground form;
- spectrum-directed surface displacement, UV bending, reconstructed normals, and neutral matte or metallic relighting;
- separate amplitude, spectral-scale, and transient-impact ripple destinations.

Slow drift, deterministic color reduction and dithering, background warp/offset destinations, and non-3D composition remain future work.

The bounded `background_pulse` provides global background brightness and scale. The separate ripple system provides meaningfully different local deformation and relighting. Both use the existing reactivity binding model, so a scene can map amplitude, spectral centroid, beats, or onsets explicitly without affecting the foreground form.

Provisional authoring shape:

```json
{
  "background": {
    "source": "image",
    "image": "./assets/background.png",
    "fit": "cover",
    "scale": 1.0,
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
    "ghosts": true,
    "shadow": true
  },
  "reactivity": {
    "modulators": {
      "background_ripple": {
        "source": "amplitude",
        "amount": 1.0,
        "clamp": [0.0, 1.0]
      }
    }
  }
}
```

This shape is part of the version 1 schema. The full object additionally exposes rotation, offset, pulse brightness, pulse scale, pulse center, the dot-field switch, and typed ripple scale and impact mappings.

Layer order should be explicit and tested: base background or image, background-only modulation, optional ghosts and shadow, foreground geometry, whole-frame finishing, then overlays.

Acceptance criteria:

- the image path is resolved and fingerprinted like form skins;
- a zero signal exactly preserves the authored background state;
- pulse and spectrum-ripple tests change background pixels while keeping isolated foreground pixels stable;
- fit modes behave consistently across aspect ratios;
- disabling overlays still guarantees no text;
- background skins do not implicitly recolor form or ribbon skins.

## Milestone 4: Make ribbons and plates first-class (first slice implemented)

The all-or-nothing `decor` concept now resolves to separately authorable ribbon and plate settings while preserving `decor: true|false` as migration shorthand.

Provisional direction:

```json
{
  "decor": {
    "enabled": true,
    "ribbons": {
      "enabled": true,
      "count": 4,
      "material": "matte",
      "surface": {
        "image": "./assets/ribbon.png",
        "mapping": "ribbon"
      }
    },
    "plates": {
      "enabled": false
    }
  }
}
```

This shape is part of the version 1 schema. Ribbon images use ribbon-local coordinates along length and twisted width rather than reusing core triplanar projection, so an image bends and twists with the ribbon instead of appearing projected through it. Plates use planar local coordinates. Both share the established `metallic`, `matte`, nearest-sampling, texel-step, and lighting-step vocabulary.

The previous hard-wired audio response is preserved when no explicit decor destinations are present. Authors can override it through `ribbon_width`, `ribbon_twist`, `ribbon_wave`, `ribbon_speed`, `plate_orbit`, and `plate_displacement`. Counts remain scene configuration rather than per-frame audio destinations, avoiding geometry that pops in and out.

Acceptance criteria:

- ribbons and plates can be enabled independently;
- authored counts and seeds resolve deterministically;
- a ribbon texture follows twisting geometry without obvious world-space sliding;
- ribbon and plate materials do not inherit the core skin accidentally;
- explicit reactivity can reproduce the current subtle bass/mid behavior;
- disabling all decor avoids its raymarching and shading cost;
- legacy boolean `decor` configs remain valid.

## Milestone 5: Presets and multi-scene integration

After the individual systems are proven, add a small preset vocabulary composed only from public controls. Candidate presets may include a restrained textured PSX surface, a harsher dithered treatment, a jagged spectrum-driven form, a pulsing skinned background, and textured reactive ribbons. Presets should not silently change cameras, forms, palettes, or scene boundaries.

The integration render should use the existing 30-second audio clip and demonstrate clean scene boundaries between:

- a PSX-skinned smooth form;
- a jagged audio-driven form;
- a skinned background with isolated pulse;
- ribbons with an independent skin and explicit reactivity;
- one combined scene used to identify interactions and performance limits.

Multi-scene work uses hard cuts. Transition authoring is not planned. The implemented `--scene-clips` mode exports every scene as an independent, audio-synchronized clip without changing its scene-local form, background, ribbon, or plate image skins.

## Milestone 6: Ordered effects system (first slice implemented)

Replace the currently empty public effect catalog with typed, ordered scene and global effect chains. The existing fixed `finish` controls provide the first owned implementations but do not, by themselves, satisfy this milestone.

The implemented library owns Glitzle's configurable primitives, the complete 19-preset Glitzle Glitch category, five of seven Retro/CRT presets, a curated cross-category preset set, four Dazzle mirrors, Dazzle XOR, four-direction Ziti, four-direction VidGlitch-compatible Tetrys, Glitzle Studio's Glitch Maker chromatic aberration and pixel sort, finite-history Slitscan, and scanline corruption. Audited Glitchstation controls include the six-effect Color family, RGB Shift, Tear, Block Jitter, Rectangles, VHS, and Arcade; Blister, Randomize, and Handheld are deliberately excluded. Six visually distinct Glitch recipes carry featured metadata for the future Qt browser. Effects run deterministically inside render workers, support global and scene chains plus 3D background, form-surface, and ribbon chains, and expose typed metadata for the future Qt inspector. Material masks captured from the immutable ray marcher let spatial effects carry form and ribbon alpha without filtering unrelated layers or the final text overlay. Slitscan workers preroll their declared history window so parallel chunks remain continuous. External process integration, audited FFmpeg recipes, plate-scoped effects, and fully general audio-to-effect-property bindings remain subsequent slices.

The first catalog should expose audited versions of bloom, streaks, flash, chroma displacement, slice glitch, vignette, scanlines, and grain. Each effect declares its stable ID, display metadata, typed properties and ranges, determinism, temporal requirements, supported quality profiles, and estimated cost. Existing `finish` documents continue to resolve compatibly while new documents may author ordered effect instances with enable/bypass controls.

Effects use the same registry in schema generation, validation, `list effects`, rendering, and the desktop inspector. Audio-reactive effect parameters are supported through typed public destinations rather than arbitrary access to implementation fields.

Acceptance criteria:

- `list effects` returns the implemented catalog instead of an empty list;
- scene and global chains preserve authored order;
- background, form-surface, and ribbon chains remain isolated from one another;
- enable/bypass does not destroy effect settings;
- effect validation fails before rendering and reports the exact instance/property;
- fixed seed and inputs reproduce deterministic effects;
- temporal effects declare and test their frame-history behavior;
- legacy `finish` configurations retain their current appearance.

## Milestone 7: Native PySide6/Qt authoring application (audio-led slice implemented)

Build a native desktop application over the existing JSON contract and application services. It must not contain a webview or require an HTTP server.

The implemented authoring slice begins with audio selection and background analysis into phrase-aligned scenes. The primary workspace combines a cached-energy waveform/hard-cut timeline, scene navigation, an explicit production-backed still preview, and structured per-scene Form, Background, and Ribbons inspectors. Each layer has an independent ordered effect stack with catalog-generated controls for bypass, mix, order, and typed parameters. Canonical JSON is an optional advanced dock rather than the primary workflow.

Analysis, preview, and full export run outside the GUI thread and support cancellation. Preview work is explicit and capped at 480×270, 12 fps, 0.2 core scale, and no antialiasing for older hardware. PySide6 6.4 through 6.6 retains the Python 3.8 runtime target and is a normal application dependency.

The remaining vertical-slice work includes:

- timeline boundary editing;
- structured controls for plates, overlay items, and custom reactivity bindings;
- a cancellable selected-range video preview;
- explicit preview/final quality selection and per-scene export actions with detailed progress.

The UI must call the same resolver, validator, analyzer, effect registry, and render pipeline as the CLI. Widget state is never an alternative project format. Long analysis, preview, and render operations run outside the Qt UI thread and support cancellation. Full-resolution real-time ray-marched playback is not required.

Acceptance criteria:

- a CLI-authored project opens and round-trips without semantic changes;
- a UI-authored project validates and renders through the CLI;
- changing a scene invalidates only relevant preview artifacts;
- preview timing selects the same scene and audio features as a final render at that timestamp;
- render progress never blocks or freezes the UI event loop;
- invalid controls are identified before expensive preview or render work;
- no browser, webview, JavaScript runtime, or local server is introduced.

## Milestone 8: Authoring ergonomics and visual discovery

This milestone incorporates the first hands-on feedback from the audio-led desktop workflow. Work proceeds in dependency order so later controls inherit consistent editing behavior rather than introducing separate state systems.

1. **Implemented:** project-level Undo and Redo for authored content changes. Scene controls, image choices, effect add/remove/reorder/bypass, effect parameters, and applied Advanced JSON share one canonical snapshot history. Opening, saving, analysis, preview, and rendering remain lifecycle operations rather than undoable content edits. Saving establishes the clean history point.
2. **Implemented:** numeric effect parameters and Mix use a combined slider and directly editable number field generated from catalog minimum, maximum, step, and type metadata. Slider drags update the number continuously but commit once on release so project history remains useful; direct entry preserves precise values.
3. **Implemented:** each effect-stack row has a visible native enable checkbox. Bypassed instances stay in their authored position with a dimmed label and retain their mix and typed parameters; toggles are layer-local canonical edits covered by project Undo and Redo.
4. Publish determinate analysis and render progress, including current scene or chunk, completed and total frames, elapsed time, and an estimated remaining duration where enough samples exist.
5. Add independent stable palette selection for form, palette-based background, and ribbons. The public contract should use `renderer.palette`, `background.palette`, and `renderer.decor.ribbons.palette` rather than silently sharing one value.
6. Audit Dazzle palette sources and adapt a curated set as stable Metalheart catalog entries with deterministic rendering tests.
7. Generate versioned low-resolution option thumbnails from a fixed fixture for forms, cameras, palettes, and effects. The UI may display these in selector popovers without invoking the 3D renderer during ordinary navigation.

Acceptance criteria:

- Undo and Redo restore the canonical authored document, structured controls, validation state, dirty marker, and preview-invalidated state together.
- Layer-local history never moves an effect or palette change into another layer or scene.
- Numeric controls retain precise keyboard entry in addition to fast slider adjustment.
- A bypassed effect remains in its authored order with all parameters intact.
- palette ownership is explicit in resolved profiles and backward-compatible documents retain their current appearance;
- progress never blocks the Qt event loop and cancellation remains scoped to the active task;
- preview thumbnails declare the renderer/catalog version used to generate them and do not become a second rendering contract.

## Test and review requirements

Every milestone requires more than confirming that a render completes:

- schema, default, enum, path, and backward-compatibility tests;
- unit tests proving each audio destination responds to its chosen signal;
- zero/low/peak signal comparisons with fixed time, seed, camera, and form;
- deterministic render and image-fingerprint tests;
- matched-frame visual studies at preview, draft, and final resolution;
- perceptual regression fixtures for approved looks;
- playable-output checks for dimensions, frame count, duration, and audio sync;
- performance measurements, particularly for jagged SDFs and decorated 3D scenes.

Visual studies should have no overlays unless text is specifically under test. Review artifacts must state their grid ordering or use filenames that make each variant unambiguous.

## Recommended sequence

1. Define and implement the typed ordered-effects contract, beginning with the existing finishing controls.
2. Build the PySide6 audio-led application slice: create from audio, select a scene on the waveform, edit layer controls and effects, preview a still, save, and render.
3. Expand the scene inspector to the full public renderer and reactivity vocabulary.
4. Add waveform boundary editing, effect reordering, final export, and per-scene export.
5. Add scene-aware preview caching and incremental final-render reuse.
6. Complete the remaining PSX finish candidates and reusable presets through the same effect/UI contracts.

This sequence proves the effects and UI architecture early while keeping the tested headless renderer and canonical JSON contract intact.
