# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2025 raspie10032

from .errors import mark_api_error, user_error

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
from .request_delay import current_timer

load_dotenv()

_session = requests.Session()

GENERATE_IMAGE_URL = "https://image.novelai.net/ai/generate-image"
SUBSCRIPTION_URL = "https://image.novelai.net/user/subscription"

MODEL_DISPLAY_LIST = [
    "NAI Diffusion V5 Curated",
    "NAI Diffusion V5 Full",
    "NAI Diffusion V5 Full — Medium Effort",
    "NAI Diffusion V4.5 Curated",
    "NAI Diffusion V4.5 Full",
    "NAI Diffusion V4 Full",
    "NAI Diffusion V4 Curated Preview",
    "NAI Diffusion V3",
    "NAI Diffusion Furry V3"
]

MODEL_SELECTION_TOOLTIP = (
    "V5 Full Medium Effort always uses 14 steps, Euler Ancestral, zero CFG Rescale, "
    "and fixed Heavy Undesired Content. Custom base/character negative prompts "
    "are ignored. Prompt Guidance remains adjustable. Image-to-image and "
    "inpainting require limit_opus_free=False and can spend Anlas."
)

MODEL_ID_MAP = {
    "NAI Diffusion V5 Curated": "nai-diffusion-5-curated",
    "NAI Diffusion V5 Full": "nai-diffusion-5-full",
    "NAI Diffusion V5 Full — Medium Effort": "nai-diffusion-5-full-medium",
    "NAI Diffusion V4.5 Curated": "nai-diffusion-4-5-curated",
    "NAI Diffusion V4.5 Full": "nai-diffusion-4-5-full",
    "NAI Diffusion V4 Full": "nai-diffusion-4-full",
    "NAI Diffusion V4 Curated Preview": "nai-diffusion-4-curated-preview",
    "NAI Diffusion V3": "nai-diffusion-3",
    "NAI Diffusion Furry V3": "nai-diffusion-furry-3"
}

V5_FULL_MEDIUM_MODEL_ID = "nai-diffusion-5-full-medium"
V5_FULL_MEDIUM_INPAINT_MODEL_ID = "nai-diffusion-5-full-medium-inpainting"
MEDIUM_EFFORT_STEPS = 14
MEDIUM_EFFORT_SAMPLER = "k_euler_ancestral"
MEDIUM_EFFORT_UNDESIRED_CONTENT = (
    "lowres, artistic error, film grain, scan artifacts, worst quality, bad quality, "
    "jpeg artifacts, very displeasing, chromatic aberration, dithering, halftone, "
    "screentone, multiple views, logo, too many watermarks, negative space, blank page"
)

