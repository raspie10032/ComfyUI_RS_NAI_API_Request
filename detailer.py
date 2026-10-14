# SPDX-License-Identifier: GPL-3.0-only
"""Region planning, identity selection and sequential masked inpainting."""

from .errors import user_error

import json
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from .detailer_matching import Match, match_characters, selected_prompts
from .image_utils import (
    pil_to_base64,
    pil_to_tensor,
    png_bytes_to_pil,
    tensor_to_pil,
    validate_single_image,
)
from .metadata import autosave, request_record, read_fields, validate_save_options, context_record
from .diagnostics import notice
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
from .references import reference_parameters, validate_references
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


def _mask_array(mask, *, allow_batch=False):
    """Return a finite 0..1 numpy mask without depending on a torch import."""
    if hasattr(mask, "detach"):
        mask = mask.detach().cpu().numpy()
    array = np.asarray(mask)
    if allow_batch:
        if array.ndim == 2:
            array = array[None, ...]
        if array.ndim != 3:
            raise user_error("DETAIL_MASK_INPUT", ValueError, "detail_mask must be [H,W] or [B,H,W].")
    else:
        if array.ndim == 3 and array.shape[0] == 1:
            array = array[0]
        if array.ndim != 2:
            raise user_error("DETAIL_MASK_INPUT", ValueError, "A detector region must contain one 2D cropped_mask.")
    if min(array.shape[-2:]) < 1 or not np.isfinite(array).all():
        raise user_error("DETAIL_MASK_INPUT", ValueError, "Detail masks need positive spatial dimensions and finite values.")
    # SAM3 individual_masks=True returns [0,H,W] when no objects are detected.
    if allow_batch and array.shape[0] == 0:
        return array.astype(np.float32, copy=False)
    array = array.astype(np.float32, copy=False)
    if array.min() < 0 or array.max() > 1:
        raise user_error("DETAIL_MASK_INPUT", ValueError, "Detail mask values must stay between 0 and 1.")
    return array


def _expanded_crop(bbox, width, height, factor):
    x, y = _center(bbox)
    half_w = max(1.0, bbox[2] - bbox[0]) * factor / 2
    half_h = max(1.0, bbox[3] - bbox[1]) * factor / 2
    return _crop_box((x - half_w, y - half_h, x + half_w, y + half_h), width, height)


def _external_mask_regions(detail_mask, width, height, crop_factor, threshold):
    masks = _mask_array(detail_mask, allow_batch=True)
    if masks.shape[1:] != (height, width):
        raise user_error(
            "DETAIL_MASK_INPUT",
            ValueError,
            f"detail_mask must match the source image ({width}x{height}); got {masks.shape[2]}x{masks.shape[1]}.",
        )
    regions = []
    cutoff = max(float(threshold), 1e-6)
    for batch_index, mask in enumerate(masks):
        ys, xs = np.nonzero(mask >= cutoff)
        if not len(xs):
            continue
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        crop_region = _expanded_crop(bbox, width, height, crop_factor)
        x0, y0, x1, y1 = crop_region
        regions.append(
            SimpleNamespace(
                bbox=bbox,
                crop_region=crop_region,
                cropped_mask=mask[y0:y1, x0:x1],
                label=f"external_mask_{batch_index + 1}",
            )
        )
    return regions


def _native_crop_mask(seg, crop_region):
    if not hasattr(seg, "cropped_mask") or seg.cropped_mask is None:
        raise user_error(
            "DETAIL_MASK_INPUT", ValueError, "The selected SEGM detector did not provide cropped_mask data."
        )
    array = _mask_array(seg.cropped_mask)
    x0, y0, x1, y1 = crop_region
    expected = (y1 - y0, x1 - x0)
    if array.shape != expected:
        array = np.asarray(
            Image.fromarray(array, mode="F").resize(
                (expected[1], expected[0]), Image.Resampling.BILINEAR
            ),
            dtype=np.float32,
        )
    return np.clip(array, 0, 1)


