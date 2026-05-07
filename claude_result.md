# Build Result — Add_facedetail pass 5 (Face Detailer behavior restoration)

## Summary

Restored `NAIFaceDetailerNode` to original first-face crop-paste behavior. All behavior-changing additions from prior passes were removed from this node only; other nodes are unchanged.

## Changes

### `generators.py`
- Removed `face_index`, `max_faces`, `target_long_side`, `blend_with_mask` from INPUT_TYPES optional and `detail()` signature.
- Removed optional `noise`, `cfg_rescale`, `prefer_brownian`, `variety_boost` from INPUT_TYPES and signature.
- Node now uses `segs[1][0]` (first face only) instead of a multi-face loop.
- Target longest side is fixed at 1024 px (was a variable `target_long_side`).
- Paste behavior is now `out_img.paste(result_downscaled, (crx0, cry0))` — no mask blending (removed `blend_with_mask` branch and `ImageFilter.GaussianBlur`).
- `feather_radius` retained in signature/UI; comment added that it is not used by the original paste behavior.
- API parameters fixed: `cfg_rescale=0.0`, `prefer_brownian=False`, `noise=0`, `variety_boost=True` (hardcoded).
- Returns `(image, image)` when no face is detected (was `(image, pil_to_tensor(empty_mask))`).
- Removed unused `ImageFilter` import.
- Kept: autosave under `NAI_autosave/face`, `save_png_preserving_metadata` from NAI result, `get_model_id(model)`, shared `build_common_parameters`/`apply_v4_parameters`/`build_nai_payload` helpers, `n_samples` sealed at 1.

### `Readme.md`
- Rewrote Face Detailer section: removed rows for `face_index`, `max_faces`, `target_long_side`, `noise`, `cfg_rescale`, `prefer_brownian`, `variety_boost`, `blend_with_mask`; added behavior description; added all remaining required params; noted `feather_radius` is retained but not used.

### `docs/nai_feature_gap_report.md`
- Updated "Face Detailer now exposes" list to state it follows original first-face crop-paste flow and intentionally does not expose the removed controls.
- Updated Face Detailer Flow steps to reflect direct paste (no blending) and fixed 1024 px target.
- Updated gap item 3 to reflect single-face-only policy instead of face index selection.

## Files changed
- `generators.py`
- `Readme.md`
- `docs/nai_feature_gap_report.md`
- `claude_result.md`

## Commands run
```
python3 -m py_compile generators.py nai_api.py image_utils.py converters.py __init__.py scripts/converter_playtest.py
python3 scripts/converter_playtest.py > docs/converter_playtest_report.md
git diff --check
git status --short --branch
```

---

# Build Result — Add_facedetail pass 4 (n_samples sealed)

## Policy

`n_samples` is sealed at 1 and is not an exposed UI parameter. This is deliberate: ComfyUI batching must be handled outside the NAI request for this node set. The API may return a multi-file ZIP for `n_samples > 1`, but that path is not supported and is not planned.

## Changes

- `nai_api.py` — added inline comment on `"n_samples": 1` stating the policy reason
- `docs/nai_feature_gap_report.md` — reclassified `n_samples = 1` as deliberate sealed policy; removed "Batch generation count is not exposed" from Confirmed Gaps; removed `n_samples` from Suggested Implementation Order; updated report to reflect current implemented state (img2img/inpaint noise exposed, scheduler list expanded to 4 values, variety_boost user-controllable, characterPrompts in txt2img/img2img/inpaint but not FaceDetailer)
- `claude_result.md` — this section; removed old "n_samples not implemented / next recommended step" framing

## Files changed
- `nai_api.py`
- `docs/nai_feature_gap_report.md`
- `claude_result.md`

## Commands run
```
python3 -m py_compile generators.py nai_api.py image_utils.py converters.py __init__.py scripts/converter_playtest.py
python3 scripts/converter_playtest.py > docs/converter_playtest_report.md
git diff --check
git status --short --branch
```

---

# Build Result — Add_facedetail pass 3 (env var bugfix)

## Implemented

### `get_nai_token()` — dual env var support
`NAI_ACCESS_TOKEN` is checked first (backward-compatible); `NAI_API_TOKEN` is accepted as a fallback. Warning message now names both variables when neither is set.

### README — Configuration section
Corrected to recommend `NAI_ACCESS_TOKEN` (the canonical name the code actually reads) and document `NAI_API_TOKEN` as a compatibility fallback. Both the `.env` example and the free-text alternative line were updated.

### README — Face Detailer table
Added missing `variety_boost` row (was present in code, missing from docs).

## Files changed
- `nai_api.py` — `get_nai_token()` fallback logic and warning text
- `Readme.md` — Configuration section rewrite; Face Detailer table `variety_boost` row

## Commands run
```
python3 -m py_compile generators.py nai_api.py image_utils.py converters.py __init__.py scripts/converter_playtest.py
git diff --check
git status --short --branch
```

## Verification result
- All files compile without errors
- `git diff --check`: no whitespace issues
- `git status`: only expected modified/untracked files on branch `Add_facedetail`

---

# Build Result — Add_facedetail pass 2 (V4 CharacterPrompt parity)

## Implemented

### V4 CharacterPrompt parity — NAIImg2ImgNode and NAIInpaintNode

Both nodes were calling `apply_v4_parameters(parameters, model_id, prompt, negative_prompt)` without forwarding `characterPrompts`, while `NovelAIGenerator` already passed it. This pass closes that gap.

Changes per node:

