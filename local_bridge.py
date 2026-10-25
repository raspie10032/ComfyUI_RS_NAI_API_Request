# SPDX-License-Identifier: GPL-3.0-only
"""Translate NAI prompts at the boundary to the installed local character pipe."""
import importlib
import math
import re
import json

from .diagnostics import notice
from dataclasses import dataclass, replace, field
from collections.abc import Sequence

LOCAL_CHARACTER_LIMIT = 10
_TOKENS = re.compile(r"\\.|[+-]?(?:\d+(?:\.\d*)?|\.\d+)::|::|[{}\[\]]", re.DOTALL)


def _tokens(text):
    end = 0
    for match in _TOKENS.finditer(text):
        if match.start() > end:
            yield text[end:match.start()]
        yield match.group()
        end = match.end()
    if end < len(text):
        yield text[end:]


def _spans(text):
    """Numeric scopes and legacy emphasis can nest; never drop text after ::."""
    stack = []
    spans = []
    weight = 1.0
    for token in _tokens(text):
        if token.endswith("::") and token != "::":
            factor = float(token[:-2])
            if not math.isfinite(factor) or not math.isfinite(weight * factor):
                raise ValueError("NAI prompt weights must be finite.")
            stack.append(("::", weight))
            weight *= factor
        elif token in ("{", "["):
            stack.append(("}" if token == "{" else "]", weight))
            weight *= 1.05 if token == "{" else 1 / 1.05
            if not math.isfinite(weight):
                raise ValueError("NAI prompt weights must be finite.")
        elif stack and token == stack[-1][0]:
            _, weight = stack.pop()
        else:
            # Parentheses and square brackets in NAI text are literal in CLIP.
            literal = token[1:] if token.startswith("\\") and len(token) == 2 else token
            if spans and spans[-1][1] == weight:
                spans[-1] = (spans[-1][0] + literal, weight)
            else:
                spans.append((literal, weight))
    return spans


def _clean(text):
    return re.sub(r",(?:\s*,)+", ",", text).strip(" ,\n\t")


def _escape(text):
    # ComfyUI's tokenizer only unescapes parentheses; square brackets are literal.
    return re.sub(r"([()])", r"\\\1", text)


def _convert(text, *, negative_field=False):
    positive, negative = [], []
    previous_negative = False
    for literal, weight in _spans(text):
        if not weight:
            previous_negative = False
            continue
        if weight < 0:
            # Deliberately discard magnitude, including nested emphasis.
            if previous_negative:
                negative[-1] += literal
            else:
                negative.append(literal)
            previous_negative = True
            continue
        previous_negative = False
        escaped = _escape(literal)
        if weight != 1 and literal.strip(" ,\n\t"):
            leading = literal[:len(literal) - len(literal.lstrip())]
            trailing = literal[len(literal.rstrip()):]
            escaped = f"{leading}({_escape(literal.strip())}:{weight:.6g}){trailing}"
        positive.append(escaped)
    regular = _clean("".join(positive))
    moved = ", ".join(_escape(_clean(s)) for s in negative if _clean(s))
    if negative_field:
        return "", join_prompts(regular, moved)
    return regular, moved


def join_prompts(*parts):
    return ", ".join(part.strip(" ,\n\t") for part in parts if part.strip(" ,\n\t"))


def local_prompts(prompt, negative_prompt="", local_negative_prompt=""):
    positive, moved = _convert(prompt)
    _, negative = _convert(negative_prompt, negative_field=True)
    # This last input already uses local syntax; do not parse it as NAI.
    return positive, join_prompts(negative, moved, local_negative_prompt)


