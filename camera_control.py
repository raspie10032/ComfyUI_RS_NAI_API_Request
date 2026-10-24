# SPDX-License-Identifier: GPL-3.0-only
"""Camera captions shared by the local sampler and NAI nodes; no model patching."""
from dataclasses import is_dataclass, replace
import math


DISTANCE_TAGS = ("extreme close-up", "close-up", "medium shot", "full body", "wide shot")


def blend_stops(value, positions, labels):
    for index, (left, right) in enumerate(zip(positions, positions[1:])):
        if value <= right:
            t = max(0., (value-left)/(right-left))
            mix = (1-math.cos(math.pi*t))/2
            return ((labels[index], 1-mix), (labels[index+1], mix))
    return ((labels[-1], 1.),)


def camera_weights(azimuth=0., elevation=0., distance=.5, roll=0., strength=1.2):
    for name, value, low, high in (("azimuth", azimuth, -180, 180),
            ("elevation", elevation, -90, 90), ("distance", distance, 0, 1),
            ("roll", roll, -45, 45), ("strength", strength, 0, 5)):
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"Camera {name}: use a finite number from {low} to {high}. / 카메라 {name}: {low}~{high}의 숫자를 입력해 주세요.")
    weights = {}
    def add(tag, value):
        weights[tag] = weights.get(tag, 0.) + value*strength
    # At the poles yaw has no meaning. Both ends of the yaw slider are rear view.
    yaw_scale = math.cos(math.radians(elevation))**2
    side = "viewed from the left side" if azimuth < 0 else "viewed from the right side"
    for tag, value in blend_stops(abs(azimuth), (0, 90, 180), ("from front", side, "from behind")):
        add(tag, value*.85*yaw_scale)
    if elevation:
        for tag, value in blend_stops(abs(elevation), (0, 60, 90),
                ("eye level", "from above" if elevation > 0 else "from below",
                 "overhead view" if elevation > 0 else "worm's-eye view")):
            if tag != "eye level":
                add(tag, value*.8)
    for tag, value in blend_stops(distance, (0, .25, .5, .75, 1), DISTANCE_TAGS):
        add(tag, value)
    if roll:
        add("dutch angle", .6*abs(roll)/45)
    return {tag: value for tag, value in weights.items() if value > 1e-12}


def camera_caption(weights, syntax="ComfyUI", weighting="weighted"):
    if syntax not in ("ComfyUI", "NovelAI") or weighting not in ("weighted", "plain"):
        raise ValueError("Choose ComfyUI/NovelAI syntax and weighted/plain camera captions.")
    parts = []
    for tag, value in weights.items():
        # This is the display precision, not a second normalization of the axes.
        if value < .005:
            continue
        number = f"{value:.2f}".rstrip("0").rstrip(".")
        if weighting == "plain":
            if value >= max(weights.values(), default=0)*.5:
                parts.append(tag)
        elif syntax == "NovelAI":
            parts.append(f"{number}::{tag}::")
        else:
            parts.append(f"({tag}:{number})")
    return ", ".join(parts)


