# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2025 raspie10032

import io
import math
import os
import threading
import time
import zipfile
from email.utils import parsedate_to_datetime

import requests
from dotenv import load_dotenv

from .runtime_control import check_interrupted, wait_until

load_dotenv()

_session = requests.Session()

GENERATE_IMAGE_URL = "https://image.novelai.net/ai/generate-image"
SUBSCRIPTION_URL = "https://image.novelai.net/user/subscription"

MODEL_DISPLAY_LIST = [
    "NAI Diffusion V5 Curated",
    "NAI Diffusion V5 Full",
    "NAI Diffusion V4.5 Curated",
    "NAI Diffusion V4.5 Full",
    "NAI Diffusion V4 Full",
    "NAI Diffusion V4 Curated Preview",
    "NAI Diffusion V3",
    "NAI Diffusion Furry V3"
]

MODEL_ID_MAP = {
    "NAI Diffusion V5 Curated": "nai-diffusion-5-curated",
    "NAI Diffusion V5 Full": "nai-diffusion-5-full",
    "NAI Diffusion V4.5 Curated": "nai-diffusion-4-5-curated",
    "NAI Diffusion V4.5 Full": "nai-diffusion-4-5-full",
    "NAI Diffusion V4 Full": "nai-diffusion-4-full",
    "NAI Diffusion V4 Curated Preview": "nai-diffusion-4-curated-preview",
    "NAI Diffusion V3": "nai-diffusion-3",
    "NAI Diffusion Furry V3": "nai-diffusion-furry-3"
}

INPAINT_MODEL_ID_OVERRIDES = {
    # V5 Curated uses the V4.5 Curated inpainting model until its own is released.
    "nai-diffusion-5-curated": "nai-diffusion-4-5-curated-inpainting",
}

SAMPLER_LIST = [
    "k_dpmpp_2m", "k_dpmpp_sde", "k_dpmpp_2m_sde", "k_dpmpp_2s_ancestral",
    "k_euler_ancestral", "k_euler", "ddim_v3"
]

SCHEDULER_LIST = ["native", "karras", "exponential", "polyexponential"]

OPUS_FREE_MAX_PIXELS = 1024 * 1024
OPUS_FREE_MAX_STEPS = 28
OPUS_V5_MIN_REMAINING_PERCENT = 2
OPUS_FREE_PARAMETER_KEYS = {
    "width", "height", "n_samples", "seed", "extra_noise_seed", "sampler",
    "steps", "scale", "negative_prompt", "cfg_rescale", "prefer_brownian",
    "noise_schedule", "params_version", "legacy", "legacy_v3_extend",
    "skip_cfg_above_sigma", "add_original_image", "legacy_uc", "v4_prompt",
    "v4_negative_prompt",
}

NAI_REQUEST_TIMEOUT = (10, 300)
NAI_SUBSCRIPTION_TIMEOUT = (10, 30)
NAI_REQUEST_INTERVAL = 2.0
_request_lock = threading.Lock()
_next_request_at = 0.0


def _retry_delay(response):
    value = response.headers.get("Retry-After", "60")
    try:
        delay = float(value)
    except (ValueError, TypeError):
        try:
            delay = parsedate_to_datetime(value).timestamp() - time.time()
        except (ValueError, TypeError, OverflowError):
            delay = 60.0
    if not math.isfinite(delay):
        delay = 60.0
    return max(NAI_REQUEST_INTERVAL, delay)

def validate_opus_free_request(payload):
    """Reject requests that cannot qualify for Opus's Anlas-free generation."""
    if payload.get("model") not in MODEL_ID_MAP.values():
        raise RuntimeError("limit_opus_free cannot verify this model; request stopped.")
    if payload.get("action") != "generate":
        raise RuntimeError(
            "limit_opus_free blocks image-to-image and inpainting because they can spend Anlas. "
            "Set it to False to allow paid requests."
        )
    parameters = payload.get("parameters")
    if not isinstance(parameters, dict) or parameters.keys() - OPUS_FREE_PARAMETER_KEYS:
        raise RuntimeError(
            "limit_opus_free blocks base and reference images because they can spend Anlas. "
            "Set it to False to allow paid requests."
        )
    width = parameters.get("width")
    height = parameters.get("height")
    steps = parameters.get("steps")
    if (
        type(width) is not int or type(height) is not int or type(steps) is not int
        or width <= 0 or height <= 0 or width * height > OPUS_FREE_MAX_PIXELS
        or steps < 1 or steps > OPUS_FREE_MAX_STEPS
        or type(parameters.get("n_samples")) is not int or parameters["n_samples"] != 1
    ):
        raise RuntimeError(
            "limit_opus_free requires one image, at most 1024x1024 pixels and 28 steps."
        )


