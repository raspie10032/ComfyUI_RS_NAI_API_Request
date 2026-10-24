# SPDX-License-Identifier: GPL-3.0-only
"""Detection-only loader for the NovelAI multi-character detailer."""
from dataclasses import dataclass

from .detection_models import CATALOG, DEFAULT_SEGM, ensure_detection_model
from .runtime_control import is_interruption
from .tagger_progress import TaggerProgress


OFF = "OFF"


def is_off(value):
    # Accept the old prototype's saved/API value without exposing two OFF items.
    return value in (OFF, "None")


def provider(name):
    import nodes
    cls = nodes.NODE_CLASS_MAPPINGS.get(name)
    if cls is None:
        pack = "ComfyUI-Impact-Subpack" if name == "UltralyticsDetectorProvider" else "ComfyUI-Impact-Pack"
        raise RuntimeError(f"{pack} is required. Install it and restart ComfyUI. / {pack} 설치 후 ComfyUI를 다시 시작해 주세요.")
    return cls


def installed_models():
    try:
        choices = provider("UltralyticsDetectorProvider").INPUT_TYPES()["required"]["model_name"][0]
    except RuntimeError:
        return [], []
    return sorted(x for x in choices if x.startswith("segm/")), sorted(x for x in choices if x.startswith("bbox/"))


def available_models():
    segms, boxes = installed_models()
    return (sorted(set(segms) | {x for x in CATALOG if x.startswith("segm/")}),
            sorted(set(boxes) | {x for x in CATALOG if x.startswith("bbox/")}))


def installed_sams():
    try:
        choices = provider("SAMLoader").INPUT_TYPES()["required"]["model_name"][0]
        return [x for x in choices if x != "ESAM"]  # Uses segment_anything.SamPredictor.
    except (RuntimeError, KeyError):
        return []


@dataclass(frozen=True)
class DetectionBundle:
    segm_detector: object = None
    bbox_detector: object = None
    sam_model: object = None
    eye_bbox_detector: object = None

    def rs_detection_bundle(self):
        return {"version": 1, "segm_detector": self.segm_detector,
                "bbox_detector": self.bbox_detector, "sam_model": self.sam_model,
                "eye_bbox_detector": self.eye_bbox_detector}


def detection_bundle(value):
    if isinstance(value, DetectionBundle):
        return value
    export = getattr(value, "rs_detection_bundle", None)
    if not callable(export):
        raise ValueError("Connect an RS NAI or RS MultiCharacter Detection Combine Loader. / RS 감지 모델 통합 로더를 연결해 주세요.")
    data = export()
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Unsupported RS detector bundle version.")
    fields = {name: data.get(name) for name in ("segm_detector", "bbox_detector", "sam_model", "eye_bbox_detector")}
    for name in ("segm_detector", "bbox_detector", "eye_bbox_detector"):
        if fields[name] is not None and not callable(getattr(fields[name], "detect", None)):
            raise ValueError(f"Invalid {name} in shared detector bundle.")
    return DetectionBundle(**fields)


