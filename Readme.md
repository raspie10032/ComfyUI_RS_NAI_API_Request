# ComfyUI_RS_NAI_API_Request

This custom node is a fork of [ComfyUI_API_Request](https://github.com/DiaoDaiaChan/ComfyUI_API_Request) with additional prompt weight conversion nodes that I've developed separately.

A custom node extension for ComfyUI that provides NovelAI prompt conversion and image generation capabilities.

## Features

This extension provides two sets of functionality:

### 1. Prompt Converters

Convert between different prompt formats:

- **ComfyUI to NovelAI V4**: Convert ComfyUI-style prompts to NovelAI V4 format
- **NovelAI V4 to ComfyUI**: Convert NovelAI V4-style prompts to ComfyUI format
- **NovelAI V4 to Old NAI**: Convert NovelAI V4-style prompts to old NovelAI format (with curly/square brackets)
- **Old NAI to NovelAI V4**: Convert old NovelAI prompts to NovelAI V4 format
- **ComfyUI to Old NAI**: Convert ComfyUI prompts directly to old NovelAI format
- **Old NAI to ComfyUI**: Convert old NovelAI prompts directly to ComfyUI format

### 2. NovelAI Image Generation

Generate images directly through the NovelAI API:

- **Character Prompt Select**: Create character prompts with positioning
- **NovelAI Generator**: Generate images using the NovelAI API with various models

## Installation

1. Clone this repository into your ComfyUI custom_nodes directory:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request.git
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the ComfyUI_RS_NAI_API_Request directory with your NovelAI API token:

```
NAI_ACCESS_TOKEN=your_novelai_token_here
```

Note: This extension uses the same environment variable name (`NAI_ACCESS_TOKEN`) as the [ComfyUI_NAIDGenerator](https://github.com/bedovyy/ComfyUI_NAIDGenerator) custom node. If you're already using that extension, you don't need to add anything to your `.env` file.

## Usage

### Prompt Converters

These nodes allow you to convert between different prompt formats:

- **ComfyUI format**: Uses parentheses with weights like `(tag:1.2)`
- **NovelAI V4 format**: Uses double colons with weights like `1.2::tag::`
- **Old NovelAI format**: Uses curly braces for emphasis like `{tag}` or square brackets for de-emphasis like `[tag]`

### NovelAI Generator

1. Use the **Character Prompt Select** node to create character prompts with positioning
2. Connect these to the **NovelAI Generator** node along with your main prompt
3. Configure generation parameters (model, sampler, steps, etc.)
4. Run the workflow to generate images directly through the NovelAI API

## Models

The following NovelAI models are supported:

- NAI Diffusion V4.5 Curated
- NAI Diffusion V4 Full
- NAI Diffusion V4 Curated Preview
- NAI Diffusion V3
- NAI Diffusion Furry V3
- NAI Diffusion V2

## Example Workflow

[Include a screenshot or description of an example workflow here]

## Requirements

- Python 3.8+
- ComfyUI
- python-dotenv
- aiohttp
- torch
- numpy
- PIL

## Credits and References

This project is based on and inspired by the following repositories:

- **Original API Implementation**: [DiaoDaiaChan/ComfyUI_API_Request](https://github.com/DiaoDaiaChan/ComfyUI_API_Request)
- **Original Prompt Converter**: [raspie10032/ComfyUI_RS_NAI_Local_Prompt_converter](https://github.com/raspie10032/ComfyUI_RS_NAI_Local_Prompt_converter)
- **Reference Implementation**: [bedovyy/ComfyUI_NAIDGenerator](https://github.com/bedovyy/ComfyUI_NAIDGenerator)

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- This project builds upon multiple community resources and the NovelAI API
- Thanks to the ComfyUI team for creating an excellent platform for AI image generation workflows