def _verify_opus_subscription(token, model_id):
    """Fail closed on missing or uncertain subscription/usage state."""
    try:
        response = _session.get(
            SUBSCRIPTION_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=NAI_SUBSCRIPTION_TIMEOUT,
        )
        try:
            response.raise_for_status()
            state = response.json()
        finally:
            response.close()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError("Could not verify Opus free-generation eligibility; request stopped.") from exc

    if (
        not isinstance(state, dict)
        or state.get("active") is not True
        or type(state.get("tier")) is not int
        or state["tier"] != 3
    ):
        raise RuntimeError("An active Opus subscription could not be verified; request stopped.")
    if model_id.startswith("nai-diffusion-5"):
        usage = state.get("usage")
        if (
            not isinstance(usage, dict)
            or usage.get("isNegative") is not False
            or type(usage.get("percent")) is not int
            or usage["percent"] < OPUS_V5_MIN_REMAINING_PERCENT
        ):
            raise RuntimeError(
                "V5 Opus free allowance is low or unverifiable; request stopped before generation."
            )


def post_nai(token, payload, url=GENERATE_IMAGE_URL, limit_opus_free=False):
    """Serialize subscription preflight, generation and retries within this process."""
    global _next_request_at
    if limit_opus_free:
        if url != GENERATE_IMAGE_URL or not isinstance(payload, dict):
            raise RuntimeError("limit_opus_free cannot verify this NovelAI request; request stopped.")
        validate_opus_free_request(payload)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    while not _request_lock.acquire(timeout=0.1):
        check_interrupted()
    try:
        for attempt in range(2):
            wait_until(_next_request_at)
            if limit_opus_free:
                _verify_opus_subscription(token, payload.get("model", ""))
                check_interrupted()
            try:
                response = _session.post(
                    url, headers=headers, json=payload, timeout=NAI_REQUEST_TIMEOUT
                )
            finally:
                # Failures also count as attempts; no overlapping transport.
                _next_request_at = time.monotonic() + NAI_REQUEST_INTERVAL
            if response.status_code == 429:
                _next_request_at = time.monotonic() + _retry_delay(response)
                if attempt == 0:
                    response.close()
                    continue
            try:
                response.raise_for_status()
                return response.content
            finally:
                response.close()
    finally:
        _request_lock.release()

def zip_to_png_bytes(zip_bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zipped:
        return zipped.read(zipped.infolist()[0])

def get_model_id(model):
    return MODEL_ID_MAP.get(model, "nai-diffusion-5-curated")


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
            "use_order": use_order,
            "legacy_uc": False,
        },
        "v4_negative_prompt": {
            "caption": {"base_caption": negative_prompt, "char_captions": neg_char_captions},
            "use_coords": False,
            "use_order": False,
            "legacy_uc": False,
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
        "params_version": 4 if model_id and model_id.startswith("nai-diffusion-5") else 3,
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
    if not model_id.startswith(("nai-diffusion-4", "nai-diffusion-5")):
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
    payload_model = (
        INPAINT_MODEL_ID_OVERRIDES.get(model_id, f"{model_id}-inpainting")
        if inpainting else model_id
    )
    return {
        "input": prompt,
        "model": payload_model,
        "action": action,
        "parameters": parameters
    }

def get_nai_token():
    token = os.getenv('NAI_ACCESS_TOKEN') or os.getenv('NAI_API_TOKEN')
    if not token:
        raise RuntimeError("NAI_ACCESS_TOKEN (or NAI_API_TOKEN) not found in environment variables.")
    return token
