# SPDX-License-Identifier: GPL-3.0-only
"""Optional native PyTorch WD-v3 inference. No ONNX runtime or generated prompts."""

import csv
import json
import threading
from pathlib import Path

from .runtime_control import check_interrupted

MODEL_REPO = "SmilingWolf/wd-vit-tagger-v3"
MODEL_REVISION = "7f6b584d0bd3f55c4531f14ba3d4761b2bccdc0f"


class WDTagger:
    def __init__(self, cache_dir, device="auto", batch_size=4):
        self.cache_dir = str(cache_dir)
        self.device = device
        self.batch_size = batch_size
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is not None:
            return
        try:
            import timm
            from huggingface_hub import hf_hub_download
            from safetensors.torch import load_file
            from timm.data import create_transform, resolve_data_config
        except ImportError as exc:
            raise RuntimeError(
                "WD matching requires requirements-tagger.txt in the ComfyUI Python environment."
            ) from exc
        paths = {}
        for name in ("config.json", "selected_tags.csv", "model.safetensors"):
            check_interrupted()
            paths[name] = hf_hub_download(
                MODEL_REPO, name, revision=MODEL_REVISION, cache_dir=self.cache_dir
            )
        config = json.loads(Path(paths["config.json"]).read_text())
        model = timm.create_model(
            config["architecture"],
            pretrained=False,
            num_classes=config["num_classes"],
            **config.get("model_args", {}),
        )
        model.load_state_dict(load_file(paths["model.safetensors"]), strict=True)
        transform = create_transform(
            **resolve_data_config(config["pretrained_cfg"], model=model),
            is_training=False,
        )
        with open(paths["selected_tags.csv"], encoding="utf-8", newline="") as handle:
            labels = list(csv.DictReader(handle))
        if len(labels) != config["num_classes"]:
            raise ValueError("WD model and tag vocabulary have different lengths.")
        self._labels = labels
        self._transform = transform
        self._model = model.eval()

    def score(self, images):
        import torch
        from PIL import Image

        if not images:
            return []
        with self._lock:
            self._load()
            check_interrupted()
            management = None
            if self.device == "auto":
                try:
                    import comfy.model_management as management

                    device = management.get_torch_device()
                    if device.type != "cpu":
                        size = sum(
                            p.numel() * p.element_size()
                            for p in self._model.parameters()
                        )
                        management.free_memory(
                            size + self.batch_size * 128 * 1024**2, device
                        )
                except ImportError:
                    device = torch.device(
                        "cuda" if torch.cuda.is_available() else "cpu"
                    )
            else:
                device = torch.device("cpu")
            results = []
            try:
                self._model.to(device)
                for start in range(0, len(images), self.batch_size):
                    check_interrupted()
                    inputs = []
                    for image in images[start : start + self.batch_size]:
                        rgba = image.convert("RGBA")
                        rgb = Image.new("RGBA", rgba.size, "white")
                        rgb.alpha_composite(rgba)
                        rgb = rgb.convert("RGB")
                        side = max(rgb.size)
                        square = Image.new("RGB", (side, side), "white")
                        square.paste(
                            rgb, ((side - rgb.width) // 2, (side - rgb.height) // 2)
                        )
                        inputs.append(self._transform(square))
                    batch = torch.stack(inputs)[:, [2, 1, 0]].to(device)
                    with torch.inference_mode():
                        output = self._model(batch).sigmoid().cpu()
                    del batch
                    for row in output.tolist():
                        results.append(
                            {
                                label["name"]: value
                                for label, value in zip(self._labels, row)
                                if label["category"] in {"0", "4"}
                            }
                        )
                return results
            finally:
                # Avoid permanently occupying VRAM alongside SAM/generation models.
                self._model.to("cpu")


class WDTaggerLoader:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "device": (["auto", "cpu"],),
                "batch_size": ("INT", {"default": 4, "min": 1, "max": 16}),
            }
        }

    RETURN_TYPES = ("RS_WD_TAGGER",)
    FUNCTION = "load"
    CATEGORY = "RS_NovelAI_API/FaceDetailer"

    def load(self, device="auto", batch_size=4):
        import folder_paths

        key = (device, batch_size, folder_paths.models_dir)
        if getattr(self, "_key", None) != key:
            self._tagger = WDTagger(
                Path(folder_paths.models_dir) / "rs_wd_tagger", device, batch_size
            )
            self._key = key
        return (self._tagger,)
