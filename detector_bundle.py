# SPDX-License-Identifier: GPL-3.0-only
"""Detection-only loader for the experimental NovelAI face detailer."""
from dataclasses import dataclass


NONE = "None"
MISSING = "No SEGM model installed"


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


@dataclass(frozen=True)
class DetectionBundle:
    segm_detector: object
    bbox_detector: object = None
    sam_model: object = None
    eye_bbox_detector: object = None


class NAIDetectorCombineLoaderTest:
    @classmethod
    def INPUT_TYPES(cls):
        segms, boxes = installed_models()
        preferred = next((x for x in segms if "face" in x.lower()), segms[0] if segms else MISSING)
        try:
            sams = list(provider("SAMLoader").INPUT_TYPES()["required"]["model_name"][0])
            sams = [x for x in sams if x != "ESAM"]  # NAI uses segment_anything.SamPredictor.
        except (RuntimeError, KeyError):
            sams = []
        return {"required": {
            "face_segm_model": (segms or [MISSING], {"default": preferred, "tooltip": "Default face mask detector. Install a face SEGM .pt model under models/ultralytics/segm."}),
        }, "optional": {
            "show_optional_models": ("BOOLEAN", {"default": False}),
            "sam_model": ([NONE] + sams, {"default": NONE, "tooltip": "Optional SAM refinement using detected face boxes. None uses the SEGM masks directly."}),
            "face_bbox_model": ([NONE] + boxes, {"default": NONE, "tooltip": "Optional face boxes for SAM. Requires SAM; None uses the SEGM face boxes."}),
            "eye_bbox_model": ([NONE] + boxes, {"default": NONE, "tooltip": "Optional extra eye context for the NovelAI request."}),
        }}

    RETURN_TYPES = ("NAI_DETECTION_BUNDLE",)
    RETURN_NAMES = ("detectors",)
    FUNCTION = "load"
    CATEGORY = "RS_NovelAI_API/Experimental"
    DESCRIPTION = "Loads detection models only. Connect the single output to NAI Face Detailer (Test). SEGM by default; optional face BBOX, SAM and eye BBOX."

    def load(self, face_segm_model, show_optional_models=False, sam_model=NONE,
             face_bbox_model=NONE, eye_bbox_model=NONE):
        # The checkbox controls display only; saved selections remain effective.
        segms, boxes = installed_models()
        if face_segm_model not in segms:
            raise ValueError("Select an installed face SEGM model from models/ultralytics/segm, then refresh ComfyUI. / 얼굴 SEGM 모델을 설치하고 새로고침 후 선택해 주세요.")
        for key, value in (("face_bbox_model", face_bbox_model), ("eye_bbox_model", eye_bbox_model)):
            if value != NONE and value not in boxes:
                raise ValueError(f"{key}: model is missing. Select an installed BBOX model. / 설치된 BBOX 모델을 선택해 주세요.")
        if face_bbox_model != NONE and sam_model == NONE:
            raise ValueError("Face BBOX requires SAM. Choose a SAM model or set face_bbox_model to None to use SEGM. / 얼굴 BBOX는 SAM과 함께 선택해 주세요. SEGM만 쓰려면 얼굴 BBOX를 None으로 두세요.")
        if sam_model != NONE and sam_model not in self.INPUT_TYPES()["optional"]["sam_model"][0]:
            raise ValueError("SAM model is missing or unsupported. Select an installed SAM ViT model. / 설치된 SAM ViT 모델을 선택해 주세요.")
        loader = provider("UltralyticsDetectorProvider")()
        cache = {}

        def yolo(name, slot):
            if name == NONE:
                return None
            if name not in cache:
                cache[name] = loader.doit(name)
            return cache[name][slot]

        return (DetectionBundle(
            yolo(face_segm_model, 1), yolo(face_bbox_model, 0),
            provider("SAMLoader")().load_model(sam_model, "CPU")[0] if sam_model != NONE else None,
            yolo(eye_bbox_model, 0),
        ),)
