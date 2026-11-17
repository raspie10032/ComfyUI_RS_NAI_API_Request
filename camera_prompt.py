# SPDX-License-Identifier: GPL-3.0-only
"""Recognize standalone prompt tags that describe a different camera view."""
import json
import math
from pathlib import Path
import re

from .camera_tags import filter_prompt_tags


_EPSILON = 1e-8
_NORMALIZE = str.maketrans({"_": " ", "-": " ", "–": " ", "‑": " ", "’": "'"})

_YAW = {
    **dict.fromkeys(("from front", "from the front", "viewed from the front"), ("front", "front quarter")),
    **dict.fromkeys(("from behind", "from the rear", "from back", "viewed from behind"), ("rear", "rear quarter")),
    **dict.fromkeys(("front view", "straight on front view", "straight on",
                     "camera on the character's front"), ("front",)),
    **dict.fromkeys(("rear view", "back view", "straight on rear view",
                     "camera on the character's rear"), ("rear",)),
    **dict.fromkeys(("from side", "from the side", "side view", "side profile", "profile"), ("side",)),
    **dict.fromkeys(("three quarter view", "3/4 view"), ("front quarter", "rear quarter")),
    **dict.fromkeys(("front three quarter view", "three quarter front view", "front 3/4 view"), ("front quarter",)),
    **dict.fromkeys(("rear three quarter view", "three quarter rear view", "rear 3/4 view", "back three quarter view"), ("rear quarter",)),
}
_LATERAL = {
    alias: (side, view)
    for side in ("left", "right")
    for alias, view in (
        (f"from {side}", None), (f"from the {side}", None), (f"from the {side} side", None),
        (f"viewed from the {side} side", None), (f"camera on the character's {side}", "side"),
        (f"{side} profile", "side"), (f"{side} side view", "side"),
        (f"{side} front three quarter view", "front quarter"),
        (f"{side} rear three quarter view", "rear quarter"),
        (f"camera on the character's front {side}", "front quarter"),
        (f"camera on the character's rear {side}", "rear quarter"),
    )
}
_PITCH = {
    **dict.fromkeys(("from above", "high angle", "high angle shot", "high camera angle"), ("high", "overhead")),
    **dict.fromkeys(("from below", "low angle", "low angle shot", "low camera angle"), ("low", "underneath")),
    **dict.fromkeys(("eye level", "eye level shot", "level camera angle"), ("level",)),
    **dict.fromkeys(("overhead", "overhead view", "directly overhead", "directly above", "top down", "top down view",
                     "bird's eye view", "birds eye view", "camera directly above the character"), ("overhead",)),
    **dict.fromkeys(("directly underneath", "directly below", "bottom up view",
                     "worm's eye view", "worms eye view", "camera directly below the character"), ("underneath",)),
}
_SPECIFIC_PITCH = frozenset({
    "slight high camera angle", "slight low camera angle",
    "steep high camera angle", "steep low camera angle",
})
_FACING = {
    **dict.fromkeys(("facing front", "facing forward", "facing viewer", "facing the viewer",
                     "facing camera", "facing the camera"), ("front",)),
    **dict.fromkeys(("facing away", "facing away from viewer", "facing away from the camera",
                     "facing away from the viewer"), ("rear", "rear quarter")),
}
_FACE_TAGS = frozenset({
    "blush", "closed eyes", "closed mouth", "expressionless", "fang", "fangs",
    "frown", "grin", "hair between eyes", "looking at viewer", "looking at the viewer",
    "looking at camera", "looking at the camera", "eye contact", "looking back",
    "looking over shoulder", "looking over the shoulder", "one eye closed",
    "open mouth", "parted lips", "pout", "smile", "smirk", "tongue out", "wink",
})
_EYE_COLOR = re.compile(
    r"(?:(?:light|dark) )?(?:amber|aqua|black|blue|brown|cyan|gold|golden|gray|grey|"
    r"green|hazel|orange|pink|purple|red|silver|teal|violet|white|yellow|heterochromatic) eyes"
)
_EYE_DETAILS = re.compile(r"(?:[a-z]+(?:[ -][a-z]+)* )?(?:pupils?|eyebrows?)")

_QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|“[^”]*”')
_PROTECTED_QUOTE = re.compile(r"\x00(\d+)\x00")


def _direction(azimuth, elevation):
    azimuth, elevation = map(math.radians, (azimuth, elevation))
    horizontal = math.cos(elevation)
    return (horizontal * math.sin(azimuth), math.sin(elevation), horizontal * math.cos(azimuth))


# Match the Anima/MOSS reference geometry while NAI camera weights remain continuous.
_VIEWS = tuple((_direction(yaw, pitch), label) for yaw, pitch, label in
               json.loads(Path(__file__).with_name("camera_views.json").read_text(encoding="utf-8")))


def nearest_view(azimuth, elevation):
    requested = _direction(azimuth, elevation)
    return max(_VIEWS, key=lambda view: sum(a*b for a, b in zip(requested, view[0])))


def _normalize(tag):
    return " ".join(tag.casefold().translate(_NORMALIZE).split()).rstrip(".!?")


def view_direction(view):
    """Describe the bearing and height of the nearest reference view."""
    (x, y, z), _ = view
    side = "left" if x < -_EPSILON else "right" if x > _EPSILON else None
    if abs(z) <= _EPSILON:
        yaw = "side" if side else "pole"
    elif z > 0:
        yaw = "front quarter" if side else "front"
    else:
        yaw = "rear quarter" if side else "rear"
    if abs(y) < _EPSILON:
        pitch = "level"
    elif y > 0:
        pitch = "overhead" if yaw == "pole" else "high"
    else:
        pitch = "underneath" if yaw == "pole" else "low"
    return yaw, side, pitch


def camera_prompt_filter(view, hidden_details=()):
    """Build a filter for the nearest camera reference view."""
    yaw, side, pitch = view_direction(view)
    reference_pitch = view[1]

    def conflicts(tag):
        tag = _normalize(tag)
        if tag in hidden_details:
            return True
        if tag in _YAW:
            return yaw not in _YAW[tag]
        if tag in _LATERAL:
            tag_side, tag_view = _LATERAL[tag]
            return side != tag_side or (tag_view is not None and yaw != tag_view)
        if tag in _PITCH:
            return pitch not in _PITCH[tag]
        if tag in _SPECIFIC_PITCH:
            return tag != reference_pitch
        if yaw != "pole":
            if tag in _FACING:
                return yaw not in _FACING[tag]
            if tag in ("facing left", "facing right"):
                return tag != f"facing {side}"
        return yaw in ("rear", "rear quarter") and (
            tag in _FACE_TAGS or _EYE_COLOR.fullmatch(tag) is not None or _EYE_DETAILS.fullmatch(tag) is not None
        )

    def clean(prompt, syntax):
        quotes = []

        def protect_quote(match):
            quotes.append(match[0])
            return f"\x00{len(quotes) - 1}\x00"

        prompt = _QUOTED.sub(protect_quote, prompt)
        cleaned = filter_prompt_tags(prompt, syntax, conflicts)
        return _PROTECTED_QUOTE.sub(lambda match: quotes[int(match[1])], cleaned) if quotes else cleaned

    return clean