def _native_owned_mask(index, regions, native_masks, width, height, threshold):
    """Keep instance membership; distance resolves only pixels in two masks."""
    x0, y0, x1, y1 = _crop_box(regions[index].crop_region, width, height)
    cutoff = max(float(threshold), 1e-6)
    owns = native_masks[index] >= cutoff
    own_x, own_y = _center(regions[index].bbox)
    for other, seg in enumerate(regions):
        check_interrupted()
        if other == index:
            continue
        ox0, oy0, ox1, oy1 = _crop_box(seg.crop_region, width, height)
        left, top, right, bottom = max(x0, ox0), max(y0, oy0), min(x1, ox1), min(y1, oy1)
        if left >= right or top >= bottom:
            continue
        member = native_masks[other][top - oy0:bottom - oy0, left - ox0:right - ox0] >= cutoff
        yy, xx = np.ogrid[top:bottom, left:right]
        cx, cy = _center(seg.bbox)
        own_distance = (xx - own_x) ** 2 + (yy - own_y) ** 2
        distance = (xx - cx) ** 2 + (yy - cy) ** 2
        wins = own_distance < distance if other < index else own_distance <= distance
        owns[top - y0:bottom - y0, left - x0:right - x0] &= ~member | wins
    return owns


def _cover_mask_cells(owns, width, height):
    """Cover every source pixel in whole API 8px cells, including thin shapes.

    Query source rectangles intersecting each cell, so downscaling or sampling
    at cell centers cannot discard a one-pixel strand or a tiny disconnected part.
    """
    h, w = owns.shape
    xs = np.arange(width // 8 + 1, dtype=np.float64) * (8 * w / width)
    ys = np.arange(height // 8 + 1, dtype=np.float64) * (8 * h / height)
    left, right = np.floor(xs[:-1]).astype(int), np.minimum(w, np.ceil(xs[1:]).astype(int))
    top, bottom = np.floor(ys[:-1]).astype(int), np.minimum(h, np.ceil(ys[1:]).astype(int))
    integral = np.pad(owns.astype(np.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    counts = (integral[bottom[:, None], right] - integral[top[:, None], right]
              - integral[bottom[:, None], left] + integral[top[:, None], left])
    return np.repeat(np.repeat(counts > 0, 8, axis=0), 8, axis=1)


def _native_mask_plan(index, regions, native_masks, source, threshold, steps,
                      limit_opus_free, eye_bbox_detector, bbox_threshold, dilation):
    """Shared preview/execution plan. API context may grow; paste stays in the mask."""
    from .generators import mask_to_grid_boxes

    check_interrupted()
    x0, y0, x1, y1 = _crop_box(regions[index].crop_region, *source.size)
    cw, ch = x1 - x0, y1 - y0
    scale = 1024 / max(cw, ch)
    nw, nh, request_steps = apply_opus_free_limits(
        max(64, round(cw * scale) // 64 * 64),
        max(64, round(ch * scale) // 64 * 64), steps, limit_opus_free,
    )
    owns = _native_owned_mask(index, regions, native_masks, *source.size, threshold)
    local_array = owns.astype(np.uint8) * 255
    raw = np.array(Image.fromarray(local_array).resize((nw, nh), Image.Resampling.NEAREST))
    # Eye detections can enlarge API context, but cannot paint outside the
    # supplied instance mask or take pixels assigned to another instance.
    if eye_bbox_detector is not None and owns.any():
        scaled = source.crop((x0, y0, x1, y1)).resize((nw, nh), Image.Resampling.LANCZOS)
        sx, sy = nw / cw, nh / ch
        for eye in _detect(eye_bbox_detector, pil_to_tensor(scaled), bbox_threshold, dilation, 1.0, 4):
            ex0, ey0, ex1, ey1 = eye.bbox
            if _owner((ex0 / sx + x0, ey0 / sy + y0, ex1 / sx + x0, ey1 / sy + y0), regions) != index:
                continue
            ex0, ey0, ex1, ey1 = _crop_box(eye.crop_region, nw, nh)
            raw[ey0:ey1, ex0:ex1] = 255
    grid = np.array(mask_to_grid_boxes(raw, nw, nh, threshold))
    # Keep the established 32px boxes/8px stride and cover thin members that
    # the box average drops. Do not partition these cells by unrelated centers.
    grid[_cover_mask_cells(owns, nw, nh)] = 255
    return Image.fromarray(grid), local_array, nw, nh, request_steps


def _resolve_mask_source(
    mask_source,
    primary_detector,
    secondary_detector,
    primary_uses_native_mask,
    sam_model,
    detail_mask,
):
    if mask_source not in {"auto", "sam", "segm", "external_mask"}:
        raise user_error("DETAIL_MODE", ValueError, f"Unknown mask_source: {mask_source}")
    native_detector = primary_detector if primary_uses_native_mask else secondary_detector
    sam_detector = primary_detector or native_detector
    selected = mask_source
    if selected == "auto":
        # Preserve the old detector+SAM behavior whenever that complete path exists.
        if sam_model is not None and sam_detector is not None:
            selected = "sam"
        elif detail_mask is not None:
            selected = "external_mask"
        elif native_detector is not None:
            selected = "segm"
        else:
            raise user_error(
                "DETAIL_MASK_INPUT",
                ValueError,
                "Connect bbox_detector + sam_model, a SEGM detector, or detail_mask from SAM3/another MASK node.",
            )
    if selected == "sam":
        if sam_model is None or sam_detector is None:
            raise user_error("DETAIL_MASK_INPUT", ValueError, "mask_source=sam requires a detector and sam_model.")
        return selected, sam_detector, secondary_detector if sam_detector is primary_detector else None
    if selected == "segm":
        if native_detector is None:
            raise user_error("DETAIL_MASK_INPUT", ValueError, "mask_source=segm requires a SEGM detector.")
        return selected, native_detector, None
    if detail_mask is None:
        raise user_error("DETAIL_MASK_INPUT", ValueError, "mask_source=external_mask requires detail_mask.")
    return selected, None, None


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
    vibes=None,
    references=None,
    normalize_vibe_strengths=True,
    detail_mask=None,
    mask_source="auto",
    primary_uses_native_mask=False,
    save_format="PNG",
    webp_quality=90,
    mask_feather=0,
    cfg_rescale=0.0,
    prefer_brownian=False,
    variety_boost=True,
    nai_context=None,
):
    from .generators import NovelAIGenerator, mask_to_grid_boxes

    validate_save_options(save_format, webp_quality)
    base_generation = context_record(nai_context) if nai_context is not None else None

    if limit_opus_free and not preview_only and (vibes or references):
        raise user_error("PAID_BLOCKED", RuntimeError,
            "limit_opus_free blocks Vibe and Precise Reference because they can spend Anlas. "
            "Set it to False to allow paid requests."
        )
    if detail_mode not in {"first", "all"} or matching_mode not in {"shared", "wd14"}:
        raise user_error("DETAIL_MODE", ValueError, "Unknown detail or matching mode.")
    validate_references(get_model_id(model), vibes, references, inpainting=True)
    characters = list(characterPrompts or [])
    if matching_mode != "shared" and not characters:
        raise user_error("MATCHING_INPUT", ValueError,
            "Connect original CharacterPromptSelect output for character matching."
        )
    if matching_mode == "shared" and len(characters) > 1:
        raise user_error("MATCHING_INPUT", ValueError, "Multiple characters require wd14 matching.")
    if matching_mode == "wd14" and tagger is None:
        raise user_error("MATCHING_INPUT", ValueError, "Connect NAI WD Tagger Loader for wd14 matching.")

    validate_single_image(image)
    source = tensor_to_pil(image)
    w, h = source.size
    selected_mask_source, region_detector, auxiliary_detector = _resolve_mask_source(
        mask_source,
        primary_detector,
        secondary_detector,
        primary_uses_native_mask,
        sam_model,
        detail_mask,
    )
    detected = (
        _external_mask_regions(detail_mask, w, h, crop_factor, threshold)
        if selected_mask_source == "external_mask"
        else _detect(region_detector, image, bbox_threshold, dilation, crop_factor)
    )
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
        notice("No regions detected. Original image returned; no NovelAI request sent.")
        return image, pil_to_tensor(Image.new("RGB", source.size)), json.dumps({"regions": [], "status": "no_detections"})
    native_masks = (
        [_native_crop_mask(seg, _crop_box(seg.crop_region, w, h)) for seg in regions]
        if selected_mask_source != "sam"
        else None
    )
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
    retried = set()
    if matching_mode == "wd14" and pending:
        scores = tagger.score(
            [_context_crop(source, regions[i].bbox, match_crop_factor) for i in pending]
        )
        if len(scores) != len(pending):
            raise user_error("TAGGER_MODEL", ValueError, "Tagger returned an unexpected number of regions.")
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
            retried.update(uncertain)
            tight_scores = tagger.score(
                [
                    _context_crop(source, regions[i].bbox, tight_factor)
                    for i in uncertain
                ]
            )
            if len(tight_scores) != len(uncertain):
                raise user_error("TAGGER_MODEL", ValueError, "Tagger returned an unexpected number of regions.")
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
                else:
                    matches[i] = match
            del tight_scores

    report = []
    for i, (seg, match) in enumerate(zip(regions, matches)):
        eligible = i < active_count and (
            matching_mode == "shared" or match.character_index is not None
        )
        if i >= active_count:
            explanation = "Not processed: detail_mode=first or max_regions limit."
        elif matching_mode == "wd14" and match.character_index is None:
            explanation = (
                f"Score {match.score:.3f} below minimum {match_min_score:.3f}."
                if match.score < match_min_score else
                f"Margin {match.margin:.3f} below minimum {match_min_margin:.3f}; candidates too similar."
            )
        else:
            explanation = "Shared prompt." if matching_mode == "shared" else "Original character prompt selected."
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
                "explanation": explanation,
                "tight_crop_retried": i in retried,
                "mask_source": getattr(seg, "repair_report", {}).get("source", selected_mask_source),
                **({"mask_repair": seg.repair_report} if hasattr(seg, "repair_report") else {}),
            }
        )
    native_plans = {}
    if native_masks is not None:
        for index, item in enumerate(report):
            if item["status"] != "planned":
                continue
            plan = _native_mask_plan(
                index, regions, native_masks, source, threshold, steps,
                limit_opus_free, eye_bbox_detector, bbox_threshold, dilation,
            )
            native_plans[index] = plan
            item["mask_pixels"] = int(np.count_nonzero(plan[1]))
            if not item["mask_pixels"]:
                item["status"] = "empty_mask"
                item["explanation"] = "No editable pixels after mask threshold and overlap ownership."
    if matching_mode == "wd14" or any(r["status"] == "skipped" for r in report):
        notice("\n".join(
            f"Region {r['region']} -> character {r['character'] or '?'}: {r['explanation']}"
            for r in report
        ))
    if preview_only:
        notice(
            "Preview only: no NovelAI request was sent. Turn off preview_only to generate.\n"
            "미리보기만 실행했습니다. NAI 생성 요청은 보내지 않았습니다. 실제 보정하려면 ‘미리보기만 실행’을 끄세요.\n"
            "プレビューのみ実行しました。NAIへ生成リクエストは送信していません。補正するには「プレビューのみ」を無効にしてください。"
        )
        preview = source.copy()
        draw = ImageDraw.Draw(preview)
        for item in report:
            color = "lime" if item["status"] == "planned" else "orange"
            draw.rectangle(item["bbox"], outline=color, width=2)
            draw.text(
                (item["bbox"][0], item["bbox"][1]),
                f"{item['region']} -> {item['character'] or '?'} "
                f"{item['status']} score={item['score']:.2f} margin={item['margin']:.2f}",
                fill=color,
            )
        preview_mask = np.zeros((h, w), dtype=np.uint8)
        if native_masks is not None:
            for index, item in enumerate(report):
                if item["status"] != "planned":
                    continue
                x0, y0, x1, y1 = _crop_box(regions[index].crop_region, w, h)
                preview_mask[y0:y1, x0:x1] = np.maximum(
                    preview_mask[y0:y1, x0:x1],
                    native_plans[index][1],
                )
        return (
            pil_to_tensor(preview),
            pil_to_tensor(Image.fromarray(preview_mask).convert("RGB")),
            json.dumps(report),
        )
    if not any(r["status"] == "planned" for r in report):
        return image, pil_to_tensor(Image.new("RGB", source.size)), json.dumps(report)

    if limit_opus_free:
        for index, item in enumerate(report[:active_count]):
            if item["status"] != "planned":
                continue
            if _crop_box(regions[index].crop_region, w, h) == (0, 0, w, h):
                raise user_error("FOCUSED_CROP", RuntimeError,
                    "limit_opus_free requires a focused crop smaller than the source image."
                )

    predictor = None
    secondaries = []
    if selected_mask_source == "sam":
        from segment_anything import SamPredictor

        predictor = SamPredictor(sam_model)
        secondaries = _detect(
            auxiliary_detector, image, bbox_threshold, dilation, crop_factor
        )
    token = get_nai_token()
    model_id = get_model_id(model)
    out = source.copy()
    total_mask = np.zeros((h, w), dtype=np.uint8)
    base_seed = int(np.random.randint(0, 0x7FFFFFFF)) if seed == -1 else int(seed)
    last_result = None
    edit_history = []
    reference_params = None
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
        if native_masks is not None:
            request_mask, local_array, nw, nh, request_steps = native_plans[index]
            local_mask = Image.fromarray(local_array)
        else:
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
            cfg_rescale=cfg_rescale,
            prefer_brownian=prefer_brownian,
            variety_boost=variety_boost,
            model_id=model_id,
        )
        if reference_params is None:
            reference_params = reference_parameters(
                model_id, token, vibes, references, normalize_vibe_strengths, inpainting=True
            )
        parameters.update(reference_params)
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
        result = png_bytes_to_pil(zip_to_png_bytes(post_nai(
            token,
            payload,
            limit_opus_free=limit_opus_free,
            allow_opus_focused_inpaint=limit_opus_free,
        )))
        if result.size != (nw, nh):
            raise user_error("IMAGE_RESPONSE", ValueError, "NAI returned an unexpected detail crop size.")
        if mask_feather:
            from .mask_repair import inside_alpha
            local_mask = Image.fromarray(np.rint(inside_alpha(local_array > 0, mask_feather) * 255).astype(np.uint8))
        out.paste(
            result.resize((cw, ch), Image.Resampling.LANCZOS), (crx0, cry0), local_mask
        )
        total_mask[cry0:cry1, crx0:crx1] = np.maximum(
            total_mask[cry0:cry1, crx0:crx1], local_array
        )
        report[index]["status"] = "edited"
        last_result = result
        edit_history.append({"region": index, "request": request_record(payload), "response": read_fields(result)[0]})
    if last_result is not None:
        # A composite has no single NAI request: keep each crop under its own history.
        metadata_source = out.copy()
        metadata_source.info.clear()
        metadata_source.info["rs_detailer_regions"] = json.dumps(report)
        folder, filename = NovelAIGenerator._get_save_path(
            "NAI_face", NovelAIGenerator._get_output_directory(), subfolder="face"
        )
        autosave(out, folder / filename, source_image=metadata_source, operation="detailer",
                 extra={"base_generation_available": base_generation is not None, "edits": edit_history,
                        **({"base_generation": base_generation} if base_generation is not None else {})},
                 save_format=save_format, webp_quality=webp_quality)
    return (
        pil_to_tensor(out),
        pil_to_tensor(Image.fromarray(total_mask).convert("RGB")),
        json.dumps(report),
    )
