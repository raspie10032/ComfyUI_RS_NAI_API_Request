# Experimental NAI detection combine loader

This branch adds two **test nodes** under `RS_NovelAI_API/Experimental`:

- **NAI Detection Combine Loader (Test)** selects detection models and returns one `detectors` connection.
- **NAI Face Detailer (Test)** uses that connection and an image to call **NovelAI inpainting**. Enter the prompt, negative prompt, NAI model, strength and seed on this node. Optional character matching and references use the existing NAI inputs.

Connect `Load Image → image` and `NAI Detection Combine Loader (Test) → detectors` on the detailer. There are no local checkpoint, CLIP, VAE or conditioning inputs.

## Start with SEGM

Install ComfyUI-Impact-Pack and ComfyUI-Impact-Subpack, and place a face SEGM `.pt` model in `ComfyUI/models/ultralytics/segm`. Restart ComfyUI, choose the model in the loader and leave the optional models at `None`. An installed model whose name contains `face` is preferred; the loader does not download models or guarantee that a filename identifies a suitable face model.

The default mask processing is **fill small notches and enclosed holes → dilation of 8 original-image pixels → NovelAI inpainting → feather inside the mask**. Dilation gives the generator room around the detected face. Repair still has addition limits so large excluded areas are not blindly filled. Expansion collisions are divided between faces and the other faces' original masks are protected.

The default is `preview_only=true`: inspect the mask and matching report without a NovelAI request. Set it to `false` to generate. `limit_opus_free` stays visible and retains the existing protection rules. A preview does not prove that a chosen model or reference operation will be free; generation checks those separately.

## Optional controls

- In the **loader**, enable `show_optional_models` to select SAM, face BBOX and eye BBOX. Face BBOX requires SAM. Without a BBOX selection, SAM uses the SEGM detector's face boxes. The eye detector supplies extra eye context to the existing NAI pipeline; it does not replace the face mask. This prototype supports the existing SAM ViT loader, not SAM3.
- In the **detailer**, enable `show_advanced` for steps, CFG, matching mode, region count, crop context, mask filling, dilation, feather, autosave and other NAI controls. All detected faces are considered by default, up to `max_regions=5`.
- Folding a section only hides its widgets. Saved selections still apply. To disable an optional model, select `None` before folding the section. Closing and hole filling can each be disabled for comparisons.
- `mask_visualization` is a black/white IMAGE of the final editing support. The matching report includes repair counts and whether the original mask came from SEGM or SAM. Feather blends inside that support, keeping pixels outside it unchanged.

An example workflow is in [examples/experimental/NAI_detection_combo_test.json](../examples/experimental/NAI_detection_combo_test.json). Choose your own image and installed face SEGM model after loading. The example starts in preview mode.

## 한국어

**감지 모델 콤바인 로더(시험)**에서 얼굴 SEGM 모델을 고르고, 출력 한 선을 **NAI 페이스 디테일러(시험)**에 연결합니다. 이미지도 연결한 뒤 디테일러에서 NAI 프롬프트·모델·강도를 정하면 됩니다. 생성은 NovelAI API로 처리합니다.

기본으로 홀·요철을 채우고 8픽셀 확장합니다. 처음에는 **미리보기만**이 켜져 있으므로 마스크를 확인한 뒤 끄면 실제 생성합니다. 로더의 **추가 감지 모델 표시**, 디테일러의 **고급 설정 표시**를 켜면 나머지 옵션이 나타납니다. 접어도 설정은 유지되므로 모델을 끄려면 `None`을 선택하세요. 얼굴 BBOX는 SAM과 함께 사용합니다.

## 日本語

**検出モデル結合ローダー（テスト）**で顔 SEGM モデルを選び、出力を **NAI 顔ディテーラー（テスト）**へ接続します。画像も接続し、ディテーラーで NAI のプロンプト・モデル・強度を指定します。生成には NovelAI API を使います。

初期設定では穴と小さな切り欠きを補修してから、マスクを元画像の8ピクセル分拡張します。最初はプレビューのみです。マスクを確認した後でプレビューを無効にすると実際に生成します。追加の検出モデルと詳細設定は折りたためます。折りたたんでも値は有効です。モデルを無効にするには `None` を選択してください。顔 BBOX は SAM と一緒に使用します。

## Validation scope

195 Python tests and eight JavaScript test files pass. Tests cover NAI infill routing, preview without authentication/API, strict guard blocking, empty detections, invalid/batched images, repaired masks and feather support, detection-only loader validation, and folding without changing saved values.

A real V5 image was previewed with the installed face SEGM model and with optional face BBOX + SAM + eye BBOX. One real V5 Full inpainting request used SEGM, strength 0.35, 28 steps and seed 161616. It produced an edited face with 56,838 mask pixels and zero changed pixels outside that mask. Account balance before and after this single test was unchanged. This is one functional example, not a general quality or billing guarantee. The optional SAM combination has live preview evidence, not a separate paid generation test.

The prototype is isolated from the published 2.7.1 release. Existing detailers keep their input schema and behavior; their feather default remains zero.
