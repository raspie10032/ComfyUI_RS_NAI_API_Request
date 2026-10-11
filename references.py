# SPDX-License-Identifier: GPL-3.0-only
"""NovelAI image references, separate from WD prompt matching."""

import base64
import hashlib
import io
import json
import math
import os
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

import requests
import torch
from PIL import Image, ImageOps

from .image_utils import pil_to_base64, tensor_to_pil
from .nai_api import post_nai
from .runtime_control import check_interrupted

ENCODE_VIBE_URL = "https://image.novelai.net/ai/encode-vibe"
VIBE_MODELS = {
    "nai-diffusion-3",
    "nai-diffusion-furry-3",
    "nai-diffusion-4-curated-preview",
    "nai-diffusion-4-full",
    "nai-diffusion-4-5-curated",
    "nai-diffusion-4-5-full",
}
PRECISE_MODELS = {"nai-diffusion-4-5-curated", "nai-diffusion-4-5-full"}
REFERENCE_TYPES = ["character", "style", "character&style"]
MAX_REFERENCES = 16
_encode_lock = threading.Lock()


@dataclass(frozen=True)
class VibeReference:
    image: str = field(repr=False)
    strength: float = 0.6
    information_extracted: float = 1.0


@dataclass(frozen=True)
class PreciseReference:
    image: str = field(repr=False)
    reference_type: str = "character"
    strength: float = 1.0
    fidelity: float = 1.0


def _finite(value, name):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    return value


def _unit(value, name):
    value = _finite(value, name)
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1.")
    return value


def _image(image):
    if image.ndim != 4 or image.shape[0] != 1 or image.shape[-1] not in (3, 4):
        raise ValueError("Each reference node requires one RGB/RGBA image; chain nodes for multiple references.")
    if min(image.shape[1:3]) < 1 or not torch.isfinite(image).all():
        raise ValueError("Reference image must contain finite pixels and have nonzero dimensions.")
    rgba = tensor_to_pil(image).convert("RGBA")
    result = Image.new("RGBA", rgba.size, "black")
    result.alpha_composite(rgba)
    return result.convert("RGB")


def _precise_image(image):
    # Match the official client's closest-aspect canvas and black letterboxing.
    sizes = [(1024, 1536), (1536, 1024), (1472, 1472)]
    ratio = image.width / image.height
    size = min(sizes, key=lambda s: abs(s[0] / s[1] - ratio))
    return ImageOps.pad(image, size, method=Image.Resampling.LANCZOS, color="black")


def _chain(previous, reference, kind):
    items = tuple(previous or ())
    if any(not isinstance(item, kind) for item in items):
        raise ValueError("Connect references of the same type when chaining nodes.")
    if reference is not None:
        items += (reference,)
    if len(items) > MAX_REFERENCES:
        raise ValueError(f"At most {MAX_REFERENCES} references can be connected.")
    return (items,)


class NAIVibeTransfer:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "strength": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.01}),
                "information_extracted": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01,
                    "tooltip": "V4/V4.5 encoding costs Anlas on first use of an image/settings combination; later uses reuse the local cache. Changing this value needs a new encoding.",
                }),
            },
            "optional": {"vibes": ("RS_NAI_VIBES",), "enabled": ("BOOLEAN", {"default": True})},
        }

    RETURN_TYPES = ("RS_NAI_VIBES",)
    RETURN_NAMES = ("vibes",)
    FUNCTION = "build"
    CATEGORY = "RS_NovelAI_API/References"
    DESCRIPTION = "Style/composition guidance. V3/V4/V4.5 only. V4/V4.5 Vibe cannot be used for inpainting or with Precise Reference. Chain nodes to add images."

    def build(self, image, strength=0.6, information_extracted=1.0, vibes=None, enabled=True):
        reference = None
        if enabled:
            strength = _finite(strength, "strength")
            information_extracted = _unit(information_extracted, "information_extracted")
            if strength != 0:
                reference = VibeReference(pil_to_base64(_image(image)), strength, information_extracted)
        return _chain(vibes, reference, VibeReference)


class NAIPreciseReference:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "reference_type": (REFERENCE_TYPES, {"default": "character"}),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "fidelity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": {"references": ("RS_NAI_REFERENCES",), "enabled": ("BOOLEAN", {"default": True})},
        }

    RETURN_TYPES = ("RS_NAI_REFERENCES",)
    RETURN_NAMES = ("references",)
    FUNCTION = "build"
    CATEGORY = "RS_NovelAI_API/References"
    DESCRIPTION = "V4.5 character/style reference, including inpainting. Each active reference adds Anlas cost per generation. Multiple character references blend identities; they are not mapped to character slots. Cannot combine with Vibe."

    def build(self, image, reference_type="character", strength=1.0, fidelity=1.0,
              references=None, enabled=True):
        reference = None
        if enabled:
            if reference_type not in REFERENCE_TYPES:
                raise ValueError("Unknown Precise Reference type.")
            strength = _finite(strength, "strength")
            fidelity = _finite(fidelity, "fidelity")
            if strength != 0:
                reference = PreciseReference(
                    pil_to_base64(_precise_image(_image(image))), reference_type, strength, fidelity
                )
        return _chain(references, reference, PreciseReference)


