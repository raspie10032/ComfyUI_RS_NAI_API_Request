# SPDX-License-Identifier: GPL-3.0-only
"""Small immutable snapshots of successful generation requests, never raw payloads."""
from dataclasses import dataclass

from .diagnostics import notice
from .nai_api import MODEL_ID_MAP


# Seed belongs to each stage. Sizes, strength, payment permission, references,
# images and masks also remain local; none can be replayed by this connection.
INHERITED_FIELDS = (
    "prompt", "negative_prompt", "model", "sampler", "steps", "cfg_scale",
    "scheduler", "cfg_rescale", "prefer_brownian", "variety_boost", "characterPrompts",
)
CONTEXT_MODES = ("inherit_all", "override_selected")


@dataclass(frozen=True)
class UnavailableNAIContext:
    """Keep IMAGE usable while rejecting incomplete context before any request."""
    reasons: tuple


def context_override_inputs():
    """Append controls so older positional widget values retain their meaning."""
    return {
        "context_mode": (list(CONTEXT_MODES), {"default": "inherit_all", "tooltip": "With context enabled, inherit everything or replace only checked fields with this node's values. Unchecked fields still come from context."}),
        **{f"override_{name}": ("BOOLEAN", {"default": False, "tooltip":
            ("Replace the complete character list with characterPrompts, including negatives and positions. No connection clears the list."
             if name == "characterPrompts" else f"Use this node's {name} in override_selected mode. An empty string, zero or False is an intentional replacement.")})
           for name in INHERITED_FIELDS},
    }


def take_context_overrides(options):
    # Do not pass UI controls to the generation/detailing pipeline.
    return {name: options.pop(f"override_{name}", False) for name in INHERITED_FIELDS}


@dataclass(frozen=True)
class ContextCharacter:
    prompt: str
    uc: str
    x: float
    y: float

    @property
    def center(self):
        return {"x": self.x, "y": self.y}


@dataclass(frozen=True)
class NAIContext:
    prompt: str
    negative_prompt: str
    model: str
    sampler: str
    steps: int
    cfg_scale: float
    scheduler: str
    cfg_rescale: float
    prefer_brownian: bool
    variety_boost: bool
    characters: tuple
    # Provenance only, not inputs to the next node.
    source_seed: int
    source_action: str
    source_size: tuple
    references_omitted: bool = False

    def settings(self):
        return {**{name: getattr(self, name) for name in INHERITED_FIELDS if name != "characterPrompts"},
                "characterPrompts": list(self.characters)}


def context_inputs():
    return {
        "nai_context": ("NAI_CONTEXT", {"tooltip": "Connect the previous NAI generation context. Carries prompts, characters and generation settings; seed, size, strength, references and Anlas protection stay local."}),
        "use_context_settings": ("BOOLEAN", {"default": True, "tooltip": "Use connected prompts, characters, model and sampling settings. Turn off to use this node's manual values. Seed always uses this node's setting."}),
    }


def inherit_context(context, enabled, *, mode="inherit_all", manual=None, overrides=None):
    if context is None or not enabled:
        return None
    if isinstance(context, UnavailableNAIContext):
        from .errors import user_error
        raise user_error("METADATA_CONTEXT", ValueError, "; ".join(context.reasons))
    if not isinstance(context, NAIContext):
        raise ValueError("Connect NAI context from NAI Load Image, NAI Image Generator or NAI Img2Img. / NAI 이미지 불러오기·생성·I2I 노드의 NAI 컨텍스트 출력을 연결해 주세요. / NAI画像読み込み・生成・I2Iノードのコンテキスト出力を接続してください。")
    if mode not in CONTEXT_MODES:
        raise ValueError("Choose inherit_all or override_selected for context mode. / 컨텍스트 모드를 전체 사용 또는 선택 항목 변경으로 설정해 주세요. / コンテキストモードを全項目継承または選択項目変更にしてください。")
    settings = context.settings()
    selected = []
    if mode == "override_selected":
        for name, enabled_field in (overrides or {}).items():
            if name not in INHERITED_FIELDS or not isinstance(enabled_field, bool):
                raise ValueError("Invalid context override selection. / 변경 항목은 제공된 스위치로 선택해 주세요. / 変更項目は用意されたスイッチで選択してください。")
            if enabled_field:
                if manual is None or name not in manual:
                    raise ValueError(f"Missing manual value for {name}. / 선택한 항목의 직접 입력값이 없습니다. / 選択項目の手動値がありません。")
                settings[name] = manual[name]
                selected.append(name)
        # None explicitly means no characters, never fallback to the original list.
        settings["characterPrompts"] = list(settings["characterPrompts"] or [])
    notice(f"NAI context: {settings['model']} · {len(settings['characterPrompts'])} character(s) · "
           "Seed, size, strength and Anlas protection use this node's settings.")
    if selected:
        notice("Manual context replacements / 직접 변경 항목 / 手動変更項目: " + ", ".join(selected))
    if context.references_omitted:
        notice("Reference images are not carried by NAI context. Connect Vibe / Precise Reference separately if needed.")
    return settings


def context_from_payload(payload):
    """Read effective values after Medium/Opus normalization and successful POST."""
    p = payload["parameters"]
    positive = p.get("v4_prompt", {}).get("caption", {}).get("char_captions", [])
    negative = p.get("v4_negative_prompt", {}).get("caption", {}).get("char_captions", [])
    characters = tuple(ContextCharacter(
        c["char_caption"], negative[i]["char_caption"] if i < len(negative) else "",
        float(c["centers"][0]["x"]), float(c["centers"][0]["y"]),
    ) for i, c in enumerate(positive))
    return NAIContext(
        prompt=payload["input"], negative_prompt=p["negative_prompt"],
        model=next(name for name, model_id in MODEL_ID_MAP.items() if model_id == payload["model"]),
        sampler=p["sampler"], steps=int(p["steps"]), cfg_scale=p["scale"],
        scheduler=p["noise_schedule"], cfg_rescale=p["cfg_rescale"],
        prefer_brownian=p["prefer_brownian"], variety_boost="skip_cfg_above_sigma" in p,
        characters=characters, source_seed=int(p["seed"]), source_action=payload["action"],
        source_size=(int(p["width"]), int(p["height"])),
        references_omitted=any(p.get(k) for k in ("reference_image_multiple", "director_reference_images")),
    )