INPAINT_MODEL_ID_OVERRIDES = {
    # V5 Curated uses the V4.5 Curated inpainting model until its own is released.
    "nai-diffusion-5-curated": "nai-diffusion-4-5-curated-inpainting",
    V5_FULL_MEDIUM_MODEL_ID: V5_FULL_MEDIUM_INPAINT_MODEL_ID,
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
OPUS_FREE_FOCUSED_INPAINT_PARAMETER_KEYS = OPUS_FREE_PARAMETER_KEYS | {
    "image", "mask", "inpaintImg2ImgStrength", "noise", "img2img",
}
OPUS_FREE_FOCUSED_INPAINT_MODELS = {
    INPAINT_MODEL_ID_OVERRIDES.get(model_id, f"{model_id}-inpainting")
    for model_id in MODEL_ID_MAP.values()
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


def _medium_effort_fixed_uc(payload, parameters):
    prompt = payload.get("input")
    if not isinstance(prompt, str):
        return False
    expected = MEDIUM_EFFORT_UNDESIRED_CONTENT
    if "nsfw" not in prompt.lower():
        expected = f"nsfw, {expected}"
    if parameters.get("negative_prompt") != expected:
        return False

    structured = parameters.get("v4_negative_prompt")
    caption = structured.get("caption") if isinstance(structured, dict) else None
    if not isinstance(caption, dict) or caption.get("base_caption") != expected:
        return False
    character_captions = caption.get("char_captions")
    return isinstance(character_captions, list) and all(
        isinstance(character, dict) and character.get("char_caption") == ""
        for character in character_captions
    )


def validate_opus_free_request(payload, allow_opus_focused_inpaint=False):
    """Reject requests that cannot qualify for Opus's Anlas-free generation."""
    action = payload.get("action")
    focused_inpaint = allow_opus_focused_inpaint and action == "infill"
    allowed_models = (
        OPUS_FREE_FOCUSED_INPAINT_MODELS
        if focused_inpaint
        else MODEL_ID_MAP.values()
    )
    if payload.get("model") not in allowed_models:
        raise user_error("FREE_CONDITIONS", RuntimeError, "limit_opus_free cannot verify this model; request stopped.")
    if action != "generate" and not focused_inpaint:
        raise user_error("PAID_BLOCKED", RuntimeError,
            "limit_opus_free blocks image-to-image and inpainting because they can spend Anlas. "
            "Set it to False to allow paid requests."
        )
    parameters = payload.get("parameters")
    allowed_keys = (
        OPUS_FREE_FOCUSED_INPAINT_PARAMETER_KEYS
        if focused_inpaint
        else OPUS_FREE_PARAMETER_KEYS
    )
    if not isinstance(parameters, dict) or parameters.keys() - allowed_keys:
        raise user_error("PAID_BLOCKED", RuntimeError,
            "limit_opus_free blocks base and reference images because they can spend Anlas. "
            "Set it to False to allow paid requests."
        )
    if payload.get("model") in {
        V5_FULL_MEDIUM_MODEL_ID,
        V5_FULL_MEDIUM_INPAINT_MODEL_ID,
    } and (
        parameters.get("steps") != MEDIUM_EFFORT_STEPS
        or parameters.get("sampler") != MEDIUM_EFFORT_SAMPLER
        or parameters.get("cfg_rescale") not in (0, 0.0)
        or not _medium_effort_fixed_uc(payload, parameters)
    ):
        raise user_error("FREE_CONDITIONS", RuntimeError,
            "limit_opus_free requires Medium Effort's fixed sampling and Undesired Content settings."
        )
    if focused_inpaint and (
        not isinstance(parameters.get("image"), str)
        or not parameters["image"]
        or not isinstance(parameters.get("mask"), str)
        or not parameters["mask"]
        or parameters.get("add_original_image") is not True
        or type(parameters.get("inpaintImg2ImgStrength")) not in (int, float)
        or not math.isfinite(parameters["inpaintImg2ImgStrength"])
        or not 0 <= parameters["inpaintImg2ImgStrength"] <= 1
        or type(parameters.get("noise")) not in (int, float)
        or not math.isfinite(parameters["noise"])
    ):
        raise user_error("FREE_CONDITIONS", RuntimeError,
            "limit_opus_free cannot verify this focused inpainting request; request stopped."
        )
    if focused_inpaint and "img2img" in parameters:
        nested = parameters["img2img"]
        if (
            not payload["model"].startswith(("nai-diffusion-4", "nai-diffusion-5"))
            or not isinstance(nested, dict)
            or set(nested) != {"strength", "color_correct"}
            or type(nested.get("strength")) not in (int, float)
            or not 0 <= nested["strength"] < 1
            or nested["strength"] != parameters["inpaintImg2ImgStrength"]
            or nested.get("color_correct") is not True
        ):
            raise user_error("FREE_CONDITIONS", RuntimeError,
                "limit_opus_free cannot verify this focused inpainting strength; request stopped."
            )
    width = parameters.get("width")
    height = parameters.get("height")
    steps = parameters.get("steps")
    if (
        type(width) is not int or type(height) is not int or type(steps) is not int
        or width <= 0 or height <= 0 or width * height > OPUS_FREE_MAX_PIXELS
        or (focused_inpaint and (width > 1024 or height > 1024))
        or steps < 1 or steps > OPUS_FREE_MAX_STEPS
        or type(parameters.get("n_samples")) is not int or parameters["n_samples"] != 1
    ):
        raise user_error("FREE_CONDITIONS", RuntimeError,
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
        mark_api_error(exc, phase="subscription", token=token)
        raise user_error(exc.rs_nai_code, RuntimeError, "Could not verify Opus free-generation eligibility; request stopped.") from exc

    if (
        not isinstance(state, dict)
        or state.get("active") is not True
        or type(state.get("tier")) is not int
        or state["tier"] != 3
    ):
        raise user_error("OPUS_REQUIRED", RuntimeError, "An active Opus subscription could not be verified; request stopped.")
    if model_id.startswith("nai-diffusion-5"):
        usage = state.get("usage")
        if (
            not isinstance(usage, dict)
            or usage.get("isNegative") is not False
            or type(usage.get("percent")) is not int
            or usage["percent"] < OPUS_V5_MIN_REMAINING_PERCENT
        ):
            raise user_error("V5_ALLOWANCE", RuntimeError,
                "V5 Opus free allowance is low or unverifiable; request stopped before generation."
            )


def post_nai(
    token,
    payload,
    url=GENERATE_IMAGE_URL,
    limit_opus_free=False,
    allow_opus_focused_inpaint=False,
):
    """Serialize subscription preflight, generation and retries within this process."""
    global _next_request_at
    if limit_opus_free:
        if url != GENERATE_IMAGE_URL or not isinstance(payload, dict):
            raise user_error("FREE_CONDITIONS", RuntimeError, "limit_opus_free cannot verify this NovelAI request; request stopped.")
        validate_opus_free_request(payload, allow_opus_focused_inpaint)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    while not _request_lock.acquire(timeout=0.1):
        check_interrupted()
    try:
        timer = current_timer.get()
        for attempt in range(2):
            if timer is not None and timer.seconds > 0:
                delay_until = time.monotonic() + timer.seconds
                timer.wait(max(_next_request_at, delay_until), retry=attempt > 0)
            else:
                wait_until(_next_request_at)
            if limit_opus_free:
                _verify_opus_subscription(token, payload.get("model", ""))
                check_interrupted()
            try:
                response = _session.post(
                    url, headers=headers, json=payload, timeout=NAI_REQUEST_TIMEOUT
                )
            except requests.RequestException as exc:
                mark_api_error(exc, phase="generation" if url == GENERATE_IMAGE_URL else "vibe encoding", token=token)
                raise
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
                content = response.content
                if url == GENERATE_IMAGE_URL:
                    from .diagnostics import record_request
                    record_request(payload)
                return content
            except requests.RequestException as exc:
                mark_api_error(exc, phase="generation" if url == GENERATE_IMAGE_URL else "vibe encoding", token=token)
                raise
            finally:
                response.close()
    finally:
        _request_lock.release()

def zip_to_png_bytes(zip_bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zipped:
        images = [item for item in zipped.infolist()
                  if not item.is_dir() and item.filename.lower().endswith(".png")]
        if len(images) != 1:
            raise user_error("IMAGE_RESPONSE", ValueError, "NovelAI response must contain exactly one PNG image; no image was saved.")
        return zipped.read(images[0])

def get_model_id(model):
    if model not in MODEL_ID_MAP:
        raise user_error("MODEL", ValueError, "Unknown NovelAI model. Select a model from the current node list.")
    return MODEL_ID_MAP[model]


MAX_CHARACTER_SLOTS = 22


def character_limit(model_id):
    if model_id.startswith("nai-diffusion-5"):
        return MAX_CHARACTER_SLOTS
    if model_id.startswith("nai-diffusion-4"):
        return 6
    return 0


def validate_character_prompts(model_id, character_prompts, *, inpainting=False):
    if inpainting:
        model_id = INPAINT_MODEL_ID_OVERRIDES.get(model_id, f"{model_id}-inpainting")
    count = len(character_prompts or [])
    limit = character_limit(model_id)
    if count and not limit:
        raise user_error("CHARACTER_MODEL", ValueError, "characterPrompts requires V4/V4.5/V5. Disconnect it for V3/Furry; these models cannot apply character slots.")
    if count > limit:
        raise user_error("CHARACTER_LIMIT", ValueError,
            f"{model_id} supports at most {limit} character prompts; received {count}. "
            "Reduce character_count or disable unused slots. V5 Curated inpainting uses V4.5 (6 characters)."
        )


def default_skip_cfg_above_sigma(model_id):
    if "4-5" in model_id:
        return 58
    if "nai-diffusion-4" in model_id:
        return 19
    return None


def apply_opus_free_limits(width, height, steps, limit_opus_free):
    original = (width, height, steps)
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

    if original != (width, height, steps):
        from .diagnostics import notice
        notice(f"Opus limit adjusted {original[0]}x{original[1]}, {original[2]} steps to {width}x{height}, {steps} steps.")
    return width, height, steps


def notice_character_count_difference(prompt, character_prompts):
    """Explain explicit count-tag mismatches without rewriting scene intent.

    Count only standalone, positive numeric tags. Natural-language counts and
    conflicting tags are ambiguous; this is guidance, not prompt validation.
    """
    if not character_prompts:
        return
    import re
    counts = {}
    tags = []
    for part in re.split(r"[,\n]", prompt):
        match = re.fullmatch(
            r"(?:([0-9]+(?:\.[0-9]+)?)::\s*)?([1-9]\d*)\s*(girls?|boys?|people|persons?|characters?)(?:\s*::)?",
            part.strip(), re.IGNORECASE,
        )
        if not match or (match[1] is not None and float(match[1]) <= 0):
            continue
        kind = match[3].lower()
        kind = "girls" if kind.startswith("girl") else "boys" if kind.startswith("boy") else "total"
        counts.setdefault(kind, set()).add(int(match[2]))
        tags.append(f"{match[2]}{match[3]}")
    if not counts or any(len(values) != 1 for values in counts.values()):
        return
    gender_total = sum(next(iter(counts[k])) for k in ("girls", "boys") if k in counts)
    total = next(iter(counts["total"])) if "total" in counts else gender_total
    if ("total" in counts and gender_total and gender_total != total) or total == len(character_prompts):
        return
    from .diagnostics import notice
    active = len(character_prompts)
    label = ", ".join(dict.fromkeys(tags))
    notice(
        f"Common prompt count tags ({label}) describe {total} people; {active} character prompts are active. "
        "Changing character_count does not rewrite the common prompt. If changing the scene's person count, update its tags and wording too.\n"
        f"공통 프롬프트의 인원 태그({label})는 {total}명, 활성 캐릭터 프롬프트는 {active}개입니다. "
        "캐릭터 슬롯 수를 바꿔도 공통 프롬프트는 그대로입니다. 그림의 인원수를 바꾸려면 태그와 문장도 수정해 주세요.\n"
        f"共通プロンプトの人数タグ（{label}）は{total}人、有効なキャラクタープロンプトは{active}件です。"
        "スロット数を変更しても共通プロンプトは変わりません。描く人数を変える場合はタグと文章も修正してください。"
    )


def build_v4_prompt(
    prompt,
    negative_prompt,
    character_prompts=None,
    use_coords=None,
    use_order=True,
    allow_character_uc=True,
):
    notice_character_count_difference(prompt, character_prompts)
    char_captions = []
    neg_char_captions = []
    if character_prompts:
        for cp in character_prompts:
            center = getattr(cp, "center", {"x": 0.5, "y": 0.5})
            char_captions.append({"char_caption": getattr(cp, "prompt", ""), "centers": [center]})
            neg_char_captions.append({
                "char_caption": getattr(cp, "uc", "") if allow_character_uc else "",
                "centers": [center],
            })

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
    validate_character_prompts(model_id, character_prompts)
    if not model_id.startswith(("nai-diffusion-4", "nai-diffusion-5")):
        return parameters

    medium_effort = model_id == V5_FULL_MEDIUM_MODEL_ID
    if medium_effort:
        from .diagnostics import notice
        notice("Medium Effort sends 14 steps, Euler Ancestral, CFG Rescale 0 and fixed Heavy UC. Base and character negative prompts are ignored.")
        negative_prompt = MEDIUM_EFFORT_UNDESIRED_CONTENT
        if "nsfw" not in prompt.lower():
            negative_prompt = f"nsfw, {negative_prompt}"
        parameters.update({
            "steps": MEDIUM_EFFORT_STEPS,
            "sampler": MEDIUM_EFFORT_SAMPLER,
            "cfg_rescale": 0.0,
            "negative_prompt": negative_prompt,
        })

    parameters.update({
        "add_original_image": True,
        "legacy_uc": False,
        **build_v4_prompt(
            prompt,
            negative_prompt,
            character_prompts=character_prompts,
            use_coords=use_coords,
            use_order=use_order,
            allow_character_uc=not medium_effort,
        )
    })
    return parameters


def build_nai_payload(prompt, model_id, action, parameters, inpainting=False):
    payload_model = (
        INPAINT_MODEL_ID_OVERRIDES.get(model_id, f"{model_id}-inpainting")
        if inpainting else model_id
    )
    for key in ("v4_prompt", "v4_negative_prompt"):
        validate_character_prompts(
            payload_model, parameters.get(key, {}).get("caption", {}).get("char_captions", [])
        )
    if inpainting and payload_model != f"{model_id}-inpainting":
        from .diagnostics import notice
        notice(f"Inpainting uses {payload_model} for the selected model.")
    if inpainting and model_id.startswith(("nai-diffusion-4", "nai-diffusion-5")):
        # The UI strength field alone is not the API's inpainting control.
        # Match the official client: partial denoising uses nested img2img;
        # full-strength infill omits it. Do not mutate the caller's parameters.
        parameters = dict(parameters)
        strength = parameters.get("inpaintImg2ImgStrength", 1.0)
        if strength != 1.0:
            parameters["img2img"] = {"strength": strength, "color_correct": True}
        else:
            parameters.pop("img2img", None)
    return {
        "input": prompt,
        "model": payload_model,
        "action": action,
        "parameters": parameters
    }

def get_nai_token():
    token = os.getenv('NAI_ACCESS_TOKEN') or os.getenv('NAI_API_TOKEN')
    if not token:
        raise user_error("TOKEN_MISSING", RuntimeError, "NAI_ACCESS_TOKEN (or NAI_API_TOKEN) not found in environment variables.")
    return token
