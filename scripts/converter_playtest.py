from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from converters import (
    ComfyUIToNovelAIV4Converter,
    NovelAIV4ToComfyUIConverter,
    NovelAIV4ToOldNAIConverter,
    OldNAIToNovelAIV4Converter,
)


@dataclass
class PromptPart:
    text: str
    weight: float = 1.0
    lossy: bool = False


POLICY_NOTES = [
    "Commas are always tag separators, even inside weighted scopes.",
    "Old NAI opening braces/brackets apply forward until closed.",
    "Old NAI closing braces/brackets with no active opener apply backward to previous tags.",
    "Unclosed NovelAI V4 numeric scopes apply to all following comma-separated tags.",
]


def split_top_level_commas(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    paren_depth = brace_depth = bracket_depth = 0
    in_v4_weight = False
    escaped = False
    i = 0

    while i < len(text):
        char = text[i]
        pair = text[i : i + 2]

        if escaped:
            current.append(char)
            escaped = False
            i += 1
            continue

        if char == "\\":
            current.append(char)
            escaped = True
            i += 1
            continue

        if pair == "::":
            in_v4_weight = not in_v4_weight
            current.append(pair)
            i += 2
            continue

        if not in_v4_weight:
            if char == "(":
                paren_depth += 1
            elif char == ")" and paren_depth:
                paren_depth -= 1
            elif char == "{":
                brace_depth += 1
            elif char == "}" and brace_depth:
                brace_depth -= 1
            elif char == "[":
                bracket_depth += 1
            elif char == "]" and bracket_depth:
                bracket_depth -= 1
            elif char == "," and paren_depth == brace_depth == bracket_depth == 0:
                part = "".join(current).strip()
                if part:
                    parts.append(part)
                current = []
                i += 1
                continue

        current.append(char)
        i += 1

    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts


def find_unescaped_weight_colon(text: str) -> int | None:
    escaped = False
    for i in range(len(text) - 1, -1, -1):
        char = text[i]
        if char == ":":
            backslashes = 0
            j = i - 1
            while j >= 0 and text[j] == "\\":
                backslashes += 1
                j -= 1
            if backslashes % 2 == 0:
                return i
    return None


def parse_comfyui(text: str) -> list[PromptPart]:
    parts: list[PromptPart] = []
    for part in split_top_level_commas(text):
        if part.startswith("(") and part.endswith(")"):
            inner = part[1:-1].strip()
            colon = find_unescaped_weight_colon(inner)
            if colon is not None:
                weight_text = inner[colon + 1 :].strip()
                if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", weight_text):
                    parts.append(PromptPart(inner[:colon].strip(), float(weight_text)))
                    continue
            parts.append(PromptPart(inner, 1.1))
        else:
            parts.append(PromptPart(part.replace(r"\(", "(").replace(r"\)", ")")))
    return parts


def parse_v4(text: str) -> list[PromptPart]:
    parts: list[PromptPart] = []
    active_weight = 1.0
    i = 0

    while i < len(text):
        while i < len(text) and text[i] in " ,":
            i += 1
        if i >= len(text):
            break

        opener = re.match(r"([-+]?\d+(?:\.\d+)?)::", text[i:])
        if opener:
            weight = float(opener.group(1))
            start = i + len(opener.group(0))
            close = text.find("::", start)
            comma = text.find(",", start)
            if close != -1 and (comma == -1 or close < comma):
                content = text[start:close].strip()
                if content:
                    parts.append(PromptPart(content, weight))
                i = close + 2
                if i < len(text) and text[i] == ",":
                    i += 1
                continue

            active_weight = weight
            i = start
            continue

        comma = text.find(",", i)
        if comma == -1:
            raw = text[i:].strip()
            i = len(text)
        else:
            raw = text[i:comma].strip()
            i = comma + 1

        closes_scope = raw.endswith("::")
        if closes_scope:
            raw = raw[:-2].strip()

        if raw:
            parts.append(PromptPart(raw, active_weight))

        if closes_scope:
            active_weight = 1.0

    return parts


def split_old_tags(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def consume_prefix_scopes(text: str) -> tuple[str, int, int]:
    curly = square = 0
    while text.startswith("{") or text.startswith("["):
        if text.startswith("{"):
            curly += 1
        else:
            square += 1
        text = text[1:].strip()
    return text, curly, square


def consume_suffix_scopes(text: str) -> tuple[str, list[str]]:
    closers: list[str] = []
    while text.endswith("}") or text.endswith("]"):
        closers.append(text[-1])
        text = text[:-1].strip()
    closers.reverse()
    return text, closers


def parse_old(text: str) -> list[PromptPart]:
    parts: list[PromptPart] = []
    active_curly = 0
    active_square = 0

    for raw in split_old_tags(text):
        content, open_curly, open_square = consume_prefix_scopes(raw)
        active_curly += open_curly
        active_square += open_square

        content, closers = consume_suffix_scopes(content)
        if content:
            parts.append(PromptPart(content, (1.05**active_curly) * (0.95**active_square)))

        for closer in closers:
            if closer == "}":
                if active_curly > 0:
                    active_curly -= 1
                else:
                    for part in parts:
                        part.weight *= 1.05
            elif closer == "]":
                if active_square > 0:
                    active_square -= 1
                else:
                    for part in parts:
                        part.weight *= 0.95

    return parts


def format_weight(weight: float) -> str:
    return f"{weight:.2f}".rstrip("0").rstrip(".")


def weights_close(left: float, right: float) -> bool:
    return abs(left - right) <= 0.005


def group_consecutive_weights(parts: list[PromptPart]) -> list[list[PromptPart]]:
    groups: list[list[PromptPart]] = []
    for part in parts:
        if groups and weights_close(groups[-1][0].weight, part.weight):
            groups[-1].append(part)
        else:
            groups.append([part])
    return groups


def write_v4(parts: list[PromptPart]) -> str:
    out = []
    for group in group_consecutive_weights(parts):
        weight = group[0].weight
        text = ", ".join(part.text for part in group)
        if not weights_close(weight, 1.0):
            out.append(f"{format_weight(weight)}::{text} ::")
        else:
            out.append(text)
    return ", ".join(out)


def write_comfyui(parts: list[PromptPart]) -> str:
    out = []
    for part in parts:
        if abs(part.weight - 1.0) > 0.005:
            out.append(f"({part.text}:{format_weight(part.weight)})")
        else:
            out.append(part.text.replace("(", r"\(").replace(")", r"\)"))
    return ", ".join(out)


def closest_power(weight: float, base: float) -> int:
    if weight <= 0 or base <= 0 or base == 1:
        return 0
    return round(math.log(weight) / math.log(base))


def write_old(parts: list[PromptPart]) -> str:
    out = []
    for group in group_consecutive_weights(parts):
        weight = group[0].weight
        text = ", ".join(part.text for part in group)
        if weight <= 0:
            out.append(f"[{text}]")
        elif weight < 0.995:
            count = max(1, closest_power(weight, 0.95))
            out.append("[" * count + text + "]" * count)
        elif weight > 1.005:
            count = max(1, closest_power(weight, 1.05))
            out.append("{" * count + text + "}" * count)
        else:
            out.append(text)
    return ", ".join(out)


CASES = [
    ("comfy_to_v4", "single weighted tag", "tag, (focus:1.2), plain"),
    ("comfy_to_v4", "multiple weighted tags", "(tag1:1.05), (tag2:0.9), (tag3:-1.5), tail"),
    ("comfy_to_v4", "comma inside weighted tag", "(misty, golden hour:1.1), background"),
    ("comfy_to_v4", "escaped parentheses", "artist:abc, e\\(f: g h\\), (negative example:-1.5)"),
    ("comfy_to_v4", "nested comfy parentheses", "((nested tag:1.2):1.1), plain"),
    ("comfy_to_v4", "unweighted parentheses", "(implicit emphasis), plain"),
    ("v4_to_comfy", "single weighted tag", "tag, 1.2::focus ::, plain"),
    ("v4_to_comfy", "multiple weighted tags", "1.05::tag1 ::, 0.9::tag2 ::, -1.5::tag3 ::, tail"),
    ("v4_to_comfy", "comma inside weighted tag", "1.1::misty, golden hour ::, background"),
    ("v4_to_comfy", "artist and literal parens", "artist:abc, e(f: g h), -1.5::negative example ::"),
    ("v4_to_comfy", "colon inside weighted tag", "1.2::artist:abc ::, 0.8::expression: smile ::"),
    ("v4_to_old", "single weighted tag", "1.2::focus ::, plain"),
    ("v4_to_old", "multiple weighted tags", "1.05::tag1 ::, 0.9::tag2 ::, 1.2::tag3 ::"),
    ("v4_to_old", "negative and zero weights", "-1.5::negative tag ::, 0::zero weight tag ::"),
    ("v4_to_old", "comma inside weighted tag", "1.1::misty, golden hour ::, background"),
    ("v4_to_old", "unclosed numeric scope", "1.3::tag1, tag2, tag3"),
    ("v4_to_old", "numeric scope closes later", "1.3::tag1, tag2::, tag3"),
    ("old_to_v4", "single curly and square", "{tag1}, [tag2], tag3"),
    ("old_to_v4", "multiple curly and square", "{{tag1}}, [[tag2]], {{{tag3}}}, [[[tag4]]]"),
    ("old_to_v4", "comma inside braces", "{{misty, golden hour}}, background"),
    ("old_to_v4", "opening scope applies forward", "{tag1, tag2, tag3"),
    ("old_to_v4", "closing scope applies backward", "tag1, tag2, tag3}"),
    ("old_to_v4", "scope opens and closes around several tags", "{tag1, tag2}, tag3"),
    ("old_to_v4", "mixed bracket types", "{[mixed]}, [{mixed2}], {tag], [tag}"),
    ("old_to_v4", "unbalanced brackets", "{{broken}, [[broken2], plain"),
]


def legacy_output(kind: str, text: str) -> str:
    if kind == "comfy_to_v4":
        return ComfyUIToNovelAIV4Converter().convert_prompt(text)[0]
    if kind == "v4_to_comfy":
        return NovelAIV4ToComfyUIConverter().convert_prompt(text)[0]
    if kind == "v4_to_old":
        return NovelAIV4ToOldNAIConverter().convert_prompt(text)[0]
    if kind == "old_to_v4":
        return OldNAIToNovelAIV4Converter().convert_prompt(text)[0]
    raise ValueError(kind)


def parser_output(kind: str, text: str) -> str:
    if kind == "comfy_to_v4":
        return write_v4(parse_comfyui(text))
    if kind == "v4_to_comfy":
        return write_comfyui(parse_v4(text))
    if kind == "v4_to_old":
        return write_old(parse_v4(text))
    if kind == "old_to_v4":
        return write_v4(parse_old(text))
    raise ValueError(kind)


def main() -> None:
    print("# Converter Playtest\n")
    print("## Policy\n")
    for note in POLICY_NOTES:
        print(f"- {note}")
    print()
    mismatch_count = 0
    for kind, name, text in CASES:
        legacy = legacy_output(kind, text)
        parser = parser_output(kind, text)
        same = legacy == parser
        if not same:
            mismatch_count += 1
        print(f"## {kind}: {name}")
        print(f"- input: `{text}`")
        print(f"- legacy: `{legacy}`")
        print(f"- parser: `{parser}`")
        print(f"- same: `{same}`")
        print()
    print(f"# Summary\n\n- cases: `{len(CASES)}`\n- mismatches: `{mismatch_count}`")


if __name__ == "__main__":
    main()
