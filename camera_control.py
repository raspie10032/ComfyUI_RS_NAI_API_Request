# SPDX-License-Identifier: GPL-3.0-only
"""Camera captions shared by the local sampler and NAI nodes; no model patching."""
from dataclasses import is_dataclass, replace
import math


DISTANCE_TAGS = ("extreme close-up", "close-up", "medium shot", "full body", "wide shot")
RANDOM_RANGES = {
    "balanced": ((-90., 90.), (-35., 35.), (.25, .85), (-10., 10.)),
    "full": ((-180., 180.), (-90., 90.), (0., 1.), (-45., 45.)),
}


def random_camera(mode, seed):
    """Portable seeded PRNG, shared with the editor. Never changes image seed."""
    if mode not in RANDOM_RANGES:
        raise ValueError("Choose balanced/full random view. / 랜덤 구도 모드를 선택해 주세요.")
    if type(seed) is not int or not 0 <= seed <= 0xffffffff:
        raise ValueError("Camera random seed: use an integer from 0 to 4294967295. / 카메라 랜덤 시드는 0~4294967295 정수입니다.")
    state = seed
    result = {}
    for name, (low, high) in zip(("azimuth", "elevation", "distance", "roll"), RANDOM_RANGES[mode]):
        state = (1664525*state + 1013904223) & 0xffffffff
        result[name] = low + (high-low)*(state/4294967296)
    return result


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
            "random_mode": (["off", "balanced", "full"], {"default": "off", "tooltip": "Random view overrides the four manual axes. Balanced avoids rear/pole/extreme framing; full uses all ranges. / 랜덤 구도는 수동 각도·거리·기울기를 대신합니다. balanced는 극단 시점을 피하고 full은 전체 범위입니다."}),
            "random_seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffff, "control_after_generate": True, "tooltip": "Camera seed only. Fixed reproduces the view; randomize changes it after each queued generation. / 카메라 전용 시드. fixed는 구도 유지, randomize는 생성마다 변경합니다. 이미지 생성 시드는 바꾸지 않습니다."}),
            "layout_sync": (["fixed", "distance_and_roll", "perspective"], {"default": "fixed", "tooltip": "perspective tilts the flat mask plane with view angles; distance_and_roll only zooms/rotates. Text stays fixed. / perspective는 좌우·상하 각도로 평면 마스크를 원근 변형합니다. distance_and_roll은 거리·회전만 연동. 글자는 고정."}),
            "canvas_aspect": ("FLOAT", {"default": 1., "min": .1, "max": 10., "step": .001, "tooltip": "Output width divided by height. Use the sampler's ratio to avoid stretched mask rotation. / 생성 너비÷높이. 샘플러와 같은 비율로 맞추세요."}),
        }}

    RETURN_TYPES = ("RS_MC_CHARACTER_PIPE", "STRING", "STRING")
    RETURN_NAMES = ("context", "prompt", "camera_prompt")
    FUNCTION = "apply"
    CATEGORY = "RS/Camera"
    DESCRIPTION = "Shared camera captions and optional mask zoom, rotation and flat-plane perspective. / 공용 카메라 시점. 마스크 확대·축소·회전과 평면 원근 변형을 선택할 수 있습니다."

    def apply(self, azimuth=0., elevation=0., distance=.5, roll=0., strength=1.2,
              weighting="weighted", prompt_syntax="ComfyUI", enabled=True, scope="scene_and_characters", context=None, base_prompt=None,
              random_mode="off", random_seed=0, layout_sync="fixed", canvas_aspect=1.):
        if layout_sync not in ("fixed", "distance_and_roll", "perspective"):
            raise ValueError("Choose fixed, distance_and_roll or perspective layout sync. / 마스크 배치 연동 방식을 선택해 주세요.")
        from .camera_layout import framing, camera_layout, layout_preview
        framing(.5, 0, canvas_aspect)
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
        # Native NAI character editors may still carry legacy mutable slots.
        # Ask the pipe to normalize them without importing its backend here.
        if enabled and strength and callable(getattr(context, "as_camera_context", None)):
            context = context.as_camera_context()
        syntax = context.syntax if context is not None else prompt_syntax
        if random_mode not in ("off", "balanced", "full"):
            raise ValueError("Choose off/balanced/full random view. / 랜덤 구도 모드를 선택해 주세요.")
        if enabled and strength and random_mode != "off":
            view = random_camera(random_mode, random_seed)
            azimuth, elevation, distance, roll = (view[k] for k in ("azimuth", "elevation", "distance", "roll"))
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
        source_regions = []
        if context is not None:
            # Preview must not make an old NAI-only context require the local
            # extension unless the user explicitly requests layout conversion.
            try:
                source_regions = layout_preview(context)
            except (ValueError, ImportError):
                if enabled and strength and layout_sync != "fixed":
                    raise
        if output is not None and enabled and strength and layout_sync != "fixed":
            output = camera_layout(output, distance, roll, canvas_aspect, azimuth, elevation,
                                   perspective=layout_sync == "perspective")
        return {"ui": {"camera_caption": [camera], "camera_syntax": [syntax],
                       "camera_regions": [source_regions],
                       "camera_layout": [{"mode": layout_sync, "aspect": canvas_aspect}],
                       "camera_values": [{"azimuth": azimuth, "elevation": elevation, "distance": distance, "roll": roll}]},
                "result": (output, prompt, camera)}


class NAICameraControl(RSCameraControl):
    """NAI-menu entry; shares the exact camera and layout implementation."""
    @classmethod
    def INPUT_TYPES(cls):
        fields = super().INPUT_TYPES()
        fields["required"]["prompt_syntax"] = (["NovelAI", "ComfyUI"], {
            "tooltip": "Used without context. Connected context keeps its own syntax. / 컨텍스트가 없을 때 사용합니다. 연결 시 원본 문법을 따릅니다."
        })
        return fields

    CATEGORY = "RS_NovelAI_API/Camera"
    DESCRIPTION = (
        "Camera captions, random views and character-center transforms for NovelAI. "
        "NAI receives captions and centers, not silhouette masks. Shared masks stay available for local round trips. / "
        "NAI 시점·랜덤 구도·캐릭터 중심 좌표 연동. NAI에는 태그와 중심 좌표를 보내며 "
        "실루엣 마스크는 로컬 왕복용으로 보존합니다."
    )
