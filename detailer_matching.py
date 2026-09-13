# SPDX-License-Identifier: GPL-3.0-only
"""Matching consumes tagger scores; request construction never receives them."""

import math
import re
from collections import Counter
from dataclasses import dataclass

from .converters import parse_naiv4


@dataclass(frozen=True)
class Match:
    character_index: int | None
    score: float
    margin: float
    reason: str


def normalize_tag(tag):
    return " ".join(
        tag.replace(r"\(", "(").replace(r"\)", ")").replace("_", " ").casefold().split()
    )


def prompt_tags(prompt):
    # Only compare a normalized copy. Never serialize this copy into a request.
    return {normalize_tag(tag) for tag, weight in parse_naiv4(prompt) if weight > 0}


def match_characters(scores, characters, min_score=0.25, min_margin=0.08):
    """Independent assignments permit multiple eyes/regions per character.

    Shared features have no discriminating value. Absence is not contradiction:
    a crop may simply not show a tag. Unknown/ambiguous regions stay unmatched.
    """
    tags = [prompt_tags(c.prompt) for c in characters]
    counts = Counter(tag for group in tags for tag in group)
    normalized = {
        normalize_tag(k): float(v)
        for k, v in scores.items()
        if math.isfinite(float(v)) and 0 <= float(v) <= 1
    }
    ranked = []
    for index, group in enumerate(tags):
        features = []
        for tag in group:
            if tag not in normalized or (len(characters) > 1 and counts[tag] > 1):
                continue
            if re.fullmatch(r"\d+(girls?|boys?|others?)", tag) or tag in {
                "solo",
                "multiple girls",
                "multiple boys",
            }:
                continue
            if tag.startswith("artist:") or any(
                x in tag for x in ("quality", "resolution", "background")
            ):
                continue
            weight = 0.25 if tag.endswith(" eyes") else 1.0
            features.append((weight, normalized[tag]))
        # Strongest discriminating evidence avoids penalizing a longer original
        # prompt for attributes outside the crop. Competing strong identities
        # then produce a small margin and remain unmatched, rather than letting
        # the character with fewer prompt tags win. Eye-only evidence is capped.
        score = max((w * v for w, v in features), default=0.0)
        ranked.append((score, index))
    ranked.sort(reverse=True)
    if not ranked:
        return Match(None, 0.0, 0.0, "no_characters")
    score, index = ranked[0]
    margin = score - (ranked[1][0] if len(ranked) > 1 else 0.0)
    if score < min_score or margin < min_margin:
        return Match(None, score, margin, "ambiguous")
    return Match(index, score, margin, "tag_match")


def selected_prompts(base_prompt, base_negative, characters, match):
    """Only original user text crosses the request boundary.

    Keep original names, franchise qualifiers, weights, and negative text intact.
    The base inputs must be shared/detail-stage instructions, not mixed identities.
    """
    if match.character_index is None:
        return base_prompt, base_negative
    character = characters[match.character_index]
    return (
        ", ".join(x for x in (base_prompt, character.prompt) if x),
        ", ".join(x for x in (base_negative, character.uc) if x),
    )
