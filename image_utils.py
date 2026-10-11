# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2025 raspie10032

import base64
import io

import numpy as np
import torch
from PIL import Image
from PIL.PngImagePlugin import PngInfo


def pil_to_base64(img):
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def png_bytes_to_pil(png_bytes):
    source = Image.open(io.BytesIO(png_bytes))
    image = source.convert("RGB")
    image.info.update(source.info)
    return image


def pil_to_tensor(img):
    img_np = np.array(img).astype(np.float32) / 255.0
    return torch.from_numpy(img_np).unsqueeze(0)


def tensor_to_pil(tensor, batch_index=0):
    img_np = tensor[batch_index].detach().cpu().numpy()
    img_np = (img_np * 255.0).clip(0, 255).astype(np.uint8)
    return Image.fromarray(img_np)


def validate_single_image(image):
    if not isinstance(image, torch.Tensor) or image.ndim != 4 or image.shape[0] != 1 or image.shape[-1] not in (3, 4):
        raise ValueError("This node requires one RGB/RGBA image. Split image batches before connecting; no images were sent.")
    if min(image.shape[1:3]) < 1 or not torch.isfinite(image).all():
        raise ValueError("Image must have nonzero dimensions and finite pixels.")


def mask_to_pil(mask):
    if not isinstance(mask, torch.Tensor) or mask.ndim not in (2, 3) or (mask.ndim == 3 and mask.shape[0] != 1):
        raise ValueError("Inpaint requires one mask (H,W or 1,H,W); split mask batches before connecting.")
    if min(mask.shape[-2:]) < 1 or not torch.isfinite(mask).all() or (mask < 0).any() or (mask > 1).any():
        raise ValueError("Mask must have nonzero dimensions and finite values from 0 to 1.")
    array = (mask.detach().cpu().numpy().reshape(mask.shape[-2:]) * 255).astype(np.uint8)
    if not array.any():
        raise ValueError("Inpaint mask is empty. Paint the area to change white; no request was sent.")
    return Image.fromarray(array)


def build_pnginfo_from_image(source_image):
    pnginfo = PngInfo()
    for key, value in source_image.info.items():
        if isinstance(value, str):
            pnginfo.add_text(key, value)
    return pnginfo


def save_png_preserving_metadata(image, save_path, source_image=None):
    if source_image is None:
        image.save(save_path)
        return
    image.save(save_path, pnginfo=build_pnginfo_from_image(source_image))
