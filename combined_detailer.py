# SPDX-License-Identifier: GPL-3.0-only
"""SEGM-first test node using the established NovelAI request pipeline."""
import math
from types import SimpleNamespace

import numpy as np

from .detector_bundle import DetectionBundle
from .diagnostics import notice
from .generation_context import context_inputs, inherit_context
from .generators import NAIFaceDetailerNode
from .image_utils import tensor_to_pil, validate_single_image
from .mask_repair import bounds, plan_masks
from .runtime_control import check_interrupted


class RepairedDetector:
    def __init__(self, bundle, *, closing=True, fill_holes=True, dilation=8, mask_threshold=0.3):
        self.bundle = bundle
        self.closing, self.fill_holes, self.dilation = closing, fill_holes, dilation
        self.mask_threshold = mask_threshold

    def detect(self, image, threshold, dilation, crop_factor, **kwargs):
        from .detailer import _detect, _native_crop_mask, _crop_box, _expanded_crop
        check_interrupted()
        height, width = image.shape[1:3]
        bundle = self.bundle
        if bundle.segm_detector is not None:
            primary, source = bundle.segm_detector, "segm"
        else:
            primary, source = bundle.bbox_detector, "bbox"
        segments = _detect(primary, image, threshold, 0, crop_factor)
        masks, valid = [], []
        predictor = None
        if source == "bbox" and bundle.sam_model is not None and segments:
            from segment_anything import SamPredictor
            predictor = SamPredictor(bundle.sam_model)
            predictor.set_image(np.asarray(tensor_to_pil(image)))
        for seg in segments:
            check_interrupted()
            if not all(np.isfinite(v) for v in (*seg.bbox, *seg.crop_region)):
                raise ValueError("Detector returned invalid coordinates. / 감지 모델이 올바르지 않은 좌표를 반환했습니다.")
            bx0, by0, bx1, by1 = _crop_box(seg.bbox, width, height)
            x0, y0, x1, y1 = _crop_box(seg.crop_region, width, height)
            if bx1 <= bx0 or by1 <= by0 or x1 <= x0 or y1 <= y0:
                continue
            if predictor is None:
                mask = np.zeros((height, width), bool)
                if source == "bbox":
                    mask[by0:by1, bx0:bx1] = True
                else:
                    mask[y0:y1, x0:x1] = _native_crop_mask(seg, (x0, y0, x1, y1)) >= max(self.mask_threshold, 1e-6)
            else:
                predicted, _, _ = predictor.predict(box=np.array([bx0, by0, bx1, by1]), multimask_output=False)
                mask = np.asarray(predicted[0], dtype=bool)
                if mask.shape != (height, width):
                    raise ValueError("SAM mask dimensions differ from the image. / SAM 마스크 크기가 원본과 다릅니다.")
            masks.append(mask)
            valid.append(seg)
        raw = np.stack(masks) if masks else np.zeros((0, height, width), bool)
        _, repaired, reports = plan_masks(raw, repair_mode="closing" if self.closing else "off",
                                          fill_holes=self.fill_holes, dilation=self.dilation)
        result = []
        for seg, fixed, report in zip(valid, repaired, reports):
            # Include dilation even with crop_factor=1. Keep identity detection boxes unchanged.
            box = bounds(fixed) if fixed.any() else seg.bbox
            bx0, by0, bx1, by1 = box
            x0, y0, x1, y1 = _expanded_crop(seg.bbox, width, height, crop_factor)
            crop = (max(0, min(x0, bx0)), max(0, min(y0, by0)), min(width, max(x1, bx1)), min(height, max(y1, by1)))
            x0, y0, x1, y1 = map(int, crop)
            result.append(SimpleNamespace(bbox=seg.bbox, crop_region=(x0, y0, x1, y1),
                cropped_mask=fixed[y0:y1, x0:x1].astype(np.float32),
                repair_report={**report, "closing": self.closing, "fill_holes": self.fill_holes,
                               "dilation": self.dilation, "source": "sam" if predictor is not None else source,
                               "face_detector": source}))
        return (height, width), result


