# SPDX-License-Identifier: GPL-3.0-only
"""Optional local WD/PixAI inference. No ONNX runtime or generated prompts."""

import csv
import hashlib
import inspect
import json
import logging
import sys
import threading
from pathlib import Path

from .runtime_control import check_interrupted
from .tagger_progress import TaggerProgress

MODEL_REPO = "SmilingWolf/wd-vit-tagger-v3"
MODEL_REVISION = "7f6b584d0bd3f55c4531f14ba3d4761b2bccdc0f"
DEFAULT_MODEL = "WD ViT v3"
PIXAI_MODEL = "PixAI Tagger v1.0"
MODELS = {
    DEFAULT_MODEL: (MODEL_REPO, MODEL_REVISION),
    "WD EVA02 Large v3": (
        "SmilingWolf/wd-eva02-large-tagger-v3",
        "b25b82a03f7282e41aa2f257a52c7583b710bd1c",
    ),
    PIXAI_MODEL: (
        "pixai-labs/pixai-tagger-v1.0",
        "9fe10addf9326e292da8a85a98ea74cd91b41771",
    ),
}
PIXAI_CODE_SHA256 = "3431279fdfff234f62664999fc1fe6bb20f1e8756f7435d0e165ebd4456f7fcd"


def check_dependencies(model_name=DEFAULT_MODEL):
    """Import optional dependencies only when the loader/matcher is used."""
    try:
        import timm
        from huggingface_hub import hf_hub_download
        from safetensors.torch import load_file
        from timm.data import create_transform, resolve_data_config
        if "tqdm_class" not in inspect.signature(hf_hub_download).parameters:
            raise RuntimeError("huggingface-hub>=1.1 is required for node download progress")
        if model_name == PIXAI_MODEL:
            from transformers import AutoImageProcessor, AutoModel
    except (ImportError, RuntimeError, OSError) as exc:
        requirements = Path(__file__).with_name(
            "requirements-tagger-pixai.txt" if model_name == PIXAI_MODEL else "requirements-tagger.txt"
        )
        raise RuntimeError(
            f"{model_name} tagger dependencies failed to import ({type(exc).__name__}: {exc}). "
            f'Install in this ComfyUI environment: "{sys.executable}" -m pip install -r "{requirements}". '
            "If already installed, check that torch and torchvision are compatible."
        ) from exc
    return timm, hf_hub_download, load_file, create_transform, resolve_data_config


