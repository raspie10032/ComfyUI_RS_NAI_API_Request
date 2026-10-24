# SPDX-License-Identifier: GPL-3.0-only
"""Per-execution notices, without adding saved widgets or output sockets."""

import logging
import inspect
from contextvars import ContextVar
from functools import wraps

from .errors import explain_exception
from .runtime_control import is_interruption

_messages = ContextVar("rs_nai_messages", default=None)
_requests = ContextVar("rs_nai_requests", default=None)


def notice(message):
    messages = _messages.get()
    if messages is None:
        logging.warning("[RS NAI] %s", message)
    elif message not in messages:
        messages.append(message)
        logging.warning("[RS NAI] %s", message)


def record_request(payload):
    """Expose only generation settings from the successful final HTTP payload."""
    state = _requests.get()
    if state is None:
        return
    from .nai_api import MODEL_ID_MAP

    parameters = payload["parameters"]
    base_model = payload["model"].removesuffix("-inpainting")
    model_name = next((name for name, value in MODEL_ID_MAP.items() if value == base_model), payload["model"])
    # Explicit allowlist: images, masks, tokens and local-only pipe data never enter UI.
    keys = ("width", "height", "seed", "sampler", "steps", "scale", "noise_schedule",
            "cfg_rescale", "prefer_brownian", "skip_cfg_above_sigma", "strength",
            "inpaintImg2ImgStrength", "noise")
    summary = {key: parameters[key] for key in keys if key in parameters}
    structured = parameters.get("v4_prompt", {})
    characters = structured.get("caption", {}).get("char_captions", [])
    summary.update(model=payload["model"], model_name=model_name, action=payload["action"],
                   characters=len(characters),
                   coordinates=bool(characters) and bool(structured.get("use_coords")),
                   negative_mode="fixed_heavy" if "-medium" in payload["model"] else "custom",
                   vibes=len(parameters.get("reference_image_multiple", [])),
                   references=len(parameters.get("director_reference_images", [])))
    state["count"] += 1
    state["last"] = {**summary, "request_count": state["count"]}


def node_notices(cls):
    """Keep direct Python tuple returns; expose notices in ComfyUI's UI result."""
    input_types = cls.INPUT_TYPES
    function = getattr(cls, cls.FUNCTION)
    takes_unique_id = "unique_id" in inspect.signature(function).parameters

    @classmethod
    def inputs(subclass):
        schema = input_types()
        schema["hidden"] = {**schema.get("hidden", {}), "unique_id": "UNIQUE_ID"}
        return schema

    @wraps(function)
    def run(self, *args, unique_id=None, **kwargs):
        messages = []
        marker = _messages.set(messages)
        requests = {"count": 0, "last": None}
        request_marker = _requests.set(requests)
        try:
            if takes_unique_id:
                kwargs["unique_id"] = unique_id
            result = function(self, *args, **kwargs)
        except Exception as exc:
            # ComfyUI must still recognize cancellation and OOM by their type.
            if not is_interruption(exc):
                explain_exception(exc)
            raise
        finally:
            _messages.reset(marker)
            _requests.reset(request_marker)
        if unique_id is None:
            return result
        ui = {"rs_nai_notice": messages,
              "rs_nai_parameters": [requests["last"]] if requests["last"] else []}
        if isinstance(result, dict):
            return {**result, "ui": {**result.get("ui", {}), **ui}}
        return {"ui": ui, "result": result}

    cls.INPUT_TYPES = inputs
    setattr(cls, cls.FUNCTION, run)
    return cls
