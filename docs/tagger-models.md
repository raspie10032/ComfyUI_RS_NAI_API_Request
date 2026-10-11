# Local tagger models

`NAI WD Tagger Loader (PyTorch)` offers three models. Its node ID, output socket,
existing device/batch widgets, and omitted-model default remain compatible with
saved workflows. The loader fetches and loads only the selected model when it executes,
with per-file byte progress and preparation status on the node. The repository does not redistribute weights or upstream model code.

| Model | Pinned revision | Upstream license |
| --- | --- | --- |
| [WD ViT v3](https://huggingface.co/SmilingWolf/wd-vit-tagger-v3) | `7f6b584d0bd3f55c4531f14ba3d4761b2bccdc0f` | Apache-2.0 |
| [WD EVA02 Large v3](https://huggingface.co/SmilingWolf/wd-eva02-large-tagger-v3) | `b25b82a03f7282e41aa2f257a52c7583b710bd1c` | Apache-2.0 |
| [PixAI Tagger v1.0](https://huggingface.co/pixai-labs/pixai-tagger-v1.0) | `9fe10addf9326e292da8a85a98ea74cd91b41771` | Apache-2.0 |

WD uses its published timm config, white square padding and BGR input. PixAI uses
the official `RescalePadProcessor` (RGB, aspect-preserving resize, black padding,
1008 pixels, normalization) and `ViTDetCls` from the selected snapshot. The
`tagger_pipeline.py` SHA-256 must be
`3431279fdfff234f62664999fc1fe6bb20f1e8756f7435d0e165ebd4456f7fcd`.
Transformers loads this local, verified snapshot with `trust_remote_code=True`
and `local_files_only=True`; it does not fetch code from a moving `main` branch.

The matcher consumes dense sigmoid scores for general and character tags only.
PixAI's copyright/style/meta/rating categories are excluded. The official
captioning thresholds are not applied because weak competing scores are needed
for the match margin. The existing minimum score/margin and ambiguity retry
remain in effect. This integration does not claim improved matching accuracy for
every character or crop; use preview to inspect your actual images.

No tagger output is inserted into generation prompts. An accepted match selects
the original character prompt and negative prompt without rewriting them.

## Checks

`python -m unittest discover -s tests -v` covers selection/default compatibility,
per-model dependency errors, selected-revision download isolation, pinned code
verification, PixAI category mapping/RGB input, batching, score-length failures,
CPU offload, and the existing matching/prompt boundary.

`python tests/smoke_wd_tagger.py --model-name "PixAI Tagger v1.0" --device auto
--cache-dir /path/to/rs_wd_tagger --output /tmp/pixai-smoke.json` exercises real
weights and two-character matching with supplied face boxes. It can download the
selected model. Set `HF_HUB_OFFLINE=1` after downloading to check cache-only use.
It does not exercise live YOLO/SAM or send NovelAI requests.

Validation for 2.4.3 (2026-10-11): 103 Python tests passed, along with the
JavaScript notice/progress routing and workflow-serialization checks. Real
EVA02 and PixAI weights each matched both supplied face regions to the expected
original character slots. This is a two-region regression fixture, not a broad
accuracy comparison or a live detector test. A running Linux ComfyUI executed
the loader, emitted real download/status events and displayed the ready state
on the node. Windows installation files were updated; Windows execution was
not tested in this Linux session.

If an initial download stalls in the Xet transport, start ComfyUI with
`HF_HUB_DISABLE_XET=1` to use Hugging Face's HTTP path. This was needed for the
local PixAI download during validation; HTTP downloads retain node progress
and use the same model cache.