class NAIDetectionCombineLoader:
    @classmethod
    def INPUT_TYPES(cls):
        segms, boxes = available_models()
        return {"required": {
            "face_segm_model": ([OFF, DEFAULT_SEGM] + [x for x in segms if x != DEFAULT_SEGM], {"default": DEFAULT_SEGM, "tooltip": "SEGM takes priority: BBOX and SAM are skipped even if selected. Face, eyes, clothes, skin, hair and whole-person masks. Missing catalog models download on execution. Installed models in ultralytics/segm appear after refreshing the model list. OFF does not download or load SEGM."}),
        }, "optional": {
            "show_optional_models": ("BOOLEAN", {"default": False}),
            "sam_model": ([OFF] + installed_sams(), {"default": OFF, "tooltip": "Used only when SEGM is OFF and a BBOX is selected. Refines BBOX regions into masks. Skipped with SEGM; OFF does not load SAM."}),
            "face_bbox_model": ([OFF] + boxes, {"default": OFF, "tooltip": "Used only when SEGM is OFF. Face, eye or hand boxes for SAM, or rectangular masks without SAM. Missing catalog models download on execution. Installed models in ultralytics/bbox appear after refreshing the model list. Skipped with SEGM; OFF does not load BBOX."}),
            "eye_bbox_model": ([OFF] + boxes, {"default": OFF, "tooltip": "Extra eye context for the NovelAI request. OFF does not load an eye model."}),
        }, "hidden": {"unique_id": "UNIQUE_ID"}}

    RETURN_TYPES = ("NAI_DETECTION_BUNDLE",)
    RETURN_NAMES = ("detectors",)
    FUNCTION = "load"
    CATEGORY = "RS_NovelAI_API"
    DESCRIPTION = "SEGM is the default and takes priority. With SEGM selected, BBOX and SAM are not loaded or run, even if selected. With SEGM OFF, BBOX alone or BBOX + SAM is used. OFF disables a model. Select face, eye, hand, clothing, skin or whole-person detectors. Missing catalog models download on execution with progress. Models added to the existing ultralytics/segm, ultralytics/bbox and sams folders appear when lists are refreshed. SAM must already be installed."

    @classmethod
    def VALIDATE_INPUTS(cls, face_segm_model=OFF, sam_model=OFF, face_bbox_model=OFF, eye_bbox_model=OFF):
        # Validate enum values here so API workflows saved with legacy None still work.
        segms, boxes = available_models() if any(not is_off(x) for x in (face_segm_model, face_bbox_model, eye_bbox_model)) else ([], [])
        if not is_off(face_segm_model) and face_segm_model != DEFAULT_SEGM and face_segm_model not in segms:
            return "Select an available SEGM model or OFF. / 목록의 SEGM 모델 또는 OFF를 선택해 주세요. / リストのSEGM モデルか OFF を選択してください。"
        for key, value in (("face_bbox_model", face_bbox_model), ("eye_bbox_model", eye_bbox_model)):
            if key == "face_bbox_model" and not is_off(face_segm_model):
                continue
            if not is_off(value) and value not in boxes:
                return f"{key}: select an installed BBOX model or OFF. / 목록의 BBOX 모델 또는 OFF를 선택해 주세요. / リストの BBOX モデルか OFF を選択してください。"
        if is_off(face_segm_model) and not is_off(face_bbox_model) and not is_off(sam_model) and sam_model not in installed_sams():
            return "Select an available SAM ViT model or OFF. / 목록의 SAM ViT 모델 또는 OFF를 선택해 주세요. / リストの SAM ViT モデルか OFF を選択してください。"
        return True

    def load(self, face_segm_model=DEFAULT_SEGM, show_optional_models=False, sam_model=OFF,
             face_bbox_model=OFF, eye_bbox_model=OFF, unique_id=None):
        # Folding only changes display. Each OFF selection disables that model.
        validation = self.VALIDATE_INPUTS(face_segm_model, sam_model, face_bbox_model, eye_bbox_model)
        if validation is not True:
            raise ValueError(validation)
        loader = None
        cache = {}
        progress = TaggerProgress(unique_id)

        def yolo(name, slot):
            nonlocal loader
            if is_off(name):
                return None
            if loader is None:
                loader = provider("UltralyticsDetectorProvider")()
            if name not in cache:
                ensure_detection_model(name, progress)
                progress.report(f"Loading: {name}", force=True)
                cache[name] = loader.doit(name)
            return cache[name][slot]

        try:
            segm = yolo(face_segm_model, 1)
            bbox = yolo(face_bbox_model, 0) if is_off(face_segm_model) else None
            sam = None
            if is_off(face_segm_model) and bbox is not None and not is_off(sam_model):
                progress.report(f"Loading: {sam_model}", force=True)
                sam = provider("SAMLoader")().load_model(sam_model, "CPU")[0]
            eyes = yolo(eye_bbox_model, 0)
            status = "SEGM (BBOX / SAM skipped)" if segm is not None else "BBOX + SAM" if sam is not None else "BBOX" if bbox is not None else "No region detector: select SEGM or BBOX"
            progress.report(f"Ready: {status}", 1, force=True)
            return (DetectionBundle(segm, bbox, sam, eyes),)
        except Exception as error:
            progress.report("Cancelled" if is_interruption(error) else f"Failed: {error}", force=True, failed=True)
            raise
