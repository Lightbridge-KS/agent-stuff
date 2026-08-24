# Prompting gpt-image-2

Distilled from the [GPT Image Models Prompting Guide](https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide) (fetched 2026-08-24).

## Fundamentals

- **Order**: background/scene → subject → key details → constraints. Name the intended
  use ("ad", "UI mock", "infographic") — it sets the polish mode. For complex requests,
  short labeled segments beat one long paragraph.
- **Specificity**: be concrete about materials, shapes, textures, and the visual medium
  (photo, watercolor, 3D render). Add quality levers only when needed (*film grain*,
  *macro detail*).
- **Photorealism**: include the word "photorealistic" literally. "Real photograph",
  "35mm film", "iPhone photo" also steer; camera specs are read loosely — use them for
  look, not physics.
- **Composition**: specify framing (close-up / wide / top-down), angle (eye-level,
  low-angle), lighting/mood (soft diffuse, golden hour), and placement when layout
  matters ("logo top-right", "subject centered, negative space left").
- **People**: describe scale, body framing, gaze, and object interaction ("full body
  visible, feet included", "looking down at the book, not the camera").
- **Constraints**: state exclusions and invariants explicitly — "no watermark, no extra
  text, no logos"; for edits: **"change only X, keep everything else the same"**, and
  repeat the preserve-list every turn to stop drift (also: don't alter saturation,
  contrast, layout, camera angle, surrounding objects).
- **Text in images**: put literal text in **quotes** or ALL CAPS; specify font style,
  size, color, placement. Spell tricky words letter-by-letter. Use `medium`/`high`
  quality for small or dense text.
- **Transparent backgrounds**: pair `--background transparent` with png/webp; describe
  the subject as *isolated on a fully transparent background* and exclude scenery,
  solid backdrops, checkerboards, and shadows. On edits, repeat "preserve the
  transparent background".
- **Multi-image inputs**: reference each by index + description ("Image 1: product
  photo… Image 2: style reference…") and say how they interact ("apply Image 2's style
  to Image 1").
- **Iterate, don't overload**: clean base prompt, then single-change refinements
  ("make lighting warmer"). Re-specify critical details if they drift.

## Recipes

### §logo

Brand personality + use case, then ask for a clean original mark. Generate `-n 4`
variants at `medium`, pick by eye, refine the winner.

> Create an original, non-infringing logo for {company}, a {business}. The logo should
> feel {personality}. Use clean, vector-like shapes, a strong silhouette, and balanced
> negative space. Favor simplicity over detail so it reads clearly at small and large
> sizes. Flat design, minimal strokes, no gradients unless essential. Fully transparent
> background. Deliver a single centered logo with generous padding, clean alpha edges,
> and no solid backdrop, scenery, checkerboard, or watermark.

### §infographic

For explainers, labeled diagrams, timelines. Dense layouts or heavy in-image text →
`--quality high`. State audience and intent ("so a student understands X technically
and visually"). Verify every label's spelling on read-back.

### §photoreal

> Create a photorealistic candid photograph of {subject}. {Texture details: skin,
> materials, wear}. Shot like a 35mm film photograph, medium close-up at eye level,
> 50mm lens. Soft {lighting}, shallow depth of field, subtle film grain, natural color
> balance. The image should feel honest and unposed. No glamorization, no heavy retouching.

### §ui-mockup

Name the platform and frame ("mobile app UI in an iPhone frame"), list the sections in
order (header, list, cards, footer info), then style ("white background, subtle accent
colors, clear typography, minimal decoration — looks like a real, well-designed app").

### §slides

Describe one slide like a designer's spec: title (quoted), background, typography
("modern sans-serif like Inter"), each element as a bullet (diagram type, exact
numbers, footnotes, logo placeholder), then the anti-list ("avoid clip art, stock
photos, gradients, anything generic"). Portrait/landscape via `--size`.

### §product

Cutouts and mockups from a real photo → `edit`:

> Extract the product from the input image and isolate it on a fully transparent
> background. Output: centered product, crisp silhouette, no halos/fringing. Preserve
> product geometry and label legibility exactly. Do not add a solid backdrop,
> checkerboard, scenery, or shadow. Do not restyle the product.

### §marketing

Real text in-image: quote it verbatim and lock it down.

> Billboard text (EXACT, verbatim, no extra characters): "{copy}". Typography: bold
> sans-serif, high contrast, centered, clean kerning. Ensure text appears once and is
> perfectly legible. No watermarks, no logos.

### §multi-image

Compositing with several `-i` inputs — index everything, freeze the rest:

> Place the {subject} from the second image into the setting of image 1, {position}.
> Use the same style of lighting, composition and background. Do not change anything else.
