# ComfyUI_RS_NAI_API_Request

This extension provides custom nodes for ComfyUI to interact with the **NovelAI API** using a synchronous `requests`-based approach. It allows you to generate images, perform image-to-image, inpainting, and advanced face detailing directly from within ComfyUI.

> Current version: **2.2.0**

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

- **NovelAI API Integration**: Image request support for NAI Diffusion V5, V4.5, V4, V3, and more.
- **Synchronous Requests**: Stable connection using `requests` library.
- **Multi-Character Support**: Specialized node for spatial multi-character prompting in NAI V4+.
- **Face Detailer**: Intelligent face detection (YOLO) and segmentation (SAM) combined with NAI inpainting for high-quality face restoration.

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
| `limit_opus_free` | BOOLEAN (Optional) | Cap total pixels to ≤ 1,048,576 and steps to ≤ 28. Applies Opus free-tier limits manually; no account detection or Anlas balance checking. Default: `True`. |

### 2. NAI Character Prompt Select (`CharacterPromptSelect`)
Defines up to 5 characters with spatial coordinates (0-10 scale) for NAI V4+.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `characterX` | STRING | Character specific prompt. |
| `characterX_uc` | STRING | Character specific negative prompt. |
| `characterX_x` / `y` | INT | Center coordinates (0-10). |
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
| `limit_opus_free` | BOOLEAN (Optional) | Cap total pixels to ≤ 1,048,576 and steps to ≤ 28. Applies Opus free-tier limits manually; no account detection or Anlas balance checking. Default: `True`. |

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
| `limit_opus_free` | BOOLEAN (Optional) | Cap total pixels to ≤ 1,048,576 and steps to ≤ 28. Applies Opus free-tier limits manually; no account detection or Anlas balance checking. Default: `True`. |

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
| `limit_opus_free` | BOOLEAN (Optional) | Cap total pixels to ≤ 1,048,576 and steps to ≤ 28. Applies Opus free-tier limits manually; no account detection or Anlas balance checking. Default: `True`. |

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

**What it does**: When enabled, the node clamps the request dimensions and step count to the conditions allowed under the NovelAI Opus free-generation tier, following the same approach as [bedovyy/ComfyUI_NAIDGenerator](https://github.com/bedovyy/ComfyUI_NAIDGenerator).

**What it does NOT do**:
- It does **not** auto-detect your account subscription tier.
- It does **not** check your Anlas balance or block requests when balance is insufficient. The NovelAI API itself will reject any request that cannot be fulfilled.
- An Anlas Tracker node is **not** included in this extension.

Set `limit_opus_free` to `False` if you have a paid subscription and want to generate at larger sizes or higher step counts.

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
| `limit_opus_free` parameter | Manual toggle (default `True`) on all generation nodes that caps total pixels to ≤ 1,048,576 and steps to ≤ 28, matching Opus free-tier generation limits. No account detection or Anlas balance checking. |

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
