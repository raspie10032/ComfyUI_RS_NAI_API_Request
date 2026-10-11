# SAM3 and native SEGM masks

`NAI Face Detailer` accepts a standard ComfyUI `MASK` through `detail_mask`.
Connect the image used for segmentation to `image`, connect SAM3's `MASK`
output to `detail_mask`, and set `mask_source=external_mask`.
No legacy SAM model or bbox detector is required for this path.

- For separate objects, enable SAM3 `individual_masks` and choose
  `detail_mode=all`. Each nonempty mask batch item becomes one region.
  A merged mask remains one region, even if it contains several objects.
- The mask dimensions must match the source image. Accepted shapes are
  `[H,W]` and `[B,H,W]`, with finite values between 0 and 1.
- An empty `[0,H,W]` batch or all-black masks mean no detections: return the
  original image, a black mask, and a `no_detections` report without requesting NAI.
- For an Impact SEGM detector, connect `segm_detector` and select `segm`.
  The separate `Detailer` node still requires its primary `segm_detector`.
- `auto` prioritizes a complete detector + legacy SAM connection, then external
  MASK, then native SEGM. Select the source explicitly when both are connected.

## Preview and overlapping objects

With `preview_only=True`, native SEGM and external MASK paths calculate the same
final composite masks used during execution. This makes no token reads or NAI
requests. The mask output shows the actual pixels eligible for replacement;
the JSON report includes `mask_source`, `mask_pixels`, and skipped regions.
Legacy bbox + SAM preview remains detection/matching-only without SAM inference.

Pixels meeting `threshold` belong to that instance. Non-overlapping members are
preserved, including branches, holes and thin features. Only pixels shared by
multiple masks are assigned to the nearest detection center; detection order
breaks equal-distance ties. Skipped instances retain ownership of their pixels,
so another instance cannot overwrite them. A fully duplicate mask may therefore
have no remaining pixels and will not issue a second request.

NAI receives a crop with a grid-aligned mask (32 px boxes / 8 px stride, with
whole-cell coverage for thin features). This request mask may extend beyond the
object for generation context. The returned image is pasted **only through the
owned source mask**, so request-grid expansion and eye detections do not enlarge
the final edit area. Each crop is taken from the original image.

`limit_opus_free` keeps its existing default and checks. A full-frame edit is
blocked in strict mode; preview remains available. No mask source bypasses the
request's account, model, reference or billing validation.

## Workflow compatibility and verification

`mask_source` is appended after the released 2.5.0 widgets on both detailers.
Older workflows that store widget values by position keep their settings.

`tests/test_native_detail_masks.py` covers the empty SAM3 batch, input validation,
2,036-pixel disjoint instance preservation, overlap ownership, duplicate masks,
native SEGM soft masks/holes, preview/execution equality, thin features after
resizing, strict full-frame blocking, and the released widget order. Generation
responses and detector outputs in these tests are mocked; they do not measure
SAM3 model quality or NovelAI generation quality.

An installed ComfyUI runtime was also checked with two supplied test masks and
two sequential V5 Full inpainting requests. Both regions were edited, the preview
and execution masks matched exactly, and every pixel outside the masks remained
unchanged. The observed total Anlas balance did not decrease for those requests;
this does not guarantee free generation for other accounts or settings.
SAM3 and SEGM detector weights were not installed for this check, so actual
segmentation inference and recognition quality were not tested. The supplied
masks exercised the standard MASK input path. A browser load of positional
2.5.0 workflows verified both detailers' settings and detector connections.