def comfy_to_nai(text):
    """Convert inline/nested CLIP weights without splitting weighted sentences.

    Follow ComfyUI token_weights: bare groups multiply by 1.1 and an explicit
    group weight replaces the inherited weight. Keep the standalone legacy
    converter unchanged for existing workflows.
    """
    text = text.replace(r"\(", "\0L").replace(r"\)", "\0R")

    def spans(value, weight=1.):
        depth, start, plain = 0, 0, 0
        result = []
        for index, char in enumerate(value):
            if char == "(":
                if depth == 0:
                    result.append((value[plain:index], weight))
                    start = index
                depth += 1
            elif char == ")" and depth:
                depth -= 1
                if depth == 0:
                    body, factor = value[start+1:index], weight * 1.1
                    head, colon, tail = body.rpartition(":")
                    if colon and head:
                        try:
                            factor = float(tail)
                            body = head
                        except ValueError:
                            pass
                    if not math.isfinite(factor):
                        raise ValueError("Local prompt weights must be finite.")
                    result.extend(spans(body, factor))
                    plain = index + 1
        result.append((value[start if depth else plain:], weight))
        return result

    out = []
    for literal, weight in spans(text):
        literal = literal.replace("\0L", "(").replace("\0R", ")")
        literal = re.sub(r"([{}\[\]])", r"\\\1", literal).replace("::", r"\:\:")
        if literal:
            out.append(literal if weight == 1 else f"{weight:.12g}::{literal}::")
    return "".join(out)


def _pipe_classes():
    import nodes
    registered = nodes.NODE_CLASS_MAPPINGS.get("RSMultiCharacterPrompts")
    if registered is None:
        # Current editors may supersede the legacy prompt node.
        registered = nodes.NODE_CLASS_MAPPINGS.get("RSMultiCharacterScene")
    if registered is None:
        raise ValueError("Install/load RS Multi-Character Sampler to use the local character pipe. / 로컬 연결에는 RS 멀티캐릭터 샘플러가 필요합니다.")
    package = registered.__module__.rpartition(".")[0]
    module = importlib.import_module(f"{package}.characters")
    if getattr(module, "PIPE_TYPE", None) != "RS_MC_CHARACTER_PIPE":
        raise ValueError("Update RS Multi-Character Sampler: incompatible character pipe.")
    return module.Character, module.CharacterPipe


PIPE_TYPE = "RS_MC_CHARACTER_PIPE"
CHARACTER_INPUT = "LIST,RS_MC_CHARACTER_PIPE,NAI_CONTEXT"


@dataclass(frozen=True)
class NAICharacterPipe(Sequence):
    """Shared socket protocol; defer local conversion until the receiving node."""
    characters: tuple
    prompt: str | None = None
    negative_prompt: str | None = None
    syntax: str = "NovelAI"
    local_record_json: str | None = field(default=None, kw_only=True)
    nai_settings_json: str | None = field(default=None, kw_only=True)

    def __len__(self):
        return len(self.characters)

    def __getitem__(self, key):
        return list(self.characters[key]) if isinstance(key, slice) else self.characters[key]

    def __add__(self, other):
        return list(self) + list(other)

    def __radd__(self, other):
        return list(other) + list(self)

    def as_camera_context(self):
        """Normalize legacy character slots without loading the local extension."""
        from dataclasses import is_dataclass
        if all(is_dataclass(c) for c in self.characters):
            return self
        from .generation_context import ContextCharacter
        characters = tuple(c if is_dataclass(c) else ContextCharacter(
            c.prompt, c.uc, c.center["x"], c.center["y"]
        ) for c in self.characters)
        return replace(self, characters=characters)

    def as_local_character_pipe(self):
        Character, CharacterPipe = _pipe_classes()
        native = None
        if self.local_record_json:
            module = importlib.import_module(CharacterPipe.__module__.rpartition(".")[0] + ".metadata")
            native = module.pipe_from_record(module.object_json(self.local_record_json))
        if not self.characters:
            raise ValueError("This image has no character captions. Add a local character prompt first. / 캐릭터 캡션이 없습니다. 로컬 캐릭터 프롬프트를 먼저 추가해 주세요.")
        if len(self) > LOCAL_CHARACTER_LIMIT:
            notice("Local multi-character uses characters 1–10; the original NAI pipe is preserved. / 로컬은 1~10번만 사용합니다. 원본 파이프는 유지됩니다.")
        convert = local_prompts if self.syntax == "NovelAI" else lambda p, n: (p, n)
        if self.syntax not in ("NovelAI", "ComfyUI"):
            raise ValueError("Unsupported character pipe prompt syntax.")
        prompt, negative = convert(self.prompt or "", self.negative_prompt or "")
        chars = []
        for index, c in enumerate(self.characters[:LOCAL_CHARACTER_LIMIT]):
            positive, uc = convert(c.prompt, c.uc)
            center = c.center
            if native is not None and index < len(native.characters):
                original = native.characters[index]
                if original.center != center and (original.bbox is not None or original.region_mask is not None):
                    raise ValueError("Character coordinates changed while carrying a local mask/box. Update placement with RS Position before exporting again. / 마스크·상자의 좌표가 달라졌습니다. RS 위치 노드에서 다시 배치해 주세요.")
                chars.append(replace(original, prompt=positive, uc=uc, x=center["x"], y=center["y"]))
            else:
                chars.append(Character(positive, uc, center["x"], center["y"]))
        # A prompt-only editor must not replace the receiving sampler's scene.
        if native is not None:
            text_convert = local_prompts if (native.character_syntax or native.syntax) == "NovelAI" else lambda p, n: (p, n)
            texts = tuple(replace(c, prompt=text_convert(c.prompt, c.uc)[0],
                                  uc=text_convert(c.prompt, c.uc)[1]) for c in native.text_regions)
            return replace(native, characters=tuple(chars), prompt=prompt if self.prompt is not None else None,
                negative_prompt=negative if self.prompt is not None else None, syntax="ComfyUI",
                character_syntax="ComfyUI", text_regions=texts, nai_settings_json=self.nai_settings_json)
        return CharacterPipe(tuple(chars), prompt=prompt if self.prompt is not None else None,
                             negative_prompt=negative if self.prompt is not None else None, syntax="ComfyUI",
                             character_syntax="ComfyUI", nai_settings_json=self.nai_settings_json)


