# ComfyUI_RS_NAI_API_Request

ComfyUI custom nodes for **NovelAI Diffusion V5 and earlier models**, supporting text-to-image generation, img2img, inpainting, Vibe Transfer, Precise Reference, multi-character prompts, and prompt-weight conversion. Reference features require a supported model as listed below.

The Detailer can use bbox+SAM, native SEGM masks, or a standard ComfyUI `MASK` from SAM3 or another mask node, and can process multiple regions sequentially. An optional **local PyTorch tagger** automatically matches each region to an original character prompt, preserving its character and series names. Tagger output is used only for matching and is never added to the generation prompt. The tagger requires no ONNX runtime and downloads only the selected model when the loader executes, after the optional dependencies are installed.

> Current version: **2.6.0**

## What's New in 2.6.0

- Both Detailers accept three mask backends: the existing detector-box-to-SAM path, a `SEGM_DETECTOR`'s native `cropped_mask`, or a standard `MASK` from SAM3/another mask node.
- `sam_model` is optional. `NAI Face Detailer` also makes `bbox_detector` optional, so a same-size external MASK can define regions without loading legacy SAM. The `Detailer` node keeps its required SEGM detector for existing workflows.
- `mask_source=auto` preserves the previous SAM behavior whenever a complete detector+SAM path is connected. Otherwise it selects `detail_mask`, then native SEGM masks. Choose `sam`, `segm`, or `external_mask` to override that rule explicitly.
- A MASK batch creates one detail region per nonempty batch item. Disconnected shapes within one batch item stay one region and share one crop/prompt assignment; split them into a mask batch when they need separate regions or character matching.
- Native masks preserve their own pixels; only actual overlaps are divided between regions. Their preview shows the exact final composite mask. Empty SAM3 batches return the original image without a request, and existing positional workflow settings keep their order. See the [SAM3 / SEGM guide](docs/sam3-segm-masks.md).
- Native SEGM/external masks appear in `preview_only` without token access, legacy SAM execution, or a NovelAI request. Existing Vibe Transfer, Precise Reference, Focused Inpainting checks, output positions, and bbox+SAM results remain unchanged.

## What's New in 2.5.0

- **Reference Inset** prepares a reference canvas and generation mask locally. Choose left/right/top/bottom and the reference percentage; the node shows both canvas and cropped output dimensions and previews the canvas when executed.
- **Reference Inset Generate** fills the empty area with NovelAI inpainting, adds `reference inset` once, and returns the cropped image, preserved full canvas, and applied prompt. Both images are autosaved. Default Anlas protection blocks generation; preparation remains local.
- **Character Asset Save / Load** keep one reference image and its original positive/negative character prompts in a portable PNG. Save locally, refresh the loader list, and reuse the image and prompts in other workflows.
- New nodes have Korean/Japanese native labels, tooltips, and friendly error messages. Existing node inputs and workflow defaults are unchanged. See the [reference inset and asset guide](docs/reference-inset.md).

## What's New in 2.4.6

- Execution errors now explain **what failed and what to do next**, in English, Korean, or Japanese according to ComfyUI's language setting. The explanation appears in the error dialog and directly on the failed node. Refresh the browser after updating.
- Distinct messages cover API authentication/status codes, timeouts and connection failures, strict Anlas protection, model/character/reference combinations, image/mask inputs, tagger dependencies/downloads, memory, and file access. Unknown failures retain their actual error type and details without guessing the cause.
- Stable error codes, HTTP status, request stage, and original traceback remain available for troubleshooting. Common token patterns are masked. Explanations do not change request/retry rules or billing protection, and cancellation remains cancellation.
- Error widgets clear when the node executes again and are excluded from saved workflow inputs. See [error messages and troubleshooting](docs/error-messages.md) for examples and scope.

**한국어:** 오류창과 실패한 노드에 원인·해결 방법을 표시합니다. 아래 상세 정보에는 오류 코드, HTTP 상태, 실패 단계와 원래 오류가 남습니다. ComfyUI 언어 설정을 따라가며 알 수 없는 원인은 단정하지 않습니다.

**日本語:** エラーダイアログと失敗したノードに原因と対処方法を表示します。エラーコード、HTTP ステータス、失敗した段階、元のエラーは詳細情報に残ります。ComfyUI の言語設定に従い、不明な原因を推測して断定しません。

