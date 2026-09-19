# SPDX-License-Identifier: GPL-3.0-only
"""Region planning, identity selection and sequential masked inpainting."""

import json

import numpy as np
from PIL import Image, ImageDraw

from .detailer_matching import Match, match_characters, selected_prompts
from .image_utils import (
    pil_to_base64,
    pil_to_tensor,
    png_bytes_to_pil,
    save_png_preserving_metadata,
    tensor_to_pil,
)
from .nai_api import (
    apply_opus_free_limits,
    apply_v4_parameters,
    build_common_parameters,
    build_nai_payload,
    get_model_id,
    get_nai_token,
    post_nai,
    zip_to_png_bytes,
)
from .runtime_control import check_interrupted


def _detect(detector, image, threshold, dilation, crop_factor, drop_size=10):
    check_interrupted()
    if detector is None:
        return []
    segs = detector.detect(
        image, threshold, dilation, crop_factor, drop_size=drop_size, detailer_hook=None
    )
    return list(segs[1]) if segs else []


def _center(box):
    x0, y0, x1, y1 = box
    return ((x0 + x1) / 2, (y0 + y1) / 2)


def _owner(box, regions):
    x, y = _center(box)
    # Containment takes priority; otherwise use nearest detection center.
    return min(
        range(len(regions)),
        key=lambda i: (
            not (
                regions[i].bbox[0] <= x <= regions[i].bbox[2]
                and regions[i].bbox[1] <= y <= regions[i].bbox[3]
            ),
            (_center(regions[i].bbox)[0] - x) ** 2
            + (_center(regions[i].bbox)[1] - y) ** 2,
        ),
    )


def _crop_box(box, width, height):
    x0, y0, x1, y1 = box
    return (max(0, int(x0)), max(0, int(y0)), min(width, int(x1)), min(height, int(y1)))


def _context_crop(image, bbox, factor):
    x, y = _center(bbox)
    half_w = (bbox[2] - bbox[0]) * factor / 2
    half_h = (bbox[3] - bbox[1]) * factor / 2
    return image.crop(
        _crop_box((x - half_w, y - half_h, x + half_w, y + half_h), *image.size)
    )


