# SPDX-License-Identifier: GPL-3.0-only
"""Local reference layout and reference-guided inpainting."""

from dataclasses import dataclass
import json
import math
import re
import secrets
import tempfile
from pathlib import Path
import uuid

import numpy as np
import torch
from PIL import Image, ImageOps

from .diagnostics import notice
from .errors import user_error
from .generators import CharacterPrompt, NovelAIGenerator
from .image_utils import (
    pil_to_base64, pil_to_tensor, png_bytes_to_pil, save_png_preserving_metadata,
    tensor_to_pil, validate_single_image,
)
from .nai_api import (
    MODEL_DISPLAY_LIST, MODEL_SELECTION_TOOLTIP, SAMPLER_LIST, SCHEDULER_LIST,
    apply_v4_parameters, build_common_parameters, build_nai_payload, get_model_id,
    get_nai_token, post_nai, validate_character_prompts, zip_to_png_bytes,
)


@dataclass(frozen=True)
class ReferenceInset:
    canvas: Image.Image
    mask: Image.Image
    target_box: tuple


def inset_boxes(width, height, placement, reference_percent):
    if (any(isinstance(v, bool) or not isinstance(v, int) or not 64 <= v <= 4096 or v % 64 for v in (width, height))
            or placement not in ("left", "right", "top", "bottom")
            or not math.isfinite(reference_percent) or not 10 <= reference_percent <= 75):
        raise user_error("INSET_LAYOUT", ValueError,
                         "Use canvas dimensions of 64–4096 in steps of 64, a reference side, and 10–75% reference space.")
    vertical = placement in ("left", "right")
    length = width if vertical else height
    split = int(length * reference_percent / 100 + 0.5)
    if placement == "left":
        return (0, 0, split, height), (split, 0, width, height)
    if placement == "right":
        return (width - split, 0, width, height), (0, 0, width - split, height)
    if placement == "top":
        return (0, 0, width, split), (0, split, width, height)
    return (0, height - split, width, height), (0, 0, width, height - split)


def reference_prompt(prompt):
    # Also recognize weighted forms such as {reference inset} and 1.2::reference inset::.
    if re.search(r"(?<!\w)reference[ _]+inset(?!\w)", prompt, re.IGNORECASE):
        return prompt
    return "reference inset" + (", " + prompt if prompt.strip() else "")


def _preview_directory():
    try:
        import folder_paths
        return Path(folder_paths.get_temp_directory())
    except ImportError:
        return Path(tempfile.gettempdir())


