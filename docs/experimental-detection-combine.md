# Experimental NAI detection combine loader

This branch adds two **test nodes** under `RS_NovelAI_API/Experimental`:

- **NAI Detection Combine Loader (Test)** selects detection models and returns one `detectors` connection.
- **NAI Face Detailer (Test)** uses that connection and an image to call **NovelAI inpainting**. Enter the prompt, negative prompt, NAI model, strength and seed on this node. Optional character matching and references use the existing NAI inputs.

Connect `Load Image → image` and `NAI Detection Combine Loader (Test) → detectors` on the detailer. There are no local checkpoint, CLIP, VAE or conditioning inputs.

## Start with SEGM

Install ComfyUI-Impact-Pack and ComfyUI-Impact-Subpack. The loader defaults to **Anzhc Face seg 640 v2 y8n**. If the file is missing, the first **execution** downloads it into the registered `ultralytics_segm` folder (normally `models/ultralytics/segm`). The loader displays the filename, percentage, received size, and loading status. Opening the node or selecting a model does not download anything. Existing models are reused; `OFF` never downloads or loads SEGM. The catalog also contains eyes, clothing, skin, hair, hands and whole-person detectors. Only the selected, active models are downloaded; BBOX/SAM ignored because of SEGM priority do not download.

The default download uses the [author's public model repository](https://huggingface.co/Anzhc/Anzhcs_YOLOs/tree/main), pinned at revision `f5a2306d7fed4f3cfc26c25ff1ab2e3f3cfce855`. The approximately 6.6 MiB download is verified by size and SHA-256 before it replaces the temporary file. Interrupted or failed downloads remove the temporary file and can be retried. A manually installed model with the same filename is reused without replacement.

**SEGM takes priority. When SEGM is selected, BBOX and SAM are neither loaded nor run, even if their saved selections are non-OFF.** Their selection values are preserved, so they become active again when SEGM is set to OFF. There is no SAM refinement after a SEGM mask. All three selectors stay visible.

| Selected models | Loaded / used for the editing mask |
| --- | --- |
| SEGM | SEGM only |
| SEGM + BBOX | SEGM only; BBOX skipped |
| SEGM + SAM | SEGM only; SAM skipped |
| SEGM + BBOX + SAM | SEGM only; BBOX and SAM skipped |
| BBOX (SEGM OFF) | BBOX rectangle |
| BBOX + SAM (SEGM OFF) | BBOX regions refined with SAM |
| SAM only / all OFF | Neither SAM nor a region detector is loaded; the detailer asks for SEGM or BBOX before a NovelAI request |

Selected eye BBOX is independent and provides eye context; it does not replace the face mask. All workflows use the same hole/notch filling, dilation and feather controls. The matching report identifies the face detector and mask source.

The default mask processing is **fill small notches and enclosed holes → dilation of 8 original-image pixels → NovelAI inpainting → feather inside the mask**. Dilation gives the generator room around the detected face. Repair still has addition limits so large excluded areas are not blindly filled. Expansion collisions are divided between faces and the other faces' original masks are protected.

The default is `preview_only=true`: inspect the mask and matching report without a NovelAI request. Set it to `false` to generate. `limit_opus_free` stays visible and retains the existing protection rules. A preview does not prove that a chosen model or reference operation will be free; generation checks those separately.

## Detector catalog and additional files

The model list combines the downloadable catalog with **all compatible models discovered by Impact Pack/Subpack in its registered folders**, including nested directories and extra model paths. Put additional files in `ComfyUI/models/ultralytics/segm`, `ComfyUI/models/ultralytics/bbox`, or `ComfyUI/models/sams`, then refresh ComfyUI's node definitions/model lists (or reload the page). No source edits or catalog registration are needed. A matching local filename is reused instead of downloaded. SAM selection uses the installed SAM ViT models; it does not automatically download SAM or include SAM3/ESAM.

| Target | SEGM choices | BBOX choices |
| --- | --- | --- |
| Face | Anzhc Face seg 640 v2 y8n (default), v4 y11n | face_yolov8n, face_yolov8n_v2, face_yolov8s, face_yolov8m |
| Eyes | Anzhc Eyes -seg-hd | eye_yolov8n, eye_yolov8s |
| Clothes | deepfashion2_yolov8s-seg | — |
| Hands | — | hand_yolov8n, hand_yolov8s |
| Skin / body | skin_yolov8n-seg_400 | — |
| Whole person | person_yolov8n-seg, person_yolov8s-seg, person_yolov8m-seg | — |
| Head / hair | Anzhc HeadHair seg y8n | — |

Skin detection covers visible skin, **not the complete clothed body**. Use a person model for the complete figure. Clothing models can produce separate regions for individual garments. To edit hands with BBOX or BBOX+SAM, first set SEGM to `OFF`. For an eye-only edit, select an eye model in the primary SEGM/BBOX selector; the optional eye-context detector alone is not a primary editing-region detector.

Model sources: [Anzhc](https://huggingface.co/Anzhc/Anzhcs_YOLOs), [Bingsu/adetailer](https://huggingface.co/Bingsu/adetailer), [anime eye detectors](https://huggingface.co/killjoyelite/anime-eye-yolov8), and [hben35096 skin model](https://github.com/hben35096/assets/releases/tag/yolo8). Download URLs, upstream revisions, expected byte counts, and SHA-256 hashes are recorded in [detection_model_catalog.json](../detection_model_catalog.json). Model licenses belong to their respective authors and are linked from those distribution pages; the node package does not redistribute the weights.

## Optional controls

- In the **loader**, enable `show_optional_models` to select the extra eye BBOX model. SEGM, BBOX and SAM are always visible. The eye detector supplies extra eye context to the existing NAI pipeline; it does not replace the face mask. This prototype supports the existing SAM ViT loader, not SAM3.
- In the **detailer**, enable `show_advanced` for steps, CFG, matching mode, region count, crop context, mask filling, dilation, feather, autosave and other NAI controls. All detected regions are considered by default, up to `max_regions=5`.
- Folding a section only hides its widgets. Saved selections still apply. To disable a model, select `OFF`. Older prototype workflows using `None` are migrated to `OFF` when opened; API calls with `None` also remain accepted. The widget serialization order is preserved. Closing and hole filling can each be disabled for comparisons.
- `mask_visualization` is a black/white IMAGE of the final editing support. The matching report includes repair counts and whether the original mask came from SEGM, BBOX or SAM. Feather blends inside that support, keeping pixels outside it unchanged.

An example workflow is in [examples/experimental/NAI_detection_combo_test.json](../examples/experimental/NAI_detection_combo_test.json). Choose your own image after loading; the default face SEGM downloads automatically on first execution if missing. The example starts in preview mode.

## 한국어

**감지 모델 콤바인 로더(시험)**에서 얼굴 SEGM 모델을 고르고, 출력 한 선을 **NAI 페이스 디테일러(시험)**에 연결합니다. 이미지도 연결한 뒤 디테일러에서 NAI 프롬프트·모델·강도를 정하면 됩니다. 생성은 NovelAI API로 처리합니다.

**SEGM·얼굴 BBOX·SAM 선택창은 항상 표시**됩니다. 각 모델에서 `OFF`를 고르면 로드도 전달도 하지 않습니다. 얼굴 SEGM만 사용하는 것이 기본이며 **BBOX 단독**, **BBOX+SAM**도 가능합니다. BBOX만 사용하면 사각 영역을 보정합니다. **SEGM을 선택하면 얼굴 BBOX·SAM은 선택값이 있어도 로드·실행하지 않습니다.** 셋 다 골라도 SEGM만 사용하며, SAM으로 다시 보정하지 않습니다. BBOX·SAM은 SEGM이 OFF일 때만 사용합니다. 저장된 선택값은 유지됩니다.

기본 모델 **Anzhc Face seg 640 v2 y8n**이 없으면 첫 실행 때 자동으로 받습니다(약 6.6 MiB). 로더에 파일명·퍼센트·받은 용량·로딩 상태가 표시됩니다. 노드를 추가하거나 모델을 고르는 것만으로는 다운로드하지 않으며, SEGM이 OFF면 받지 않습니다. 기존 파일은 재사용하고 다운로드 실패·취소 시 임시 파일을 지웁니다. 다음 실행 때 다시 시도할 수 있습니다.

전부 OFF인 묶음도 만들 수 있지만, 디테일러를 실행하려면 **SEGM 또는 BBOX가 하나 이상** 필요합니다. SAM·보조 눈 모델만으로는 수정 영역을 정할 수 없다고 실행 전에 안내합니다. 눈 BBOX는 **눈 감지 옵션 펼치기**에서 선택합니다.

기본으로 홀·요철을 채우고 8픽셀 확장합니다. 처음에는 **미리보기만**이 켜져 있으므로 마스크를 확인한 뒤 끄면 실제 생성합니다. 디테일러의 **고급 설정 표시**를 켜면 나머지 옵션이 나타납니다. 접어도 선택값은 유지됩니다. 예전 시험 워크플로의 `None`은 열 때 `OFF`로 바뀌며 입력 순서는 유지됩니다.

### 모델 목록과 직접 추가하기

- **얼굴:** 기본 Anzhc v2·v4 SEGM, YOLOv8 얼굴 BBOX n/n_v2/s/m.
- **눈:** Anzhc Eyes SEGM, eye_yolov8n/s BBOX.
- **옷:** deepfashion2 SEGM. **손:** hand_yolov8n/s BBOX.
- **몸의 피부 영역:** skin_yolov8n-seg_400. **옷을 포함한 인물 전체:** person_yolov8n/s/m-seg.
- **머리·머리카락:** Anzhc HeadHair SEGM.

선택한 미설치 모델만 실행할 때 받습니다. 직접 추가할 모델은 원래 쓰던 **`models/ultralytics/segm`, `models/ultralytics/bbox`, `models/sams`** 폴더에 넣고 ComfyUI 목록 새로고침 또는 페이지 새로고침을 하면 표시됩니다. 하위 폴더와 추가 모델 경로도 지원하며 목록 중복은 제거합니다. SAM은 설치된 ViT 모델을 사용합니다.

피부 모델은 옷 입은 전신을 잡는 모델이 아닙니다. 전신은 `person` 모델을 쓰고, 손 BBOX를 쓰려면 먼저 SEGM을 OFF로 바꿔 주세요. 눈만 보정하려면 기본 SEGM/BBOX 선택칸에서 눈 모델을 고릅니다. 얼굴 전용 입력 이름은 예전 시험 워크플로 호환을 위해 내부적으로 유지합니다.

## 日本語

**検出モデル結合ローダー（テスト）**で顔 SEGM モデルを選び、出力を **NAI 顔ディテーラー（テスト）**へ接続します。画像も接続し、ディテーラーで NAI のプロンプト・モデル・強度を指定します。生成には NovelAI API を使います。

**SEGM・顔BBOX・SAMの選択欄は常に表示**されます。それぞれ `OFF` にすると、そのモデルはロードも受け渡しもしません。標準は顔SEGMのみですが、**BBOX単独**・**BBOX+SAM**も使えます。BBOX単独では矩形を補正します。**SEGM選択時は、顔BBOX・SAMが選択されていてもロード・実行しません。** 3つ選んでもSEGMのみを使い、SAMで再補正しません。BBOX・SAMはSEGMがOFFの場合のみ有効です。選択値は保持されます。

標準の **Anzhc Face seg 640 v2 y8n** がなければ初回実行時に自動ダウンロードします（約6.6 MiB）。ノードにファイル名・進捗率・受信量・ロード状態を表示します。ノード追加やモデル選択だけではダウンロードしません。SEGMがOFFならダウンロードも行いません。既存ファイルを再利用し、失敗・中断時は一時ファイルを削除します。次の実行で再試行できます。

全てOFFでもローダーは空のモデルセットを出力できますが、ディテーラーには**SEGMまたはBBOXが1つ以上**必要です。SAM・補助の目モデルだけの場合は実行前に案内します。目BBOXは**目の検出オプションを表示**で選択します。

初期設定では穴と小さな切り欠きを補修してから、マスクを元画像の8ピクセル分拡張します。最初はプレビューのみです。マスクを確認した後でプレビューを無効にすると実際に生成します。詳細設定を折りたたんでも値は有効です。以前のテストワークフローの `None` は読み込み時に `OFF` に変換され、入力の保存順序も維持されます。

### モデル一覧と手動追加

顔（Anzhc v2/v4 SEGM、YOLOv8 n/n_v2/s/m BBOX）、目（Anzhc Eyes SEGM、eye_yolov8n/s BBOX）、服（deepfashion2 SEGM）、手（hand_yolov8n/s BBOX）、肌（skin_yolov8n-seg_400）、人物全体（person_yolov8n/s/m-seg）、頭・髪（Anzhc HeadHair SEGM）を選択できます。

未インストールの選択モデルだけを実行時にダウンロードします。追加モデルは既存の **`models/ultralytics/segm`、`models/ultralytics/bbox`、`models/sams`** に配置してモデル一覧またはページを更新してください。サブフォルダーと追加モデルパスも読み取り、重複表示を除きます。SAMはインストール済みのViTモデルを使用します。

肌モデルは服を含む全身の検出ではありません。全身は`person`、手のBBOXはSEGMをOFFにして使います。目だけ補正する場合は主SEGM/BBOX欄で目モデルを選びます。顔用の内部入力名は以前のテストワークフローとの互換性のため保持しています。

## Validation scope

The OFF/priority/catalog update passes **209 Python tests and 8 JavaScript test files**. A fresh default SEGM download emitted real byte progress, passed SHA-256 validation, and was reused without network on the next run. An all-OFF detailer execution failed with the model-selection explanation and no model download. With SEGM+BBOX+SAM selected, only SEGM loaded and ran. BBOX-only and BBOX+SAM previews also passed.

All **17 catalog weights** were loaded and inferred through the running ComfyUI detailer in preview mode. A single V5 portrait produced face/eye/clothing/skin/person/head masks; the two hand models correctly reported no detections there. On the existing four-person V5 example, both hand models detected three regions. A detector copied into a nested standard model folder after server startup appeared on a fresh model-list request and ran without restarting. These are integration checks on two images, not a general detector accuracy evaluation. No new NovelAI calls or Anlas spending were used for this update.

Tests cover NAI infill routing, preview without authentication/API, strict guard blocking, empty detections, invalid/batched images, repaired masks and feather support, all 16 loader combinations (including eye BBOX), all eight SEGM/BBOX/SAM detailer combinations, shared BBOX model caching, invalid selections before model loading, legacy `None` values, and folding without changing saved values.

A real V5 image was previewed with the installed face SEGM model and with optional BBOX + SAM + eye BBOX. One real V5 Full inpainting request used SEGM, strength 0.35, 28 steps and seed 161616. It produced an edited face with 56,838 mask pixels and zero changed pixels outside that mask. Account balance before and after this single test was unchanged. This is one functional example, not a general quality or billing guarantee. The optional SAM combination has live preview evidence, not a separate paid generation test.

The prototype is isolated from the published 2.7.1 release. Existing detailers keep their input schema and behavior; their feather default remains zero.