| Node | Change |
|------|--------|
| `NAIImg2ImgNode` | Added `characterPrompts: ("LIST",)` to `optional` INPUT_TYPES |
| `NAIImg2ImgNode` | Added `characterPrompts=None` to `generate()` signature |
| `NAIImg2ImgNode` | Passes `characterPrompts` to `apply_v4_parameters()` |
| `NAIInpaintNode` | Added `characterPrompts: ("LIST",)` to `optional` INPUT_TYPES |
| `NAIInpaintNode` | Added `characterPrompts=None` to `generate()` signature |
| `NAIInpaintNode` | Passes `characterPrompts` to `apply_v4_parameters()` |

`apply_v4_parameters` already accepted `character_prompts=None` and forwarded it to `build_v4_prompt`, so no changes to `nai_api.py` were required.

`NAIFaceDetailerNode` left unchanged — face-prompt oriented; `characterPrompts` not added per scope instructions.

### README updates

Expanded previously stub-documented nodes (Img2Img, Inpaint) with full parameter tables:
- `scheduler` (list with all 4 values)
- `cfg_rescale`
- `prefer_brownian`
- `noise` (img2img and inpaint)
- `variety_boost`
- `characterPrompts` (V4/V4.5 only note)

Also added missing optional params to the `NovelAIGenerator` table (`scheduler`, `cfg_rescale`, `prefer_brownian`, `variety_boost`).

## Files changed
- `generators.py` — INPUT_TYPES and generate signatures for `NAIImg2ImgNode` and `NAIInpaintNode`
- `Readme.md` — expanded Img2Img, Inpaint, and Generator parameter tables

## Commands run
```
python3 -m py_compile generators.py nai_api.py image_utils.py converters.py __init__.py scripts/converter_playtest.py
git diff --check
git status --short --branch
```

## Verification result
- All files compile without errors
- `git diff --check`: no whitespace issues
- `git status`: only expected modified/untracked files on branch `Add_facedetail`

---

# Build Result — Add_facedetail pass 1 (stabilization)

## Implemented

> Current-state note: Face Detailer changes in this pass were superseded by pass 5. The current node keeps the original first-face crop-paste flow and does not expose the FaceDetailer-specific controls listed in this historical section.

### Bug fixes
- **NAIFaceDetailerNode**: Fixed `NameError` — `MODEL_ID_MAP` was referenced directly but not imported. Changed to `get_model_id(model)` which is imported from `nai_api`.

### Refactor completed — NAIFaceDetailerNode payload
Replaced 36-line inline payload dict (with duplicated skip_cfg_above_sigma logic and manual v4_prompt construction) with the shared helpers:
- `build_common_parameters()` — handles width/height/seed/sampler/steps/cfg_scale/negative_prompt/scheduler/cfg_rescale/prefer_brownian/variety_boost/model_id
- `parameters.update({...})` — adds image/mask/add_original_image/inpaintImg2ImgStrength/noise
- `apply_v4_parameters()` — conditionally adds v4_prompt/v4_negative_prompt/legacy_uc for v4 models
- `build_nai_payload()` — constructs final payload with inpainting model suffix

### New optional controls added
| Node | New param | Default | Notes |
|------|-----------|---------|-------|
| NovelAIGenerator | `variety_boost` | `True` | Controls `skip_cfg_above_sigma` (via `build_common_parameters`) |
| NAIImg2ImgNode | `noise` | `0.0` | Passed to NAI img2img parameters |
| NAIImg2ImgNode | `variety_boost` | `True` | Controls `skip_cfg_above_sigma` |
| NAIInpaintNode | `noise` | `0.0` | Was hardcoded `0`; now exposed |
| NAIInpaintNode | `variety_boost` | `True` | Controls `skip_cfg_above_sigma` |
| NAIFaceDetailerNode | `variety_boost` | `True` | Controls `skip_cfg_above_sigma` |

### Scheduler list
`SCHEDULER_LIST = ["native", "karras", "exponential", "polyexponential"]` — already present in `nai_api.py` and wired through all nodes via `SCHEDULER_LIST` import.

### Refactor boundaries confirmed
- `image_utils.py` — PIL/base64/tensor/metadata helpers only
- `nai_api.py` — NAI constants, token, post_nai, zip extraction, model IDs, samplers/schedulers, parameter builders, v4 prompt helpers, payload builder
- `generators.py` — ComfyUI node classes and FaceDetailer processing only; no inline NAI payload construction

### Preserved behaviors
- Generated PNG bytes written directly to autosave (metadata preserved)
- Face Detailer saves under `NAI_autosave/face/` with `save_png_preserving_metadata`
- Face Detailer returns `(image, mask_visualization)`
- All existing optional FaceDetailer controls remain: `face_index`, `max_faces`, `target_long_side`, `noise`, `cfg_rescale`, `prefer_brownian`, `blend_with_mask`
- `extra_noise_seed` now included in FaceDetailer calls (via `build_common_parameters`), aligning with other nodes
- `legacy_v3_extend: False` now included in FaceDetailer calls (via `build_common_parameters`), aligning with other nodes

## Files changed
- `generators.py` — all node INPUT_TYPES and generate/detail method signatures updated

## Known limitations

### Vibe Transfer / Precise Reference / Director Tools / Character Reference
Not implemented. Fields identified in `/tmp/NAIA2.0/core/generation_request.py`:
- Vibe Transfer: `reference_image_multiple`, `reference_information_extracted_multiple`, `reference_strength_multiple`
- Director Tools: `controlnet_condition`, `controlnet_strength`, `controlnet_model`
- Character Reference: per-character `reference_image` in `char_captions`
These are documented as future work only.

## Next recommended step
- Optionally expose `extra_noise_seed` as a separate optional INT input (currently always mirrors `seed`)
- Consider adding `legacy_uc` boolean for V3/V2 model compatibility
