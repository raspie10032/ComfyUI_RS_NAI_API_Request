# SPDX-License-Identifier: GPL-3.0-only
"""Validate recovered values before exposing an executable NAI context."""
import math
import json

from .generation_context import ContextCharacter, NAIContext, UnavailableNAIContext
from .nai_api import MODEL_ID_MAP, SAMPLER_LIST, SCHEDULER_LIST, character_limit

AUTO_MODEL = "from_metadata"


def restore_context(data, model_choice=AUTO_MODEL):
    """Return a context or an explicit unavailable value plus local UI diagnostics.

    Never replace missing metadata with a consumer's default prompt. Incomplete
    files still work as IMAGE/MASK; enabled context consumers fail before auth.
    """
    issues = []

    def issue(code, field=""):
        value = {"code": code, "field": field}
        if value not in issues:
            issues.append(value)

    blocked = {"detailer_not_base", "inset_canvas_coordinates", "automatic_coordinates",
               "invalid_characters", "invalid_comment", "invalid_record",
               "invalid_exif", "invalid_hidden_metadata", "invalid_settings", "local_generation_settings"}
    for warning in data.get("warnings", []):
        if warning in blocked:
            issue(warning)
    settings = dict(data.get("settings", {}))
    if model_choice != AUTO_MODEL:
        if model_choice not in MODEL_ID_MAP:
            issue("invalid", "model")
        else:
            settings["model"] = model_choice

    def valid(name, predicate):
        if name not in settings:
            issue("missing", name)
        elif not predicate(settings[name]):
            issue("invalid", name)

    def number(value, low, high):
        return type(value) in (int, float) and math.isfinite(value) and low <= value <= high

    for name in ("prompt", "negative_prompt"):
        valid(name, lambda v: isinstance(v, str))
    for name, choices in (("model", MODEL_ID_MAP), ("sampler", SAMPLER_LIST), ("scheduler", SCHEDULER_LIST)):
        valid(name, lambda v, choices=choices: isinstance(v, str) and v in choices)
    for name, low, high in (("steps", 1, 50), ("seed", 0, 0xffffffff), ("width", 1, 65536), ("height", 1, 65536)):
        valid(name, lambda v, low=low, high=high: type(v) is int and low <= v <= high)
    for name, high in (("cfg_scale", 30), ("cfg_rescale", 1)):
        valid(name, lambda v, high=high: number(v, 0, high))
    for name in ("prefer_brownian", "variety_boost"):
        valid(name, lambda v: type(v) is bool)

    characters = []
    for i, char in enumerate(data.get("characters", []), 1):
        field = f"character {i}"
        if not isinstance(char, dict) or not all(isinstance(char.get(k), str) for k in ("prompt", "negative_prompt")):
            issue("invalid", field)
            continue
        centers = char.get("centers")
        if not isinstance(centers, list) or len(centers) != 1:
            issue("single_center_required", field)
            continue
        center = centers[0]
        if not isinstance(center, dict) or not all(number(center.get(k), 0, 1) for k in ("x", "y")):
            issue("invalid", field + " coordinates")
            continue
        characters.append(ContextCharacter(char["prompt"], char["negative_prompt"], center["x"], center["y"]))
    model = settings.get("model")
    if isinstance(model, str) and model in MODEL_ID_MAP and len(characters) > character_limit(MODEL_ID_MAP[model]):
        issue("character_limit", "characters")
    report = {"status": "unavailable" if issues else "ready", "issues": issues,
              "model_choice": model_choice, "character_count": len(characters)}
    if issues:
        reasons = tuple(f"{i['code']}: {i['field']}" if i['field'] else i['code'] for i in issues)
        return UnavailableNAIContext(reasons), report

    record = data.get("record", {})
    request = record.get("base_generation" if data.get("settings_origin") == "nai_context" else "request", {})
    action = request.get("action", data.get("operation", "unknown"))
    if action not in ("generate", "img2img", "infill"):
        action = "unknown"
    report["model"] = model
    return NAIContext(
        **{key: settings[key] for key in ("prompt", "negative_prompt", "model", "sampler", "steps",
                                         "cfg_scale", "scheduler", "cfg_rescale", "prefer_brownian", "variety_boost")},
        characters=tuple(characters), source_seed=settings["seed"], source_action=action,
        source_size=(settings["width"], settings["height"]),
        references_omitted="references_omitted" in data.get("warnings", []),
        local_record_json=json.dumps(data["local_record"], allow_nan=False) if data.get("local_record") else None,
    ), report
