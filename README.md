# ComfyUI_RS_NAI_API_Request

ComfyUI custom nodes for **NovelAI Diffusion V5 and earlier models**, supporting text-to-image generation, img2img, inpainting, multi-character prompts, and prompt-weight conversion.

The YOLO/SAM detailer can process multiple detected regions sequentially. An optional **PyTorch WD tagger** automatically matches each region to an original character prompt, preserving its character and series names. Tagger output is used only for matching and is never added to the generation prompt. The tagger requires no ONNX runtime and downloads its model automatically on first use after the optional dependencies are installed.

> Current version: **2.4.0**

## What's New in 2.4.0

- Added **NAI Diffusion V5 Full — Medium Effort** for generation, img2img, and inpainting.
- Medium Effort uses NovelAI's distilled checkpoints and always sends 14 steps, Euler Ancestral, zero CFG Rescale, and the fixed Heavy Undesired Content preset. The node ignores the steps, sampler, CFG Rescale, base negative prompt, and character negative prompts shown in an existing workflow while this model is selected.
- Medium Effort img2img remains blocked when `limit_opus_free=True`, like every request carrying a base image, because that mode can spend Anlas.
- `limit_opus_free=True` recognizes both Medium checkpoints, still verifies the V5 Opus allowance, and rejects a Medium payload whose fixed settings were changed before transport.

## What's New in 2.3.1

- Preserved the Vibe Transfer and Precise Reference inputs while allowing the Face Detailer to use Opus Focused Inpainting in `limit_opus_free` mode.
- `limit_opus_free` still rejects Vibe and Precise Reference before token access or Vibe encoding, because reference features can add Anlas charges.
- General img2img and inpainting remain blocked in strict mode; only the detailer's internally produced focused crops receive the narrowly validated exception.

## What's New in 2.3.0

- Added **NAI Vibe Transfer** and **NAI Precise Reference** image-input nodes with per-image settings and optional chaining.
- Added reference inputs to generation, img2img, inpainting, and detailer nodes, with model/process compatibility checked before requests.
- V4/V4.5 Vibe encodings are cached locally to avoid paying to encode the same image/settings again. Encoding uses the same serial request queue and two-second interval as generation.
- V5 does not currently support these features. Select a supported model explicitly; the extension does not change models to enable references.

## What's New in 2.2.1

- Character X/Y inputs now use **0.0–1.0 in 0.1 increments**, rounded to one decimal place and sent directly as normalized coordinates.
- Default positions are unchanged (for example, the old `3` is now `0.3`). When loading an older workflow, update saved coordinate values to the new range (`5` becomes `0.5`, `10` becomes `1.0`); the old 0–10 input scale is no longer used.

## What's New in 2.2.0

- Added `detail_mode=all` for sequential detailing of multiple detected regions; existing workflows keep the `first` default.
- Added automatic matching to original character prompts with the optional native PyTorch WD tagger. Tagger output is used only for matching and never added to generation prompts.
- Preserved the original API mask grid while compositing each region through its own mask.
- Serialized NovelAI requests with a minimum two-second delay after each HTTP attempt completes.
- Validated two-face processing with a real ComfyUI/YOLO/SAM/WD/NovelAI run and 39 regression tests. Exact four-eye detection and reliable expression preservation remain outside the verified coverage.

## What's New in 2.1.1

- Added NovelAI Diffusion V5 Curated and V5 Full model selection.
- V5 requests use `params_version: 4` while older models keep `params_version: 3`.
- V5 continues to use NovelAI's `v4_prompt` / `v4_negative_prompt` conditioning structure, including character prompts.
- V5 Full uses native V5 inpainting. V5 Curated follows NovelAI's current client fallback to V4.5 Curated inpainting.
- Autosaves are written under `output/<date>/NAI_autosave/`. A newly created nested folder may require refreshing the file browser or image feed before its first image appears in the listing.

## Features

