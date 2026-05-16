# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2025 raspie10032

import re
import math

# ---------------------------------------------------------------------------
# Shared helpers
#
# A single intermediate representation (a list of ``(text, weight)`` tags,
# commas being tag separators in every syntax) backs all six converters.
# Each format has one parser and one serializer; the node classes are thin
# wrappers. This removes the duplicated, partly-contradictory exception
# handling that used to live in every class.
# ---------------------------------------------------------------------------

_ARTIST_TOKEN = "__artist__"
_DEFAULT_WEIGHT = 1.1
_WEIGHT_MIN, _WEIGHT_MAX = -5.0, 5.0

# Strict number: rejects "1.2.3", "--", "." that the old "[\d.-]+" accepted.
_STRICT_NUM = re.compile(r"-?\d+(?:\.\d+)?")
# Trailing ":<number-ish>" probe (lenient on purpose, see _trailing_weight).
_TRAILING_WEIGHT = re.compile(r":([\d.-]+)\s*$")
# A NovelAI V4 scope opener at a tag boundary: "<number>::".
_V4_OPEN = re.compile(r"^\s*(-?\d+(?:\.\d+)?)::")


def _guard_artist(text):
    """Hide the colon in ``artist:`` so it is never read as a weight marker."""
    return text.replace("artist:", _ARTIST_TOKEN)


def _restore_artist(text):
    return text.replace(_ARTIST_TOKEN, "artist:")


def _strict_float(token):
    """Return ``float(token)`` only if ``token`` is a well-formed number."""
    token = token.strip()
    if _STRICT_NUM.fullmatch(token):
        try:
            return float(token)
        except ValueError:
            return None
    return None


def _format_weight(value):
    """Compact numeric form: ``1.0500 -> 1.05``, ``-1.5000 -> -1.5``."""
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _closest_power(weight, base):
    """Nearest integer exponent ``n`` so that ``base ** n ~= weight``."""
    if weight <= 0 or base <= 0 or base == 1:
        return 0
    return round(math.log(weight) / math.log(base))


# ---------------------------------------------------------------------------
# ComfyUI  <->  IR
# ---------------------------------------------------------------------------


def _split_top_level(text):
    """Split on commas that are not escaped and not inside parentheses."""
    parts, buf, depth, i = [], [], 0, 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text) and text[i + 1] in "()":
            buf.append(text[i:i + 2])
            i += 2
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _matches_outer_paren(segment):
    depth, i = 0, 0
    while i < len(segment):
        ch = segment[i]
        if ch == "\\" and i + 1 < len(segment) and segment[i + 1] in "()":
            i += 2
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i == len(segment) - 1
        i += 1
    return False


def _trailing_weight(inner):
    """Return ``(weight_token, body)`` if ``inner`` ends with ``:<num>``.

    Uses the lenient probe so a malformed ``1.2.3`` is still detected and
    then rejected by the strict float check, preserving the historical
    fallback (keep the whole inner text, default weight).
    """
    m = _TRAILING_WEIGHT.search(inner)
    if not m:
        return None, inner
    return m.group(1), inner[:m.start()].strip()


def _eval_comfy_segment(segment):
    """Resolve one comma-segment into ``(text, weight)`` or ``None``.

    ComfyUI nesting: every bare ``(...)`` level multiplies by the 1.1
    default while an explicit ``(...:w)`` level multiplies by ``w``.
    Escaped ``\\(`` / ``\\)`` are literal characters, not group markers.
    """
    segment = segment.strip()
    if not segment:
        return None

    if segment.startswith("(") and _matches_outer_paren(segment):
        inner = segment[1:-1]
        token, body = _trailing_weight(inner)

        if token is None:
            level_weight, child_text = _DEFAULT_WEIGHT, inner
        else:
            parsed = _strict_float(token)
            if parsed is None:
                level_weight, child_text = _DEFAULT_WEIGHT, inner
            elif not (_WEIGHT_MIN <= parsed <= _WEIGHT_MAX):
                print(f"Warning: Weight '{parsed}' is outside the -5 to 5 range. Using default value 1.1 for: {body.strip()}")
                level_weight, child_text = _DEFAULT_WEIGHT, body
            else:
                level_weight, child_text = parsed, body

        child = _eval_comfy_segment(child_text)
        if child is None:
            return None
        inner_text, inner_weight = child
        if not inner_text:
            return None
        return (inner_text, level_weight * inner_weight)

    return (segment.replace("\\(", "(").replace("\\)", ")"), 1.0)


