# ComfyUI_RS_NAI_API_Request

This extension provides custom nodes for ComfyUI to interact with the **NovelAI API** using a synchronous `requests`-based approach. It allows you to generate images, perform image-to-image, inpainting, and advanced face detailing directly from within ComfyUI.

## Features

- **NovelAI API Integration**: Full support for NAI Diffusion V4.5, V4, V3, and more.
- **Synchronous Requests**: Stable connection using `requests` library.
- **Multi-Character Support**: Specialized node for spatial multi-character prompting in NAI V4/V4.5.
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
| `model` | LIST | NAI Model (V4.5, V4, V3, etc.). |
| `width` / `height` | INT | Image dimensions (steps of 64). |
| `sampler` | LIST | Sampler (e.g., k_euler, k_dpmpp_2m). |
| `steps` | INT | Generation steps (1-50). |
| `cfg_scale` | FLOAT | Guidance scale. |
| `seed` | INT | Random seed (-1 for random). |
| `scheduler` | LIST (Optional) | Noise scheduler: `native`, `karras`, `exponential`, `polyexponential`. |
| `cfg_rescale` | FLOAT (Optional) | Prompt guidance rescale (0.0–1.0). |
| `prefer_brownian` | BOOLEAN (Optional) | Use brownian noise in sampler. |
| `variety_boost` | BOOLEAN (Optional) | Enable `skip_cfg_above_sigma` for more varied outputs (V4/V4.5). |
| `characterPrompts` | LIST (Optional) | Per-character prompts from `CharacterPromptSelect` (V4/V4.5 only). |
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
| `characterPrompts` | LIST (Optional) | Per-character prompts from `CharacterPromptSelect` (V4/V4.5 only). |
| `limit_opus_free` | BOOLEAN (Optional) | Cap total pixels to ≤ 1,048,576 and steps to ≤ 28. Applies Opus free-tier limits manually; no account detection or Anlas balance checking. Default: `True`. |

### 4. NAI Inpaint (`NAIInpaintNode`)
Specialized node for inpainting. Automatically snaps dimensions to 64px.

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
| `characterPrompts` | LIST (Optional) | Per-character prompts from `CharacterPromptSelect` (V4/V4.5 only). |
| `limit_opus_free` | BOOLEAN (Optional) | Cap total pixels to ≤ 1,048,576 and steps to ≤ 28. Applies Opus free-tier limits manually; no account detection or Anlas balance checking. Default: `True`. |

### 5. NAI Face Detailer (`NAIFaceDetailerNode`)
Advanced face restoration using YOLO detection and SAM segmentation before sending to NAI API.

**Requirement**: Requires [ComfyUI-Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack) and [ComfyUI-Impact-Subpack](https://github.com/ltdrdata/ComfyUI-Impact-Subpack) for detectors. BBOX_DETECTOR types are provided by ComfyUI-Impact-Subpack.

**Behavior**: Detects the first face, crops it, resizes the crop so its longest side is 1024 px, runs SAM segmentation, sends the crop to NAI inpaint, then pastes the downscaled inpaint result directly back over the original crop region.

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
| `segm_detector` | SEGM_DETECTOR (Optional) | Alternative detection source, equal layer to `bbox_detector`. When connected, segm replaces bbox as the detector while SAM still produces the final mask. |
| `eye_bbox_detector` | BBOX_DETECTOR (Optional) | Additional detector for eye area mask refinement. |
| `limit_opus_free` | BOOLEAN (Optional) | Cap total pixels to ≤ 1,048,576 and steps to ≤ 28. Applies Opus free-tier limits manually; no account detection or Anlas balance checking. Default: `True`. |

Face Detailer outputs the composited image and a mask visualization. If no face is detected the original image is returned on both outputs. Edited results are autosaved under `NAI_autosave/face` with metadata preserved from the NAI inpaint result.

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
| `NAIFaceDetailerNode` | Full face detailer implementation: YOLO detection → SAM segmentation → NAI inpainting → crop-paste composite. Only the first detected face is processed per run. |
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
| `feather_radius` UI input (Face Detailer) | Unused parameter removed; the crop-paste approach does not apply feathering. |
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