def reference_inputs():
    return {
        "vibes": ("RS_NAI_VIBES",),
        "references": ("RS_NAI_REFERENCES",),
        "normalize_vibe_strengths": ("BOOLEAN", {"default": True, "tooltip": "V4/V4.5 Vibe: scale strengths down if their absolute sum exceeds 1.0."}),
    }


def validate_references(model_id, vibes=None, references=None, inpainting=False):
    """Check every entry before any paid encoding or generation request."""
    if vibes and references:
        raise ValueError("NovelAI does not support Vibe Transfer and Precise Reference together. Connect only one.")
    for items, kind in ((vibes, VibeReference), (references, PreciseReference)):
        if not items:
            continue
        if len(items) > MAX_REFERENCES or any(not isinstance(item, kind) for item in items):
            raise ValueError(f"Expected at most {MAX_REFERENCES} references of the connected type.")
        for item in items:
            _finite(item.strength, "strength")
            if not item.image:
                raise ValueError("Reference image is empty.")
            if isinstance(item, VibeReference):
                _unit(item.information_extracted, "information_extracted")
            else:
                _finite(item.fidelity, "fidelity")
                if item.reference_type not in REFERENCE_TYPES:
                    raise ValueError("Unknown Precise Reference type.")
    if vibes:
        if model_id not in VIBE_MODELS:
            raise ValueError("Vibe Transfer requires NAI V3, V4, or V4.5. V5 and the legacy Furry model are not supported; select a supported model explicitly.")
        if inpainting and model_id.startswith("nai-diffusion-4"):
            raise ValueError("V4/V4.5 Vibe Transfer does not support inpainting/detailing. Use V4.5 Precise Reference for this process.")
    if references and model_id not in PRECISE_MODELS:
        raise ValueError("Precise Reference requires NAI V4.5 Full or Curated. Select V4.5 explicitly.")


def _encoded_vibe(vibe, model_id, token):
    import folder_paths

    key = hashlib.sha256(json.dumps(
        [1, model_id, float(vibe.information_extracted).hex(), vibe.image],
        separators=(",", ":"),
    ).encode()).hexdigest()
    directory = Path(folder_paths.models_dir) / "rs_nai_vibes"
    path = directory / f"{key}.json"
    while not _encode_lock.acquire(timeout=0.1):
        check_interrupted()
    try:
        check_interrupted()
        if path.exists():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                raw = base64.b64decode(cached["encoding"], validate=True)
                if not raw or hashlib.sha256(raw).hexdigest() != cached["sha256"]:
                    raise ValueError("Invalid checksum")
                return cached["encoding"]
            except (ValueError, KeyError, TypeError) as exc:
                raise RuntimeError(f"Invalid Vibe cache: {path}. Restore or remove this file before re-encoding; re-encoding can cost Anlas.") from exc
        # Create/check the destination before requesting a paid encoding.
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            try:
                try:
                    raw = post_nai(token, {
                        "image": vibe.image,
                        "information_extracted": vibe.information_extracted,
                        "model": model_id,
                    }, url=ENCODE_VIBE_URL)
                except requests.HTTPError as exc:
                    if exc.response is not None and exc.response.status_code == 402:
                        raise RuntimeError(
                            "NovelAI requires more Anlas to encode this Vibe. Check your Anlas balance; no encoding was cached and no generation was sent."
                        ) from exc
                    raise
                if not raw:
                    raise RuntimeError("NovelAI returned an empty Vibe encoding.")
                encoding = base64.b64encode(raw).decode("ascii")
                json.dump({"encoding": encoding, "sha256": hashlib.sha256(raw).hexdigest()}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            except BaseException:
                handle.close()
                temporary.unlink(missing_ok=True)
                raise
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return encoding
    finally:
        _encode_lock.release()


def reference_parameters(model_id, token, vibes=None, references=None,
                         normalize_vibe_strengths=True, inpainting=False):
    validate_references(model_id, vibes, references, inpainting)
    check_interrupted()
    if references:
        return {
            "director_reference_images": [r.image for r in references],
            "director_reference_descriptions": [
                {"caption": {"base_caption": r.reference_type, "char_captions": []}, "legacy_uc": False}
                for r in references
            ],
            "director_reference_information_extracted": [1.0 for _ in references],
            "director_reference_strength_values": [r.strength for r in references],
            "director_reference_secondary_strength_values": [1.0 - r.fidelity for r in references],
        }
    if not vibes:
        return {}
    strengths = [v.strength for v in vibes]
    if model_id.startswith("nai-diffusion-4"):
        if normalize_vibe_strengths and sum(abs(s) for s in strengths) > 1:
            total = sum(abs(s) for s in strengths)
            strengths = [s / total for s in strengths]
        return {
            "reference_image_multiple": [_encoded_vibe(v, model_id, token) for v in vibes],
            "reference_strength_multiple": strengths,
        }
    images = []
    for vibe in vibes:
        image = Image.open(io.BytesIO(base64.b64decode(vibe.image)))
        images.append(pil_to_base64(ImageOps.pad(
            image, (448, 448), method=Image.Resampling.LANCZOS, color="black"
        )))
    return {
        "reference_image_multiple": images,
        "reference_information_extracted_multiple": [v.information_extracted for v in vibes],
        "reference_strength_multiple": strengths,
    }