def parse_comfyui(text):
    tags = []
    for segment in _split_top_level(_guard_artist(text)):
        if segment.strip() == "":
            tags.append(("", 1.0))  # preserve empty slots ("a, , b")
            continue
        resolved = _eval_comfy_segment(segment)
        if resolved is not None:  # drop fully empty groups "()"
            tags.append(resolved)
    return tags


def to_comfyui(tags):
    parts = []
    for text, weight in tags:
        escaped = text.replace("(", r"\(").replace(")", r"\)")
        if weight == 1.0:
            parts.append(escaped)
        else:
            parts.append(f"({escaped}:{_format_weight(weight)})")
    return _restore_artist(", ".join(parts))


# ---------------------------------------------------------------------------
# NovelAI V4  <->  IR
# ---------------------------------------------------------------------------


def parse_naiv4(text):
    """Parse NovelAI V4 numeric-scope syntax into IR.

    Rules (per the README spec):
      - commas separate tags;
      - ``<w>::`` at a tag boundary opens a numeric scope;
      - a closing ``::`` ends the active scope after the current tag;
      - an opened scope with no closing ``::`` applies forward to all
        following comma-separated tags.

    The intentional space before a closing ``::`` (the guard that stops a
    trailing number being read as a weight) is handled naturally: the
    opener is matched only at a tag boundary, so ``team 5 ::`` is a close.
    """
    guarded = _guard_artist(text)
    tags = []
    current_weight = 1.0
    scope_active = False

    for chunk in guarded.split(","):
        open_match = _V4_OPEN.match(chunk)
        if open_match:
            value = _strict_float(open_match.group(1))
            if value is not None:
                current_weight = value
                scope_active = True
                chunk = chunk[open_match.end():]

        if "::" in chunk:
            content = chunk.split("::", 1)[0].strip()
            weight = current_weight if scope_active else 1.0
            if content:
                tags.append((content, weight))
            current_weight, scope_active = 1.0, False
        else:
            content = chunk.strip()
            weight = current_weight if scope_active else 1.0
            tags.append((content, weight))

    return tags


def to_naiv4(tags):
    """Serialize IR to V4, merging consecutive same-weight tags into one
    scope (``1.05::a ::, 1.05::b ::`` -> ``1.05::a, b ::``)."""
    out, i, n = [], 0, len(tags)
    while i < n:
        text, weight = tags[i]
        if weight == 1.0:
            out.append(text)
            i += 1
            continue
        group = []
        while i < n and tags[i][1] == weight:
            group.append(tags[i][0])
            i += 1
        out.append(f"{_format_weight(weight)}::{', '.join(group)} ::")
    return _restore_artist(", ".join(out))


# ---------------------------------------------------------------------------
# Old NAI  <->  IR
#
# Brace/bracket power math and its 2-decimal display are preserved exactly;
# weights are rounded to 2 decimals at parse time so the V4 serializer
# reproduces the historical strings (1.05**3 -> "1.16", etc.).
# ---------------------------------------------------------------------------


