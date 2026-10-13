"""Conservative, geometry-only notch repair. No model or network access."""
import math

import cv2
import numpy as np
from scipy import ndimage


def validate_masks(masks, height, width):
    masks = np.asarray(masks, dtype=np.float32)
    if masks.ndim == 2:
        masks = masks[None]
    if masks.ndim != 3 or masks.shape[1:] != (height, width):
        raise ValueError("MASK must be [H,W] or [instances,H,W] at the image size. / 마스크 크기를 원본 이미지와 맞춰 주세요.")
    if not np.isfinite(masks).all() or np.any((masks < 0) | (masks > 1)):
        raise ValueError("MASK values must be finite and between 0 and 1. / 마스크 값은 0~1이어야 합니다.")
    return masks >= 0.5


def bounds(mask):
    ys, xs = np.nonzero(mask)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def repair_instance(mask, width_ratio, depth_ratio, max_added_ratio, fill_holes, close_notches=True):
    """Close each component separately; accept complete additions within eye band."""
    result = mask.copy()
    components, count = ndimage.label(mask)
    rejected = 0
    for index in range(1, count + 1):
        part = components == index
        x0, y0, x1, y1 = bounds(part)
        h, w = y1 - y0, x1 - x0
        span = min(h, w)
        gap = max(1, round(span * width_ratio))
        depth = max(1, round(span * depth_ratio))
        radius = max(1, math.ceil(gap / 2))
        roi = part[y0:y1, x0:x1]
        padded = np.pad(roi.astype(np.uint8), radius + 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1,) * 2)
        closed = cv2.morphologyEx(padded, cv2.MORPH_CLOSE, kernel)
        closed = closed[radius + 1:-radius - 1, radius + 1:-radius - 1].astype(bool)
        holes = ndimage.binary_fill_holes(roi) & ~roi
        candidate = closed & ~roi & ~holes if close_notches else np.zeros_like(roi)
        if fill_holes:
            candidate |= holes
        additions, n = ndimage.label(candidate)
        accepted = np.zeros_like(roi)
        budget = int(roi.sum() * max_added_ratio)
        # Whole candidate components must fit the band: never cut a rejected repair in half.
        for j in range(1, n + 1):
            addition = additions == j
            ax0, ay0, ax1, ay1 = bounds(addition)
            minor, major = sorted((ax1 - ax0, ay1 - ay0))
            in_band = ay0 >= h * 0.18 and ay1 <= h * 0.78
            size = int(addition.sum())
            if in_band and minor <= gap and major <= depth and size + accepted.sum() <= budget:
                accepted |= addition
            else:
                rejected += 1
        result[y0:y1, x0:x1] |= accepted
    return result, rejected


def dilate_mask(mask, radius):
    """Add sampling room in source-image pixels after repair, including at holes."""
    if radius == 0 or not mask.any():
        return mask.copy()
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1,) * 2)
    return cv2.dilate(mask.astype(np.uint8), kernel, borderType=cv2.BORDER_CONSTANT,
                      borderValue=0).astype(bool)


def plan_masks(masks, repair_mode="closing", notch_width=0.12, notch_depth=0.25,
               max_added_ratio=0.08, fill_holes=True, dilation=0):
    """Repair, then expand for sampling; original instance ownership wins."""
    if isinstance(dilation, (bool, np.bool_)) or not isinstance(dilation, (int, np.integer)) or not 0 <= dilation <= 128:
        raise ValueError("dilation must be an integer from 0 to 128 source pixels. / 마스크 여유는 원본 기준 0~128 정수 픽셀로 설정해 주세요.")
    n, h, w = masks.shape
    owners = np.full((h, w), -1, dtype=np.int32)
    added_owners = np.full((h, w), -1, dtype=np.int32)
    original_distance = np.full((h, w), np.inf)
    added_distance = np.full((h, w), np.inf)
    yy, xx = np.ogrid[:h, :w]
    repaired, reports = [], []
    for index, mask in enumerate(masks):
        if not mask.any():
            repaired.append(mask.copy())
            reports.append({"instance": index, "source_pixels": 0, "rejected_additions": 0,
                            "repair_added_pixels": 0, "dilation_candidate_pixels": 0})
            continue
        x0, y0, x1, y1 = bounds(mask)
        distance = (xx - (x0 + x1 - 1) / 2) ** 2 + (yy - (y0 + y1 - 1) / 2) ** 2
        claim = mask & (distance < original_distance)
        owners[claim] = index
        original_distance[claim] = distance[claim]
        fixed, rejected = repair_instance(mask, notch_width, notch_depth, max_added_ratio,
                                          fill_holes, close_notches=repair_mode == "closing")
        repair_added = int((fixed & ~mask).sum())
        expanded = dilate_mask(fixed, dilation)
        dilation_added = int((expanded & ~fixed).sum())
        fixed = expanded
        repaired.append(fixed)
        claim = (fixed & ~mask) & (distance < added_distance)
        added_owners[claim] = index
        added_distance[claim] = distance[claim]
        reports.append({"instance": index, "source_pixels": int(mask.sum()), "rejected_additions": rejected,
                        "repair_added_pixels": repair_added, "dilation_candidate_pixels": dilation_added})
    original = np.stack([owners == i for i in range(n)]) if n else masks.copy()
    final_owners = np.where(owners >= 0, owners, added_owners)
    final = np.stack([final_owners == i for i in range(n)]) if n else masks.copy()
    for i, report in enumerate(reports):
        report.update(owned_pixels=int(original[i].sum()), final_pixels=int(final[i].sum()),
                      added_pixels=int((final[i] & ~original[i]).sum()))
    return original, final, reports


def inside_alpha(mask, feather):
    if feather <= 0:
        return mask.astype(np.float32)
    distance = ndimage.distance_transform_edt(np.pad(mask, 1))[1:-1, 1:-1]
    return np.minimum(distance / feather, 1).astype(np.float32) * mask
