# NAI API and Face Detailer Feature Gap Report

Date: 2026-05-07
Branch: Add_facedetail

## Current Implementation

### API Transport

- `nai_api.post_nai()` sends JSON to `https://image.novelai.net/ai/generate-image` by default.
- It uses a shared `requests.Session`.
- It retries once after a 60 second sleep for HTTP 429.
- It expects NovelAI image responses to be ZIP files and reads the first ZIP member as PNG.
- Token lookup currently uses `NAI_ACCESS_TOKEN`.

### Generation Nodes

Implemented generation surface:

- Text-to-image: `action = generate`
- Image-to-image: `action = img2img`
- Inpaint: `action = infill`, with `model_id + "-inpainting"`
- Upscale: `https://api.novelai.net/ai/upscale`
- V4/V4.5 multi-character prompt payload for text-to-image, image-to-image, and inpaint (not FaceDetailer)
- Metadata-preserving autosave for generated PNG payloads
- Face Detailer autosave under `NAI_autosave/face`

Common exposed generation parameters:

- `model`
- `width`
- `height`
- `sampler`
- `steps`
- `cfg_scale`
- `seed`
- `scheduler`
- `cfg_rescale`
- `prefer_brownian`
- `strength` for image-to-image and inpaint

Sealed internal parameters (not exposed, intentional policy):

- `n_samples = 1` — deliberate policy; ComfyUI batching is handled outside the NAI request for this node set
- `params_version = 3`
- `legacy = False`
- `add_original_image = True` for inpaint

User-controllable parameters added in this branch:

- `scheduler` — full list: native, karras, exponential, polyexponential
- `noise` — exposed for img2img and inpaint (inpaint default 0)
- `variety_boost` — controls `skip_cfg_above_sigma` (58 for V4.5, 19 for V4); user can disable

Face Detailer intentionally follows original first-face crop-paste flow. It does not expose `face_index`, `max_faces`, `target_long_side`, `blend_with_mask`, `noise`, `cfg_rescale`, `prefer_brownian`, or `variety_boost`. These parameters are fixed internally: longest-side target is 1024 px, API noise is 0, cfg_rescale is 0.0, prefer_brownian is false, variety_boost is true.

## Face Detailer Flow

The Face Detailer is a local pipeline wrapped around NovelAI inpaint:

1. Detect face bboxes with an Impact Pack `BBOX_DETECTOR`.
2. Use the first detected face only (`segs[1][0]`).
3. Crop the detector crop region from the input image.
4. Resize the crop so its longest side is 1024 px, snapped to a multiple of 64.
5. Run SAM on the resized crop using the face bbox.
6. Optionally add eye detector crop regions to the mask.
7. Convert the SAM mask into 32 px grid boxes with 8 px stride.
8. Send the resized crop and generated mask to NovelAI inpaint.
9. Downscale the full inpaint result to the original crop size.
10. Paste the downscaled result directly over the original crop region (no mask blending).
11. Save the composited output to `NAI_autosave/face`, preserving text metadata from the NAI inpaint result.

## Confirmed Gaps

### High Priority

1. Add Quality Tags is missing.

   NovelAI exposes an automatic quality preamble toggle. The node has no `add_quality_tags` control and does not emulate the documented model-specific quality tags.

2. Undesired Content presets are missing.

   The node only accepts raw `negative_prompt`. It does not expose model-specific UC presets such as Heavy, Light, Human Focus, or Furry Focus.

3. Decrisper is missing.

   NovelAI documents Decrisper as a guidance-related toggle. The current node exposes `cfg_rescale`, but has no explicit `dynamic_thresholding` or Decrisper toggle.

### Medium Priority

1. V4/V4.5 character controls are not available in Face Detailer.

   Text-to-image, Img2Img, and Inpaint all accept `characterPrompts`. Face Detailer does not expose it; it always sends empty `char_captions`.

2. V4 negative character controls are partially wired.

   `CharacterPromptSelect` collects per-character negative prompts, and txt2img sends them in `v4_negative_prompt`, but `use_coords` and `use_order` are hard-coded false for negative character captions.

3. `use_coords` and `use_order` are not user-configurable.

   The sample workflow from older node versions includes these as inputs, but the current node hard-codes them.

4. Sampler list may be incomplete.

   The code exposes seven samplers. This should be checked against the current NAI web payload before declaring complete.

5. Model list may be incomplete or stale over time.

   The code includes V4.5 Curated, V4.5 Full, V4 Full, V4 Curated Preview, V3, Furry V3, and V2. Model availability changes should be verified periodically against NovelAI.

### Lower Priority / Separate Nodes

1. Vibe Transfer is not implemented.

    NovelAI documentation lists Vibe Transfer as an image-generation topic. No node accepts vibe/reference images or reference strength style parameters.

2. Precise Reference is not implemented.

    NovelAI documents Character Reference, Style Reference, and Character & Style Reference for V4.5. No node accepts precise reference images, strength, or fidelity.

3. Director Tools are not implemented.

    Missing tool nodes include Remove Background, Line Art, Sketch, Colorize, Emotion, and Declutter.

4. Enhance is not implemented as a dedicated node.

    NovelAI documents Enhance as a separate workflow. This repo has upscaling, but not a dedicated enhance action.

5. Prompt Randomizer and Prompt Chunks are not implemented.

    These are documented UI features, but the repo currently focuses on prompt conversion and generation calls.

6. Text Rendering helper controls are not implemented.

    V4.5 improves text rendering, but there is no dedicated helper node or template control for text prompt workflows.

7. Canvas workflow is not implemented.

    Current inpaint supports mask-based infill, but there is no broader canvas/outpaint-style workflow in the node surface.

## Face Detailer Specific Gaps

1. The mask is quantized into grid boxes.

   This may be intentional for NAI inpaint compatibility, but it can overpaint more area than the SAM mask. There is no mode for raw SAM mask, box mask, or blended mask.

2. Metadata on Face Detailer output is copied from the inpaint crop result.

   This preserves NAI text metadata, but the saved composite does not add local crop/mask/face-detail provenance fields.

3. Only the first detected face is processed.

   Face Detailer always uses `segs[1][0]`. Multi-face processing, face index selection, and area/confidence sorting are intentionally not exposed in order to preserve original behavior.

## Suggested Implementation Order

1. Expose remaining missing scalar controls:
   `dynamic_thresholding`, `add_quality_tags`, and `uc_preset`. Optionally add a numeric `skip_cfg_above_sigma` override for advanced users who need a specific threshold (base `skip_cfg` behavior is already covered by `variety_boost`).

2. Continue Face Detailer quality controls:
   add mask mode selection, detector sorting modes, and optional local provenance metadata.

3. Add reference-image features as separate nodes:
   start with Precise Reference for V4.5, then Vibe Transfer after the payload shape is confirmed.

4. Add Director Tool nodes separately:
   Remove Background, Line Art, Sketch, Colorize, Emotion, Declutter. These likely need endpoint/payload confirmation from live web UI traffic or a maintained client library.

## Verification Needed Before Implementation

The public NovelAI docs confirm the feature surface, but not every API payload key. Before implementing features that are not already present in this repo, verify the exact JSON fields from one of these sources:

- Current NovelAI web app network payloads from the browser devtools.
- A maintained NovelAI API client that already supports V4.5 reference/director features.
- A small live API probe with known-safe inputs and explicit error capture.
