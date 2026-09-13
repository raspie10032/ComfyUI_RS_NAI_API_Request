# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2025 raspie10032

from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from .image_utils import (
    pil_to_base64,
    pil_to_tensor,
    png_bytes_to_pil,
    tensor_to_pil,
)
from .nai_api import (
    MODEL_DISPLAY_LIST,
    SAMPLER_LIST,
    SCHEDULER_LIST,
    apply_opus_free_limits,
    apply_v4_parameters,
    build_common_parameters,
    build_nai_payload,
    get_model_id,
    get_nai_token,
    post_nai,
    zip_to_png_bytes,
)
from .wd_tagger import WDTaggerLoader

# Constants
BOX_SIZE = 32
GRID_STEP = 8

# Helper Functions
def mask_to_grid_boxes(sam_mask_np, img_w, img_h, threshold=0.3):
    """
    SAM mask to BOX_SIZE(32px) grid boxes.
    Sliding with GRID_STEP(8px).
    """
    result = np.zeros((img_h, img_w), dtype=np.uint8)
    # Ensure sam_mask_np is 2D and 0-255
    if len(sam_mask_np.shape) == 3:
        sam_mask_np = sam_mask_np.squeeze()

    for y in range(0, img_h - BOX_SIZE + 1, GRID_STEP):
        for x in range(0, img_w - BOX_SIZE + 1, GRID_STEP):
            region = sam_mask_np[y:y + BOX_SIZE, x:x + BOX_SIZE]
            if region.mean() / 255.0 >= threshold:
                result[y:y + BOX_SIZE, x:x + BOX_SIZE] = 255
    return Image.fromarray(result, mode="L")

class CharacterPrompt:
    def __init__(self, prompt, uc, x, y):
        self.prompt = prompt
        self.uc = uc
        self.center = {"x": x, "y": y}

class CharacterPromptSelect:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "character1": ("STRING", {"default": "Input Character 1"}),
                "character1_uc": ("STRING", {"default": "negative_prompt"}),
                "character1_x": ("INT", {"default": 3, "min": 0, "max": 10}),
                "character1_y": ("INT", {"default": 3, "min": 0, "max": 10}),
            },
            "optional": {
                "character2_enable": ("BOOLEAN", {"default": True}),
                "character2": ("STRING", {"default": "Input Character 2"}),
                "character2_uc": ("STRING", {"default": "negative_prompt"}),
                "character2_x": ("INT", {"default": 1, "min": 0, "max": 10}),
                "character2_y": ("INT", {"default": 3, "min": 0, "max": 10}),
                "character3_enable": ("BOOLEAN", {"default": False}),
                "character3": ("STRING", {"default": ""}),
                "character3_uc": ("STRING", {"default": "negative_prompt"}),
                "character3_x": ("INT", {"default": 1, "min": 0, "max": 10}),
                "character3_y": ("INT", {"default": 3, "min": 0, "max": 10}),
                "character4_enable": ("BOOLEAN", {"default": False}),
                "character4": ("STRING", {"default": ""}),
                "character4_uc": ("STRING", {"default": "negative_prompt"}),
                "character4_x": ("INT", {"default": 1, "min": 0, "max": 10}),
                "character4_y": ("INT", {"default": 3, "min": 0, "max": 10}),
                "character5_enable": ("BOOLEAN", {"default": False}),
                "character5": ("STRING", {"default": ""}),
                "character5_uc": ("STRING", {"default": "negative_prompt"}),
                "character5_x": ("INT", {"default": 1, "min": 0, "max": 10}),
                "character5_y": ("INT", {"default": 3, "min": 0, "max": 10}),
            },
        }

    RETURN_TYPES = ("LIST",)
    RETURN_NAMES = ("CharacterPrompt",)
    FUNCTION = "build_character_prompt"
    CATEGORY = "RS_NovelAI_API/Characters"

    def build_character_prompt(self, **kwargs):
        character_prompts = []
        for i in range(1, 6):
            enable = kwargs.get(f"character{i}_enable", True) if i == 1 else kwargs.get(f"character{i}_enable", False)
            if enable:
                prompt = kwargs.get(f"character{i}", "")
                uc = kwargs.get(f"character{i}_uc", "")
                x_val = kwargs.get(f"character{i}_x", 0)
                y_val = kwargs.get(f"character{i}_y", 0)
                x = max(0.0, min(1.0, float(x_val) / 10.0))
                y = max(0.0, min(1.0, float(y_val) / 10.0))
                character_prompts.append(CharacterPrompt(prompt, uc, x, y))
        return (character_prompts,)

