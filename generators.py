# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2025 raspie10032

from .errors import user_error

from datetime import datetime
from pathlib import Path
import math
import uuid

import numpy as np
from PIL import Image

from .image_utils import (
    pil_to_base64,
    pil_to_tensor,
    png_bytes_to_pil,
    tensor_to_pil,
    validate_single_image,
    mask_to_pil,
)
from .metadata import autosave, save_inputs, validate_save_options
from .diagnostics import notice
from .generation_context import context_inputs, context_override_inputs, context_from_payload, inherit_context, take_context_overrides, INHERITED_FIELDS
from .nai_api import (
    MODEL_DISPLAY_LIST,
    MODEL_SELECTION_TOOLTIP,
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
    validate_character_prompts,
    MAX_CHARACTER_SLOTS,
)
from .wd_tagger import WDTaggerLoader
from .references import (
    NAIPreciseReference, NAIVibeTransfer, reference_inputs, reference_parameters,
    validate_references,
)

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
    DESCRIPTION = "Choose character_count to show 1–22 slots (default 5). Hidden slots keep their values but are excluded from output. This does not change the common prompt: update tags such as 5girls and phrases such as five women separately. V5 supports 22 active prompts; V4/V4.5 and V5 Curated inpainting support 6. X/Y are normalized 0–1 coordinates; migrate old 0–10 values by dividing by ten. Positions guide the model; they are not hard masks."
    @classmethod
    def INPUT_TYPES(cls):
        inputs = {
            "required": {
                "character1": ("STRING", {"default": "Input Character 1"}),
                "character1_uc": ("STRING", {"default": "negative_prompt"}),
                "character1_x": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.1, "round": 0.1}),
                "character1_y": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.1, "round": 0.1}),
            },
            "optional": {
                "character2_enable": ("BOOLEAN", {"default": True}),
                "character2": ("STRING", {"default": "Input Character 2"}),
                "character2_uc": ("STRING", {"default": "negative_prompt"}),
                "character2_x": ("FLOAT", {"default": 0.1, "min": 0.0, "max": 1.0, "step": 0.1, "round": 0.1}),
                "character2_y": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.1, "round": 0.1}),
                "character3_enable": ("BOOLEAN", {"default": False}),
                "character3": ("STRING", {"default": ""}),
                "character3_uc": ("STRING", {"default": "negative_prompt"}),
                "character3_x": ("FLOAT", {"default": 0.1, "min": 0.0, "max": 1.0, "step": 0.1, "round": 0.1}),
                "character3_y": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.1, "round": 0.1}),
                "character4_enable": ("BOOLEAN", {"default": False}),
                "character4": ("STRING", {"default": ""}),
                "character4_uc": ("STRING", {"default": "negative_prompt"}),
                "character4_x": ("FLOAT", {"default": 0.1, "min": 0.0, "max": 1.0, "step": 0.1, "round": 0.1}),
                "character4_y": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.1, "round": 0.1}),
                "character5_enable": ("BOOLEAN", {"default": False}),
                "character5": ("STRING", {"default": ""}),
                "character5_uc": ("STRING", {"default": "negative_prompt"}),
                "character5_x": ("FLOAT", {"default": 0.1, "min": 0.0, "max": 1.0, "step": 0.1, "round": 0.1}),
                "character5_y": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.1, "round": 0.1}),
            },
        }

        inputs["optional"]["character_count"] = ("INT", {
            "default": 5, "min": 1, "max": MAX_CHARACTER_SLOTS,
            "tooltip": "Show and use only these slots. Hidden values are kept but not sent to NAI. Update the common prompt's person count (e.g. 5girls, five women) separately. V5: 22; V4/V4.5 and V5 Curated inpainting: 6. Disable individual slots to skip them.",
        })
        for i in range(6, MAX_CHARACTER_SLOTS + 1):
            inputs["optional"].update({
                f"character{i}_enable": ("BOOLEAN", {"default": True}),
                f"character{i}": ("STRING", {"default": ""}),
                f"character{i}_uc": ("STRING", {"default": ""}),
                f"character{i}_x": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.1, "round": 0.1}),
                f"character{i}_y": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.1, "round": 0.1}),
            })
        return inputs

    RETURN_TYPES = ("LIST",)
    RETURN_NAMES = ("CharacterPrompt",)
    FUNCTION = "build_character_prompt"
    CATEGORY = "RS_NovelAI_API/Characters"

    def build_character_prompt(self, character_count=5, **kwargs):
        if isinstance(character_count, bool) or not isinstance(character_count, int) or not 1 <= character_count <= MAX_CHARACTER_SLOTS:
            raise user_error("CHARACTER_INPUT", ValueError, "character_count must be an integer from 1 to 22.")
        character_prompts = []
        for i in range(1, character_count + 1):
            enable = kwargs.get(f"character{i}_enable", i == 1 or i >= 6)
            if enable:
                prompt = kwargs.get(f"character{i}", "")
                uc = kwargs.get(f"character{i}_uc", "")
                x_val = kwargs.get(f"character{i}_x", 0)
                y_val = kwargs.get(f"character{i}_y", 0)
                if not all(math.isfinite(float(v)) for v in (x_val, y_val)):
                    raise user_error("CHARACTER_INPUT", ValueError, "Character coordinates must be finite values from 0 to 1.")
                if not all(0 <= float(v) <= 1 for v in (x_val, y_val)):
                    notice(f"Character {i}: coordinates outside 0–1 were clamped. For an old 0–10 workflow, divide saved coordinates by 10 (3 becomes 0.3); check the original values before running generation.")
                x = round(max(0.0, min(1.0, float(x_val))), 1)
                y = round(max(0.0, min(1.0, float(y_val))), 1)
                character_prompts.append(CharacterPrompt(prompt, uc, x, y))
        excluded = [str(i) for i in range(character_count + 1, MAX_CHARACTER_SLOTS + 1)
                    if kwargs.get(f"character{i}_enable", i >= 6) and kwargs.get(f"character{i}", "")]
        if excluded:
            slots = ", ".join(excluded)
            count = len(character_prompts)
            notice(
                f"Using {count} character prompts. Stored slots {slots} are excluded from output, including NAI context. "
                "Update the common prompt's person count separately (e.g. 5girls → 3girls, five women → three women).\n"
                f"캐릭터 프롬프트 {count}개 사용. 저장된 {slots}번 슬롯은 출력과 NAI 컨텍스트에서 제외됩니다. "
                "공통 프롬프트의 인원수는 별도로 바꿔 주세요(예: 5girls → 3girls, five women → three women).\n"
                f"キャラクタープロンプトを{count}件使用。保存済みスロット {slots} は出力とNAIコンテキストから除外されます。"
                "共通プロンプトの人数は別途変更してください（例: 5girls → 3girls、five women → three women）。"
            )
        return (character_prompts,)