class NAIMultiCharacterDetailer:
    @classmethod
    def INPUT_TYPES(cls):
        old = NAIFaceDetailerNode.INPUT_TYPES()
        req = old["required"]
        model_choices, model_options = req["model"]
        return {"required": {
            "image": req["image"], "detectors": ("NAI_DETECTION_BUNDLE",),
            **{key: req[key] for key in ("prompt", "negative_prompt", "model", "strength", "seed")},
            "model": (model_choices, {**model_options, "default": "NAI Diffusion V5 Full"}),
        }, "optional": {
            "show_advanced": ("BOOLEAN", {"default": False}),
            **{key: value for key, value in old["optional"].items()
               if key not in {"bbox_detector", "segm_detector", "sam_model", "eye_bbox_detector", "detail_mask", "mask_source", "preview_only", "request_delay_seconds"}},
            **{key: req[key] for key in ("sampler", "steps", "cfg_scale", "scheduler", "threshold", "crop_factor")},
            "bbox_threshold": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.01}),
            "detail_mode": (["all", "first"], {"default": "all"}),
            "max_regions": ("INT", {"default": 5, "min": 1, "max": 64, "tooltip": "Maximum number of regions to process. Quality cannot be guaranteed as the number of processed regions increases."}),
            "closing": ("BOOLEAN", {"default": True, "tooltip": "Fill small notches before dilation."}),
            "fill_holes": ("BOOLEAN", {"default": True, "tooltip": "Fill enclosed holes within the repair limits, before dilation."}),
            "dilation": ("INT", {"default": 8, "min": 0, "max": 128, "tooltip": "Extra editing room in original-image pixels, after hole/notch filling."}),
            "mask_feather": ("INT", {"default": 8, "min": 0, "max": 64, "tooltip": "Blend inside the expanded mask. Separate from crop context and dilation."}),
            **context_inputs(),
            "use_context_settings": ("BOOLEAN", {"default": True, "tooltip": "On: inherit prompts, characters, model and sampling settings from connected NAI context. Off: use this node's manual values. Both modes perform NovelAI correction; the seed stays local."}),
        }}

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("image", "mask_visualization", "matching_report")
    FUNCTION = "detail"
    CATEGORY = "RS_NovelAI_API"
    DESCRIPTION = "Detect regions, match original character prompts and correct them with NovelAI inpainting. Connect image + detection bundle, and optionally NAI context from T2I or img2img. Fills holes/notches and expands masks by default. Up to 22 characters and 64 regions; quality cannot be guaranteed as the number of processed regions increases. Execution performs correction, with no preview-only mode."

    def detail(self, image, detectors, prompt, negative_prompt, model, strength=0.55, seed=-1,
               show_advanced=False, closing=True, fill_holes=True,
               dilation=8, mask_feather=8, sampler="k_euler", steps=28, cfg_scale=6.0,
               scheduler="karras", threshold=0.3, bbox_threshold=0.3, crop_factor=3.0,
               detail_mode="all", max_regions=5, nai_context=None, use_context_settings=True, **options):
        from .detailer import run_face_detail
        from .errors import user_error
        # Old API graphs may still send this removed prototype setting.
        options.pop("preview_only", None)
        if not isinstance(detectors, DetectionBundle):
            raise ValueError("Connect NAI Detection Combine Loader. / NAI 감지 모델 콤바인 로더를 연결해 주세요. / NAI検出モデル結合ローダーを接続してください。")
        if detectors.segm_detector is None and detectors.bbox_detector is None:
            raise user_error("DETECTION_MODEL_SELECTION", ValueError, "Select a primary SEGM or BBOX model in the combine loader.")
        inherited = inherit_context(nai_context, use_context_settings)
        if inherited is not None:
            prompt, negative_prompt, model, sampler, steps, cfg_scale, scheduler = (
                inherited.pop(key) for key in ("prompt", "negative_prompt", "model", "sampler", "steps", "cfg_scale", "scheduler"))
            options.update(inherited)
            if len(options["characterPrompts"]) > 1 and options.get("matching_mode", "shared") == "shared":
                options["matching_mode"] = "wd14"
                notice("Multiple characters in NAI context: automatic character matching requires a connected tagger. / 컨텍스트에 여러 캐릭터가 있어 태거로 원래 캐릭터 프롬프트를 선택합니다. 태거 로더를 연결해 주세요. / 複数キャラクターの選択にはタガーローダーを接続してください。")
        validate_single_image(image)
        if isinstance(mask_feather, bool) or not isinstance(mask_feather, int) or not 0 <= mask_feather <= 64:
            raise ValueError("mask_feather must be 0–64 pixels. / 경계 부드러움은 0~64픽셀로 설정해 주세요.")
        if not math.isfinite(crop_factor) or crop_factor < 1:
            raise ValueError("crop_factor must be at least 1. / 크롭 여백은 1 이상으로 설정해 주세요.")
        detector = RepairedDetector(detectors, closing=closing, fill_holes=fill_holes,
                                    dilation=dilation, mask_threshold=threshold)
        return run_face_detail(image, detector, None, None, prompt, negative_prompt, model,
            strength, threshold, sampler, steps, cfg_scale, bbox_threshold, 0, crop_factor,
            scheduler, seed, primary_uses_native_mask=True, mask_source="segm",
            eye_bbox_detector=detectors.eye_bbox_detector, preview_only=False,
            detail_mode=detail_mode, max_regions=max_regions, mask_feather=mask_feather,
            nai_context=nai_context, **options)