def run_face_detail(
    image,
    primary_detector,
    secondary_detector,
    sam_model,
    prompt,
    negative_prompt,
    model,
    strength,
    threshold,
    sampler,
    steps,
    cfg_scale,
    bbox_threshold,
    dilation,
    crop_factor,
    scheduler,
    seed,
    eye_bbox_detector=None,
    limit_opus_free=True,
    detail_mode="first",
    matching_mode="shared",
    characterPrompts=None,
    tagger=None,
    match_min_score=0.25,
    match_min_margin=0.08,
    match_crop_factor=2.0,
    max_regions=16,
    preview_only=False,
):
    from .generators import NovelAIGenerator, mask_to_grid_boxes

    if limit_opus_free and not preview_only:
        raise RuntimeError("limit_opus_free blocks face detailing because inpainting can spend Anlas. Set it to False to allow paid requests.")

    if detail_mode not in {"first", "all"} or matching_mode not in {"shared", "wd14"}:
        raise ValueError("Unknown detail or matching mode.")
    characters = list(characterPrompts or [])
    if matching_mode != "shared" and not characters:
        raise ValueError(
            "Connect original CharacterPromptSelect output for character matching."
        )
    if matching_mode == "shared" and len(characters) > 1:
        raise ValueError("Multiple characters require wd14 matching.")
    if matching_mode == "wd14" and tagger is None:
        raise ValueError("Connect NAI WD Tagger Loader for wd14 matching.")

    source = tensor_to_pil(image)
    w, h = source.size
    detected = _detect(primary_detector, image, bbox_threshold, dilation, crop_factor)
    # Keep a stable spatial numbering for all-mode and previews; first preserves detector order.
    if detail_mode == "all":
        detected.sort(key=lambda s: (_center(s.bbox)[0], _center(s.bbox)[1]))
    regions = []
    for seg in detected:
        values = tuple(seg.bbox) + tuple(seg.crop_region)
        if not all(np.isfinite(v) for v in values):
            continue
        x0, y0, x1, y1 = _crop_box(seg.crop_region, w, h)
        bx0, by0, bx1, by1 = _crop_box(seg.bbox, w, h)
        if x1 > x0 and y1 > y0 and bx1 > bx0 and by1 > by0:
            regions.append(seg)
    if not regions:
        return image, image, json.dumps({"regions": [], "status": "no_detections"})
    # Ownership uses every detection, even when limiting the number of requests.
    active_count = min(len(regions), 1 if detail_mode == "first" else max_regions)
    matches = [
        Match(
            0 if characters and matching_mode == "shared" else None,
            1.0,
            1.0,
            "shared" if matching_mode == "shared" else "unassigned",
        )
        for _ in regions
    ]
    pending = list(range(active_count))
    if matching_mode == "wd14" and pending:
        scores = tagger.score(
            [_context_crop(source, regions[i].bbox, match_crop_factor) for i in pending]
        )
        if len(scores) != len(pending):
            raise ValueError("Tagger returned an unexpected number of regions.")
        for i, score in zip(pending, scores):
            matches[i] = match_characters(
                score, characters, match_min_score, match_min_margin
            )
        del scores  # Tagger observations do not enter the request builder.
        # A contextual crop can include another character. Retry uncertain
        # regions once with less context; never force an assignment by order.
        uncertain = [i for i in pending if matches[i].character_index is None]
        tight_factor = min(1.25, match_crop_factor)
        if uncertain and tight_factor < match_crop_factor:
            tight_scores = tagger.score(
                [
                    _context_crop(source, regions[i].bbox, tight_factor)
                    for i in uncertain
                ]
            )
            if len(tight_scores) != len(uncertain):
                raise ValueError("Tagger returned an unexpected number of regions.")
            for i, score in zip(uncertain, tight_scores):
                match = match_characters(
                    score, characters, match_min_score, match_min_margin
                )
                if match.character_index is not None:
                    matches[i] = Match(
                        match.character_index,
                        match.score,
                        match.margin,
                        "tag_match_tight",
                    )
            del tight_scores

    report = []
    for i, (seg, match) in enumerate(zip(regions, matches)):
        eligible = i < active_count and (
            matching_mode == "shared" or match.character_index is not None
        )
        report.append(
            {
                "region": i + 1,
                "bbox": [float(x) for x in seg.bbox],
                "crop": list(_crop_box(seg.crop_region, w, h)),
                "character": None
                if match.character_index is None
                else match.character_index + 1,
                "score": match.score,
                "margin": match.margin,
                "reason": match.reason,
                "status": "planned" if eligible else "skipped",
            }
        )
    if preview_only:
        preview = source.copy()
        draw = ImageDraw.Draw(preview)
        for item in report:
            color = "lime" if item["status"] == "planned" else "orange"
            draw.rectangle(item["bbox"], outline=color, width=2)
            draw.text(
                (item["bbox"][0], item["bbox"][1]),
                f"{item['region']} -> {item['character'] or '?'}",
                fill=color,
            )
        return (
            pil_to_tensor(preview),
            pil_to_tensor(Image.new("RGB", source.size)),
            json.dumps(report),
        )
    if not any(r["status"] == "planned" for r in report):
        return image, pil_to_tensor(Image.new("RGB", source.size)), json.dumps(report)

    token = get_nai_token()
    model_id = get_model_id(model)
    secondaries = _detect(
        secondary_detector, image, bbox_threshold, dilation, crop_factor
    )
    from segment_anything import SamPredictor

    predictor = SamPredictor(sam_model)
    out = source.copy()
    total_mask = np.zeros((h, w), dtype=np.uint8)
    base_seed = int(np.random.randint(0, 0x7FFFFFFF)) if seed == -1 else int(seed)
    last_result = None
    for index, seg in enumerate(regions[:active_count]):
        if report[index]["status"] != "planned":
            continue
        check_interrupted()
        crx0, cry0, crx1, cry1 = _crop_box(seg.crop_region, w, h)
        # Frozen source: another request must not change this region's input or identity.
        crop = source.crop((crx0, cry0, crx1, cry1))
        cw, ch = crop.size
        scale = 1024 / max(cw, ch)
        nw, nh, request_steps = apply_opus_free_limits(
            max(64, round(cw * scale) // 64 * 64),
            max(64, round(ch * scale) // 64 * 64),
            steps,
            limit_opus_free,
        )
        scaled = crop.resize((nw, nh), Image.Resampling.LANCZOS)
        sx, sy = nw / cw, nh / ch
        predictor.set_image(np.array(scaled.convert("RGB")))
        boxes = [seg.bbox] + [
            s.bbox for s in secondaries if _owner(s.bbox, regions) == index
        ]
        mask_np = np.zeros((nh, nw), dtype=np.uint8)
        for bx0, by0, bx1, by1 in boxes:
            check_interrupted()
            box = [
                max(0, (bx0 - crx0) * sx),
                max(0, (by0 - cry0) * sy),
                min(nw, (bx1 - crx0) * sx),
                min(nh, (by1 - cry0) * sy),
            ]
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            masks, _, _ = predictor.predict(
                box=np.array([box], dtype=float), multimask_output=False
            )
            mask_np = np.maximum(mask_np, (masks[0] * 255).astype(np.uint8))
        for eye in _detect(
            eye_bbox_detector, pil_to_tensor(scaled), bbox_threshold, dilation, 1.0, 4
        ):
            ex0, ey0, ex1, ey1 = eye.bbox
            original_box = (
                ex0 / sx + crx0,
                ey0 / sy + cry0,
                ex1 / sx + crx0,
                ey1 / sy + cry0,
            )
            if _owner(original_box, regions) != index:
                continue
            ex0, ey0, ex1, ey1 = _crop_box(eye.crop_region, nw, nh)
            if ex1 > ex0 and ey1 > ey0:
                mask_np[ey0:ey1, ex0:ex1] = 255
        if not mask_np.any():
            report[index]["status"] = "empty_mask"
            continue
        grid_mask = mask_to_grid_boxes(mask_np, nw, nh, threshold)
        # Preserve the original 32px boxes / 8px stride at API resolution.
        # A downscale/upscale round trip breaks that grid and produces corrupt
        # infill edges on the live API. Clip ownership in whole 8px cells only.
        centers = [_center(s.bbox) for s in regions]
        own_x, own_y = centers[index]
        gy, gx = np.ogrid[: nh // 8, : nw // 8]
        gx = crx0 + (gx + 0.5) * 8 / sx
        gy = cry0 + (gy + 0.5) * 8 / sy
        own_cells = np.ones((nh // 8, nw // 8), dtype=bool)
        cell_distance = (gx - own_x) ** 2 + (gy - own_y) ** 2
        for other, (cx, cy) in enumerate(centers):
            if other != index:
                distance = (gx - cx) ** 2 + (gy - cy) ** 2
                own_cells &= (
                    cell_distance < distance
                    if other < index
                    else cell_distance <= distance
                )
        owned_pixels = np.repeat(np.repeat(own_cells, 8, axis=0), 8, axis=1)
        request_mask = Image.fromarray(
            np.where(owned_pixels, np.array(grid_mask), 0).astype(np.uint8)
        )
        local_mask = request_mask.resize((cw, ch), Image.Resampling.NEAREST)
        # Disjoint ownership at original resolution prevents overlapping crops from
        # overwriting another character. Build in crop space to bound memory.
        yy, xx = np.ogrid[cry0:cry1, crx0:crx1]
        own_distance = (xx - own_x) ** 2 + (yy - own_y) ** 2
        owns = np.ones((ch, cw), dtype=bool)
        for other, (cx, cy) in enumerate(centers):
            if other != index:
                distance = (xx - cx) ** 2 + (yy - cy) ** 2
                owns &= (
                    own_distance < distance
                    if other < index
                    else own_distance <= distance
                )
        local_array = np.where(owns, np.array(local_mask), 0).astype(np.uint8)
        local_mask = Image.fromarray(local_array)
        if not local_array.any():
            report[index]["status"] = "empty_mask"
            continue
        request_prompt, request_negative = selected_prompts(
            prompt, negative_prompt, characters, matches[index]
        )
        parameters = build_common_parameters(
            nw,
            nh,
            (base_seed + index) % 2**32,
            sampler,
            request_steps,
            cfg_scale,
            request_negative,
            scheduler=scheduler,
            cfg_rescale=0.0,
            prefer_brownian=False,
            variety_boost=True,
            model_id=model_id,
        )
        parameters.update(
            {
                "image": pil_to_base64(scaled),
                "mask": pil_to_base64(request_mask),
                "add_original_image": True,
                "inpaintImg2ImgStrength": strength,
                "noise": 0,
            }
        )
        # Single selected character is expressed in the crop's base prompt. No
        # full-image character coordinates or inferred tag text are forwarded.
        apply_v4_parameters(parameters, model_id, request_prompt, request_negative)
        payload = build_nai_payload(
            request_prompt, model_id, "infill", parameters, inpainting=True
        )
        check_interrupted()
        result = png_bytes_to_pil(zip_to_png_bytes(post_nai(token, payload, limit_opus_free=limit_opus_free)))
        if result.size != (nw, nh):
            raise ValueError("NAI returned an unexpected detail crop size.")
        out.paste(
            result.resize((cw, ch), Image.Resampling.LANCZOS), (crx0, cry0), local_mask
        )
        total_mask[cry0:cry1, crx0:crx1] = np.maximum(
            total_mask[cry0:cry1, crx0:crx1], local_array
        )
        report[index]["status"] = "edited"
        last_result = result
    if last_result is not None:
        # Preserve API metadata and record the multi-request provenance separately.
        last_result.info["rs_detailer_regions"] = json.dumps(report)
        folder, filename = NovelAIGenerator._get_save_path(
            "NAI_face", NovelAIGenerator._get_output_directory(), subfolder="face"
        )
        save_png_preserving_metadata(out, folder / f"{filename}.png", last_result)
    return (
        pil_to_tensor(out),
        pil_to_tensor(Image.fromarray(total_mask).convert("RGB")),
        json.dumps(report),
    )
