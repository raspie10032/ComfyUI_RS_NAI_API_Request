# Image autosave and NovelAI metadata / 이미지 저장과 NAI 정보 / 画像保存とNAI情報

[English](#english) · [한국어](#한국어) · [日本語](#日本語)

## English

### Save from the generation node

1. Choose `save_format` on the generation, img2img, inpaint, face detailer or reference inset generation node.
2. `PNG` is the default for existing workflows. `WebP lossless` preserves exact pixels. `WebP lossy` enables `webp_quality` (1–100, default 90).
3. Run as usual. The result goes into the existing dated `NAI_autosave` folder (`face` / `inset` subfolders where applicable). The inset node saves both its full canvas and crop.

NAI prompts, character positions, original response information and effective request settings are stored in PNG text or WebP EXIF. Source/reference image bytes and credentials are not added. This does **not** embed a ComfyUI workflow; connect a standard Save Image node if workflow sharing is needed. Saving locally adds no Anlas charge; generation retains its normal cost.

### Read and reuse an image

1. Add **NAI Load Image** (`RS_NovelAI_API/Image`). Select or upload an image as with Load Image. A preview and metadata appear immediately, without queueing generation.
2. Read or copy the prompt and negative prompt. Expand each character for its text and positions, and **Generation settings** for other parameters.
3. Choose the target generation, img2img or inpaint node. Use **Refresh targets** if the node was just added, then **Apply settings**. The result lists applied and skipped fields.
4. An unshared **Character Prompt Select** node is updated, or created and connected if needed. Values supplied by connected inputs are not overwritten; shared or custom character connections are left for manual editing. Seed reuse sets `control_after_generate` to `fixed`.
5. Connect IMAGE/MASK normally when needed. Reading metadata requires no separate metadata output or wire. No generation is queued by the Apply button, and the target's Anlas protection stays as set.

PNG text, WebP EXIF UserComment and NAI compressed alpha metadata (`stealth_pngcomp`) are read locally. An image with missing/damaged metadata still loads when its pixel data is readable. This loader does not verify a NovelAI cryptographic signature.

### Restoration limits

- Missing settings are reported, not guessed. NAI files often identify models by a hash; an unrecognized hash requires manual model selection. New autosaves record the actual request model.
- Character application requires explicit positions on the node's 0.1 coordinate grid, one position per character, and a supported character count. NAI automatic placement, multiple positions and finer coordinates can be inspected/copied but are not silently rounded or replaced.
- Reference images, source images and masks are not reconstructed from generation parameters. Reconnect the required images. Model-specific fixed settings still apply (for example Medium's sampler/steps/negative prompt).
- With `NAI context` connected, the multi-character detailer autosaves that context as the whole-image metadata: common prompts, all characters and their coordinates, model and sampling settings. NAI Load Image can display/apply it again. The context seed and dimensions describe the source generation; actual face requests stay in the separate correction history. Turning off **Use context settings** changes correction inputs only; the connected source context is still preserved. Without a context (including older files), the loader shows correction history only and never substitutes the last crop prompt. This does not reconstruct base metadata for existing files or add a NAI_CONTEXT output to the loader.
- Inset output records full-canvas coordinates and the crop rectangle. Automatic application is disabled because reconstructing that request requires the reference canvas; text can still be copied.
- Image hosts and editors may strip EXIF or PNG text. Keep the original file. A small file size or `.webp` extension does not prove metadata was retained.

## 한국어

### 자동 저장

1. 생성·img2img·인페인트·페이스 디테일러·인셋 생성 노드의 **자동 저장 형식**을 고릅니다.
2. 기존과 같은 `PNG`, 픽셀이 그대로 유지되는 `WebP lossless`, 용량을 줄이는 `WebP lossy` 중 선택합니다. 손실 압축일 때만 **WebP 품질**(1–100, 기본 90)이 보입니다.
3. 평소처럼 실행하면 기존 날짜별 `NAI_autosave` 폴더에 저장됩니다. 디테일러는 `face`, 인셋은 `inset` 하위 폴더를 사용하며 인셋은 전체 캔버스와 잘라낸 결과를 모두 저장합니다.

NAI 프롬프트·캐릭터 좌표·서버 응답 정보와 실제 요청 설정을 보존합니다. **ComfyUI 워크플로는 넣지 않습니다.** 워크플로가 필요하면 기존 이미지 저장 노드를 연결하면 됩니다. 참조 이미지 원본·입력 이미지·인증 정보도 넣지 않습니다. 파일 저장 자체는 무료이며 생성 비용은 기존 규칙을 따릅니다.

### 불러와서 적용하기

1. **NAI 이미지 불러오기** 노드에서 파일을 선택하거나 업로드합니다. 실행 버튼을 누르지 않아도 미리보기와 생성 정보가 바로 표시됩니다.
2. 공통 프롬프트·네거티브를 확인하거나 복사합니다. 캐릭터 항목을 펼치면 개별 프롬프트·네거티브·좌표가 보이고, **생성 설정**을 펼치면 시드 등의 값을 볼 수 있습니다.
3. **적용할 노드 선택 → 설정 적용**을 누릅니다. 방금 만든 대상이 안 보이면 **대상 목록 새로고침**을 누르세요. 적용된 항목과 적용하지 못한 항목이 표시됩니다.
4. 연결된 캐릭터 노드가 다른 노드와 공유되지 않으면 값을 채웁니다. 캐릭터 노드가 없으면 새로 만들어 연결합니다. 외부 입력선으로 값이 공급되거나 다른 노드와 공유 중이면 해당 항목은 건너뜁니다. 시드는 고정 모드로 적용됩니다.
5. 이미지는 일반 로드 이미지처럼 IMAGE/MASK 출력을 연결해 쓰면 됩니다. 메타데이터용 선은 필요 없습니다. 적용 버튼은 생성을 실행하지 않으며, 기존 과금 보호 설정도 유지합니다.

### 복원이 제한되는 경우

- 알 수 없는 모델 해시나 빠진 설정은 추측하지 않고 표시합니다. 모델은 직접 선택하세요. 이번 버전으로 자동 저장한 파일에는 실제 요청 모델도 기록됩니다.
- 캐릭터 자동 배치·여러 위치·0.1 단위보다 세밀한 좌표는 현재 캐릭터 노드로 정확히 옮길 수 없어 자동 적용하지 않습니다. 표시된 값을 확인하고 텍스트를 복사할 수 있습니다.
- 참조 이미지·img2img 입력 이미지·마스크는 다시 연결해야 합니다. Medium 모델의 고정 스텝·샘플러·네거티브 규칙도 그대로 적용됩니다.
- 멀티 캐릭터 디테일러에 **NAI 컨텍스트**를 연결하면 공통 프롬프트·모든 캐릭터와 좌표·모델·샘플링 설정을 전체 그림 메타데이터로 자동 저장합니다. NAI 이미지 불러오기에서 다시 확인·적용할 수 있습니다. 시드·해상도는 원본 컨텍스트 기준이며, 실제 얼굴 보정 요청은 별도 이력에 남습니다. **컨텍스트 설정 사용**을 꺼도 연결된 원본 컨텍스트는 저장됩니다. 컨텍스트가 없거나 이전에 저장한 결과는 보정 이력만 보여주며, 마지막 얼굴 프롬프트로 원본 정보를 대신하지 않습니다. 기존 파일의 원본 정보를 소급 복원하거나 로더에 NAI_CONTEXT 출력을 추가하는 기능은 아닙니다.
- 인셋 결과의 정보는 참조 이미지를 포함한 전체 캔버스 기준입니다. 캔버스를 다시 준비해야 하므로 자동 적용은 하지 않고 확인·복사를 제공합니다.
- 메타데이터가 없거나 손상돼도 이미지 자체를 읽을 수 있으면 불러옵니다. 로더는 NAI 서명 진위를 검증하지 않습니다. 이미지 사이트나 편집기가 정보를 제거할 수 있으니 원본 파일을 보관하세요.

## 日本語

### 自動保存

1. 生成・img2img・インペイント・顔補正・インセット生成ノードで**自動保存形式**を選びます。
2. 従来の `PNG`、画素を保持する `WebP lossless`、容量を抑える `WebP lossy` を選択できます。非可逆圧縮のときだけ **WebP品質**（1–100、初期値90）が表示されます。
3. 通常どおり実行すると、既存の日付別 `NAI_autosave` フォルダーに保存されます。顔補正は `face`、インセットは `inset` サブフォルダーを使用し、インセットはキャンバス全体と切り抜き結果の両方を保存します。

NAIのプロンプト・キャラクター座標・応答情報と実際のリクエスト設定を保持します。**ComfyUIワークフローは埋め込みません。** 必要な場合は通常のSave Imageノードを使用してください。参照画像・入力画像のデータや認証情報も追加しません。保存自体にAnlasは不要ですが、生成には従来の料金条件が適用されます。

### 読み込んで適用

1. **NAI画像を読み込む**ノードで画像を選択・アップロードすると、実行せずにプレビューと生成情報が表示されます。
2. 共通プロンプト・ネガティブを確認・コピーできます。各キャラクターを開くと個別のテキストと座標、**生成設定**を開くとシードなどが表示されます。
3. 適用先の生成・img2img・インペイントノードを選び、**設定を適用**を押します。新しいノードが見つからなければ**適用先を更新**してください。適用済み・適用できなかった項目が表示されます。
4. 共有されていない既存のキャラクターノードを更新し、未接続なら作成して接続します。接続入力からの値や共有中のキャラクターは上書きしません。シードは固定モードで適用します。
5. 画像は通常どおりIMAGE/MASK出力で接続できます。メタデータ用の配線は不要です。適用ボタンで生成は実行されず、Anlas保護設定も維持されます。

### 復元の制限

- 不足する設定や未知のモデルハッシュは推測しません。モデルは手動選択してください。今回の自動保存には実際の要求モデルも記録されます。
- 自動配置・複数位置・0.1刻みより細かい座標は現在のノードで正確に再現できないため、自動適用せず確認・コピーを提供します。
- 参照画像・元画像・マスクは接続し直してください。Mediumなどの固定設定も引き続き適用されます。
- マルチキャラクター補正に **NAIコンテキスト**を接続すると、共通プロンプト・全キャラクターと座標・モデル・サンプリング設定を画像全体のメタデータとして自動保存します。NAI画像ローダーで確認・適用できます。シードとサイズは元コンテキストの値で、実際の顔補正は別の履歴に残ります。**コンテキスト設定を使用**をオフにしても接続された元コンテキストは保存されます。未接続や過去の結果では補正履歴だけを表示し、最後の顔の情報を全体の設定には使いません。既存ファイルの元情報を遡って復元したり、ローダーにNAI_CONTEXT出力を追加したりする機能ではありません。
- インセットの情報は参照を含むキャンバス全体の座標です。参照キャンバスの再準備が必要なため、自動適用には対応していません。
- 画像の画素が読めれば、メタデータがなくても読み込めます。NAIの署名検証は行いません。画像サイトや編集ソフトで情報が消える場合があるため、元ファイルを保管してください。