def pipe_from_context(context):
    from .generation_context import NAIContext
    if not isinstance(context, NAIContext):
        # Incomplete metadata must still leave IMAGE/MASK usable.
        return NAICharacterPipe(())
    return NAICharacterPipe(context.characters, context.prompt, context.negative_prompt,
        local_record_json=context.local_record_json,
        nai_settings_json=json.dumps(context_snapshot(context), ensure_ascii=True, allow_nan=False))


def nai_character_list(source):
    """Accept legacy lists and the local sampler's native character pipe."""
    if source is None:
        return []
    if isinstance(source, NAICharacterPipe) and source.syntax == "NovelAI":
        return list(source)
    if not hasattr(source, "characters"):
        return list(source)
    from .generation_context import ContextCharacter
    syntax = getattr(source, "character_syntax", None) or source.syntax
    if syntax not in ("NovelAI", "ComfyUI"):
        raise ValueError("Unsupported character pipe prompt syntax.")
    convert = (lambda text: text) if syntax == "NovelAI" else comfy_to_nai
    return [ContextCharacter(convert(c.prompt), convert(c.uc), c.center['x'], c.center['y'])
            for c in source.characters]


def prepare_characters(model_id, source, *, inpainting=False):
    from .nai_api import character_limit, INPAINT_MODEL_ID_OVERRIDES
    characters = nai_character_list(source)
    snapshot = local_record(source)
    if snapshot:
        local = json.loads(snapshot).get("rs_multicharacter", {})
        features = []
        if any(local.get("character_masks", [])) or any(local.get("boxes", [])):
            features.append("mask/box")
        if any(v.get("name", "None") != "None" for v in local.get("character_loras", [])):
            features.append("LoRA")
        if local.get("text_regions"):
            features.append("text regions")
        if local.get("interaction") or any(local.get("body_parts", [])):
            features.append("interaction/body guidance")
        if features:
            notice("NAI receives captions and center coordinates. Local-only settings are preserved for return, "
                   "but not applied by NAI / 로컬 전용 설정은 보존되며 NAI에서는 적용되지 않습니다: " + ", ".join(features))
    effective_model = INPAINT_MODEL_ID_OVERRIDES.get(model_id, f"{model_id}-inpainting") if inpainting else model_id
    limit = character_limit(effective_model)
    if characters and not limit:
        from .nai_api import validate_character_prompts
        validate_character_prompts(effective_model, characters)
    if len(characters) > limit:
        notice(f"{effective_model}: using the first {limit} of {len(characters)} characters; original pipe preserved. / NAI 모델 한도에 따라 앞 {limit}명만 사용합니다. 원본 파이프는 유지됩니다.")
    return characters[:limit]


