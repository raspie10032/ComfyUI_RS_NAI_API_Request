# SPDX-License-Identifier: GPL-3.0-only
"""Subject details appropriate to the selected camera view and framing."""
import re

from .camera_prompt import _normalize, _QUOTED, view_direction
from .camera_tags import iter_prompt_tags


_HEAD_FRAMING = frozenset({
    "extreme close up", "extreme closeup", "close up", "closeup", "face close up", "head close up",
    "close up shot", "extreme close up shot", "facial close up", "facial portrait", "headshot", "head shot", "face focus",
})
_BODY_FRAMING = frozenset({
    "bust shot", "chest up", "head and shoulders", "shoulder up",
    "upper body", "upper body shot", "waist up", "cowboy shot", "medium close up",
    "medium shot", "medium full shot", "three quarter shot", "full body", "full body shot", "full body portrait", "full shot",
})
_WIDE_FRAMING = frozenset({
    "wide shot", "very wide shot", "extreme wide shot", "long shot", "extreme long shot",
})
_SPECIAL_CROP = frozenset({
    "no humans", "no people", "empty scene", "unoccupied scene", "subject out of frame",
    "head out of frame", "face out of frame", "body out of frame", "cropped head",
    "faceless", "headless", "eyes only", "hands only", "feet only",
    "eye focus", "eyes focus", "mouth focus", "hand focus", "hands focus",
    "foot focus", "feet focus", "leg focus", "lower body", "lower body shot",
    "torso only", "back focus", "object focus",
})
_FRAMING_PHRASE = re.compile(
    r"^(?:(?:an?|the) )?(?:extreme )?close ?up(?: shot)? (?:of|on) (.+)$"
)
_FACE_CROP = re.compile(
    r"(?:(?:the|a|her|his|their|the subject's|the character's) )?"
    r"(?:face|head|(?:facial )?profile)$"
)

# The tag, the natural-language equivalent, and alternate descriptions that
# already carry the same visible detail. Keep the cues neutral about clothing.
_DETAILS = {
    "face visible": ("The face is in view.", ("visible face", "face is visible")),
    "facial profile": ("The outline of the face is in view.", ("face in profile", "facial silhouette")),
    "back of head": ("The back of the head is in view.", ("back of the head", "back of head visible", "the back of the head is visible")),
    "side of head": ("One side of the head is in view.", ("side of the head", "side of head visible")),
    "top of head": ("The top of the head is in view.", ("top of the head", "crown of head", "crown of the head")),
    "underside of chin": ("The underside of the chin is in view.", ("underside of the chin", "under chin")),
    "front of torso": ("The front of the torso is in view.", ("with the front of the torso visible",
                        "with the front and one side of the torso visible", "front of the torso")),
    "side of torso": ("The side of the torso is in view.", ("with the camera looking directly at the side of the torso",
                       "side of the torso")),
    "upper back": ("The upper back is in view.", ("back visible", "visible back", "back of torso",
                   "back of the torso", "the upper back is visible", "with the back of the torso visible",
                   "with the back and one side of the torso visible")),
    "near shoulder visible": ("The shoulder nearest the camera is in view.", ("near shoulder", "nearer shoulder")),
    "backs of shoulders": ("The backs of the shoulders are in view.", ("back of shoulders", "backs of the shoulders")),
    "tops of shoulders": ("The tops of the shoulders are in view.", ("tops of the shoulders", "shoulders from above")),
    "top of near shoulder": ("The top of the shoulder nearest the camera is in view.", ("top of the near shoulder",)),
    "foreshortened body outline": ("The body outline is foreshortened.", ("foreshortened silhouette",)),
}
_HEAD = {
    "front": ("face visible",), "front quarter": ("face visible", "side of head"),
    "side": ("facial profile",), "rear quarter": ("back of head", "side of head"),
    "rear": ("back of head",),
}
_TORSO = {
    "front": ("front of torso",), "front quarter": ("front of torso", "near shoulder visible"),
    "side": ("side of torso", "near shoulder visible"), "rear quarter": ("upper back", "near shoulder visible"),
    "rear": ("upper back", "backs of shoulders"),
}


def hidden_detail_tags(view):
    """Recognize earlier visibility cues that contradict this view."""
    yaw, _, pitch = view_direction(view)
    hidden = ()
    if yaw in ("front", "front quarter"):
        hidden = ("upper back", "back of head", "backs of shoulders")
    elif yaw in ("rear", "rear quarter"):
        hidden = ("front of torso", "face visible", "facial profile", "underside of chin")
    elif yaw == "side":
        hidden = ("front of torso", "upper back")
    if pitch == "overhead":
        hidden = ("underside of chin",)
    elif pitch == "underneath":
        hidden = ("top of head", "tops of shoulders", "top of near shoulder")
    return {label for tag in hidden for label in (tag, _normalize(_DETAILS[tag][0]), *_DETAILS[tag][1])}


def _prompt_tags(prompt, syntax):
    text = _QUOTED.sub(" quoted text ", prompt or "")
    for tag, weight in iter_prompt_tags(text, syntax):
        yield _normalize(tag).strip(" !?"), weight


def detail_framing(prompt, syntax, distance, fallback="body"):
    tags = {tag for tag, weight in _prompt_tags(prompt, syntax) if weight > 0}
    crops = [match[1] for tag in tags if (match := _FRAMING_PHRASE.fullmatch(tag))]
    if tags & _SPECIAL_CROP or any(not _FACE_CROP.fullmatch(crop) for crop in crops):
        return "special"
    if distance != .5:
        # At the close-up/medium midpoint, either framing can be captioned.
        return "head" if distance <= .375 else "wide" if distance > .875 else "body"
    if tags & _HEAD_FRAMING or crops:
        return "head"
    if tags & _BODY_FRAMING:
        return "body"
    if tags & _WIDE_FRAMING:
        return "wide"
    if "portrait" in tags:
        return "head"
    return fallback


def visible_detail_caption(view, framing, prompt, syntax):
    yaw, _, pitch = view_direction(view)
    height = view[0][1]
    if framing == "special":
        return ""
    if pitch == "underneath":
        cues = () if framing == "head" else ("foreshortened body outline",)
    elif pitch == "overhead":
        cues = ("top of head", "tops of shoulders") if framing == "body" else ("top of head",)
    elif framing == "head":
        cues = _HEAD[yaw]
        if height > .7:
            cues = ("top of head", cues[0])
        elif height < -.45 and yaw in ("front", "front quarter"):
            cues = ("face visible", "underside of chin")
    elif framing == "wide":
        cues = _TORSO[yaw][:1]
    elif pitch == "high":
        shoulder = "top of near shoulder" if yaw in ("front quarter", "side", "rear quarter") else "tops of shoulders"
        cues = (_TORSO[yaw][0], shoulder)
    else:
        cues = _TORSO[yaw]

    present = {tag for tag, _ in _prompt_tags(prompt, syntax)}
    parts = []
    for tag in cues:
        sentence, aliases = _DETAILS[tag]
        if present.isdisjoint((tag, _normalize(sentence), *aliases)):
            parts.append(tag)
    return ", ".join(parts)