## What's New in 2.4.5

- **Expandable character slots**: `character_count` shows 1–22 slots, with the familiar 5-slot view as the default. Increase it to add characters; decrease it to hide and exclude the later slots. Their text and coordinates are kept when saved and reopened. Existing five-slot workflows retain their input order and defaults.
- **Model limits**: V5 supports up to 22 active character prompts; V4/V4.5 supports 6. V5 Curated inpainting uses V4.5 Curated, so its limit is also 6. Excess prompts produce a local error before image/reference encoding or an API request; nothing is silently dropped. See the [official multi-character documentation](https://docs.novelai.net/en/image/multiplecharacters/).
- Both face detailers can match against all 22 original character candidates. `detail_mode` and `max_regions` still control how many detected regions are processed (`first` by default; `all` with up to 64 regions). The slot limit is not a guarantee of multi-character recognition accuracy. Use `preview_only` to inspect uncertain matches without generation.
- Korean and Japanese labels and tooltips include the new slots and count control. Refresh the ComfyUI page after updating.

## What's New in 2.4.4

- Added Korean and Japanese translations for all 15 nodes through [ComfyUI's native locale files](https://docs.comfy.org/custom-nodes/i18n): names, descriptions, input labels, tooltips, named outputs, and reference/detailer options. Socket type names and the display of option values follow ComfyUI's own locale handling.
- Choose **한국어** or **日本語** in **ComfyUI Settings → Comfy → Locale → Language**. After updating the extension, restart ComfyUI and refresh the browser to load the new translations.
- Node IDs, saved input values, model names, sampler identifiers, and generation prompts remain unchanged. Other languages continue to use the existing English node definitions. Runtime notices, download status messages, and matching reports remain in English; execution error explanations are localized as of 2.4.6.

**한국어:** ComfyUI 설정에서 언어를 **한국어**로 선택하면 노드 이름·설명·입출력 항목·툴팁이 한국어로 표시됩니다. 업데이트 후에는 ComfyUI를 재시작하고 브라우저를 새로고침하세요.

**日本語:** ComfyUIの設定で言語を**日本語**にすると、ノード名・説明・入出力ラベル・ツールチップが日本語で表示されます。更新後はComfyUIを再起動し、ブラウザーを再読み込みしてください。

## What's New in 2.4.3

- Choose a local tagger model in the existing `NAI WD Tagger Loader (PyTorch)` node's `model_name` menu. Existing workflows keep WD ViT v3 as their default.
- Only the selected model downloads when the loader executes. Each model has its own pinned HuggingFace cache; switching models replaces the loader's active model.
- Download progress appears directly on the loader node: current filename, percentage and received/total MiB, followed by loading and ready states. Cached files are reused.
- Each model uses its own preprocessing. General/character scores feed the existing matcher; unrelated prediction categories are excluded. Larger models need additional dependencies and memory; start with `batch_size=1`.

## What's New in 2.4.2

- Reviewed every published Comfy.ICU node page against the current implementation. The [page-by-page audit](docs/node-page-audit.md) distinguishes fixes from outdated external descriptions.
- WD Tagger Loader checks optional dependencies as soon as it executes. Missing/broken imports include the actual ComfyUI Python installation command. Version 2.4.2 loaded weights on the first match; 2.4.3 prepares them in the loader with visible download progress.
- Execution notices appear on the node for malformed/downgraded prompt weights, obsolete coordinates, Opus dimension/step changes, Medium fixed settings and detailer skips. Notices are read-only and are not saved as workflow inputs; existing input order/defaults and output sockets are preserved.
- V3/Furry generation rejects connected character slots before reading the token or preparing references. Unknown models no longer silently select a different model. Detailers can still match a character and use its original text in a V3 base prompt.
- Img2img, inpaint and detailers reject image batches instead of silently using the first image. Inpaint validates a single nonempty mask and warns about differing source/mask dimensions.
- Autosave names are unique even within the same timestamp. ZIP responses select the sole PNG regardless of metadata/directory order, and reject missing or multiple images.
- Detailer reports explain score/margin skips and request limits, including the latest tighter-crop result. API masks and disjoint compositing are unchanged.

Reload the ComfyUI browser page after updating to load the notice widget. It appears after execution when there is something to report. For old 0–10 coordinate workflows, update the original saved values to 0–1; ambiguous values are not automatically migrated.

## What's New in 2.4.1

- Unified the previously separate Linux integration into `main`. Windows and Linux now use the same package, including V5 Full Medium Effort, Vibe Transfer, Precise Reference, and Face Detailer Focused Inpainting.
- Added **NAI Vibe Transfer** and **NAI Precise Reference** nodes, optional reference inputs on generation and detailer nodes, and local caching for V4/V4.5 Vibe encodings.
- Allowed the detailer's internally produced Focused Inpainting crops in `limit_opus_free` mode, with crop, payload, subscription, and V5 allowance checks. General img2img/inpainting and both reference features remain blocked in strict mode.
- Preserved the Medium settings and inpainting strength fix from 2.3.1. Existing node names, inputs, defaults, and outputs are retained; reference inputs are appended as optional connections.

See [Vibe Transfer and Precise Reference](#vibe-transfer-and-precise-reference) for setup, supported models, costs, and example API workflows. See [Medium Effort compatibility and validation](docs/medium-effort.md) for Medium settings and verification scope.

## What's New in 2.3.1

- Fixed inpainting strength for V4/V4.5/V5, including Medium Effort and both face detailers. Partial strength now reaches the API as `img2img.strength` with color correction, matching the NovelAI web client. A strength of 1 uses full inpainting without that option.
- Added a model tooltip explaining Medium's fixed settings and when image input can spend Anlas, without changing saved workflow input positions.
- Expanded tests across generation, img2img, inpainting, multi-region detailing, output decoding/autosave, and Medium's checks before network requests.

## What's New in 2.3.0

- Added **NAI Diffusion V5 Full — Medium Effort** for generation, img2img, and inpainting.
- Medium Effort uses NovelAI's distilled checkpoints and always sends 14 steps, Euler Ancestral, zero CFG Rescale, and the fixed Heavy Undesired Content preset. The node ignores the steps, sampler, CFG Rescale, base negative prompt, and character negative prompts shown in an existing workflow while this model is selected.
- Medium Effort img2img and general inpainting remain blocked when `limit_opus_free=True`, because those modes can spend Anlas.
- `limit_opus_free=True` recognizes Medium text generation, still verifies the V5 Opus allowance, and rejects a payload whose fixed Medium settings were changed before transport.

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

- **Reference inset**: Automatic canvas/mask preparation, output-size preview, reference-guided inpainting, and exact result cropping.
- **Character assets**: Portable reference PNGs with original prompts, a local save/load library, and an in-node refresh button.
- **Image references**: Vibe Transfer for supported V3/V4/V4.5 models, plus V4.5 Precise Reference for character and style guidance.
- **NovelAI generation**: Text-to-image, img2img, and inpainting with NAI Diffusion V5, V4.5, V4, V3, and supported Furry models.
- **Multi-character prompts**: Up to 22 character slots for V5 (6 for V4/V4.5), with separate positive/negative prompts and X/Y coordinates from 0.0 to 1.0 in 0.1 increments.
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
   cd ComfyUI_RS_NAI_API_Request
   ```
3. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```

## Configuration (API Token)

Generation requires your **NovelAI API Token**. Converters, character/reference builders, and WD matching/preview run without a NovelAI token. WD model files may be downloaded from HuggingFace on first use.

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
Defines up to 22 characters with spatial coordinates (0.0–1.0 scale). Start with the default five slots and increase `character_count` as needed. V4/V4.5 accept 6 active prompts; V5 accepts 22 (except V5 Curated inpainting: 6). Newly revealed slots 6–22 are enabled; fill them in or turn off their individual switch. Slots outside the count are excluded even if their switches are on.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `character_count` | INT | Visible/usable slots, 1–22; default 5. Hidden values are preserved. |
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
Advanced region restoration using bbox+SAM, native SEGM masks, or a standard ComfyUI MASK before sending focused crops to the NAI API.

**Requirement**: Requires [ComfyUI-Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack) and [ComfyUI-Impact-Subpack](https://github.com/ltdrdata/ComfyUI-Impact-Subpack) for detectors. BBOX_DETECTOR types are provided by ComfyUI-Impact-Subpack.

**Behavior**: Defaults to the first detected region. With `detail_mode=all`, plans all regions from the original image, assigns character prompts when enabled, and inpaints each region sequentially. Results are composited through masks with disjoint ownership where crops overlap. Native SEGM and external MASK paths preserve all above-threshold pixels belonging to each instance and assign only genuinely overlapping pixels by nearest detection center (stable detection order breaks ties). The crop targets a 1024 px longest side before 64 px dimension alignment. The API mask uses 32 px boxes at an 8 px stride and covers thin native-mask details in whole 8 px cells. Native paths composite only inside the owned source mask; the legacy bbox+SAM path retains its whole-cell request ownership and resized composite mask. This avoids a mask downscale/upscale round trip that produced visible artifacts during live V5 Full testing.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `image` | IMAGE | Source image. |
| `bbox_detector` | BBOX_DETECTOR (Optional) | YOLO detector (e.g., face_yolov8m.pt). Pair with `sam_model` for the legacy path. |
| `sam_model` | SAM_MODEL (Optional) | Legacy SAM model. In `auto`, a complete detector+SAM path preserves the previous behavior. |
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
| `segm_detector` | SEGM_DETECTOR (Optional) | Native mask source when SAM is absent or `mask_source=segm`; with bbox+SAM in `auto`, it remains an additional SAM box source for compatibility. |
| `detail_mask` | MASK (Optional) | Same-size standard ComfyUI mask, including SAM3 output. Each nonempty batch item becomes one region. |
| `mask_source` | LIST (Optional) | `auto` preserves a complete SAM path, otherwise chooses external MASK then SEGM. Explicit choices are `sam`, `segm`, and `external_mask`. |
| `eye_bbox_detector` | BBOX_DETECTOR (Optional) | Additional detector for eye area mask refinement. |
| `limit_opus_free` | BOOLEAN (Optional) | Allows only verified Opus Focused Inpainting crops while `True`; full-frame crops stop before token access or transport. Set `False` to allow other paid edits. Default: `True`. |

Face Detailer outputs the composited image, a mask visualization, and a JSON matching report. The existing first two output socket indices are unchanged. If no region is detected, including an empty SAM3 batch, the original image and a black mask preview are returned. For native SEGM/external MASK, `preview_only=True` displays the exact final composite mask and records `mask_pixels` per region, without token access or NovelAI requests. The legacy bbox+SAM preview remains detection/matching-only. See [SAM3 / SEGM setup and mask behavior](docs/sam3-segm-masks.md). Edited results are autosaved under `NAI_autosave/face` with metadata preserved from the NAI inpaint result.

### 5b. Detailer (`NAIFaceDetailerSegmNode`)
Same pipeline as NAI Face Detailer, but `segm_detector` remains the **required** primary detector. With no SAM model, its native `cropped_mask` supplies the editable pixels (threshold and overlap ownership still apply). Connecting `sam_model` with `mask_source=auto` preserves the previous behavior: SEGM boxes guide SAM and optional `bbox_detector` boxes are assigned to those regions. `detail_mask` can instead receive a same-size standard MASK from SAM3 or another node when `mask_source=external_mask`. `eye_bbox_detector` and `limit_opus_free` behave identically to the Face Detailer node. Displayed in ComfyUI as **Detailer**.

### 5c. Automatic character matching (native PyTorch)

Both Detailer nodes accept the original `CharacterPromptSelect` output through
`characterPrompts`. Connect `NAI WD Tagger Loader (PyTorch)` to `tagger`, select
`detail_mode=all` and `matching_mode=wd14` to process several characters.
The `wd14` mode and `RS_WD_TAGGER` socket accept all models in the loader's selection menu, preserving existing workflows.

Install the optional dependencies **using the Python environment that runs
ComfyUI**: `python -m pip install -r requirements-tagger.txt`. Reuse its existing
PyTorch/torchvision installation. Additional model dependencies and installation
commands are listed in [the model notes](docs/tagger-models.md). If dependencies
are missing, the loader reports an installation command using the current
ComfyUI Python environment. The loader checks the dependencies for
the selected model before returning a handle. No ONNX package is used. Ordinary generation
and shared-prompt detailing do not import timm or download a tagger.

The loader provides `device=auto` (ComfyUI's selected device) or `cpu`, a batch
size, and `model_name`:

| Selection | Official model | Input | Weight download |
| --- | --- | --- | --- |
| **WD ViT v3** (default) | [SmilingWolf/wd-vit-tagger-v3](https://huggingface.co/SmilingWolf/wd-vit-tagger-v3) | 448 × 448, BGR | About 377 MB |
| **WD EVA02 Large v3** | [SmilingWolf/wd-eva02-large-tagger-v3](https://huggingface.co/SmilingWolf/wd-eva02-large-tagger-v3) | 448 × 448, BGR | About 1.26 GB |

Select a model and execute a workflow using this loader (matching or
`preview_only`) to download it. The loader shows a per-file progress bar, filename,
percentage and received/total MiB, then a loading and ready status. Installing
the node alone does not download weights. Files are cached
under `ComfyUI/models/rs_wd_tagger`, separated by model and pinned revision.
Already downloaded models are reused. Models that require custom architecture
or processor code download it from a pinned, reviewed revision and verify its
SHA-256 before loading. Model-specific requirements, licenses and source links are recorded in
[the model notes](docs/tagger-models.md).

Inference runs locally; image crops are not sent to model hosts. Models
are kept on CPU between calls and offloaded from GPU after tagging, including
failed inference. Larger models need more memory and compute: start with `batch_size=1`.
Initial downloads/model loading and CPU inference take additional time. Tagger
selection, downloads and local inference do not use NovelAI or Anlas.

Models produce different score distributions. The Detailer's existing
`match_min_score` and `match_min_margin` still control acceptance; category
thresholds from captioning examples are not applied before matching. Preview
matches on your own images when switching models. Ambiguous matches remain skipped.

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
| `preview_only` | Show numbered detections and automatic matches without reading the API token or making NAI requests. Native SEGM/external masks are shown in `mask_visualization`; the legacy SAM path still previews boxes without running SAM. WD inference/download can still occur. |

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

Example API graphs: [Vibe Transfer](workflow_example/vibe_transfer_api.json) and [Precise Reference](workflow_example/precise_reference_api.json). Replace `reference.png` with your input filename. They retain the default `limit_opus_free=True`, which blocks reference requests. To run a reference generation after accepting its Anlas cost, explicitly set the generator's `limit_opus_free` input to `False`.

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

Validation for this addition: earlier real ComfyUI V3 Vibe generation and inpainting completed. The integrated release passes 78 offline tests covering payloads, caching, request serialization, strict guards, focused crops, Medium, and existing behavior. The earlier live V4/V4.5 encoding attempt returned HTTP 402 for insufficient Anlas, and Precise Reference was not live-validated. Those paid reference paths were not retried for this integration release; they are not presented as completed live tests. Windows native runtime was not exercised from the Linux host.

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

All generation nodes, including `NAIReferenceInsetGenerate` and both Face Detailers, include a `limit_opus_free` parameter.

Reference inset generation uses ordinary inpainting and is blocked before token access or image encoding when protection is enabled. Canvas preparation and character asset save/load are local operations and use no Anlas.

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

## Historical Face Detailer Refactor

These changes originated in `Add_facedetail` and are included in the current `main` package.

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
| [NAIA 2.0](https://github.com/DNT-LAB/NAIA2.0) | GPL-3.0 (upstream) | Reference for the reference inset and character asset workflows, introduced in [NAIA — Reference Inset, V5 Assets](https://arca.live/b/aiart/185642997) |
| [ComfyUI-Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack) | GPL-3.0-only | External detector dependency and workflow integration for the Face Detailer node |
| [ComfyUI-Impact-Subpack](https://github.com/ltdrdata/ComfyUI-Impact-Subpack) | GPL-3.0-only | External sub-package providing BBOX_DETECTOR types; bbox loading moved to this package |
| [segment-anything](https://github.com/facebookresearch/segment-anything) | Apache-2.0 | SAM segmentation runtime dependency used by the Face Detailer node |
| NovelAI API | Proprietary (external service) | Remote image generation API; no NovelAI code is bundled |

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for full details.

Thanks to NAIA for sharing the reference inset and V5 asset workflow. Its linked article informed the workflow and usability design of our ComfyUI inset and asset nodes.

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
