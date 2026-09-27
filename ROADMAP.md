# Metalheart Studio Roadmap

Status: planning baseline, 2026-09-26

This roadmap covers the next visual-system work after image-skinned 3D forms. It is intentionally JSON-first and headless. It does not authorize implementation by itself; each milestone begins with a small visual study and an agreed configuration contract.

## Product direction

Metalheart should support rough, authored, audio-reactive imagery without converging on a polished Blender-like render. The intended direction is PSX-inspired rather than an exact emulation of PlayStation hardware: visible texels, stepped lighting, controlled projection instability, faceted or jagged forms, and deliberate color reduction should be available without forcing every scene into the same treatment.

The following rules apply across the roadmap:

- JSON remains the complete authoring surface; no browser or UI work is planned yet.
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
| Background | The reference renderer builds a palette gradient with moving procedural noise, a dot field, blurred foreground ghosts, and a drop shadow. | There is no public `background` block, image skin, or dedicated audio-reactive background destination. The global onset flash is not a background-only pulse. |
| Ribbons and plates | `decor: true` creates seeded ribbons and plates. In 3D, bass subtly widens ribbons and moves plates while mid energy changes ribbon twist speed. | Ribbons and plates are bundled behind one boolean. Counts, materials, skins, motion, and reactivity are not independently authorable. |
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

## Milestone 3: First-class backgrounds

Introduce a per-scene `background` object instead of exposing reference-renderer fields directly. The first version should support:

- `palette`, preserving the current procedural background;
- `image`, in which a config-relative image replaces the palette gradient;
- image fit modes such as `cover`, `contain`, and `tile`;
- scale, rotation, offset, opacity, and optional slow drift;
- independent enabling of the dot field, foreground ghosts, and drop shadow;
- the same deterministic color-reduction and dithering vocabulary used by the PSX work where applicable.

The initial audio-reactive destination should be a bounded `background_pulse`. It should change background brightness and/or scale around a configurable center without pulsing the foreground form. Additional destinations can follow only if they produce meaningfully different results, such as background warp or image offset. They must use the existing reactivity binding model so a scene can map amplitude, a frequency band, beats, or onsets explicitly.

Provisional authoring shape:

```json
{
  "background": {
    "source": "image",
    "image": "./assets/background.png",
    "fit": "cover",
    "scale": 1.0,
    "opacity": 1.0,
    "ghosts": true,
    "shadow": true
  },
  "reactivity": {
    "modulators": {
      "background_pulse": {
        "source": "bass",
        "amount": 0.2,
        "clamp": [0.0, 0.2]
      }
    }
  }
}
```

This shape is a proposal, not yet a stable schema.

Layer order should be explicit and tested: base background or image, background-only modulation, optional ghosts and shadow, foreground geometry, whole-frame finishing, then overlays.

Acceptance criteria:

- the image path is resolved and fingerprinted like form skins;
- a zero signal exactly preserves the authored background state;
- pulse tests change background pixels while keeping isolated foreground pixels stable;
- fit modes behave consistently across aspect ratios;
- disabling overlays still guarantees no text;
- background skins do not implicitly recolor form or ribbon skins.

## Milestone 4: Make ribbons and plates first-class

Replace the all-or-nothing `decor` concept with separately authorable ribbon and plate settings while preserving `decor: true|false` as migration shorthand.

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

This shape is also provisional. Ribbon images should use ribbon-local coordinates along length and width rather than reusing core triplanar projection; that lets an image bend and twist with the ribbon instead of appearing projected through it. Plates can use planar local coordinates. Both should share the established `metallic`, `matte`, and later PSX-style material vocabulary.

The current hard-wired audio response should be made explicit through typed destinations. The first useful set is likely ribbon width, twist, wave amplitude, and motion speed. Plate orbit or displacement may follow. Counts and topology should remain scene configuration, not per-frame audio destinations, to avoid popping geometry in and out.

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

1. Produce the Milestone 1 surface-only visual study and choose the minimum PSX control set.
2. Stabilize that schema and its tests before combining it with new geometry.
3. Prototype faceting and jaggedness separately, then approve their audio mappings.
4. Add the background contract and isolated pulse before extending skins to other geometry.
5. Split ribbons from plates, add local-coordinate skins, and expose their existing audio behavior.
6. Build the 30-second integration render only after the isolated fixtures pass.

This sequence keeps each visual decision independently reviewable and avoids hiding a texture, geometry, background, or reactivity problem inside a heavily combined render.
