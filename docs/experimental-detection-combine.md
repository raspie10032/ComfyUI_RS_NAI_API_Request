# Experimental NAI detection combine loader

This branch adds two **test nodes** under `RS_NovelAI_API/Experimental`:

- **NAI Detection Combine Loader (Test)** selects detection models and returns one `detectors` connection.
- **NAI Face Detailer (Test)** uses that connection and an image to call **NovelAI inpainting**. Enter the prompt, negative prompt, NAI model, strength and seed on this node. Optional character matching and references use the existing NAI inputs.

Connect `Load Image → image` and `NAI Detection Combine Loader (Test) → detectors` on the detailer. There are no local checkpoint, CLIP, VAE or conditioning inputs.

**Quality cannot be guaranteed as the number of processed regions increases.** Higher region counts may reduce detection, character matching, and correction quality. Check the preview and start with a small number of regions.

## Start with SEGM

Install ComfyUI-Impact-Pack and ComfyUI-Impact-Subpack. The loader defaults to **Anzhc Face seg 640 v2 y8n**. If the file is missing, the first **execution** downloads it into the registered `ultralytics_segm` folder (normally `models/ultralytics/segm`). The loader displays the filename, percentage, received size, and loading status. Opening the node or selecting a model does not download anything. Existing models are reused; `OFF` never downloads or loads SEGM. The catalog also contains eyes, clothing, skin, hair, hands and whole-person detectors. Only the selected, active models are downloaded; BBOX/SAM ignored because of SEGM priority do not download.