class NovelAIGenerator:
    DESCRIPTION = "Generates one image. Connect NAI context to inherit prompts, characters and generation settings, or override only selected fields. Seed, size, references and Anlas protection stay local. The output context and autosave record the effective generated settings after Opus limits and fixed Medium settings. V3/Furry cannot use characterPrompts."
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
        filename = f'{prefix}_{datetime.now().strftime("%y%m%d_%H%M%S_%f")}_{uuid.uuid4().hex[:8]}'
        return autosave_folder, filename

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"default": "prompt here"}),
                "negative_prompt": ("STRING", {"default": "lowres, bad anatomy"}),
                "model": (MODEL_DISPLAY_LIST, {"default": MODEL_DISPLAY_LIST[0], "tooltip": MODEL_SELECTION_TOOLTIP}),
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
                "characterPrompts": ("LIST", {"tooltip": "V5: up to 22 active character prompts; V4/V4.5: up to 6. V5 Curated inpainting uses V4.5 (6)."}),
                "limit_opus_free": ("BOOLEAN", {"default": True}),
                **reference_inputs(),
                **save_inputs(),
                **context_inputs(),
                **context_override_inputs(),
            }
        }

    RETURN_TYPES = ("IMAGE", "NAI_CONTEXT")
    RETURN_NAMES = ("image", "nai_context")
    FUNCTION = "generate"
    CATEGORY = "RS_NovelAI_API/Generation"

    def generate(self, prompt, negative_prompt, model, width, height, sampler, steps, cfg_scale, seed,
                 scheduler="karras", cfg_rescale=0.0, prefer_brownian=False, variety_boost=True, characterPrompts=None,
                 limit_opus_free=True, vibes=None, references=None, normalize_vibe_strengths=True, save_format="PNG", webp_quality=90,
                 nai_context=None, use_context_settings=True, context_mode="inherit_all", **context_options):
        if limit_opus_free and (vibes or references):
            raise user_error("PAID_BLOCKED", RuntimeError,
                "limit_opus_free blocks Vibe and Precise Reference because they can spend Anlas. "
                "Set it to False to allow paid requests."
            )
        overrides = take_context_overrides(context_options)
        if context_options:
            raise TypeError("Unknown context input: " + ", ".join(context_options))
        manual = {name: value for name, value in zip(INHERITED_FIELDS, (
            prompt, negative_prompt, model, sampler, steps, cfg_scale, scheduler,
            cfg_rescale, prefer_brownian, variety_boost, characterPrompts))}
        inherited = inherit_context(nai_context, use_context_settings, mode=context_mode,
                                    manual=manual, overrides=overrides)
        if inherited is not None:
            (prompt, negative_prompt, model, sampler, steps, cfg_scale, scheduler,
             cfg_rescale, prefer_brownian, variety_boost, characterPrompts) = (
                inherited[key] for key in INHERITED_FIELDS)
        validate_save_options(save_format, webp_quality)
        model_id = get_model_id(model)
        validate_character_prompts(model_id, characterPrompts)
        validate_references(model_id, vibes, references, inpainting=False)
        token = get_nai_token()

        if seed == -1:
            seed = np.random.randint(0, 0x7fffffff)

        width, height, steps = apply_opus_free_limits(width, height, steps, limit_opus_free)

        parameters = build_common_parameters(
            width, height, seed, sampler, steps, cfg_scale, negative_prompt,
            scheduler=scheduler, cfg_rescale=cfg_rescale, prefer_brownian=prefer_brownian,
            variety_boost=variety_boost, model_id=model_id
        )
        parameters.update(reference_parameters(
            model_id, token, vibes, references, normalize_vibe_strengths,
            inpainting=False,
        ))
        apply_v4_parameters(parameters, model_id, prompt, negative_prompt, characterPrompts)
        payload = build_nai_payload(prompt, model_id, "generate", parameters)

        result_bytes = post_nai(token, payload, limit_opus_free=limit_opus_free)
        png_bytes = zip_to_png_bytes(result_bytes)
        pil_img = png_bytes_to_pil(png_bytes)

        # Autosave
        save_folder, filename = self._get_save_path('NAI', self.output_dir)
        save_path = autosave(pil_img, save_folder / filename, payload=payload, save_format=save_format, webp_quality=webp_quality)
        print(f'Image saved: {save_path}')

        return (pil_to_tensor(pil_img), context_from_payload(payload))

