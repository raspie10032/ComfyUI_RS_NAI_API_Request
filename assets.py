# SPDX-License-Identifier: GPL-3.0-only
"""Portable reference PNGs containing only user-selected image and prompts."""

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from .diagnostics import notice
from .errors import user_error
from .image_utils import pil_to_tensor, tensor_to_pil, validate_single_image

ASSET_KEY = "rs_nai_character_asset"


def asset_directory():
    try:
        import folder_paths
        return Path(folder_paths.get_input_directory()) / "rs_nai_assets"
    except ImportError:
        return Path("input") / "rs_nai_assets"


def asset_path(filename):
    root = asset_directory().resolve()
    if not isinstance(filename, str) or not filename or "/" in filename or "\\" in filename or Path(filename).suffix.lower() != ".png":
        raise user_error("ASSET_FILE", ValueError, "Choose an asset PNG from input/rs_nai_assets.")
    path = (root / filename).resolve()
    if path.parent != root:
        raise user_error("ASSET_FILE", ValueError, "Asset paths must stay inside input/rs_nai_assets.")
    if not path.is_file():
        raise user_error("ASSET_FILE", FileNotFoundError, f"Asset not found: {filename}. Save an asset first, then refresh the list.")
    return path


class NAICharacterAssetSave:
    DESCRIPTION = "Save one reference image with its original character prompt and negative prompt in a portable PNG under ComfyUI/input/rs_nai_assets. Existing assets are never overwritten. Saving is local and uses no Anlas. The PNG contains these prompts: check them before sharing."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
            "name": ("STRING", {"default": "character", "tooltip": "Display name used in the file name. A unique suffix prevents overwriting."}),
            "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "Original character description to reuse with this image. No inferred tags are added."}),
            "negative_prompt": ("STRING", {"default": "", "multiline": True}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("asset_file",)
    FUNCTION = "save"
    CATEGORY = "RS_NovelAI_API/Characters"
    OUTPUT_NODE = True

    def save(self, image, name, prompt, negative_prompt):
        validate_single_image(image)
        root = asset_directory()
        root.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")[:60] or "character"
        # Prefix also prevents Windows reserved device names such as CON and AUX.
        filename = f"NAI_{safe_name}_{uuid.uuid4().hex}.png"
        metadata = PngInfo()
        metadata.add_text(ASSET_KEY, json.dumps({"version": 1, "name": name, "prompt": prompt,
                                               "negative_prompt": negative_prompt}, ensure_ascii=False))
        fd, temporary = tempfile.mkstemp(prefix=".rs_nai_asset_", suffix=".tmp", dir=root)
        try:
            with os.fdopen(fd, "wb") as output:
                tensor_to_pil(image).save(output, format="PNG", pnginfo=metadata)
            os.replace(temporary, root / filename)
        finally:
            Path(temporary).unlink(missing_ok=True)
        notice(f"Asset saved: input/rs_nai_assets/{filename}. Refresh the asset loader list to select it.")
        return {"ui": {"images": [{"filename": filename, "subfolder": "rs_nai_assets", "type": "input"}]},
                "result": (filename,)}


class NAICharacterAssetLoad:
    DESCRIPTION = "Load a reference PNG saved with NAI Character Asset Save. Refresh the list after saving or copying assets into input/rs_nai_assets. Outputs the image and original prompts unchanged. Connect prompt to a character slot or to the inset generator's base prompt, and add your scene description."

    @classmethod
    def INPUT_TYPES(cls):
        root = asset_directory()
        files = sorted(p.name for p in root.glob("*.png") if p.is_file() and p.resolve().parent == root.resolve())
        return {"required": {"asset_file": (files or [""], {"tooltip": "Select a saved asset PNG. Use Refresh assets to update this list after saving or importing."})}}

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "prompt", "negative_prompt")
    FUNCTION = "load"
    CATEGORY = "RS_NovelAI_API/Characters"

    @classmethod
    def IS_CHANGED(cls, asset_file):
        path = asset_path(asset_file)
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def load(self, asset_file):
        path = asset_path(asset_file)
        try:
            with Image.open(path) as source:
                data = json.loads(source.info.get(ASSET_KEY, "null"))
                if (not isinstance(data, dict) or data.get("version") != 1
                        or not all(isinstance(data.get(key), str) for key in ("name", "prompt", "negative_prompt"))):
                    raise user_error("ASSET_FILE", ValueError, "Missing or unsupported character asset metadata. Use NAI Character Asset Save to create the asset.")
                image = source.convert("RGBA" if "A" in source.getbands() or "transparency" in source.info else "RGB")
        except (json.JSONDecodeError, OSError) as exc:
            # Keep concrete permission/disk failures and the underlying PIL error.
            exc.rs_nai_code = "ASSET_FILE"
            raise
        return (pil_to_tensor(image), data["prompt"], data["negative_prompt"])


NODE_CLASS_MAPPINGS = {"NAICharacterAssetSave": NAICharacterAssetSave, "NAICharacterAssetLoad": NAICharacterAssetLoad}
NODE_DISPLAY_NAME_MAPPINGS = {"NAICharacterAssetSave": "NAI Character Asset Save", "NAICharacterAssetLoad": "NAI Character Asset Load"}