- **Image references**: Vibe Transfer for supported V3/V4/V4.5 models, plus V4.5 Precise Reference for character and style guidance.
- **NovelAI generation**: Text-to-image, img2img, and inpainting with NAI Diffusion V5, V4.5, V4, V3, and supported Furry models.
- **Multi-character prompts**: Up to five character slots with separate positive/negative prompts and X/Y coordinates from 0.0 to 1.0 in 0.1 increments.
- **Multiple-region detailing**: YOLO detection, SAM masks, and sequential NAI inpainting, with masked compositing for overlapping crops. Select `detail_mode=all` to process multiple regions.
- **Automatic character matching**: An optional native PyTorch WD tagger selects the original character prompt for each region. Unclear matches are retried with a tighter crop and skipped if still ambiguous.
- **Controlled API requests**: Requests run sequentially, with at least two seconds after each HTTP attempt completes before the next begins.
- **Prompt-weight conversion**: Utilities for converting prompt-weight syntax between supported local formats and NovelAI.

## Installation

### Method 1: ComfyUI Manager (Recommended)
1. Open ComfyUI.
2. Click on **Manager** -> **Custom Nodes Manager**.
3. Search for `ComfyUI_RS_NAI_API_Request`.
4. Click **Install**.

### Method 2: Manual Installation
1. Navigate to your ComfyUI `custom_nodes` directory.
2. Clone this repository:
   ```bash
   git clone https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request.git
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration (API Token)

To use these nodes, you must provide your **NovelAI API Token**.

1. Create a `.env` file in the root of this custom node directory (`ComfyUI_RS_NAI_API_Request/.env`).
2. Add your token to the file using the canonical variable name:
   ```text
   NAI_ACCESS_TOKEN=your_api_token_here
   ```
   `NAI_API_TOKEN` is also accepted as a fallback for compatibility, but `NAI_ACCESS_TOKEN` is recommended.

Alternatively, you can set either variable as a system environment variable (`NAI_ACCESS_TOKEN` is checked first; `NAI_API_TOKEN` is checked if the first is absent).

## Nodes

### 1. NAI Image Generator (`NovelAIGenerator`)
Main node for text-to-image generation.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `prompt` | STRING | The main positive prompt. |
| `negative_prompt` | STRING | The main negative prompt. |
| `model` | LIST | NAI Model (V5, V4.5, V4, V3, etc.). |
| `width` / `height` | INT | Image dimensions (steps of 64). |
| `sampler` | LIST | Sampler (e.g., k_euler, k_dpmpp_2m). |
| `steps` | INT | Generation steps (1-50). |
| `cfg_scale` | FLOAT | Guidance scale. |
| `seed` | INT | Random seed (-1 for random). |
| `scheduler` | LIST (Optional) | Noise scheduler: `native`, `karras`, `exponential`, `polyexponential`. |
| `cfg_rescale` | FLOAT (Optional) | Prompt guidance rescale (0.0–1.0). |
| `prefer_brownian` | BOOLEAN (Optional) | Use brownian noise in sampler. |
| `variety_boost` | BOOLEAN (Optional) | Enable `skip_cfg_above_sigma` for more varied outputs (V4/V4.5). |
| `characterPrompts` | LIST (Optional) | Per-character prompts from `CharacterPromptSelect` (V4+ only). |
| `limit_opus_free` | BOOLEAN (Optional) | Require an active Opus subscription and Anlas-free text generation conditions; check V5 allowance before each request. Default: `True`. |

### 2. NAI Character Prompt Select (`CharacterPromptSelect`)
Defines up to 5 characters with spatial coordinates (0.0–1.0 scale) for NAI V4+.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `characterX` | STRING | Character specific prompt. |
| `characterX_uc` | STRING | Character specific negative prompt. |
| `characterX_x` / `y` | FLOAT | Center coordinates (0.0–1.0, step 0.1, one decimal place). |
| `characterX_enable`| BOOLEAN| Enable/Disable specific character slot. |

### 3. NAI Img2Img (`NAIImg2ImgNode`)
Performs image-to-image generation.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `image` | IMAGE | Source image. |
| `prompt` / `negative_prompt` | STRING | Positive / negative prompts. |
| `model` | LIST | NAI model selection. |
| `width` / `height` | INT | Output dimensions (steps of 64). |
| `sampler` | LIST | Sampler algorithm. |
| `steps` | INT | Generation steps (1–50). |
| `cfg_scale` | FLOAT | Guidance scale. |
| `strength` | FLOAT | Denoising strength (0.0–1.0). |
| `seed` | INT | Random seed (-1 for random). |
| `scheduler` | LIST (Optional) | Noise scheduler: `native`, `karras`, `exponential`, `polyexponential`. |
| `cfg_rescale` | FLOAT (Optional) | Prompt guidance rescale (0.0–1.0). |
| `prefer_brownian` | BOOLEAN (Optional) | Use brownian noise in sampler. |
| `noise` | FLOAT (Optional) | Extra noise added before sampling (0.0–1.0). |
| `variety_boost` | BOOLEAN (Optional) | Enable `skip_cfg_above_sigma` for more varied outputs (V4/V4.5). |
| `characterPrompts` | LIST (Optional) | Per-character prompts from `CharacterPromptSelect` (V4+ only). |
| `limit_opus_free` | BOOLEAN (Optional) | Blocks img2img while `True`, because a base image can cost Anlas. Set `False` to allow the paid request. Default: `True`. |

### 4. NAI Inpaint (`NAIInpaintNode`)
Specialized node for inpainting. Automatically snaps dimensions to 64px.

V5 Full uses its native V5 inpainting model. Until NovelAI releases V5 Curated inpainting, selecting V5 Curated follows the official client and uses V4.5 Curated inpainting.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `image` | IMAGE | Source image. |
| `mask` | MASK | Area to inpaint (white = repaint). |
| `prompt` / `negative_prompt` | STRING | Positive / negative prompts. |
| `model` | LIST | NAI model selection. |
| `width` / `height` | INT | Output dimensions (snapped to 64px). |
| `sampler` | LIST | Sampler algorithm. |
| `steps` | INT | Generation steps (1–50). |
| `cfg_scale` | FLOAT | Guidance scale. |
| `strength` | FLOAT | Inpainting strength (0.0–1.0). |
| `seed` | INT | Random seed (-1 for random). |
| `scheduler` | LIST (Optional) | Noise scheduler: `native`, `karras`, `exponential`, `polyexponential`. |
| `cfg_rescale` | FLOAT (Optional) | Prompt guidance rescale (0.0–1.0). |
| `prefer_brownian` | BOOLEAN (Optional) | Use brownian noise in sampler. |
| `noise` | FLOAT (Optional) | Extra noise added before sampling (0.0–1.0). |
| `variety_boost` | BOOLEAN (Optional) | Enable `skip_cfg_above_sigma` for more varied outputs (V4/V4.5). |
| `characterPrompts` | LIST (Optional) | Per-character prompts from `CharacterPromptSelect` (V4+ only). |
| `limit_opus_free` | BOOLEAN (Optional) | Blocks inpainting while `True`, including V5 Curated's V4.5 fallback, because a base image can cost Anlas. Set `False` to allow the paid request. Default: `True`. |

### 5. NAI Face Detailer (`NAIFaceDetailerNode`)
Advanced face restoration using YOLO detection and SAM segmentation before sending to NAI API.

**Requirement**: Requires [ComfyUI-Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack) and [ComfyUI-Impact-Subpack](https://github.com/ltdrdata/ComfyUI-Impact-Subpack) for detectors. BBOX_DETECTOR types are provided by ComfyUI-Impact-Subpack.

**Behavior**: Defaults to the first detected region. With `detail_mode=all`, plans all regions from the original image, assigns character prompts when enabled, and inpaints each region sequentially. Results are composited through masks with disjoint ownership where crops overlap. The crop targets a 1024 px longest side before 64 px dimension alignment. The API mask retains the original 32 px boxes at an 8 px stride. Region ownership clips whole 8 px cells at request resolution; only the separate composite mask is resized to the source crop. This avoids a mask downscale/upscale round trip that produced visible artifacts during live V5 Full testing.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `image` | IMAGE | Source image. |
| `bbox_detector` | BBOX_DETECTOR| YOLO detector (e.g., face_yolov8m.pt). |
| `sam_model` | SAM_MODEL | SAM model for precise segmentation. |
| `prompt` / `negative_prompt` | STRING | Positive / negative prompts for inpainting. |
| `model` | LIST | NAI model selection. |
| `strength` | FLOAT | Inpainting denoising strength (0.0–1.0). |
| `threshold` | FLOAT | SAM grid-box mask threshold. |
| `sampler` | LIST | Sampler algorithm. |
| `steps` | INT | Generation steps (1–50). |
| `cfg_scale` | FLOAT | Guidance scale. |
| `bbox_threshold` | FLOAT | Confidence threshold for YOLO detection. |
| `dilation` | INT | Bbox dilation in pixels. |
| `crop_factor` | FLOAT | Zoom factor around the detected face. |
| `scheduler` | LIST | Noise scheduler. |
| `seed` | INT | Random seed (-1 for random). |
| `segm_detector` | SEGM_DETECTOR (Optional) | Additional detection source. Each detection is assigned to one primary region before contributing a SAM input box. SAM still produces the final mask. |
| `eye_bbox_detector` | BBOX_DETECTOR (Optional) | Additional detector for eye area mask refinement. |
| `limit_opus_free` | BOOLEAN (Optional) | Allows only verified Opus Focused Inpainting crops while `True`; full-frame crops stop before token access or transport. Set `False` to allow other paid edits. Default: `True`. |

Face Detailer outputs the composited image, a mask visualization, and a JSON matching report. The existing first two output socket indices are unchanged. If no face is detected the original image is returned on the first two outputs. Edited results are autosaved under `NAI_autosave/face` with metadata preserved from the NAI inpaint result.

### 5b. Detailer (`NAIFaceDetailerSegmNode`)
Same pipeline as NAI Face Detailer, but `segm_detector` is the **required** primary detector (defines the crop region) and `bbox_detector` is **optional** (additional source assigned to primary regions). SAM always produces the final mask. `eye_bbox_detector` and `limit_opus_free` behave identically to the Face Detailer node. Displayed in ComfyUI as **Detailer**.

### 5c. Automatic character matching (native PyTorch)

Both Detailer nodes accept the original `CharacterPromptSelect` output through
`characterPrompts`. Connect `NAI WD Tagger Loader (PyTorch)` to `tagger`, select
`detail_mode=all` and `matching_mode=wd14` to process several characters.

Install the optional dependencies **using the Python environment that runs
ComfyUI**: `python -m pip install -r requirements-tagger.txt`. Reuse its existing
PyTorch/torchvision installation. No ONNX package is used. Ordinary generation
and shared-prompt detailing do not import timm or download a tagger.

The loader provides `device=auto` (ComfyUI's selected device) or `cpu`, and a batch
size. On the first WD match it downloads WD ViT Tagger v3's safetensors weights,
config and tag vocabulary from the same pinned revision into
`ComfyUI/models/rs_wd_tagger`. It caches the CPU model and offloads GPU weights
back to CPU after tagging. Initial download/model load and CPU inference take
additional time. The loader does not make a NovelAI request.

**Tagger scores are used only to select a character. They never become positive
or negative prompt text.** Each request combines the Detailer's user-supplied
shared/stage prompt with the selected original character prompt verbatim, and
combines the corresponding original negatives. Character names, franchise names,
qualifiers and weights remain in that original text even when the tagger does
not know the character. Only that selected character is sent; full-image
character coordinates are not reused for a crop.

Keep the Detailer `prompt` input for shared style/detail-stage instructions.
Keep character identities, their franchise tags and character-specific attributes
in the original character slots. A single flat prompt containing multiple mixed
identities is not automatically split or assigned to characters. Tags should use
Danbooru/NovelAI naming for matching; original strings are preserved for requests.

| Input | Behavior |
|---|---|
| `detail_mode` | `first` preserves detector order; `all` numbers valid regions from left to right, then top to bottom. |
| `matching_mode` | `shared` applies the common prompt (optionally one original character); `wd14` automatically selects among original character slots. Multiple slots require `wd14`. |
| `match_crop_factor` | Context around each primary bbox for matching; independent of the inpaint `crop_factor`. Default 2.0. |
| `match_min_score` | Minimum strongest discriminating tag score, default 0.25. This is a heuristic score, not a calibrated identity probability. |
| `match_min_margin` | Minimum lead over the next character, default 0.08. |
| `max_regions` | Maximum regions considered for API requests, default 16. Unprocessed regions still retain their mask ownership. |
| `preview_only` | Show numbered detections and automatic matches, without reading the API token, running SAM, or making NAI requests. WD inference/download can still occur. |

Matching ignores shared attributes and common scene/quality tags, reduces the
weight of eye color, and uses the strongest distinct evidence without penalizing
longer original prompts. Ambiguous contextual crops are retried once at a tighter
factor (up to 1.25). Still-ambiguous regions are skipped with the source pixels
preserved; there is **no manual mapping input and no forced ordering fallback**.
Multiple regions can belong to the same character, as with separate eye detections.
This is not a one-to-one assignment constraint.

For eye refinement, prefer a face detector as the primary detector and an eye
detector on `eye_bbox_detector`, so identity matching sees the head. Eye-only
primary boxes are supported but may not contain enough identity evidence even
after context expansion. Context that includes another character, similar
identities, and characters absent from the tag vocabulary can remain ambiguous.
There is no automatic semantic grouping of eye pairs into faces in this version.

The JSON `matching_report` records detection boxes, selected original character
slot, match score/margin and planned/edited/skipped/empty-mask status. It contains
no inferred prompt. A final edited PNG preserves the last API response metadata
and adds `rs_detailer_regions` for the multi-region report. The last response's
metadata alone is not a full multi-request workflow record.

### Vibe Transfer and Precise Reference

Connect `Load Image` to either **NAI Vibe Transfer** or **NAI Precise Reference**, then connect its output to the generator's `vibes` or `references` input. The same inputs are available on img2img, inpainting, and both detailer nodes, subject to the compatibility table below. Leave them disconnected for the existing behavior.

| Feature | Models | Normal generation / img2img | Inpainting / detailing |
| :--- | :--- | :--- | :--- |
| Vibe Transfer | V3 | Supported | Supported |
| Vibe Transfer | V4 / V4.5 | Supported | Not supported |
| Precise Reference | V4.5 Full / Curated | Supported | Supported |
| Either feature | V5, legacy Furry | Not supported | Not supported |

Model capabilities follow the [official NovelAI client](https://novelai.net/image). [Precise Reference](https://docs.novelai.net/en/image/precisereference/) is currently incompatible with Vibe Transfer, so connect one feature at a time. Even when V5 Curated inpainting normally falls back to V4.5 internally, reference use requires selecting V4.5 explicitly.

**NAI Vibe Transfer** accepts one image, `strength` (default 0.6), and `information_extracted` (default 1.0). To combine images, connect one Vibe node's output to the next Vibe node's optional `vibes` input, then connect the final output to the generator. Each node retains its own settings; up to 16 references can be chained. `enabled=false` or strength zero omits that node's image. The V4/V4.5 `normalize_vibe_strengths` option scales strengths down when their absolute sum exceeds 1.0.

V3 sends a prepared image directly. V4/V4.5 first call the Vibe encoder and store the returned encoding in `ComfyUI/models/rs_nai_vibes`. Cache keys include image content, model, and information extracted. Changing strength or the generation seed reuses the encoding; changing image/model/extraction settings requires another encoding. Cache data contains no token. If a cache file is damaged, execution reports the file rather than silently paying to encode it again. The cache is shared within this ComfyUI installation; separate processes have separate request locks.

**NAI Precise Reference** accepts one image, `reference_type` (`character`, `style`, or `character&style`), `strength`, and `fidelity` (both default 1.0). Chain nodes through `references` to combine up to 16 images. Images are fitted without stretching to the closest 1024×1536, 1472×1472, or 1536×1024 canvas, with black padding. Finite negative strength/fidelity values supplied through connected inputs are also forwarded; the default widgets cover 0–1.

Precise references are global generation guidance. Multiple character references **blend identities**, rather than mapping each image to a character prompt slot. In a detailer, the connected references apply to every edited region; use a single region when applying one character's reference. This feature is separate from the local WD tagger and does not add tags to text prompts. A detailer's `preview_only` mode does not encode or upload references.

**Costs:** according to the official [Vibe documentation](https://docs.novelai.net/en/image/vibetransfer/), a new V4/V4.5 encoding costs 2 Anlas; each Vibe beyond four adds 2 Anlas per generation. [Precise Reference](https://docs.novelai.net/en/image/precisereference/) adds 5 Anlas per reference per generation. These charges can apply even when base generation qualifies for Opus free generation. For that reason, `limit_opus_free=True` blocks both reference types before token access, Vibe encoding, or generation. Set it to `False` only when you intend to permit those charges, and check NovelAI's current pricing before use.

Validation for this addition: real ComfyUI V3 Vibe generation and inpainting completed, and local payload/cache/regression tests passed. Live V4/V4.5 encoding returned HTTP 402 because the test account had insufficient Anlas. Precise Reference live generation remains unverified for the same balance limitation; neither is presented as a completed live test.

### Request serialization and pacing

All NAI calls from this extension share a process-local lock. The next request
starts at least **2 seconds after the previous network attempt completes**, even
when another node calls the common helper. The first request does not have an
artificial initial delay and no trailing sleep is added after the last request.

HTTP 429 is retried at most once. A valid numeric or HTTP-date `Retry-After` is
respected, with a 2-second minimum and a 60-second fallback for invalid/missing
values; the final 429 also leaves the cooldown in place. Every network attempt
uses a 10-second connect / 300-second read timeout. Waiting for the lock/cooldown
is cancellable through ComfyUI. An in-flight synchronous HTTP call finishes or
times out before cancellation can take effect. This lock cannot coordinate other
ComfyUI processes, programs, or separately installed extensions.

### 6. Prompt Converters
Prompt converter nodes translate weighted prompts between ComfyUI, NovelAI V4, and old NovelAI styles.

| Converter | Direction |
| :--- | :--- |
| `ComfyUIToNovelAIV4Converter` | ComfyUI weighted prompt -> NovelAI V4 numeric scope prompt |
| `NovelAIV4ToComfyUIConverter` | NovelAI V4 numeric scope prompt -> ComfyUI weighted prompt |
| `NovelAIV4ToOldNAIConverter` | NovelAI V4 numeric scope prompt -> old NovelAI brace/bracket prompt |
| `OldNAIToNovelAIV4Converter` | old NovelAI brace/bracket prompt -> NovelAI V4 numeric scope prompt |

#### Converter Weight Rules

The converter should treat comma characters as tag separators in every supported syntax. This means a weighted range such as `1.3::tag1, tag2 ::` contains two weighted tags, not one literal tag containing a comma.

NovelAI V4 numeric weights use scoped ranges:

- `1.3::tag1, tag2 ::` applies `1.3` to `tag1` and `tag2`.
- `1.3::tag1, tag2, tag3` has no closing `::`, so `1.3` applies forward to all following comma-separated tags.
- A closing `::` ends the active numeric scope after the current comma-separated tag.

Old NovelAI weights use brace/bracket scopes:

- `{` opens a forward `1.05x` scope for following comma-separated tags until a matching `}` closes it.
- `[` opens a forward `0.95x` scope for following comma-separated tags until a matching `]` closes it.
- A closing `}` with no active `{` applies `1.05x` backward to all previous parsed tags.
- A closing `]` with no active `[` applies `0.95x` backward to all previous parsed tags.
- Mixed braces and brackets are handled by the same character-level scope rules. For example, `{[tag]}` multiplies `1.05 * 0.95`, which is treated as approximately neutral after normalization.

When writing converted prompts, consecutive tags with the same effective weight should be merged into a single scope where possible:

- `1.05::tag1 ::, 1.05::tag2 ::` can be written as `1.05::tag1, tag2 ::`.
- `{tag1}, {tag2}` can be written as `{tag1, tag2}`.

Old NovelAI brace/bracket syntax cannot exactly represent arbitrary numeric weights, negative weights, or zero weights. Those values are converted to the nearest practical old-style approximation when exporting to old NovelAI syntax.

## Opus Free-Generation Protection

All generation nodes (`NovelAIGenerator`, `NAIImg2ImgNode`, `NAIInpaintNode`, `NAIFaceDetailerNode`) include a `limit_opus_free` parameter.

| Property | Value |
| :--- | :--- |
| Default | `True` (enabled) |
| Pixel cap | Total pixels ≤ 1,048,576 (e.g., 1024 × 1024) — width and height are scaled down proportionally if the product exceeds this limit |
| Step cap | Steps ≤ 28 |

**What it does**: For text-to-image, it clamps dimensions and steps, requires an active Opus subscription, and checks NovelAI's V5 allowance immediately before each V5 generation. An unknown response, expired subscription, or V5 allowance below 2% stops the request. V4.5 and older do not need the V5 allowance field. Subscription checks and generation run under one process-local lock, including retries.

Image-to-image and general inpainting use a base image and can cost Anlas even at free-generation dimensions, so they stop before a request when this setting is `True`. Vibe and Precise Reference also stop before token access or reference encoding. With no references connected, Face Detailer is limited to its internally produced Focused Inpainting crops: each request must be smaller than the source image, at most 1,048,576 pixels, at most 28 steps, and exactly one sample. Unsupported payload fields, full-frame crops, reference payloads, and unknown models fail closed. Detailer `preview_only` remains local. Set `limit_opus_free` to `False` only when you intend to allow paid operations or text-to-image outside the free limits. See NovelAI's [Focused Inpainting documentation](https://docs.novelai.net/en/image/inpaint/).

This is a conservative preflight, not a billing guarantee: NovelAI may change its pricing or usage accounting, and a separate client or ComfyUI process can consume the same allowance after the check. The check does not read or compare your Anlas balance. See NovelAI's [subscription rules](https://docs.novelai.net/en/subscription/) and [V5 usage FAQ](https://docs.novelai.net/en/faq/).

## Screenshots

*(Screenshots placeholders)*

## Requirements

- `requests`
- `Pillow`
- `numpy`
- `python-dotenv`
- `segment_anything` (SAM)
- **ComfyUI-Impact-Pack** (Mandatory for Face Detailer node)
- **ComfyUI-Impact-Subpack** (Mandatory for Face Detailer node; provides BBOX_DETECTOR types used for bbox loading)

## Branch Comparison: `main` vs `Add_facedetail`

This section summarizes the differences introduced in the `Add_facedetail` branch relative to `main`.

### Newly Added

| Item | Description |
| :--- | :--- |
| `nai_api.py` | New module housing shared NAI API helpers (request building, response parsing) extracted from `generators.py`. |
| `image_utils.py` | New module with image manipulation helpers shared by the Face Detailer and generator nodes. |
| `NAIFaceDetailerNode` | Full face detailer implementation: YOLO detection → SAM segmentation → NAI inpainting → crop-paste composite. Defaults to the first detected face; `detail_mode=all` enables multiple regions. |
| Metadata-preserving autosave | Face Detailer results are autosaved with NAI metadata intact (same metadata written by the inpainting call). |
| `/face` autosave subfolder | Face Detailer autosaves are written to `NAI_autosave/face/` to keep them separate from standard generation outputs. |
| `n_samples=1` policy | Face Detailer enforces a single sample per NAI API call, matching NAI inpaint constraints. |
| `segment-anything>=1.0` | SAM added as an explicit runtime dependency in `requirements.txt` and `pyproject.toml`. |
| `limit_opus_free` parameter | Default-on conservative preflight for text-to-image and Face Detailer Focused Inpainting; blocks other image-based paid actions. |

### Removed / Pruned

| Item | Reason |
| :--- | :--- |
| `claude_result.md` | Development artifact, not part of the runtime package. |
| `docs/converter_playtest_report.md` | Development artifact, not part of the runtime package. |
| `docs/nai_feature_gap_report.md` | Development artifact, not part of the runtime package. |
| `scripts/converter_playtest.py` | Development script, not part of the runtime package. |
| `feather_radius` UI input (Face Detailer) | Unused parameter removed; the current masked composite uses hard mask boundaries, without feathering. |
| `aiohttp>=3.8.4` dependency | Replaced by `requests>=2.31.0`, which is what the runtime has always used. |
| NAI Upscaler node | Not present in this branch or `main`; removed prior to this work. |
| Anlas Tracker node | Not implemented; Anlas balance tracking is out of scope. |

### Behavior-Preserving Changes

- `load_dotenv()` calls consolidated — previously called redundantly at module level in both `generators.py` and `__init__.py`; now called once.
- `__init__.py` import and export variable names normalized to match the names exported by `generators.py`.
- `_get_save_path` return signature simplified to a `(path, filename)` tuple (was a 5-tuple with unused empty-string fields).

## Credits / Acknowledgments

| Project | License | Role |
| :--- | :--- | :--- |
| [bedovyy/ComfyUI_NAIDGenerator](https://github.com/bedovyy/ComfyUI_NAIDGenerator) | GPL-3.0-only | Reference for Opus free-generation limit behavior (pixel cap and step cap logic) |
| [ComfyUI-Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack) | GPL-3.0-only | External detector dependency and workflow integration for the Face Detailer node |
| [ComfyUI-Impact-Subpack](https://github.com/ltdrdata/ComfyUI-Impact-Subpack) | GPL-3.0-only | External sub-package providing BBOX_DETECTOR types; bbox loading moved to this package |
| [segment-anything](https://github.com/facebookresearch/segment-anything) | Apache-2.0 | SAM segmentation runtime dependency used by the Face Detailer node |
| NovelAI API | Proprietary (external service) | Remote image generation API; no NovelAI code is bundled |

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for full details.

## License

The source code in this repository is published under **GPL-3.0-only**.
Full corresponding source is provided in this repository.
The complete GPLv3 license text is in the [COPYING](COPYING) file.
See the [LICENSE](LICENSE) file for the short SPDX notice.

Copyright (c) 2025 raspie10032

*This is a factual license notice, not legal advice.*

## Workflow Examples

Files in `workflow_example/` (`example.json`, `example.png`) are project-provided examples distributed with this project under GPL-3.0-only unless otherwise noted.

## Detailer validation

Run `python -m unittest discover -s tests -v` for deterministic regression tests
(detectors, SAM and NAI transport are simulated in pipeline tests).

For an optional real-weight CPU smoke after installing tagger dependencies, run
`python tests/smoke_wd_tagger.py --cache-dir /path/to/model-cache --output /path/to/result.json`.
This uses the repository screenshot and supplied face-box fixtures, then runs
real PyTorch tagging and automatic matching, including the tighter-crop retry.
It does not run live YOLO, SAM, ComfyUI UI execution or NovelAI generation.
