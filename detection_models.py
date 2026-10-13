# SPDX-License-Identifier: GPL-3.0-only
"""Fetch selected catalog detectors on execution, verified before installation."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from urllib.request import urlopen

from .errors import user_error
from .runtime_control import check_interrupted, is_interruption


DEFAULT_FILENAME = "Anzhc Face seg 640 v2 y8n.pt"
DEFAULT_SEGM = "segm/" + DEFAULT_FILENAME
CATALOG = json.loads((Path(__file__).with_name("detection_model_catalog.json")).read_text(encoding="utf-8"))
_download_lock = threading.Lock()


def ensure_detection_model(name, progress):
    if name not in CATALOG:
        return None  # User-installed models are resolved by Impact Subpack.
    import folder_paths

    spec = CATALOG[name]
    kind, filename = name.split("/", 1)
    category = "ultralytics_" + kind
    expected_size = spec["size"]

    while not _download_lock.acquire(timeout=0.1):
        check_interrupted()
    temporary = None
    try:
        check_interrupted()
        # Match Impact Subpack's lookup order, including additional model paths.
        existing = folder_paths.get_full_path("ultralytics", name)
        existing = existing or folder_paths.get_full_path(category, filename)
        if existing is not None:
            return Path(existing)
        roots = folder_paths.get_folder_paths(category)
        if not roots:
            raise RuntimeError("Install ComfyUI-Impact-Subpack and restart ComfyUI. / Impact-Subpack 설치 후 다시 시작해 주세요.")
        target = Path(roots[0]) / filename
        if target.is_file():
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        progress.report(f"Downloading {filename}: 0% (0 / {expected_size / 1024**2:.1f} MiB)", force=True)
        digest, received = hashlib.sha256(), 0
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".nai-detector-", suffix=".part", delete=False) as output:
            temporary = Path(output.name)
            with urlopen(spec["url"], timeout=30) as response:
                while True:
                    check_interrupted()
                    chunk = response.read(128 * 1024)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > expected_size:
                        raise ValueError("Unexpected model file size")
                    output.write(chunk)
                    digest.update(chunk)
                    progress.report(f"Downloading {filename}: {received / expected_size:.0%} ({received / 1024**2:.1f} / {expected_size / 1024**2:.1f} MiB)", min(received / expected_size, 0.999))
        check_interrupted()
        if received != expected_size or digest.hexdigest() != spec["sha256"]:
            raise ValueError("Model download verification failed (size/SHA-256)")
        os.replace(temporary, target)
        temporary = None
        # Invalidate ComfyUI's file listing after installing the complete file.
        for category in (category, "ultralytics"):
            folder_paths.filename_list_cache.pop(category, None)
        progress.report(f"Downloaded: {filename}", 1, force=True)
        return target
    except Exception as error:
        if is_interruption(error):
            raise
        message = (f"Could not download {name}. Check the network and model folder permissions, then run again. "
                   f"You can also place the file in models/ultralytics/{kind}. "
                   f"({type(error).__name__}: {error})")
        raise user_error("DETECTION_MODEL_DOWNLOAD", RuntimeError, message) from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        _download_lock.release()