class NAIImg2ImgNode:
    DESCRIPTION = "Requires one image; split batches before use. General img2img requires limit_opus_free=False and may spend Anlas. Width/height resize the source to the requested size. NAI context inherits prompts, characters, model and sampling settings. Seed remains local. The context output records the settings actually sent by this stage."
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "prompt": ("STRING", {"default": "prompt here"}),
                "negative_prompt": ("STRING", {"default": "lowres, bad anatomy"}),
                "model": (MODEL_DISPLAY_LIST, {"default": MODEL_DISPLAY_LIST[0], "tooltip": MODEL_SELECTION_TOOLTIP}),
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
                "characterPrompts": ("LIST", {"tooltip": "V5: up to 22 active character prompts; V4/V4.5: up to 6. V5 Curated inpainting uses V4.5 (6)."}),
                "limit_opus_free": ("BOOLEAN", {"default": True}),
                **reference_inputs(),
                **save_inputs(),
                **context_inputs(),
                **context_override_inputs(),
            }
        }

    RETURN_TYPES = ("IMAGE", "NAI_CONTEXT")
    RETURN_NAMES = ("image", "nai_context")
    FUNCTION = "generate"
    CATEGORY = "RS_NovelAI_API/Generation"

    def generate(self, image, prompt, negative_prompt, model, width, height, sampler, steps, cfg_scale, strength, seed,
                 scheduler="karras", cfg_rescale=0.0, prefer_brownian=False, noise=0.0, variety_boost=True, characterPrompts=None,
                 limit_opus_free=True, vibes=None, references=None, normalize_vibe_strengths=True, save_format="PNG", webp_quality=90,
                 nai_context=None, use_context_settings=True, context_mode="inherit_all", **context_options):
        if limit_opus_free:
            raise user_error("PAID_BLOCKED", RuntimeError, "limit_opus_free blocks image-to-image because it can spend Anlas. Set it to False to allow paid requests.")
        overrides = take_context_overrides(context_options)
        if context_options:
            raise TypeError("Unknown context input: " + ", ".join(context_options))
        manual = {name: value for name, value in zip(INHERITED_FIELDS, (
            prompt, negative_prompt, model, sampler, steps, cfg_scale, scheduler,
            cfg_rescale, prefer_brownian, variety_boost, characterPrompts))}
        inherited = inherit_context(nai_context, use_context_settings, mode=context_mode,
                                    manual=manual, overrides=overrides)
        if inherited is not None:
            (prompt, negative_prompt, model, sampler, steps, cfg_scale, scheduler,
             cfg_rescale, prefer_brownian, variety_boost, characterPrompts) = (
                inherited[key] for key in INHERITED_FIELDS)
        validate_save_options(save_format, webp_quality)
        model_id = get_model_id(model)
        validate_character_prompts(model_id, characterPrompts)
        validate_references(model_id, vibes, references, inpainting=False)
        validate_single_image(image)
        token = get_nai_token()

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
        parameters.update(reference_parameters(
            model_id, token, vibes, references, normalize_vibe_strengths,
            inpainting=False,
        ))
        apply_v4_parameters(parameters, model_id, prompt, negative_prompt, characterPrompts)
        payload = build_nai_payload(prompt, model_id, "img2img", parameters)

        result_bytes = post_nai(token, payload, limit_opus_free=limit_opus_free)
        png_bytes = zip_to_png_bytes(result_bytes)
        result_pil = png_bytes_to_pil(png_bytes)

        # Autosave
        save_folder, filename = NovelAIGenerator._get_save_path('NAI_i2i', NovelAIGenerator._get_output_directory())
        save_path = autosave(result_pil, save_folder / filename, payload=payload, save_format=save_format, webp_quality=webp_quality)
        print(f'Image saved: {save_path}')

        return (pil_to_tensor(result_pil), context_from_payload(payload))

