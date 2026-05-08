# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2025 raspie10032

import os
import requests
import zipfile
import io
import time
from dotenv import load_dotenv
from .image_utils import pil_to_tensor, png_bytes_to_pil, tensor_to_pil

load_dotenv()

_session = requests.Session()

GENERATE_IMAGE_URL = "https://image.novelai.net/ai/generate-image"

MODEL_DISPLAY_LIST = [
    "NAI Diffusion V4.5 Curated",
    "NAI Diffusion V4.5 Full",
    "NAI Diffusion V4 Full",
    "NAI Diffusion V4 Curated Preview",
    "NAI Diffusion V3",
    "NAI Diffusion Furry V3",
    "NAI Diffusion V2"
]

MODEL_ID_MAP = {
    "NAI Diffusion V4.5 Curated": "nai-diffusion-4-5-curated",
    "NAI Diffusion V4.5 Full": "nai-diffusion-4-5-full",
    "NAI Diffusion V4 Full": "nai-diffusion-4-full",
    "NAI Diffusion V4 Curated Preview": "nai-diffusion-4-curated-preview",
    "NAI Diffusion V3": "nai-diffusion-3",
    "NAI Diffusion Furry V3": "nai-diffusion-furry-3",
    "NAI Diffusion V2": "nai-diffusion-2"
}

SAMPLER_LIST = [
    "k_dpmpp_2m", "k_dpmpp_sde", "k_dpmpp_2m_sde", "k_dpmpp_2s_ancestral",
    "k_euler_ancestral", "k_euler", "ddim_v3"
]

SCHEDULER_LIST = ["native", "karras", "exponential", "polyexponential"]

OPUS_FREE_MAX_PIXELS = 1024 * 1024
OPUS_FREE_MAX_STEPS = 28

def post_nai(token, payload, url=GENERATE_IMAGE_URL):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    try:
        response = _session.post(url, headers=headers, json=payload)
        
        if response.status_code == 429:
            print("NAI API: 429 Too Many Requests. Sleeping for 60 seconds...")
            time.sleep(60)
            response = _session.post(url, headers=headers, json=payload)
            
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"NAI API Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        raise e

def zip_to_png_bytes(zip_bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zipped:
        return zipped.read(zipped.infolist()[0])

def get_model_id(model):
    return MODEL_ID_MAP.get(model, "nai-diffusion-4-5-curated")


def default_skip_cfg_above_sigma(model_id):
    if "4-5" in model_id:
        return 58
    if "nai-diffusion-4" in model_id:
        return 19
    return None


def apply_opus_free_limits(width, height, steps, limit_opus_free):
    if not limit_opus_free:
        return width, height, steps

    steps = min(steps, OPUS_FREE_MAX_STEPS)

    if width * height > OPUS_FREE_MAX_PIXELS:
        import math
        scale = math.sqrt(OPUS_FREE_MAX_PIXELS / (width * height))
        width = max(64, int(width * scale) // 64 * 64)
        height = max(64, int(height * scale) // 64 * 64)
        # Floor-rounding can still exceed the limit when one dimension is
        # clamped to the 64 minimum; reduce the larger dimension until safe.
        while width * height > OPUS_FREE_MAX_PIXELS:
            if width >= height:
                width = max(64, width - 64)
            else:
                height = max(64, height - 64)

    return width, height, steps


def build_v4_prompt(prompt, negative_prompt, character_prompts=None, use_coords=None, use_order=True):
    char_captions = []
    neg_char_captions = []
    if character_prompts:
        for cp in character_prompts:
            center = getattr(cp, "center", {"x": 0.5, "y": 0.5})
            char_captions.append({"char_caption": getattr(cp, "prompt", ""), "centers": [center]})
            neg_char_captions.append({"char_caption": getattr(cp, "uc", ""), "centers": [center]})

    if use_coords is None:
        use_coords = bool(char_captions)

    return {
        "v4_prompt": {
            "caption": {"base_caption": prompt, "char_captions": char_captions},
            "use_coords": use_coords,
            "use_order": use_order
        },
        "v4_negative_prompt": {
            "caption": {"base_caption": negative_prompt, "char_captions": neg_char_captions},
            "use_coords": False,
            "use_order": False
        }
    }


def build_common_parameters(width, height, seed, sampler, steps, cfg_scale, negative_prompt,
                            scheduler="karras", cfg_rescale=0.0, prefer_brownian=False,
                            variety_boost=True, model_id=None):
    parameters = {
        "width": width,
        "height": height,
        "n_samples": 1,  # Intentionally fixed: ComfyUI batching is handled outside the NAI request for this node set
        "seed": seed,
        "extra_noise_seed": seed,
        "sampler": sampler,
        "steps": steps,
        "scale": cfg_scale,
        "negative_prompt": negative_prompt,
        "cfg_rescale": cfg_rescale,
        "prefer_brownian": prefer_brownian,
        "noise_schedule": scheduler,
        "params_version": 3,
        "legacy": False,
        "legacy_v3_extend": False
    }

    if variety_boost and model_id:
        skip_cfg = default_skip_cfg_above_sigma(model_id)
        if skip_cfg is not None:
            parameters["skip_cfg_above_sigma"] = skip_cfg

    return parameters


def apply_v4_parameters(parameters, model_id, prompt, negative_prompt, character_prompts=None,
                        use_coords=None, use_order=True):
    if "nai-diffusion-4" not in model_id:
        return parameters

    parameters.update({
        "add_original_image": True,
        "legacy_uc": False,
        **build_v4_prompt(
            prompt,
            negative_prompt,
            character_prompts=character_prompts,
            use_coords=use_coords,
            use_order=use_order,
        )
    })
    return parameters


def build_nai_payload(prompt, model_id, action, parameters, inpainting=False):
    payload_model = f"{model_id}-inpainting" if inpainting else model_id
    return {
        "input": prompt,
        "model": payload_model,
        "action": action,
        "parameters": parameters
    }

def get_nai_token():
    token = os.getenv('NAI_ACCESS_TOKEN') or os.getenv('NAI_API_TOKEN')
    if not token:
        print("Warning: NAI_ACCESS_TOKEN (or NAI_API_TOKEN) not found in environment variables.")
    return token
