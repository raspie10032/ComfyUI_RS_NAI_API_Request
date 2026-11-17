# SPDX-License-Identifier: GPL-3.0-only
"""Read and filter camera tags while preserving unrelated prompt syntax."""
from .converters import (
    _DEFAULT_WEIGHT, _WEIGHT_MIN, _WEIGHT_MAX, _eval_comfy_segment, _guard_artist,
    _matches_outer_paren, _split_top_level, _strict_float, _trailing_weight,
)
from .local_bridge import _weighted_tokens


def _native_tags(text):
    """Track weighted tags and retain numeric and legacy scope boundaries."""
    raw, literal, markup, weights = [], [], [], []
    for token, content, weight in _weighted_tokens(text):
        if content is None:
            raw.append(token)
            markup.append(token)
            continue
        if token.startswith("\\") and token != content:
            parts = [token]
        else:
            parts = token.split(",")
        for index, part in enumerate(parts):
            if index:
                yield "".join(raw), "".join(literal).strip(), min(weights, default=0), "".join(markup)
                raw, literal, markup, weights = [], [], [], []
            raw.append(part)
            literal.append(content if len(parts) == 1 else part)
            if part.strip():
                weights.append(weight)
    yield "".join(raw), "".join(literal).strip(), min(weights, default=0), "".join(markup)


def iter_prompt_tags(text, syntax):
    """Yield individual tags even inside a weighted comma group."""
    if syntax == "NovelAI":
        for _, tag, weight, _ in _native_tags(text):
            yield tag, weight
        return

    for part in _split_top_level(_guard_artist(text)):
        segment = part.strip()
        if segment.startswith("(") and _matches_outer_paren(segment):
            token, body = _trailing_weight(segment[1:-1])
            weight = _strict_float(token) if token is not None else None
            if token is None or weight is not None:
                if weight is None or not _WEIGHT_MIN <= weight <= _WEIGHT_MAX:
                    weight = _DEFAULT_WEIGHT
                for tag, child_weight in iter_prompt_tags(body, syntax):
                    yield tag, weight * child_weight
                continue
        resolved = _eval_comfy_segment(segment)
        if resolved is not None:
            yield resolved


def filter_prompt_tags(text, syntax, remove):
    """Drop matching positively weighted tags while retaining other conditioning."""
    if syntax == "NovelAI":
        parts = []
        pending = ""
        removed = False
        for raw, tag, weight, markup in _native_tags(text):
            if weight > 0 and remove(tag):
                pending += markup
                removed = True
            else:
                parts.append(pending + raw)
                pending = ""
        if not removed:
            return text
        if not any(part.strip() for part in parts):
            return ""
        return (",".join(parts) + (" " + pending if pending else "")).strip(" ,")

    def filter_comfy(part):
        segment = part.strip()
        if segment.startswith("(") and _matches_outer_paren(segment):
            inner = segment[1:-1]
            token, body = _trailing_weight(inner)
            weight = _strict_float(token) if token is not None else None
            if weight is not None and _WEIGHT_MIN <= weight <= 0:
                return part
            if token is None or weight is not None:
                trimmed = filter_prompt_tags(body, syntax, remove)
                if trimmed != body:
                    if not trimmed:
                        return None
                    start = part.index("(") + 1
                    end = inner.rfind(":") if token is not None else len(inner)
                    return part[:start] + trimmed + part[start + end:]
        tag = _eval_comfy_segment(_guard_artist(part))
        return None if tag is not None and tag[1] > 0 and remove(tag[0]) else part

    parts = _split_top_level(text)
    kept = [part for original in parts if (part := filter_comfy(original)) is not None]
    return text if kept == parts else ",".join(part for part in kept if part.strip()).strip()