class RSCameraControl:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "azimuth": ("FLOAT", {"default": 0., "min": -180., "max": 180., "step": 1., "tooltip": "Horizontal view: 0 front, ±90 side, ±180 rear. / 좌우 시점: 0 정면, ±90 측면, ±180 뒤."}),
            "elevation": ("FLOAT", {"default": 0., "min": -90., "max": 90., "step": 1., "tooltip": "Positive looks down; negative looks up. This adds captions, not a 3D camera. / 양수는 내려다보기, 음수는 올려다보기입니다. 시점 태그를 추가합니다."}),
            "distance": ("FLOAT", {"default": .5, "min": 0., "max": 1., "step": .01, "tooltip": "0 extreme close-up, 0.5 medium shot, 1 wide shot. / 0 극근접, 0.5 중간 거리, 1 원경."}),
            "roll": ("FLOAT", {"default": 0., "min": -45., "max": 45., "step": 1., "tooltip": "Tilt amount adds dutch angle. Text alone cannot guarantee tilt direction. / 기울기 양을 태그로 유도하며 방향까지 보장하지 않습니다."}),
            "strength": ("FLOAT", {"default": 1.2, "min": 0., "max": 5., "step": .05, "tooltip": "Caption weight scale. Start at 0.8–1.4; high values may distort or split the image. / 0.8~1.4부터 시작하세요. 높이면 왜곡·분할이 생길 수 있습니다."}),
            "weighting": (["weighted", "plain"], {"tooltip": "Plain omits numerical weights for models without weighted prompt parsing. / 가중치 문법을 지원하지 않는 경로에는 plain을 사용하세요."}),
            "prompt_syntax": (["ComfyUI", "NovelAI"], {"tooltip": "Used without context. Connected context keeps its own syntax. / 컨텍스트가 없을 때 사용합니다. 연결 시 원본 문법을 따릅니다."}),
            "enabled": ("BOOLEAN", {"default": True, "tooltip": "Off passes the scene through without camera captions. / 끄면 시점 태그를 추가하지 않습니다."}),
            "scope": (["scene_and_characters", "scene_only"], {"tooltip": "Share the view with character regions, or affect only the common caption. Existing text regions and placements stay fixed. / 캐릭터 영역에도 같은 시점을 전달하거나 공통 문장에만 적용합니다. 글자 영역·배치는 유지됩니다."}),
        }, "optional": {
            "context": ("RS_MC_CHARACTER_PIPE,NAI_CONTEXT", {"tooltip": "Final character pipe or NAI context. Character placements and model settings are preserved. / 최종 캐릭터 파이프 또는 NAI 컨텍스트. 캐릭터 배치는 유지됩니다."}),
            "base_prompt": ("STRING", {"forceInput": True, "tooltip": "Optional scene caption, in the context's syntax. Required when a connected pipe has no scene. / 연결 파이프에 공통 프롬프트가 없으면 장면 문장을 연결하세요."}),
        }}

    RETURN_TYPES = ("RS_MC_CHARACTER_PIPE", "STRING", "STRING")
    RETURN_NAMES = ("context", "prompt", "camera_prompt")
    FUNCTION = "apply"
    CATEGORY = "RS/Camera"
    DESCRIPTION = "Camera captions for NAI and local workflows. Use context output for inherited prompts, or prompt output without a context. Character masks/coordinates are not rotated. / NAI·로컬 공용 시점 태그. 컨텍스트 상속에는 컨텍스트 출력을 연결하세요. 마스크·좌표 자체를 회전시키지 않습니다."

    def apply(self, azimuth=0., elevation=0., distance=.5, roll=0., strength=1.2,
              weighting="weighted", prompt_syntax="ComfyUI", enabled=True, scope="scene_and_characters", context=None, base_prompt=None):
        if context is not None and (not is_dataclass(context) or not hasattr(context, "characters")
                or not hasattr(context, "prompt") or not hasattr(context, "syntax")):
            raise ValueError("Connect a finalized RS character pipe or NAI context. / 최종 RS 캐릭터 파이프 또는 NAI 컨텍스트를 연결해 주세요.")
        if base_prompt is not None and not isinstance(base_prompt, str):
            raise ValueError("Connect a text STRING as the scene caption. / 장면 프롬프트는 문자열을 연결해 주세요.")
        if scope not in ("scene_and_characters", "scene_only"):
            raise ValueError("Choose scene_and_characters or scene_only. / 시점 적용 범위를 선택해 주세요.")
        scene = base_prompt if base_prompt is not None else (context.prompt if context is not None else "")
        if enabled and strength and scene is None:
            raise ValueError("This pipe has no scene caption. Connect base_prompt so the sampler's scene is not replaced by camera tags. / 공통 프롬프트가 없는 파이프입니다. base_prompt에 장면 문장을 연결하세요.")
        syntax = context.syntax if context is not None else prompt_syntax
        weights = camera_weights(azimuth, elevation, distance, roll, strength)
        camera = camera_caption(weights, syntax, weighting) if enabled else ""
        prompt = ", ".join(part for part in (scene, camera) if part)
        changes = {"prompt": prompt}
        if context is not None and camera and scope == "scene_and_characters":
            # Regional sampling can suppress an early common caption. Each
            # character must see the same view, using its own prompt syntax.
            character_syntax = getattr(context, "character_syntax", None) or syntax
            caption = camera_caption(weights, character_syntax, weighting)
            characters = []
            for character in context.characters:
                if not is_dataclass(character) or not isinstance(getattr(character, "prompt", None), str):
                    raise ValueError("Invalid character captions in the shared context. / 컨텍스트의 캐릭터 프롬프트 형식을 확인해 주세요.")
                characters.append(replace(character, prompt=", ".join(p for p in (character.prompt, caption) if p)))
            changes["characters"] = tuple(characters)
        output = replace(context, **changes) if context is not None and (camera or base_prompt is not None) else context
        return {"ui": {"camera_caption": [camera], "camera_syntax": [syntax]}, "result": (output, prompt, camera)}