class WDTagger:
    def __init__(self, cache_dir, device="auto", batch_size=4, model_name=DEFAULT_MODEL):
        if model_name not in MODELS:
            raise ValueError(f"Unknown tagger model: {model_name!r}. Choose from {list(MODELS)}.")
        self.model_name = model_name
        self.cache_dir = str(cache_dir)
        self.device = device
        self.batch_size = batch_size
        self._model = None
        self._lock = threading.Lock()

    def _load(self, progress=None):
        progress = progress or TaggerProgress()
        if self._model is not None:
            progress.report(f"Ready: {self.model_name} (already loaded)", 1, force=True)
            return
        timm, hf_hub_download, load_file, create_transform, resolve_data_config = check_dependencies(self.model_name)
        paths = {}
        repo, revision = MODELS[self.model_name]
        filenames = ("config.json", "selected_tags.csv", "model.safetensors")
        if self.model_name == PIXAI_MODEL:
            filenames = ("config.json", "preprocessor_config.json", "tagger_pipeline.py", "model.safetensors")
        logging.info("[RS NAI Tagger] %s: checking cache; downloading missing files.", self.model_name)
        for name in filenames:
            check_interrupted()
            progress.report(f"Checking cache: {name}", force=True)
            logging.info("[RS NAI Tagger] %s: resolving %s", self.model_name, name)
            paths[name] = hf_hub_download(
                repo, name, revision=revision, cache_dir=self.cache_dir,
                tqdm_class=progress.download_bar(name),
            )
            progress.report(f"File ready: {name}", 1, force=True)
        logging.info("[RS NAI Tagger] %s: loading weights on CPU.", self.model_name)
        progress.report(f"Loading {self.model_name} on CPU…", force=True)
        config = json.loads(Path(paths["config.json"]).read_text(encoding="utf-8"))
        if self.model_name == PIXAI_MODEL:
            self._load_pixai(paths, config)
            progress.report(f"Ready: {self.model_name}", 1, force=True)
            return
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
        progress.report(f"Ready: {self.model_name}", 1, force=True)

    def _load_pixai(self, paths, config):
        from transformers import AutoImageProcessor, AutoModel

        # The official architecture is custom code; only execute the reviewed revision.
        if hashlib.sha256(Path(paths["tagger_pipeline.py"]).read_bytes()).hexdigest() != PIXAI_CODE_SHA256:
            raise ValueError("PixAI model code checksum mismatch. Remove the cached tagger_pipeline.py and retry.")
        if sum(count for _, count in config["tags_split"]) != config["num_classes"]:
            raise ValueError("PixAI tag category lengths do not match the model.")
        labels = []
        for category, count in config["tags_split"]:
            labels.extend(
                {"name": name, "category": {"general": "0", "character": "4"}.get(category, "ignored")}
                for name in config["tags"][len(labels):len(labels) + count]
            )
        if len(labels) != config["num_classes"] or len(labels) != len(config["tags"]):
            raise ValueError("PixAI model and tag vocabulary have different lengths.")
        snapshot = str(Path(paths["config.json"]).parent)
        processor = AutoImageProcessor.from_pretrained(snapshot, trust_remote_code=True, local_files_only=True)
        model = AutoModel.from_pretrained(snapshot, trust_remote_code=True, local_files_only=True)
        self._labels = labels
        self._processor = processor
        self._model = model.eval()

    def score(self, images):
        import torch

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
                        workspace = 1024 if self.model_name == PIXAI_MODEL else 128
                        management.free_memory(size + self.batch_size * workspace * 1024**2, device)
                except ImportError:
                    device = torch.device(
                        "cuda" if torch.cuda.is_available() else "cpu"
                    )
            else:
                device = torch.device("cpu")
            results = []
            try:
                logging.info("[RS NAI Tagger] %s: scoring %d crops on %s (batch size %d).", self.model_name, len(images), device, self.batch_size)
                self._model.to(device)
                for start in range(0, len(images), self.batch_size):
                    check_interrupted()
                    crops = images[start : start + self.batch_size]
                    if self.model_name == PIXAI_MODEL:
                        # PixAI uses RGB, resize then black padding; WD uses BGR and white square padding.
                        batch = self._processor(crops, return_tensors="pt")["pixel_values"].to(device)
                    else:
                        batch = torch.stack([self._prepare_wd(image) for image in crops])[:, [2, 1, 0]].to(device)
                    with torch.inference_mode():
                        output = self._model(batch).float().sigmoid().cpu()
                    del batch
                    if output.ndim != 2 or output.shape != (len(crops), len(self._labels)):
                        raise ValueError(f"{self.model_name} returned scores inconsistent with its tag vocabulary.")
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

    def _prepare_wd(self, image):
        from PIL import Image

        rgba = image.convert("RGBA")
        rgb = Image.new("RGBA", rgba.size, "white")
        rgb.alpha_composite(rgba)
        rgb = rgb.convert("RGB")
        side = max(rgb.size)
        square = Image.new("RGB", (side, side), "white")
        square.paste(
            rgb, ((side - rgb.width) // 2, (side - rgb.height) // 2)
        )
        return self._transform(square)


class WDTaggerLoader:
    DESCRIPTION = "Choose WD ViT v3, WD EVA02 Large v3 or PixAI v1.0. The loader downloads only the selected model and shows byte progress on the node. Cached files are reused. Inference is local. Scores select an original character slot; they never become prompt text."
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "device": (["auto", "cpu"],),
                "batch_size": ("INT", {"default": 4, "min": 1, "max": 16}),
            },
            "optional": {
                "model_name": (list(MODELS), {"default": DEFAULT_MODEL, "tooltip": "Executing this loader downloads only the selected model, with progress on the node. Cached files are reused. PixAI needs requirements-tagger-pixai.txt and more memory; start with batch_size=1."}),
            },
            "hidden": {"tagger_node_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("RS_WD_TAGGER",)
    FUNCTION = "load"
    CATEGORY = "RS_NovelAI_API/FaceDetailer"

    def load(self, device="auto", batch_size=4, model_name=DEFAULT_MODEL, tagger_node_id=None):
        if device not in {"auto", "cpu"} or type(batch_size) is not int or not 1 <= batch_size <= 16:
            raise ValueError("WD tagger requires device auto/cpu and batch_size 1–16.")
        if model_name not in MODELS:
            raise ValueError(f"Unknown tagger model: {model_name!r}. Choose from {list(MODELS)}.")
        progress = TaggerProgress(tagger_node_id)
        try:
            progress.report(f"Checking dependencies: {model_name}", force=True)
            check_dependencies(model_name)
            import folder_paths

            key = (device, batch_size, folder_paths.models_dir, model_name)
            if getattr(self, "_key", None) != key:
                self._tagger = WDTagger(
                    Path(folder_paths.models_dir) / "rs_wd_tagger", device, batch_size, model_name
                )
                self._key = key
            with self._tagger._lock:
                self._tagger._load(progress)
        except Exception:
            # Preserve the detailed exception in ComfyUI; never display Ready on failure.
            progress.report("Model preparation failed or cancelled; see the execution error.", force=True, failed=True)
            raise
        return (self._tagger,)
