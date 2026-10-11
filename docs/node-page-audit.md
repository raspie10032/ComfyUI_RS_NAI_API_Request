# Comfy.ICU node review — 2026-10-11

Baseline: unified `main` 2.4.1 (`2711085`). Release: 2.4.2.
All 13 entries in the [extension listing](https://comfy.icu/extension/raspie10032__ComfyUI_RS_NAI_API_Request) were opened and read in Firefox, including the input tables and caveats. The two reference nodes in the current repository were checked separately: their expected Comfy.ICU URLs returned 404. External descriptions are not an API specification and are not maintained by this repository.

## Every node

| Page | Evidence and disposition |
| --- | --- |
| [CharacterPromptSelect](https://comfy.icu/node/CharacterPromptSelect) | The page describes obsolete 0–10 coordinates and V3 ignoring characters. Current coordinates are 0–1. Nonfinite coordinates now fail; out-of-range direct inputs keep the historical clamp but show a migration notice. V3 generation now rejects character slots. No automatic conversion of ambiguous old values. |
| [ComfyUIToNovelAIV4](https://comfy.icu/node/ComfyUIToNovelAIV4) | Reproduced `(tag:o)` disappearing. Preserve legacy parse output, report each omitted malformed group and substituted out-of-range weight on the node. Escape literal parentheses. |
| [ComfyUIToOldNAI](https://comfy.icu/node/ComfyUIToOldNAI) | Same malformed-input notice; zero/negative weights report their unavoidable legacy-bracket replacement. Integer bracket counts are approximate by design; the page's numerical examples do not define the converter. |
| [NAIFaceDetailerNode](https://comfy.icu/node/NAIFaceDetailerNode) | First-face-only statement is obsolete: use `detail_mode=all`. Preview/report now expose score/margin skip reasons and region limits; failed tighter-crop retries retain their latest scores. Image batches fail before detection. API grid masks and per-region compositing are preserved. |
| [NAIFaceDetailerSegmNode](https://comfy.icu/node/NAIFaceDetailerSegmNode) | Shares the bbox detailer's fixes. Current code uses the segmentation detector's boxes to guide SAM; it does not directly paste the detector's polygon. Added an explicit node description. No polygon substitution was introduced. |
| [NAIImg2ImgNode](https://comfy.icu/node/NAIImg2ImgNode) | The page's free-limit resizing account is obsolete: strict mode blocks general img2img. Batches previously used only image zero; now rejected. V3 character slots rejected before token/encoding. Shared autosave and response fixes apply. |
| [NAIInpaintNode](https://comfy.icu/node/NAIInpaintNode) | Strict mode blocks general inpainting. Validate single image/mask, finite 0–1 mask values and nonempty repaint area; mismatched dimensions produce an alignment notice. V5 Curated fallback is visible. Soft mask values remain intact; no automatic blur added. |
| [NovelAIGenerator](https://comfy.icu/node/NovelAIGenerator) | Opus resizes/step changes and Medium fixed settings are now reported. Unsupported character/model inputs fail early. Autosaves no longer collide within a second; ZIP metadata ordering no longer prevents image selection. Subscription preflight already existed; page claims to the contrary are outdated. |
| [NovelAIV4ToComfyUI](https://comfy.icu/node/NovelAIV4ToComfyUI) | An inline suffix after closing `::` without a comma is historically omitted; now reported. Numeric weights remain exact on this path; the page's general ±5 clamp claim does not describe every conversion direction. Unclosed forward scopes remain supported. |
| [NovelAIV4ToOldNAI](https://comfy.icu/node/NovelAIV4ToOldNAI) | Negative/zero replacement is now visible in the UI, alongside inline-suffix loss. Numeric-to-bracket quantization remains intentional. |
| [OldNAIToComfyUI](https://comfy.icu/node/OldNAIToComfyUI) | Nested/backward bracket behavior and historical two-decimal rounding checked against existing regression tests. No new parse defect demonstrated; documented behavior retained. |
| [OldNAIToNovelAIV4](https://comfy.icu/node/OldNAIToNovelAIV4) | Same legacy bracket and rounding contract. No demonstrated defect requiring changed output. Description explains the rounding/backward scope behavior. |
| [RSWDTaggerLoader](https://comfy.icu/node/RSWDTaggerLoader) | Reproduced deferred missing-dependency failure. Loader now imports optional dependencies before returning a handle and supplies this interpreter's installation command. Cached model resolution, CPU loading and scoring stages are logged. Model download remains lazy. |
| [NAIVibeTransfer](https://comfy.icu/node/NAIVibeTransfer) — 404 | Repository node inspected despite absent listing. Existing model checks, finite parameters, single-image validation, list limits, lazy encoding and strict pre-encoding blocking retained. Existing reference regression tests run. |
| [NAIPreciseReference](https://comfy.icu/node/NAIPreciseReference) — 404 | Repository node inspected despite absent listing. Existing supported-model/type checks, image preparation, reference limits and strict blocking retained. No unsupported V5 capability was added. |

## Operational guidance

- Notices are shown after execution in a read-only node widget and in the ComfyUI console. Hidden execution metadata was added; saved input positions/defaults and output sockets are unchanged. Reload the browser after updating. Pure converter calls still return tuples.
- The converter keeps existing output for malformed input. A notice is not automatic repair: inspect it before passing the text to generation. Old NAI cannot exactly represent numeric weights or negative/zero emphasis.
- Old coordinate migration requires the original saved values: divide 0–10 values by ten. Values already in 0–1 cannot be identified reliably as old or new. A frontend may clamp values before execution, so do not rely solely on the runtime notice to repair old workflows.
- One NovelAI image per generation request is supported. Split input batches upstream; use a separate queued request per image. General img2img/inpainting and references require `limit_opus_free=False` and can spend Anlas. Do not disable protection just to silence an error.
- HTTP 429 handling already honors `Retry-After` with one retry and interruptible waiting. It is not unconditionally a 60-second sleep. A 402 failure is not retried. Process-local free preflight is not an account-wide billing guarantee.
- For seam reports, inspect the actual mask and source first. Existing tests prove disjoint ownership/outside-mask preservation for synthetic overlapping regions. They do not establish subjective seam quality on every image. No new real-image seam defect was reproduced here, so no blur/feather change was made.

## Verification and reproducibility

Verified on Linux with the ComfyUI Python environment:

| Check | Result |
| --- | --- |
| Python regression suite | 92 tests passed, including strict billing guards, references, Medium payloads, malformed inputs, autosave collisions and response archives. |
| Browser extension unit check | Existing callback preserved; plain-text/read-only notice lifecycle, both serialization paths and node dimensions checked. |
| Actual ComfyUI execution | All six converters returned strings to Preview Any; clean conversion cleared notices. WD loader imports succeeded. Strict img2img/inpaint and V3 character-slot inputs failed as intended. |
| Actual Firefox UI, ComfyUI frontend 1.51.9 | Warning rendered on the node, disappeared after clean execution, and was excluded from both positional and named saved workflow values. The first UI attempt exposed a serialization flag difference; the release handles both workflow and API serialization. |
| Existing workflow schema | All 15 nodes retain required/optional input names, order, defaults and output sockets. Hidden execution ID added for notices. |
| Cached WD model on CPU | Real weights selected the two original character slots; the second selection used the tighter-crop retry. No NovelAI call. |

From the repository root, using the Python interpreter that runs ComfyUI:

```bash
python -m unittest discover -s tests
python -m compileall -q .
git diff --check
node tests/test_notices.mjs
HF_HUB_OFFLINE=1 python tests/smoke_wd_tagger.py --cache-dir /path/to/existing/rs_wd_tagger --output /tmp/wd-smoke.json
```

The optional WD smoke uses real cached model weights on CPU with supplied face-box fixtures. It verifies automatic character selection and tighter-crop retry; detector/SAM/NovelAI calls are not live in that test. Network/request/error/strict-limit tests use mocks. Runtime converter, UI notice and installed-file checks are recorded separately in the completion report.

No new paid NovelAI generation is required by these local diagnostics, input validation, response selection or file-naming changes. Previously verified Medium payload behavior is covered by regressions. V4/V4.5 paid reference-generation quality and Windows runtime execution are not newly verified by this audit.
