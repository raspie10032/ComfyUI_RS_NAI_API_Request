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


def inherit_context(context, enabled):
    if context is None or not enabled:
        return None
    if not isinstance(context, NAIContext):
        raise ValueError("Connect NAI context from NAI Image Generator or NAI Img2Img. / NAI 생성 또는 I2I 노드의 NAI 컨텍스트 출력을 연결해 주세요. / NAI生成またはI2Iノードのコンテキスト出力を接続してください。")
    notice(f"NAI context: {context.model} · {len(context.characters)} character(s) · "
           "using connected generation settings. Seed, size, strength and Anlas protection use this node's settings.")
    if context.references_omitted:
        notice("Reference images are not carried by NAI context. Connect Vibe / Precise Reference separately if needed.")
    return context.settings()


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