def parse_oldnai(text):
    """Character-level scope parser for old NovelAI brace/bracket syntax.

    - ``{`` / ``[`` open a forward 1.05x / 0.95x scope to the matching
      ``}`` / ``]``;
    - an unmatched closing ``}`` / ``]`` applies 1.05x / 0.95x backward to
      all already-parsed tags;
    - mixed ``{[tag]}`` multiplies the factors (1.05 * 0.95);
    - a tag's weight is snapshotted from the scope active when its text
      begins.
    """
    guarded = _guard_artist(text)
    tags = []
    stack = []           # list of factors for currently-open { or [
    buf = []
    snapshot = None      # weight captured at the start of the current tag

    def cur_product():
        p = 1.0
        for f in stack:
            p *= f
        return p

    def flush():
        nonlocal buf, snapshot
        content = "".join(buf).strip()
        if content:
            tags.append([content, round(snapshot if snapshot is not None else cur_product(), 2)])
        buf = []
        snapshot = None

    def note_char(ch):
        nonlocal snapshot
        if snapshot is None and ch.strip():
            snapshot = cur_product()
        buf.append(ch)

    for ch in guarded:
        if ch == "{":
            stack.append(1.05)
        elif ch == "[":
            stack.append(0.95)
        elif ch == "}":
            if 1.05 in stack:
                # close the nearest open "{"
                for k in range(len(stack) - 1, -1, -1):
                    if stack[k] == 1.05:
                        del stack[k]
                        break
            else:
                for t in tags:
                    t[1] = round(t[1] * 1.05, 2)
        elif ch == "]":
            if 0.95 in stack:
                for k in range(len(stack) - 1, -1, -1):
                    if stack[k] == 0.95:
                        del stack[k]
                        break
            else:
                for t in tags:
                    t[1] = round(t[1] * 0.95, 2)
        elif ch == ",":
            flush()
        else:
            note_char(ch)

    flush()
    return [(t[0], t[1]) for t in tags]


def _oldnai_encoding(weight, text):
    """Return ``(signature, open_str, close_str)`` for one tag.

    ``signature`` groups mergeable neighbors; ``None`` means "plain text".
    Power math and the negative/zero fallback are unchanged.
    """
    if weight <= 0:
        print(f"Warning: Old NAI format cannot represent negative or zero weights. Applying the default decrease weight of 0.95 > '[{text}]' instead.")
        return ("neg", "[", "]")
    if weight < 1:
        n = _closest_power(weight, 0.95)
        return (("sq", n), "[" * n, "]" * n) if n > 0 else (None, "", "")
    if weight == 1:
        return (None, "", "")
    n = _closest_power(weight, 1.05)
    return (("cu", n), "{" * n, "}" * n) if n > 0 else (None, "", "")


def to_oldnai(tags):
    """Serialize IR to old NAI, merging neighbors with identical bracketing
    (``{tag1}, {tag2}`` -> ``{tag1, tag2}``)."""
    encoded = [(text,) + _oldnai_encoding(weight, text) for text, weight in tags]
    out, i, n = [], 0, len(encoded)
    while i < n:
        text, sig, open_s, close_s = encoded[i]
        if sig is None:
            out.append(text)
            i += 1
            continue
        group = []
        while i < n and encoded[i][1] == sig:
            group.append(encoded[i][0])
            i += 1
        out.append(f"{open_s}{', '.join(group)}{close_s}")
    return _restore_artist(", ".join(out))


# ---------------------------------------------------------------------------
# Node classes (ComfyUI contract unchanged)
# ---------------------------------------------------------------------------


class ComfyUIToNovelAIV4Converter:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"comfyui_prompt": ("STRING", {"multiline": True, "default": "qw, a, (b c:1.05), d, e\\(f: g h\\), black bikini top, (negative example:-1.5), shorts under bikini bottom, (i j:1.2)"})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("novelai_prompt",)
    FUNCTION = "convert_prompt"
    CATEGORY = "RS_NovelAI_API/Converters"

    def convert_prompt(self, comfyui_prompt):
        return (to_naiv4(parse_comfyui(comfyui_prompt)),)