class NAIReferenceInset:
    DESCRIPTION = "Prepare a reference canvas locally without an API call. Width/height describe the whole canvas; the node shows the smaller cropped output size. Run this node for an actual image preview. Connect inset to NAI Reference Inset Generate when ready."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {"tooltip": "One reference image. Fits without stretching or cropping; transparency is composited on white."}),
            "canvas_width": ("INT", {"default": 1216, "min": 64, "max": 4096, "step": 64, "tooltip": "Whole canvas including the reference. The cropped output will be smaller."}),
            "canvas_height": ("INT", {"default": 832, "min": 64, "max": 4096, "step": 64, "tooltip": "Whole canvas including the reference. The cropped output will be smaller."}),
            "placement": (["left", "right", "top", "bottom"], {"default": "left", "tooltip": "Side occupied by the reference. The other side is generated."}),
            "reference_percent": ("INT", {"default": 50, "min": 10, "max": 75, "tooltip": "Percentage reserved for the reference. Smaller reference space gives a larger output, but may weaken consistency."}),
        }}

    RETURN_TYPES = ("RS_NAI_INSET", "IMAGE", "MASK")
    RETURN_NAMES = ("inset", "canvas", "generation_mask")
    FUNCTION = "prepare"
    CATEGORY = "RS_NovelAI_API/Reference Inset"
    OUTPUT_NODE = True

    def prepare(self, image, canvas_width, canvas_height, placement, reference_percent):
        validate_single_image(image)
        ref_box, target_box = inset_boxes(canvas_width, canvas_height, placement, reference_percent)
        source = tensor_to_pil(image).convert("RGBA")
        white = Image.new("RGBA", source.size, "white")
        source = Image.alpha_composite(white, source).convert("RGB")
        rw, rh = ref_box[2] - ref_box[0], ref_box[3] - ref_box[1]
        border = min(2, (min(rw, rh) - 1) // 2)
        ratio = min((rw - 2 * border) / source.width, (rh - 2 * border) / source.height)
        size = (max(1, round(source.width * ratio)), max(1, round(source.height * ratio)))
        reference = source.resize(size, Image.Resampling.LANCZOS)
        reference = ImageOps.expand(reference, border=border, fill="black")
        canvas = Image.new("RGB", (canvas_width, canvas_height), "white")
        canvas.paste(reference, (ref_box[0] + (rw - reference.width) // 2, ref_box[1] + (rh - reference.height) // 2))
        mask = Image.new("L", canvas.size, 0)
        mask.paste(255, target_box)
        inset = ReferenceInset(canvas, mask, target_box)
        preview_dir = _preview_directory()
        preview_dir.mkdir(parents=True, exist_ok=True)
        name = f"rs_nai_inset_{uuid.uuid4().hex}.png"
        canvas.save(preview_dir / name)
        return {"ui": {
            "images": [{"filename": name, "subfolder": "", "type": "temp"}],
            "rs_nai_inset_size": [canvas_width, canvas_height, target_box[2] - target_box[0], target_box[3] - target_box[1]],
        }, "result": (inset, pil_to_tensor(canvas), torch.from_numpy(np.array(mask).astype(np.float32) / 255).unsqueeze(0))}


class NAIReferenceInsetGenerate:
    DESCRIPTION = "Generate the empty part of a prepared reference canvas and crop it automatically. Adds reference inset once to the prompt. Uses full inpaint strength (1). May spend Anlas; default protection blocks requests. Character coordinates refer to the cropped output. Full canvas and cropped result are both autosaved."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "inset": ("RS_NAI_INSET",),
            "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "Describe the reference character and the new scene. reference inset is added automatically if absent."}),
            "negative_prompt": ("STRING", {"default": "lowres, bad anatomy", "multiline": True}),
            "model": (MODEL_DISPLAY_LIST, {"default": "NAI Diffusion V5 Full", "tooltip": MODEL_SELECTION_TOOLTIP + " V5 Curated inpainting uses V4.5 Curated."}),
            "seed": ("INT", {"default": -1, "min": -1, "max": 0xffffffff}),
            "steps": ("INT", {"default": 28, "min": 1, "max": 50}),
            "cfg_scale": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 30.0, "step": 0.5}),
            "limit_opus_free": ("BOOLEAN", {"default": True, "tooltip": "Reference inset uses ordinary inpainting. True blocks before token access or encoding. False permits possible Anlas spending."}),
        }, "optional": {
            "sampler": (SAMPLER_LIST, {"default": "k_euler_ancestral"}),
            "scheduler": (SCHEDULER_LIST, {"default": "karras"}),
            "characterPrompts": ("LIST", {"tooltip": "Original character prompts. Coordinates 0–1 refer to the generated output and are mapped to the full canvas automatically."}),
        }}

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("image", "full_canvas", "applied_prompt")
    FUNCTION = "generate"
    CATEGORY = "RS_NovelAI_API/Reference Inset"

    def generate(self, inset, prompt, negative_prompt, model, seed, steps, cfg_scale,
                 limit_opus_free=True, sampler="k_euler_ancestral", scheduler="karras", characterPrompts=None):
        if limit_opus_free:
            raise user_error("PAID_BLOCKED", RuntimeError,
                             "Reference inset uses ordinary inpainting and may spend Anlas. Use the preparation node for a free local preview, or set limit_opus_free=False to permit generation.")
        if not isinstance(inset, ReferenceInset):
            raise user_error("INSET_LAYOUT", ValueError, "Connect the inset output of NAI Reference Inset.")
        width, height = inset.canvas.size
        x0, y0, x1, y1 = inset.target_box
        model_id = get_model_id(model)
        validate_character_prompts(model_id, characterPrompts, inpainting=True)
        characters = [CharacterPrompt(c.prompt, c.uc,
                      (x0 + c.center["x"] * (x1 - x0)) / width,
                      (y0 + c.center["y"] * (y1 - y0)) / height) for c in (characterPrompts or [])]
        prompt = reference_prompt(prompt)
        token = get_nai_token()
        seed = secrets.randbelow(0x100000000) if seed == -1 else seed
        parameters = build_common_parameters(width, height, seed, sampler, steps, cfg_scale,
                                             negative_prompt, scheduler=scheduler, model_id=model_id)
        parameters.update(image=pil_to_base64(inset.canvas), mask=pil_to_base64(inset.mask),
                          add_original_image=True, inpaintImg2ImgStrength=1.0, noise=0.0)
        apply_v4_parameters(parameters, model_id, prompt, negative_prompt, characters)
        payload = build_nai_payload(prompt, model_id, "infill", parameters, inpainting=True)
        png_bytes = zip_to_png_bytes(post_nai(token, payload, limit_opus_free=False))
        generated = png_bytes_to_pil(png_bytes)
        if generated.size != (width, height):
            raise user_error("INSET_RESPONSE", RuntimeError,
                             f"Expected a {width}x{height} canvas, received {generated.width}x{generated.height}. The response was not cropped or resized; check the model and server response.")
        composite = Image.composite(generated, inset.canvas, inset.mask)
        cropped = composite.crop(inset.target_box)
        generated.info["rs_nai_inset"] = json.dumps({"version": 1, "canvas_size": [width, height], "crop_box": list(inset.target_box)})
        folder, filename = NovelAIGenerator._get_save_path("NAI_inset", NovelAIGenerator._get_output_directory(), "inset")
        save_png_preserving_metadata(composite, folder / f"{filename}_canvas.png", generated)
        save_png_preserving_metadata(cropped, folder / f"{filename}.png", generated)
        notice(f"Reference inset: canvas {width}×{height}; cropped output {cropped.width}×{cropped.height}. Applied prompt: {prompt}")
        return (pil_to_tensor(cropped), pil_to_tensor(composite), prompt)


NODE_CLASS_MAPPINGS = {"NAIReferenceInset": NAIReferenceInset, "NAIReferenceInsetGenerate": NAIReferenceInsetGenerate}
NODE_DISPLAY_NAME_MAPPINGS = {"NAIReferenceInset": "NAI Reference Inset", "NAIReferenceInsetGenerate": "NAI Reference Inset Generate"}