def nai_pipe_prompts(prompt, negative_prompt, source):
    if source is None or not hasattr(source, "characters") or source.prompt is None:
        return prompt, negative_prompt
    if source.syntax == "NovelAI":
        return source.prompt, source.negative_prompt or ""
    if source.syntax != "ComfyUI":
        raise ValueError("Unsupported character pipe prompt syntax.")
    return comfy_to_nai(source.prompt), comfy_to_nai(source.negative_prompt or "")


def pipe_from_metadata(metadata):
    from .generation_context import ContextCharacter
    settings = metadata.get("settings", {})
    blocked = {"invalid_characters", "invalid_comment", "invalid_record", "invalid_exif",
               "invalid_hidden_metadata", "automatic_coordinates", "inset_canvas_coordinates", "detailer_not_base"}
    if blocked.intersection(metadata.get("warnings", [])):
        raise ValueError("Character metadata or coordinates cannot be restored safely. / 캐릭터 정보 또는 좌표를 복원할 수 없습니다.")
    characters = []
    for item in metadata.get("characters", []):
        centers = item.get("centers", [])
        if len(centers) != 1:
            raise ValueError("The shared pipe requires one X/Y center per character.")
        x, y = centers[0].get("x"), centers[0].get("y")
        if (type(x) not in (int, float) or type(y) not in (int, float)
                or not math.isfinite(x) or not math.isfinite(y) or not 0 <= x <= 1 or not 0 <= y <= 1):
            raise ValueError("Invalid character X/Y metadata.")
        characters.append(ContextCharacter(item["prompt"], item["negative_prompt"], x, y))
    return NAICharacterPipe(tuple(characters), settings.get("prompt"), settings.get("negative_prompt"),
                            metadata.get("prompt_syntax", "NovelAI"),
                            local_record_json=json.dumps(metadata["local_record"], allow_nan=False) if metadata.get("local_record") else None,
                            nai_settings_json=json.dumps(metadata["record"]["nai_context"], allow_nan=False) if metadata.get("record", {}).get("nai_context") else None)


def local_record(source):
    """Copy a bounded scene snapshot; never copy raw API payloads or tensors."""
    if source is None:
        return None
    existing = getattr(source, "local_record_json", None)
    if existing is not None:
        from .metadata import json_object
        return json.dumps(json_object(existing), ensure_ascii=True, allow_nan=False)
    export = getattr(source, "rs_context_record", None)
    if callable(export):
        from .metadata import json_object
        text = json.dumps(export(), ensure_ascii=True, allow_nan=False)
        json_object(text)
        return text
    return None


def context_snapshot(context):
    return {"settings": {**{k: getattr(context, k) for k in (
        "prompt", "negative_prompt", "model", "sampler", "steps", "cfg_scale", "scheduler",
        "cfg_rescale", "prefer_brownian", "variety_boost")},
        "seed": context.source_seed, "width": context.source_size[0], "height": context.source_size[1]},
        "characters": [{"prompt": c.prompt, "negative_prompt": c.uc, "centers": [c.center]} for c in context.characters],
        "operation": context.source_action, "warnings": ["references_omitted"] if context.references_omitted else []}


def inherited_pipe_settings(source, manual):
    from .generation_context import NAIContext, INHERITED_FIELDS
    from .metadata_context import restore_context
    from .metadata import json_object
    if manual is None:
        raise ValueError("Local pipes require this node's NAI model and sampling settings.")
    settings = {key: manual[key] for key in INHERITED_FIELDS}
    saved = getattr(source, "nai_settings_json", None)
    if saved:
        context, _ = restore_context(json_object(saved))
        if not isinstance(context, NAIContext):
            raise ValueError("The stored NAI settings are incomplete. Disable context or choose valid NAI settings.")
        settings.update(context.settings())
    settings["prompt"], settings["negative_prompt"] = nai_pipe_prompts(
        settings["prompt"], settings["negative_prompt"], source)
    # Keep the immutable source until request construction captures its extras.
    settings["characterPrompts"] = source
    return settings


def context_extra(context):
    extra = {"nai_context": context_snapshot(context)}
    if context.local_record_json:
        from .metadata import json_object
        extra["local_context"] = json_object(context.local_record_json)
    return extra