class NovelAIV4ToComfyUIConverter:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"novelai_prompt": ("STRING", {"multiline": True, "default": "qw, a, 1.05::b c::, d, e(f: g h), black bikini top, -1.5::negative example::, shorts under bikini bottom, 1.2::i j::"})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("comfyui_prompt",)
    FUNCTION = "convert_prompt"
    CATEGORY = "RS_NovelAI_API/Converters"

    def convert_prompt(self, novelai_prompt):
        return (to_comfyui(parse_naiv4(novelai_prompt)),)


class NovelAIV4ToOldNAIConverter:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"novelai_v4_prompt": ("STRING", {"multiline": True, "default": "1.05::tag1::, 0.9::tag3::, 1.2::tag4::, 1.1::misty, golden hour::, -1.5::negative tag::, 0::zero weight tag::"})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("novelai_old_prompt",)
    FUNCTION = "convert_prompt"
    CATEGORY = "RS_NovelAI_API/Converters"

    def convert_prompt(self, novelai_v4_prompt):
        return (to_oldnai(parse_naiv4(novelai_v4_prompt)),)


class OldNAIToNovelAIV4Converter:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"novelai_old_prompt": ("STRING", {"multiline": True, "default": "{tag1}, [tag2], {{tag3}}, [[tag4]], tag5, {{{important tag}}}, {{misty, golden hour}}"})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("novelai_v4_prompt",)
    FUNCTION = "convert_prompt"
    CATEGORY = "RS_NovelAI_API/Converters"

    def convert_prompt(self, novelai_old_prompt):
        return (to_naiv4(parse_oldnai(novelai_old_prompt)),)


class ComfyUIToOldNAIConverter:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"comfyui_prompt": ("STRING", {"multiline": True, "default": "qw, a, (b c:1.05), d, e\\(f: g h\\), black bikini top, denim shorts, shorts under bikini bottom, (i j:1.2)"})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("novelai_old_prompt",)
    FUNCTION = "convert_prompt"
    CATEGORY = "RS_NovelAI_API/Converters"

    def convert_prompt(self, comfyui_prompt):
        return (to_oldnai(parse_comfyui(comfyui_prompt)),)


class OldNAIToComfyUIConverter:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"novelai_old_prompt": ("STRING", {"multiline": True, "default": "{tag1}, [tag2], {{tag3}}, [[tag4]], tag5, {{{important tag}}}, {{misty, golden hour}}"})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("comfyui_prompt",)
    FUNCTION = "convert_prompt"
    CATEGORY = "RS_NovelAI_API/Converters"

    def convert_prompt(self, novelai_old_prompt):
        return (to_comfyui(parse_oldnai(novelai_old_prompt)),)


# Node class mappings
CONVERTER_NODE_CLASS_MAPPINGS = {
    "ComfyUIToNovelAIV4": ComfyUIToNovelAIV4Converter,
    "NovelAIV4ToComfyUI": NovelAIV4ToComfyUIConverter,
    "NovelAIV4ToOldNAI": NovelAIV4ToOldNAIConverter,
    "OldNAIToNovelAIV4": OldNAIToNovelAIV4Converter,
    "ComfyUIToOldNAI": ComfyUIToOldNAIConverter,
    "OldNAIToComfyUI": OldNAIToComfyUIConverter,
}

# Node display name mappings
CONVERTER_NODE_DISPLAY_NAME_MAPPINGS = {
    "ComfyUIToNovelAIV4": "Convert ComfyUI to Novel AI V4",
    "NovelAIV4ToComfyUI": "Convert Novel AI V4 to ComfyUI",
    "NovelAIV4ToOldNAI": "Convert Novel AI V4 to Old NAI",
    "OldNAIToNovelAIV4": "Convert Old NAI to Novel AI V4",
    "ComfyUIToOldNAI": "Convert ComfyUI to Old NAI",
    "OldNAIToComfyUI": "Convert Old NAI to ComfyUI",
}
