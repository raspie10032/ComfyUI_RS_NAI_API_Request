# SPDX-License-Identifier: GPL-3.0-only
"""Shared 2-D camera framing. No guessed depth or model-specific projection."""
import base64
from dataclasses import replace
import json
import math


def framing(distance, roll, aspect):
    if type(aspect) not in (int, float) or not math.isfinite(aspect) or not .1 <= aspect <= 10:
        raise ValueError("Camera canvas aspect must be 0.1–10 (width / height). / 화면 비율은 너비÷높이, 0.1~10입니다.")
    angle = math.radians(roll)
    return 2 ** (2 * (.5 - distance)), math.cos(angle), math.sin(angle), aspect


def project(x, y, transform):
    scale, co, si, aspect = transform
    x, y = (x - .5) * aspect, y - .5
    return (.5 + scale * (co*x - si*y) / aspect,
            .5 + scale * (si*x + co*y))


def _warp(mask, transform):
    # Chunked inverse nearest sampling keeps memory bounded on 4096px masks.
    import numpy as np
    scale, co, si, aspect = transform
    if scale == 1 and si == 0:
        return mask
    w, h = mask.width, mask.height
    source = np.unpackbits(np.frombuffer(mask.packed, dtype=np.uint8), count=w*h).reshape(h, w)
    result = np.zeros((h, w), dtype=np.uint8)
    x = ((np.arange(w, dtype=np.float64) + .5) / w - .5) * aspect / scale
    for top in range(0, h, 64):
        y = ((np.arange(top, min(top+64, h), dtype=np.float64) + .5) / h - .5)[:, None] / scale
        sx = np.floor((.5 + (co*x + si*y)/aspect) * w).astype(np.int64)
        sy = np.floor((.5 - si*x + co*y) * h).astype(np.int64)
        inside = (sx >= 0) & (sx < w) & (sy >= 0) & (sy < h)
        result[top:top+len(y)] = source[sy.clip(0,h-1), sx.clip(0,w-1)] * inside
    if not result.any():
        return None
    return replace(mask, packed=np.packbits(result.reshape(-1)).tobytes())


def _character(character, transform, number):
    mask = getattr(character, "region_mask", None)
    box = getattr(character, "bbox", None)
    part_changes = {}
    if hasattr(character, "body_parts"):
        part_changes["body_parts"] = tuple((name, changed) for name, part in character.body_parts
                      if (changed := _warp(part, transform)) is not None)
    if mask is not None:
        region = _warp(mask, transform)
        if region is None:
            raise ValueError(f"Camera framing hides character {number}'s entire mask. Reduce zoom/tilt or adjust Position. / 카메라 배치로 {number}번 마스크가 전부 화면 밖입니다. 확대·기울기를 줄이거나 위치를 조절해 주세요.")
        x, y = region.center
        return replace(character, x=x, y=y, region_mask=region, bbox=None, **part_changes)
    if box is not None:
        left, top, right, bottom = box
        corners = [project(x,y,transform) for x in (left,right) for y in (top,bottom)]
        left, top = max(0., min(p[0] for p in corners)), max(0., min(p[1] for p in corners))
        right, bottom = min(1., max(p[0] for p in corners)), min(1., max(p[1] for p in corners))
        if left >= right or top >= bottom:
            raise ValueError(f"Camera framing hides character {number}'s box. / {number}번 상자가 카메라 화면 밖입니다. 확대·기울기를 줄여 주세요.")
        return replace(character, x=(left+right)/2, y=(top+bottom)/2, bbox=(left,top,right,bottom), **part_changes)
    x, y = project(character.x, character.y, transform)
    if not 0 <= x <= 1 or not 0 <= y <= 1:
        raise ValueError(f"Camera framing puts character {number}'s point outside the canvas. Reduce zoom/tilt. / {number}번 좌표가 화면 밖입니다. 확대·기울기를 줄여 주세요.")
    return replace(character, x=x, y=y, **part_changes)


def camera_layout(context, distance, roll, aspect):
    transform = framing(distance, roll, aspect)
    if transform[0] == 1 and transform[2] == 0:
        return context
    # NAI carries local masks in an immutable metadata snapshot. Edit that
    # snapshot and its visible centers together, preserving its NAI settings.
    if getattr(context, "local_record_json", None) and callable(getattr(context,"as_local_character_pipe",None)):
        native = context.as_local_character_pipe()
        changed = camera_layout(native, distance, roll, aspect)
        characters = tuple(replace(c, x=n.x, y=n.y) for c,n in zip(context.characters,changed.characters))
        if len(characters) != len(context.characters):
            raise ValueError("Camera layout needs all characters; use at most 10 for local masks. / 마스크 연동은 캐릭터 10명까지 가능합니다.")
        return replace(context, characters=characters,
                       local_record_json=json.dumps(changed.rs_context_record(), ensure_ascii=True, allow_nan=False))
    return replace(context, characters=tuple(_character(c,transform,i) for i,c in enumerate(context.characters,1)))


def layout_preview(context):
    """Bounded, executed input thumbnail, for live client-side framing only."""
    if context is None:
        return []
    if getattr(context, "local_record_json", None) and callable(getattr(context,"as_local_character_pipe",None)):
        context = context.as_local_character_pipe()
    rows = []
    for i, c in enumerate(context.characters, 1):
        row = dict(id=i, x=c.x, y=c.y, box=getattr(c,"bbox",None))
        mask = getattr(c,"region_mask",None)
        if mask is not None:
            import numpy as np
            w, h = mask.width, mask.height
            factor = min(1., 128/max(w,h))
            pw, ph = max(1,round(w*factor)), max(1,round(h*factor))
            source = np.unpackbits(np.frombuffer(mask.packed,dtype=np.uint8),count=w*h).reshape(h,w)
            x = np.minimum(w-1, ((np.arange(pw)+.5)/pw*w).astype(int))
            y = np.minimum(h-1, ((np.arange(ph)+.5)/ph*h).astype(int))
            row["mask"] = dict(width=pw,height=ph,
                bits=base64.b64encode(np.packbits(source[y[:,None],x[None,:]].reshape(-1))).decode("ascii"))
        rows.append(row)
    for i,c in enumerate(getattr(context,"text_regions",()), len(rows)+1):
        rows.append(dict(id=i,x=c.x,y=c.y,box=getattr(c,"bbox",None),kind="text"))
    return rows
