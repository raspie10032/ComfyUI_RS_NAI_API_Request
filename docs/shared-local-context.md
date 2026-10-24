# RS MultiCharacter interoperability

Update both extensions together. Connect a local character pipe to an NAI `nai_context` or `character_prompts` input, or connect an NAI context/character output to the local character and builder inputs. A pipe can pass through local LoRA, placement, mask, reference, interaction and finalize nodes without re-entering its prompts.

Common/character prompts, negatives and centers are shared. Local ComfyUI weights convert to NAI syntax and NAI weights convert to local syntax once. A receiving local sampler applies imported character negatives only in their regions; no extra regional negative path is created when they are empty.

Local model/sampler settings and NAI model/sampler settings remain separate. NAI seeds, canvas, strength, payment protection and API reference inputs continue using that stage's controls. Converting a pipe never grants Anlas permission. Local settings can be restored locally using `use_image_settings`.

NAI does not apply local LoRAs, region masks/boxes, text regions, body-part hints, image-reference configuration or interaction settings. It receives captions and character centers, reports unsupported local features and carries their original data for return to local nodes. Character limits apply only at the receiving side; the original pipe is unchanged. Changing an active count does not rewrite a person-count tag in the common caption.

The NAI and local detection combine loaders have identical controls and interchangeable detector bundles. WD tagger loader controls and outputs are also interchangeable. Their original output socket names and order remain intact. Local and API detailers continue using their respective backends.

Whole-image context and local extras survive PNG and both WebP formats, including NAI detailer saves. Individual inpaint crop requests are retained separately from the whole-image scene. Inset metadata for another canvas is rejected as a replacement for that scene. No workflow JSON serialization is added by this feature.

## Verification

`tests/test_bidirectional_pipe.py` covers both directions, syntax, counts, rich pipe edits, sampling settings, strict protection, detector/tagger controls and image saves. The shared graph check is reproducible without API access:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /path/to/ComfyUI/.venv/bin/python tests/verify_shared_graph.py \
  --comfy /path/to/ComfyUI --mc /path/to/ComfyUI_RS_MultiCharacter_Sampler
```

It runs the real ComfyUI validator/executor on nine mixed nodes and checks two NAI request payloads, output characters and coordinates. It mocks API responses, rejects actual HTTP and reports `real_http_requests: 0`. This is offline interoperability evidence, not live API or GPU quality validation.

On 2026-10-25, the full Python suite passed 288 tests with `RS_MC_TEST_PATH` and `RS_MC_TEST_COMFYUI` set. All 13 JavaScript test files passed with `node --test tests/test_*.mjs`. The companion extension ran 250 Python tests (one old-core-only case skipped) and 14 UI test files. No live NAI generation or Anlas spending was used for these changes.

한국어: 양쪽 확장을 함께 업데이트하면 공통 파이프·감지기·태거를 서로 연결할 수 있습니다. NAI가 지원하지 않는 로컬 기능은 안내하고 보관하여 돌아올 때 복원합니다. 모델·샘플러·과금 보호 설정은 각 백엔드의 설정을 따릅니다.