The default download uses the [author's public model repository](https://huggingface.co/Anzhc/Anzhcs_YOLOs/tree/main), pinned at revision `f5a2306d7fed4f3cfc26c25ff1ab2e3f3cfce855`. The approximately 6.6 MiB download is verified by size and SHA-256 before it replaces the temporary file. Interrupted or failed downloads remove the temporary file and can be retried. A manually installed model with the same filename is reused without replacement.

**SEGM takes priority. When SEGM is selected, BBOX and SAM are neither loaded nor run, even if their saved selections are non-OFF.** Their selection values are preserved, so they become active again when SEGM is set to OFF. There is no SAM refinement after a SEGM mask. A read-only note below the selectors explains the current execution path before running. Changing a model clears the previous loading status, without clearing saved model selections. All three selectors stay visible.

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

An example workflow is in [examples/experimental/NAI_detection_combo_test.json](../examples/experimental/NAI_detection_combo_test.json). Choose your own image after loading; the default face SEGM downloads automatically on first execution if missing. The example starts in preview mode and shows the image/detections and editing mask together. White mask pixels are editable; black pixels are preserved.

### Changing the example's person count

Reducing `character_count` from 5 to 3 excludes slots 4 and 5 from generation and NAI context. Their saved text remains available if you expand the slots again. Also update the T2I common prompt: `5girls` → `3girls`, `five women` → `three women`, and `all five faces visible` → `all three faces visible`. I2I and the detailer inherit the common prompt unchanged. `max_regions` limits editing regions; it does not set the number of people drawn. The same character can be matched to more than one region.

## 한국어

### 예제의 인원수 바꾸기

`character_count`를 5에서 3으로 줄이면 4·5번 슬롯은 생성 요청과 NAI 컨텍스트에서 제외됩니다. 저장된 내용은 다시 펼칠 때 복원하기 위해 남겨둡니다. **T2I 공통 프롬프트도** `5girls` → `3girls`, `five women` → `three women`, `all five faces visible` → `all three faces visible`로 바꿔 주세요. I2I와 디테일러는 공통 프롬프트를 그대로 이어받습니다. `max_regions`는 보정할 영역 수의 상한이며 그림에 나올 인원수를 정하지 않습니다. 같은 캐릭터가 여러 영역에 매칭될 수도 있습니다.

**단, 처리 수가 많을수록 품질을 보장하지 못합니다.** 처리 영역이 많아지면 감지·캐릭터 매칭·보정 품질이 떨어질 수 있으므로, 미리보기를 확인하고 적은 수부터 시험해 주세요.

**감지 모델 콤바인 로더(시험)**에서 얼굴 SEGM 모델을 고르고, 출력 한 선을 **NAI 페이스 디테일러(시험)**에 연결합니다. 이미지도 연결한 뒤 디테일러에서 NAI 프롬프트·모델·강도를 정하면 됩니다. 생성은 NovelAI API로 처리합니다.

**SEGM·BBOX·SAM 선택창은 항상 표시**됩니다. 각 모델에서 `OFF`를 고르면 로드도 전달도 하지 않습니다. 얼굴 SEGM만 사용하는 것이 기본이며 **BBOX 단독**, **BBOX+SAM**도 가능합니다. BBOX만 사용하면 사각 영역을 보정합니다. **SEGM을 선택하면 BBOX·SAM은 선택값이 있어도 로드·실행하지 않습니다.** 셋 다 골라도 SEGM만 사용하며, SAM으로 다시 보정하지 않습니다. BBOX·SAM은 SEGM이 OFF일 때만 사용합니다. 저장된 선택값은 유지됩니다. 선택창 아래에 **현재 선택의 실행 방식**이 바로 표시되고, 모델을 바꾸면 이전 로딩 완료 표시는 지웁니다. 예제에는 **이미지와 수정 마스크 미리보기**를 함께 연결했습니다. 흰 영역은 수정 대상, 검은 영역은 보존 대상입니다.

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

### サンプルの人数を変更する

`character_count`を5から3に減らすと、スロット4・5は生成リクエストとNAIコンテキストから除外されます。再び表示したときに復元できるよう、入力内容は保存されます。**T2Iの共通プロンプトも** `5girls` → `3girls`、`five women` → `three women`、`all five faces visible` → `all three faces visible`に変更してください。I2Iとディテーラーは共通プロンプトをそのまま引き継ぎます。`max_regions`は補正領域数の上限で、描く人数の指定ではありません。同じキャラクターが複数領域に照合される場合もあります。

**ただし、処理する領域数が多くなるほど、品質を保証できません。** 検出・キャラクターの照合・補正の品質が低下する可能性があるため、プレビューを確認し、少ない領域数からお試しください。

**検出モデル結合ローダー（テスト）**で顔 SEGM モデルを選び、出力を **NAI 顔ディテーラー（テスト）**へ接続します。画像も接続し、ディテーラーで NAI のプロンプト・モデル・強度を指定します。生成には NovelAI API を使います。

**SEGM・BBOX・SAMの選択欄は常に表示**されます。それぞれ `OFF` にすると、そのモデルはロードも受け渡しもしません。標準は顔SEGMのみですが、**BBOX単独**・**BBOX+SAM**も使えます。BBOX単独では矩形を補正します。**SEGM選択時は、BBOX・SAMが選択されていてもロード・実行しません。** 3つ選んでもSEGMのみを使い、SAMで再補正しません。BBOX・SAMはSEGMがOFFの場合のみ有効です。選択値は保持されます。モデル選択欄の下に現在の実行方法を表示します。モデルを変更すると以前のロード完了表示を消去します。サンプルで画像と編集マスクを同時に確認できます。白い部分が編集対象、黒い部分は保持されます。

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

A real V5 image was previewed with the installed face SEGM model and with optional BBOX + SAM + eye BBOX. One real V5 Full inpainting request used SEGM, strength 0.35, 28 steps and seed 161616. It produced an edited face with 56,838 mask pixels and zero changed pixels outside that mask. Account balance before and after this single test was unchanged. This is one functional example, not a general quality or billing guarantee. The subsequent usability check also completed six real V5 Full face edits: four SEGM faces matched to characters 1–4 with WD ViT v3 at strength 0.35, one default SEGM portrait at strength 0.55, and one BBOX+SAM portrait at strength 0.35. All three output images preserved every pixel outside their editing masks. The balance stayed unchanged for each workflow; this does not establish free billing for other accounts or settings. The initial test-server run stopped before submission because its environment lacked the API token; after correcting that environment, the recorded rerun succeeded.

The prototype is isolated from the published 2.7.1 release. Existing detailers keep their input schema and behavior; their feather default remains zero.


## T2I → I2I → detailer context / 생성 설정 이어받기 / 生成設定の引き継ぎ

**한국어:** T2I의 `image`와 `nai_context`를 각각 I2I의 같은 입력에 연결하고, I2I의 두 출력을 시험 디테일러의 `image`·`nai_context`에 연결합니다. 캐릭터 프롬프트는 T2I에 한 번만 연결하면 됩니다. 디테일러에는 감지 모델 콤바인 로더를 연결하고, 여러 캐릭터라면 태거 로더도 연결하세요. 컨텍스트의 여러 캐릭터는 자동 매칭으로 원래 프롬프트를 선택하며, 태거가 없으면 안내 오류로 중단합니다.

컨텍스트는 **실제 전송한 공통/캐릭터 프롬프트·네거티브·모델·샘플러·스텝·CFG·스케줄러·CFG Rescale·Brownian·Variety 설정**을 전달합니다. Medium/Opus 제한으로 조정된 값도 반영합니다. **시드는 단계마다 따로 설정**합니다. 이전 시드는 기록용이며 다음 노드의 시드를 덮어쓰지 않습니다. I2I의 크기·강도·노이즈, 디테일러의 감지·매칭·마스크·크롭 설정, Anlas 보호·요청 지연·저장 설정도 각 노드에서 정합니다. Vibe/Precise 참조 이미지는 컨텍스트로 전달하지 않으므로 필요한 단계에 별도로 연결하세요.

컨텍스트 연결 시 가져오는 설정은 접힙니다. `컨텍스트 설정 사용`을 끄거나 연결을 빼면 보존돼 있던 직접 입력값을 다시 사용합니다. 연결된 별도 `characterPrompts`보다 컨텍스트의 캐릭터 목록이 우선합니다. I2I는 성공한 자기 요청의 설정으로 새 컨텍스트를 출력합니다.

**중간 I2I를 ComfyUI의 바이패스로 설정하면 이미지와 컨텍스트가 모두 T2I에서 디테일러로 바로 전달됩니다.** I2I 요청은 발생하지 않고 디테일러는 자기 시드를 사용합니다. 이미지 선과 컨텍스트 선을 모두 연결해야 합니다. `Mute`는 바이패스와 다르며 사용하지 마세요. 기존 IMAGE 출력은 0번 슬롯을 유지합니다. 기존 워크플로는 컨텍스트 연결 없이 사용할 수 있습니다.

**English:** Connect both `image` and `nai_context` from T2I to I2I, then both outputs from I2I to the experimental detailer. Character prompts only need a connection to T2I. Add the detector combine loader to the detailer and a tagger for multiple characters. Multiple characters in context automatically use matching to select their original prompts; a missing tagger produces an explanation instead of a generation request.

Context carries effective positive/negative common and character prompts, model, sampler, steps, CFG, scheduler, CFG Rescale, Brownian and Variety settings, after Medium/Opus normalization. **Every stage keeps its own seed.** Previous seeds are provenance only. Size, strength, noise, detection/matching/mask/crop settings, Anlas protection, request delay and saving remain local. Reference images are not carried; connect Vibe/Precise separately at the stage that needs them. Connected context overrides a separate character input. Turn off `use_context_settings` or disconnect context to restore manual values. I2I outputs a fresh context after its own successful request.

**ComfyUI bypass on I2I forwards both IMAGE and NAI_CONTEXT from T2I to the detailer and skips the I2I request.** Keep both wires connected; use Bypass, not Mute. The detailer retains its local seed. The existing IMAGE output remains at slot 0, and older workflows do not require context.

**日本語:** T2Iの`image`と`nai_context`をI2Iへ、I2Iの両出力を試験ディテーラーへ接続します。キャラクタープロンプトはT2Iに1回接続すれば十分です。ディテーラーには検出モデルのコンバインローダーを、複数キャラクターにはタガーも接続してください。複数キャラクターは自動照合で元のプロンプトを選び、タガーがなければ説明付きエラーで停止します。

コンテキストは実際に送信した共通/キャラクターの正負プロンプト、モデル、サンプラー、ステップ、CFG、スケジューラ、CFG Rescale、Brownian、Varietyを引き継ぎます。Medium/Opusで調整した値も反映します。**シードは各ノードで別々に設定**し、前段のシードは記録のみです。サイズ・強度・ノイズ、検出/照合/マスク/余白、Anlas保護、待機時間、保存は各ノードの設定を使います。参照画像は引き継がないため、Vibe/Preciseは必要な段階へ別に接続してください。コンテキストのキャラクターは別接続のキャラクター入力より優先します。設定の使用を無効にするか接続を外すと手動値へ戻ります。I2Iは成功した自分のリクエストから新しいコンテキストを出力します。

**I2IをComfyUIのBypassにすると画像とコンテキストの両方がT2Iからディテーラーへ直接渡り、I2Iリクエストは実行されません。** 両方の線を接続し、MuteではなくBypassを使ってください。ディテーラーのシードは独立です。既存のIMAGE出力はスロット0のままで、従来のワークフローにコンテキスト接続は不要です。

Live validation (2026-10-13): a five-character V5 Full workflow used different T2I, I2I and detailer seeds. The normal chain completed four correctly matched edits and skipped one low-score character; the bypass chain completed all five. Both retained original prompts and the effective sampling settings, with identical preview/live masks and zero changed pixels outside those masks. The actual ComfyUI frontend routed both outputs around bypassed I2I, omitted it from the execution graph, and preserved that behavior after save/reload. These are functional examples, not a guarantee of character-matching quality: the initial broad matching crop misidentified a blue-haired character after I2I. Tightening the matching crop resolved that assignment, while the red-haired character remained below the unchanged score threshold. Inspect the matching preview for each source image.
