# ComfyUI_RS_NAI_API_Request

This extension provides custom nodes for ComfyUI to interact with the **NovelAI API** using a synchronous `requests`-based approach. It allows you to generate images, perform image-to-image, inpainting, and advanced face detailing directly from within ComfyUI.

## Features

- **NovelAI API Integration**: Full support for NAI Diffusion V4.5, V4, V3, and more.
- **Synchronous Requests**: Stable connection using `requests` library.
- **Multi-Character Support**: Specialized node for spatial multi-character prompting in NAI V4/V4.5.
- **Face Detailer**: Intelligent face detection (YOLO) and segmentation (SAM) combined with NAI inpainting for high-quality face restoration.
- **Upscaler**: Server-side NAI upscaling (2x/4x).

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
2. Add your token to the file:
   ```text
   NAI_API_TOKEN=your_api_token_here
   ```
Alternatively, you can set an environment variable named `NAI_API_TOKEN`.

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
| `characterPrompts` | LIST (Optional) | Character specific prompts from `CharacterPromptSelect`. |

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
| `strength` | FLOAT | Denoising strength (0.0 to 1.0). |
| *Other* | - | Same as `NovelAIGenerator`. |

### 4. NAI Inpaint (`NAIInpaintNode`)
Specialized node for inpainting. Automatically snaps dimensions to 64px.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `image` | IMAGE | Source image. |
| `mask` | MASK | Area to inpaint. |
| `strength` | FLOAT | Inpainting strength. |
| *Other* | - | Same as `NovelAIGenerator`. |

### 5. NAI Face Detailer (`NAIFaceDetailerNode`)
Advanced face restoration using YOLO detection and SAM segmentation before sending to NAI API.

**Requirement**: Requires [ComfyUI-Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack) for detectors.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `image` | IMAGE | Source image. |
| `bbox_detector` | BBOX_DETECTOR| YOLO detector (e.g., face_yolov8m.pt). |
| `sam_model` | SAM_MODEL | SAM model for precise segmentation. |
| `threshold` | FLOAT | SAM segmentation threshold. |
| `crop_factor` | FLOAT | Zoom factor around the detected face. |
| `eye_bbox_detector`| BBOX_DETECTOR| (Optional) Additional detector for eye area refinement. |

### 6. NAI Upscaler (`NAIUpscalerNode`)
Server-side high-quality upscaling.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `image` | IMAGE | Source image. |
| `scale` | INT | Upscale factor (2 or 4). |

## Screenshots

*(Screenshots placeholders)*

## Requirements

- `requests`
- `Pillow`
- `numpy`
- `python-dotenv`
- `segment_anything` (SAM)
- **ComfyUI-Impact-Pack** (Mandatory for Face Detailer node)

## License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.
Copyright (c) 2026 raspie10032
