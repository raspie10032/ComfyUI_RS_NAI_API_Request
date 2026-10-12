"""Optional real-weight tagger smoke; no live YOLO, SAM or NovelAI requests.

Run from package root:
    python tests/smoke_wd_tagger.py --cache-dir /path/to/cache --output /path/to/result.json

Uses supplied face-box fixtures on the regression image, not interactive
region assignment. The runtime itself automatically selects the character slots.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))


def main():
    from ComfyUI_RS_NAI_API_Request.detailer import run_face_detail
    from ComfyUI_RS_NAI_API_Request.generators import CharacterPrompt
    from ComfyUI_RS_NAI_API_Request.image_utils import pil_to_tensor
    from ComfyUI_RS_NAI_API_Request.wd_tagger import DEFAULT_MODEL, MODELS, WDTagger

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-name", choices=list(MODELS), default=DEFAULT_MODEL)
    parser.add_argument("--device", choices=["auto", "cpu"], default="cpu")
    parser.add_argument("--batch-size", type=int, default=1)
    args = parser.parse_args()
    image = Image.open(ROOT / "tests/fixtures/wd-tagger-two-characters.png").convert("RGB")
    boxes = [(3580, 405, 3750, 560), (3650, 695, 3860, 860)]
    regions = [SimpleNamespace(bbox=b, crop_region=b) for b in boxes]
    detector = SimpleNamespace(
        detect=lambda *a, **kw: ((image.height, image.width), regions)
    )
    characters = [
        CharacterPrompt(
            "akiyama yukari, girls und panzer, brown hair, brown eyes, short hair, messy hair",
            "",
            0.5,
            0.5,
        ),
        CharacterPrompt(
            "nishizumi miho, girls und panzer, brown hair, brown eyes, short hair",
            "",
            0.5,
            0.5,
        ),
    ]
    start = time.monotonic()
    _, _, report = run_face_detail(
        pil_to_tensor(image),
        detector,
        None,
        None,
        "eye detail",
        "bad quality",
        "NAI Diffusion V5 Full",
        0.4,
        0.3,
        "k_euler",
        20,
        5,
        0.5,
        0,
        3,
        "karras",
        123,
        detail_mode="all",
        matching_mode="wd14",
        characterPrompts=characters,
        tagger=WDTagger(args.cache_dir, args.device, args.batch_size, args.model_name),
        preview_only=True,
    )
    result = {
        "model_name": args.model_name,
        "model_revision": MODELS[args.model_name][1],
        "device": args.device,
        "source": "tests/fixtures/wd-tagger-two-characters.png with supplied face-box fixtures",
        "validation": "real tagger/PyTorch and automatic matching; no live YOLO/SAM/NAI",
        "seconds_including_cached_load": time.monotonic() - start,
        "regions": json.loads(report),
    }
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    assert [r["character"] for r in result["regions"]] == [2, 1], result
    if args.model_name == DEFAULT_MODEL:
        assert result["regions"][1]["reason"] == "tag_match_tight", result
    print("PASS: two character slots selected automatically.")


if __name__ == "__main__":
    main()