class NovelAIGenerator:
    def __init__(self):
        self.output_dir = self._get_output_directory()

    @classmethod
    def _get_output_directory(cls):
        try:
            import folder_paths
            return folder_paths.get_output_directory()
        except ImportError:
            output_dir = Path('./output')
            output_dir.mkdir(exist_ok=True)
            return str(output_dir)

    @classmethod
    def _get_save_path(cls, prefix, output_dir, subfolder=None):
        current_date = datetime.now().strftime('%Y-%m-%d')
        autosave_folder = Path(output_dir) / current_date / 'NAI_autosave'
        if subfolder:
            autosave_folder = autosave_folder / subfolder
        autosave_folder.mkdir(parents=True, exist_ok=True)
        filename = f'{prefix}_{datetime.now().strftime("%y%m%d_%H%M%S")}'
        return autosave_folder, filename

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"default": "prompt here"}),
                "negative_prompt": ("STRING", {"default": "lowres, bad anatomy"}),
                "model": (MODEL_DISPLAY_LIST, {"default": MODEL_DISPLAY_LIST[0]}),
                "width": ("INT", {"default": 832, "min": 64, "max": 4096, "step": 64}),
                "height": ("INT", {"default": 1216, "min": 64, "max": 4096, "step": 64}),
                "sampler": (SAMPLER_LIST, {"default": "k_euler"}),
                "steps": ("INT", {"default": 28, "min": 1, "max": 50}),
                "cfg_scale": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 30.0, "step": 0.5}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 0xffffffff}),
            },
            "optional": {
                "scheduler": (SCHEDULER_LIST, {"default": "karras"}),
                "cfg_rescale": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "prefer_brownian": ("BOOLEAN", {"default": False}),
                "variety_boost": ("BOOLEAN", {"default": True}),
                "characterPrompts": ("LIST",),
                "limit_opus_free": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "generate"
    CATEGORY = "RS_NovelAI_API/Generation"

    def generate(self, prompt, negative_prompt, model, width, height, sampler, steps, cfg_scale, seed,
                 scheduler="karras", cfg_rescale=0.0, prefer_brownian=False, variety_boost=True, characterPrompts=None,
                 limit_opus_free=True):
        token = get_nai_token()
        model_id = get_model_id(model)

        if seed == -1:
            seed = np.random.randint(0, 0x7fffffff)

        width, height, steps = apply_opus_free_limits(width, height, steps, limit_opus_free)

        parameters = build_common_parameters(
            width, height, seed, sampler, steps, cfg_scale, negative_prompt,
            scheduler=scheduler, cfg_rescale=cfg_rescale, prefer_brownian=prefer_brownian,
            variety_boost=variety_boost, model_id=model_id
        )
        apply_v4_parameters(parameters, model_id, prompt, negative_prompt, characterPrompts)
        payload = build_nai_payload(prompt, model_id, "generate", parameters)

        result_bytes = post_nai(token, payload)
        png_bytes = zip_to_png_bytes(result_bytes)
        pil_img = png_bytes_to_pil(png_bytes)

        # Autosave
        save_folder, filename = self._get_save_path('NAI', self.output_dir)
        save_path = save_folder / f'{filename}.png'
        save_path.write_bytes(png_bytes)
        print(f'Image saved: {save_path}')

        return (pil_to_tensor(pil_img),)

class NAIImg2ImgNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "prompt": ("STRING", {"default": "prompt here"}),
                "negative_prompt": ("STRING", {"default": "lowres, bad anatomy"}),
                "model": (MODEL_DISPLAY_LIST, {"default": MODEL_DISPLAY_LIST[0]}),
                "width": ("INT", {"default": 832, "min": 64, "max": 4096, "step": 64}),
                "height": ("INT", {"default": 1216, "min": 64, "max": 4096, "step": 64}),
                "sampler": (SAMPLER_LIST, {"default": "k_euler"}),
                "steps": ("INT", {"default": 28, "min": 1, "max": 50}),
                "cfg_scale": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 30.0, "step": 0.5}),
                "strength": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 0xffffffff}),
            },
            "optional": {
                "scheduler": (SCHEDULER_LIST, {"default": "karras"}),
                "cfg_rescale": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "prefer_brownian": ("BOOLEAN", {"default": False}),
                "noise": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "variety_boost": ("BOOLEAN", {"default": True}),
                "characterPrompts": ("LIST",),
                "limit_opus_free": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "generate"
    CATEGORY = "RS_NovelAI_API/Generation"

    def generate(self, image, prompt, negative_prompt, model, width, height, sampler, steps, cfg_scale, strength, seed,
                 scheduler="karras", cfg_rescale=0.0, prefer_brownian=False, noise=0.0, variety_boost=True, characterPrompts=None,
                 limit_opus_free=True):
        token = get_nai_token()
        model_id = get_model_id(model)

        width, height, steps = apply_opus_free_limits(width, height, steps, limit_opus_free)

        pil_img = tensor_to_pil(image).resize((width, height), Image.LANCZOS)

        if seed == -1:
            seed = np.random.randint(0, 0x7fffffff)

        parameters = build_common_parameters(
            width, height, seed, sampler, steps, cfg_scale, negative_prompt,
            scheduler=scheduler, cfg_rescale=cfg_rescale, prefer_brownian=prefer_brownian,
            variety_boost=variety_boost, model_id=model_id
        )
        parameters.update({
            "strength": strength,
            "noise": noise,
            "image": pil_to_base64(pil_img),
        })
        apply_v4_parameters(parameters, model_id, prompt, negative_prompt, characterPrompts)
        payload = build_nai_payload(prompt, model_id, "img2img", parameters)

        result_bytes = post_nai(token, payload)
        png_bytes = zip_to_png_bytes(result_bytes)
        result_pil = png_bytes_to_pil(png_bytes)

        # Autosave
        save_folder, filename = NovelAIGenerator._get_save_path('NAI_i2i', NovelAIGenerator._get_output_directory())
        save_path = save_folder / f'{filename}.png'
        save_path.write_bytes(png_bytes)
        print(f'Image saved: {save_path}')

        return (pil_to_tensor(result_pil),)

class NAIInpaintNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mask": ("MASK",),
                "prompt": ("STRING", {"default": "prompt here"}),
                "negative_prompt": ("STRING", {"default": "lowres, bad anatomy"}),
                "model": (MODEL_DISPLAY_LIST, {"default": MODEL_DISPLAY_LIST[0]}),
                "width": ("INT", {"default": 832, "min": 64, "max": 4096, "step": 64}),
                "height": ("INT", {"default": 1216, "min": 64, "max": 4096, "step": 64}),
                "sampler": (SAMPLER_LIST, {"default": "k_euler"}),
                "steps": ("INT", {"default": 28, "min": 1, "max": 50}),
                "cfg_scale": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 30.0, "step": 0.5}),
                "strength": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 0xffffffff}),
            },
            "optional": {
                "scheduler": (SCHEDULER_LIST, {"default": "karras"}),
                "cfg_rescale": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "prefer_brownian": ("BOOLEAN", {"default": False}),
                "noise": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "variety_boost": ("BOOLEAN", {"default": True}),
                "characterPrompts": ("LIST",),
                "limit_opus_free": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "generate"
    CATEGORY = "RS_NovelAI_API/Generation"

    def generate(self, image, mask, prompt, negative_prompt, model, width, height, sampler, steps, cfg_scale, strength, seed,
                 scheduler="karras", cfg_rescale=0.0, prefer_brownian=False, noise=0.0, variety_boost=True, characterPrompts=None, limit_opus_free=True):
        token = get_nai_token()
        model_id = get_model_id(model)

        # Snap width/height to 64
        width = (width // 64) * 64
        height = (height // 64) * 64

        width, height, steps = apply_opus_free_limits(width, height, steps, limit_opus_free)

        pil_img = tensor_to_pil(image).resize((width, height), Image.LANCZOS)

        # Mask preprocessing
        if len(mask.shape) == 3:
            mask_np = (mask[0].cpu().numpy() * 255).astype(np.uint8)
        else:
            mask_np = (mask.cpu().numpy() * 255).astype(np.uint8)
        pil_mask = Image.fromarray(mask_np, mode="L").resize((width, height), Image.NEAREST)

        if seed == -1:
            seed = np.random.randint(0, 0x7fffffff)

        parameters = build_common_parameters(
            width, height, seed, sampler, steps, cfg_scale, negative_prompt,
            scheduler=scheduler, cfg_rescale=cfg_rescale, prefer_brownian=prefer_brownian,
            variety_boost=variety_boost, model_id=model_id
        )
        parameters.update({
            "image": pil_to_base64(pil_img),
            "mask": pil_to_base64(pil_mask),
            "add_original_image": True,
            "inpaintImg2ImgStrength": strength,
            "noise": noise,
        })
        apply_v4_parameters(parameters, model_id, prompt, negative_prompt, characterPrompts)
        payload = build_nai_payload(prompt, model_id, "infill", parameters, inpainting=True)

        result_bytes = post_nai(token, payload)
        png_bytes = zip_to_png_bytes(result_bytes)
        result_pil = png_bytes_to_pil(png_bytes)

        # Autosave
        save_folder, filename = NovelAIGenerator._get_save_path('NAI_inpaint', NovelAIGenerator._get_output_directory())
        save_path = save_folder / f'{filename}.png'
        save_path.write_bytes(png_bytes)
        print(f'Image saved: {save_path}')

        return (pil_to_tensor(result_pil),)

def _run_face_detail(*args, **kwargs):
    from .detailer import run_face_detail
    return run_face_detail(*args, **kwargs)


def _detailer_options():
    return {
        "detail_mode": (["first", "all"], {"default": "first"}),
        "matching_mode": (["shared", "wd14"], {"default": "shared"}),
        "characterPrompts": ("LIST",),
        "tagger": ("RS_WD_TAGGER",),
        "match_min_score": ("FLOAT", {"default": 0.25, "min": 0.01, "max": 1.0, "step": 0.01}),
        "match_min_margin": ("FLOAT", {"default": 0.08, "min": 0.01, "max": 1.0, "step": 0.01}),
        "match_crop_factor": ("FLOAT", {"default": 2.0, "min": 1.0, "max": 5.0, "step": 0.1}),
        "max_regions": ("INT", {"default": 16, "min": 1, "max": 64}),
        "preview_only": ("BOOLEAN", {"default": False}),
    }


class NAIFaceDetailerNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "bbox_detector": ("BBOX_DETECTOR",),
                "sam_model": ("SAM_MODEL",),
                "prompt": ("STRING", {"default": "smiling face, highly detailed"}),
                "negative_prompt": ("STRING", {"default": "lowres, bad anatomy"}),
                "model": (MODEL_DISPLAY_LIST, {"default": MODEL_DISPLAY_LIST[0]}),
                "strength": ("FLOAT", {"default": 0.55, "min": 0.0, "max": 1.0, "step": 0.01}),
                "threshold": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.01}),
                "sampler": (SAMPLER_LIST, {"default": "k_euler"}),
                "steps": ("INT", {"default": 28, "min": 1, "max": 50}),
                "cfg_scale": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 30.0, "step": 0.5}),
                "bbox_threshold": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "dilation": ("INT", {"default": 4, "min": 0, "max": 64}),
                "crop_factor": ("FLOAT", {"default": 3.0, "min": 1.0, "max": 10.0, "step": 0.1}),
                "scheduler": (SCHEDULER_LIST, {"default": "karras"}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 0xffffffff}),
            },
            "optional": {
                "segm_detector": ("SEGM_DETECTOR",),
                "eye_bbox_detector": ("BBOX_DETECTOR",),
                "limit_opus_free": ("BOOLEAN", {"default": True}),
                **_detailer_options(),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("image", "mask_visualization", "matching_report")
    FUNCTION = "detail"
    CATEGORY = "RS_NovelAI_API/FaceDetailer"

    def detail(self, image, bbox_detector, sam_model, prompt, negative_prompt, model, strength, threshold,
               sampler, steps, cfg_scale, bbox_threshold, dilation, crop_factor, scheduler, seed,
               segm_detector=None, eye_bbox_detector=None, limit_opus_free=True, **detail_options):
        return _run_face_detail(
            image, bbox_detector, segm_detector, sam_model,
            prompt, negative_prompt, model, strength, threshold,
            sampler, steps, cfg_scale, bbox_threshold, dilation,
            crop_factor, scheduler, seed,
            eye_bbox_detector=eye_bbox_detector, limit_opus_free=limit_opus_free, **detail_options,
        )


class NAIFaceDetailerSegmNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "segm_detector": ("SEGM_DETECTOR",),
                "sam_model": ("SAM_MODEL",),
                "prompt": ("STRING", {"default": "smiling face, highly detailed"}),
                "negative_prompt": ("STRING", {"default": "lowres, bad anatomy"}),
                "model": (MODEL_DISPLAY_LIST, {"default": MODEL_DISPLAY_LIST[0]}),
                "strength": ("FLOAT", {"default": 0.55, "min": 0.0, "max": 1.0, "step": 0.01}),
                "threshold": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.01}),
                "sampler": (SAMPLER_LIST, {"default": "k_euler"}),
                "steps": ("INT", {"default": 28, "min": 1, "max": 50}),
                "cfg_scale": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 30.0, "step": 0.5}),
                "bbox_threshold": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "dilation": ("INT", {"default": 4, "min": 0, "max": 64}),
                "crop_factor": ("FLOAT", {"default": 3.0, "min": 1.0, "max": 10.0, "step": 0.1}),
                "scheduler": (SCHEDULER_LIST, {"default": "karras"}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 0xffffffff}),
            },
            "optional": {
                "bbox_detector": ("BBOX_DETECTOR",),
                "eye_bbox_detector": ("BBOX_DETECTOR",),
                "limit_opus_free": ("BOOLEAN", {"default": True}),
                **_detailer_options(),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("image", "mask_visualization", "matching_report")
    FUNCTION = "detail"
    CATEGORY = "RS_NovelAI_API/FaceDetailer"

    def detail(self, image, segm_detector, sam_model, prompt, negative_prompt, model, strength, threshold,
               sampler, steps, cfg_scale, bbox_threshold, dilation, crop_factor, scheduler, seed,
               bbox_detector=None, eye_bbox_detector=None, limit_opus_free=True, **detail_options):
        return _run_face_detail(
            image, segm_detector, bbox_detector, sam_model,
            prompt, negative_prompt, model, strength, threshold,
            sampler, steps, cfg_scale, bbox_threshold, dilation,
            crop_factor, scheduler, seed,
            eye_bbox_detector=eye_bbox_detector, limit_opus_free=limit_opus_free, **detail_options,
        )



NODE_CLASS_MAPPINGS = {
    "RSWDTaggerLoader": WDTaggerLoader,
    "NovelAIGenerator": NovelAIGenerator,
    "CharacterPromptSelect": CharacterPromptSelect,
    "NAIImg2ImgNode": NAIImg2ImgNode,
    "NAIInpaintNode": NAIInpaintNode,
    "NAIFaceDetailerNode": NAIFaceDetailerNode,
    "NAIFaceDetailerSegmNode": NAIFaceDetailerSegmNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RSWDTaggerLoader": "NAI WD Tagger Loader (PyTorch)",
    "NovelAIGenerator": "NAI Image Generator",
    "CharacterPromptSelect": "NAI Character Prompt Select",
    "NAIImg2ImgNode": "NAI Img2Img",
    "NAIInpaintNode": "NAI Inpaint",
    "NAIFaceDetailerNode": "NAI Face Detailer",
    "NAIFaceDetailerSegmNode": "Detailer",
}