class NAIInpaintNode:
    DESCRIPTION = "Requires one image and one nonempty mask; white repaints and black preserves. Width/height resize image and mask. Requires limit_opus_free=False and may spend Anlas. V5 Curated falls back to V4.5 Curated inpainting."
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mask": ("MASK",),
                "prompt": ("STRING", {"default": "prompt here"}),
                "negative_prompt": ("STRING", {"default": "lowres, bad anatomy"}),
                "model": (MODEL_DISPLAY_LIST, {"default": MODEL_DISPLAY_LIST[0], "tooltip": MODEL_SELECTION_TOOLTIP}),
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
                "characterPrompts": ("LIST", {"tooltip": "V5: up to 22 active character prompts; V4/V4.5: up to 6. V5 Curated inpainting uses V4.5 (6)."}),
                "limit_opus_free": ("BOOLEAN", {"default": True}),
                **reference_inputs(),
                **save_inputs(),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "generate"
    CATEGORY = "RS_NovelAI_API/Generation"

    def generate(self, image, mask, prompt, negative_prompt, model, width, height, sampler, steps, cfg_scale, strength, seed,
                 scheduler="karras", cfg_rescale=0.0, prefer_brownian=False, noise=0.0, variety_boost=True, characterPrompts=None,
                 limit_opus_free=True, vibes=None, references=None, normalize_vibe_strengths=True, save_format="PNG", webp_quality=90):
        if limit_opus_free:
            raise user_error("PAID_BLOCKED", RuntimeError, "limit_opus_free blocks inpainting because it can spend Anlas. Set it to False to allow paid requests.")
        validate_save_options(save_format, webp_quality)
        model_id = get_model_id(model)
        validate_character_prompts(model_id, characterPrompts, inpainting=True)
        validate_references(model_id, vibes, references, inpainting=True)
        validate_single_image(image)
        pil_mask = mask_to_pil(mask)
        token = get_nai_token()

        # Snap width/height to 64
        width = (width // 64) * 64
        height = (height // 64) * 64

        width, height, steps = apply_opus_free_limits(width, height, steps, limit_opus_free)

        pil_img = tensor_to_pil(image).resize((width, height), Image.LANCZOS)

        # Keep source/mask aligned using the same requested dimensions.
        if pil_mask.size != (image.shape[2], image.shape[1]):
            notice("Mask dimensions differ from the source image; both are resized to the requested output dimensions. Check mask alignment.")
        pil_mask = pil_mask.resize((width, height), Image.NEAREST)

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
        parameters.update(reference_parameters(
            model_id, token, vibes, references, normalize_vibe_strengths,
            inpainting=True,
        ))
        apply_v4_parameters(parameters, model_id, prompt, negative_prompt, characterPrompts)
        payload = build_nai_payload(prompt, model_id, "infill", parameters, inpainting=True)

        result_bytes = post_nai(token, payload, limit_opus_free=limit_opus_free)
        png_bytes = zip_to_png_bytes(result_bytes)
        result_pil = png_bytes_to_pil(png_bytes)

        # Autosave
        save_folder, filename = NovelAIGenerator._get_save_path('NAI_inpaint', NovelAIGenerator._get_output_directory())
        save_path = autosave(result_pil, save_folder / filename, payload=payload, save_format=save_format, webp_quality=webp_quality)
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
        "preview_only": ("BOOLEAN", {"default": False, "tooltip": "No NAI requests. Native SEGM/external MASK shows the final composite mask after threshold, overlap ownership and skips; legacy bbox+SAM previews detections only."}),
        **reference_inputs(),
    }


class NAIFaceDetailerNode:
    DESCRIPTION = "Optional bbox+SAM, native SEGM masks, or a standard MASK from SAM3/another node. auto preserves bbox+SAM when connected. detail_mode=all processes multiple regions sequentially; preview_only sends no NAI request."
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "prompt": ("STRING", {"default": "smiling face, highly detailed"}),
                "negative_prompt": ("STRING", {"default": "lowres, bad anatomy"}),
                "model": (MODEL_DISPLAY_LIST, {"default": MODEL_DISPLAY_LIST[0], "tooltip": MODEL_SELECTION_TOOLTIP}),
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
                "sam_model": ("SAM_MODEL",),
                "segm_detector": ("SEGM_DETECTOR",),
                "detail_mask": ("MASK",),
                "eye_bbox_detector": ("BBOX_DETECTOR",),
                "limit_opus_free": ("BOOLEAN", {"default": True}),
                **_detailer_options(),
                "mask_source": (["auto", "sam", "segm", "external_mask"], {"default": "auto"}),
                **save_inputs(),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("image", "mask_visualization", "matching_report")
    FUNCTION = "detail"
    CATEGORY = "RS_NovelAI_API/FaceDetailer"

    def detail(self, image, prompt, negative_prompt, model, strength, threshold,
               sampler, steps, cfg_scale, bbox_threshold, dilation, crop_factor, scheduler, seed,
               bbox_detector=None, sam_model=None, segm_detector=None, detail_mask=None,
               mask_source="auto", eye_bbox_detector=None, limit_opus_free=True, **detail_options):
        return _run_face_detail(
            image, bbox_detector, segm_detector, sam_model,
            prompt, negative_prompt, model, strength, threshold,
            sampler, steps, cfg_scale, bbox_threshold, dilation,
            crop_factor, scheduler, seed,
            eye_bbox_detector=eye_bbox_detector, limit_opus_free=limit_opus_free,
            detail_mask=detail_mask, mask_source=mask_source,
            primary_uses_native_mask=False, **detail_options,
        )


class NAIFaceDetailerSegmNode:
    DESCRIPTION = "Uses native SEGM masks when SAM is absent, or preserves the previous SEGM-boxes-to-SAM path when SAM is connected. A standard MASK from SAM3/another node can also be selected."
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "segm_detector": ("SEGM_DETECTOR",),
                "prompt": ("STRING", {"default": "smiling face, highly detailed"}),
                "negative_prompt": ("STRING", {"default": "lowres, bad anatomy"}),
                "model": (MODEL_DISPLAY_LIST, {"default": MODEL_DISPLAY_LIST[0], "tooltip": MODEL_SELECTION_TOOLTIP}),
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
                "sam_model": ("SAM_MODEL",),
                "bbox_detector": ("BBOX_DETECTOR",),
                "detail_mask": ("MASK",),
                "eye_bbox_detector": ("BBOX_DETECTOR",),
                "limit_opus_free": ("BOOLEAN", {"default": True}),
                **_detailer_options(),
                "mask_source": (["auto", "sam", "segm", "external_mask"], {"default": "auto"}),
                **save_inputs(),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("image", "mask_visualization", "matching_report")
    FUNCTION = "detail"
    CATEGORY = "RS_NovelAI_API/FaceDetailer"

    def detail(self, image, segm_detector, prompt, negative_prompt, model, strength, threshold,
               sampler, steps, cfg_scale, bbox_threshold, dilation, crop_factor, scheduler, seed,
               sam_model=None, bbox_detector=None, detail_mask=None, mask_source="auto",
               eye_bbox_detector=None, limit_opus_free=True, **detail_options):
        return _run_face_detail(
            image, segm_detector, bbox_detector, sam_model,
            prompt, negative_prompt, model, strength, threshold,
            sampler, steps, cfg_scale, bbox_threshold, dilation,
            crop_factor, scheduler, seed,
            eye_bbox_detector=eye_bbox_detector, limit_opus_free=limit_opus_free,
            detail_mask=detail_mask, mask_source=mask_source,
            primary_uses_native_mask=True, **detail_options,
        )



NODE_CLASS_MAPPINGS = {
    "RSWDTaggerLoader": WDTaggerLoader,
    "NAIVibeTransfer": NAIVibeTransfer,
    "NAIPreciseReference": NAIPreciseReference,
    "NovelAIGenerator": NovelAIGenerator,
    "CharacterPromptSelect": CharacterPromptSelect,
    "NAIImg2ImgNode": NAIImg2ImgNode,
    "NAIInpaintNode": NAIInpaintNode,
    "NAIFaceDetailerNode": NAIFaceDetailerNode,
    "NAIFaceDetailerSegmNode": NAIFaceDetailerSegmNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RSWDTaggerLoader": "NAI WD Tagger Loader (PyTorch)",
    "NAIVibeTransfer": "NAI Vibe Transfer",
    "NAIPreciseReference": "NAI Precise Reference",
    "NovelAIGenerator": "NAI Image Generator",
    "CharacterPromptSelect": "NAI Character Prompt Select",
    "NAIImg2ImgNode": "NAI Img2Img",
    "NAIInpaintNode": "NAI Inpaint",
    "NAIFaceDetailerNode": "NAI Face Detailer",
    "NAIFaceDetailerSegmNode": "Detailer",
}
