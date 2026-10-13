# NAI Multi-Character Detailer / 멀티 캐릭터 디테일러 / マルチキャラクターディテーラー

Available in **2.8.0**, under `RS_NovelAI_API`. Execution detects regions, matches original character prompts and corrects eligible regions with NovelAI. **There is no preview-only switch.** Outputs: corrected IMAGE, mask visualization IMAGE and matching report STRING.

**Quality cannot be guaranteed as the number of processed regions increases.**

## English

1. Install ComfyUI-Impact-Pack and ComfyUI-Impact-Subpack for detectors, plus the optional tagger dependencies described in the repository README for character matching. Restart ComfyUI and refresh the page after updating.
2. Connect **NAI Detection Combine Loader → detectors** on **NAI Multi-Character Detailer**. The default face SEGM model downloads on first execution if missing; filename, percentage and received size appear on the loader. Selection alone does not download it.
3. Connect both `image` and `nai_context` from **T2I → I2I → detailer**. Connect character prompts to T2I once and a tagger to the detailer. Multiple characters in context require a tagger: it selects the original prompt and never adds inferred tags to the request.
4. Adjust strength, seed, maximum regions and Anlas protection on the detailer. Each stage keeps its own seed. Execute to correct, then inspect the resulting mask and report for edited/skipped regions. Ambiguous character matches are skipped.

**Context ON/OFF selects inherited/manual settings. Both paths correct the image.** Context carries effective common/character positive and negative prompts, model, sampler, steps, CFG, scheduler, CFG Rescale, Brownian and Variety settings, including Medium/Opus normalization. Size, strength, noise, detection/matching/masks/crops, Anlas protection, timers and saving remain local. Vibe/Precise images require separate connections.

**Bypass I2I** to forward both image and context directly from T2I. Keep both wires connected. Bypass omits the I2I request; Mute is different. IMAGE remains output slot 0 for older workflows.

Up to **22 character prompts / 64 regions**, default **5 regions**. These are configuration limits, not an accuracy guarantee. When changing five characters to three, reduce `character_count` and update the common prompt (`5girls` → `3girls`, `five women` → `three women`). Hidden slots retain editable text but are excluded from requests/context. `max_regions` controls correction regions, not the generated number of people.

### Detector selection

| Selection | Used for correction |
|---|---|
| SEGM selected | Native SEGM mask; BBOX/SAM download, loading and inference are skipped. |
| SEGM OFF, BBOX selected, SAM OFF | BBOX rectangle |
| SEGM OFF, BBOX + SAM selected | SAM mask inside detected BBOX |
| SEGM and BBOX OFF | Explained error; SAM or auxiliary eye detection alone cannot define primary regions. |

OFF models never download or load. The three selectors stay visible and retain their values. To correct eyes as the main target, select an eye model in the main SEGM/BBOX selector; the optional eye BBOX is auxiliary.

| Target | Catalog SEGM | Catalog BBOX |
|---|---|---|
| Face | Anzhc Face v2 / v4 | YOLOv8 n / n_v2 / s / m |
| Eye | Anzhc Eyes HD | eye YOLOv8 n / s |
| Clothing | DeepFashion2 | — |
| Hand | — | hand YOLOv8 n / s |
| Exposed skin | skin YOLOv8 | — |
| Whole person | person YOLOv8 n / s / m | — |
| Head / hair | Anzhc HeadHair | — |

Additional weights appear from registered folders, including subfolders: normally `models/ultralytics/segm`, `models/ultralytics/bbox`, `models/sams`. Refresh the model list/page. SAM uses locally installed ViT weights. Skin detection is not whole-person detection. The default face model is about 6.6 MiB, pinned and SHA-256 verified; interrupted downloads discard temporary files, and existing weights are reused. Sources: [Anzhc](https://huggingface.co/Anzhc/Anzhcs_YOLOs), [Bingsu](https://huggingface.co/Bingsu/adetailer), [eye detectors](https://huggingface.co/killjoyelite/anime-eye-yolov8).

Defaults: fill enclosed holes and small notches, dilate by **8 original-image pixels**, then feather inside the mask by **8 pixels**. Repair limits avoid blindly filling large occluded regions. Advanced controls change each operation independently. Folding them does not disable their settings.

### Existing test workflows and examples

On workflow load, test node IDs migrate to the stable names. The old `preview_only` widget and links into that removed input are removed; later settings and remaining connections are preserved. Custom titles stay intact. Old API graphs retain deprecated compatibility aliases, but their preview flag no longer suppresses correction.

**Loading does not execute. Running a migrated workflow now corrects the image**, subject to saved Anlas protection and matching checks. Strict protection allows only validated Focused Inpainting crops and blocks other potentially paid edits. Review it before queuing. The original Face Detailer nodes retain their existing behavior.

- [T2I → I2I → detailer](../examples/multi-character-detailer/NAI_context_normal.json)
- [T2I → bypassed I2I → detailer](../examples/multi-character-detailer/NAI_context_I2I_bypass.json)

Examples have **Anlas protection enabled**: I2I stops at the guard until allowed on that node; the detailer permits only validated Focused Inpainting crops under strict protection. They are not detection-only previews; upstream T2I can execute. Five character prompts and independent fixed seeds are included.

## 한국어

**실행하면 감지 → 캐릭터 매칭 → NAI 보정까지 진행합니다. 미리보기만 실행은 없습니다.** 결과 이미지·마스크·매칭 보고서로 결과와 건너뛴 사유를 확인하세요. **처리수가 많을수록 품질을 보장하지 못합니다.**

1. 감지에는 Impact Pack/Subpack, 여러 캐릭터 매칭에는 태거 의존성이 필요합니다.
2. **NAI 감지 모델 콤바인 로더 → NAI 멀티 캐릭터 디테일러**로 연결하세요. 기본 얼굴 SEGM은 없으면 최초 실행 시 다운로드하며 파일명·퍼센트·받은 용량을 표시합니다.
3. **T2I 이미지 + NAI 컨텍스트 → I2I → 디테일러**를 모두 연결하세요. 캐릭터는 T2I에 한 번만 연결하고, 디테일러에는 태거를 연결합니다.
4. 시드·강도·처리 개수·Anlas 보호는 각 노드에서 설정합니다. 컨텍스트를 꺼도 직접 입력값으로 보정합니다. Vibe/Precise 이미지는 필요한 단계에 따로 연결합니다.
5. I2I를 **바이패스**하면 이미지와 컨텍스트가 T2I에서 직접 전달됩니다. 두 선을 모두 연결하세요. Mute는 다릅니다.

SEGM 선택 시 BBOX·SAM은 다운로드·로드·추론을 건너뜁니다. SEGM OFF에서는 BBOX 단독 또는 BBOX+SAM을 사용합니다. OFF 모델은 불러오지 않습니다. 얼굴·눈·옷·손·피부·머리카락·인물 전체 모델을 선택하거나 기존 모델 폴더에 파일을 추가하고 목록을 새로고침하세요. 눈을 주 대상으로 보정할 때는 주 SEGM/BBOX 목록에서 눈 모델을 선택합니다.

홀·요철 채우기 → 8픽셀 확장 → 경계 부드러움이 기본입니다. 상세 설정을 접어도 값은 적용됩니다. 캐릭터 최대 22명·영역 최대 64개, 기본 5개입니다. 인원을 줄이면 캐릭터 개수와 **공통 프롬프트의 인원 표현도 함께** 바꾸세요. 숨긴 슬롯은 저장만 되고 요청에서는 제외됩니다.

시험 워크플로를 열면 이름과 삭제된 미리보기 입력을 이전합니다. 시드·Anlas 보호 등 뒤의 값과 나머지 연결을 유지합니다. **불러오기만으로 실행되지는 않지만, 실행하면 실제 보정합니다.** 예제는 Anlas 보호가 켜져 있으므로 I2I/보정 전에 해당 노드에서 확인하세요. 기존 페이스 디테일러 동작은 유지합니다.

## 日本語

**実行すると検出 → キャラクター照合 → NAI補正を行います。「プレビューのみ」はありません。** 結果画像・マスク・照合レポートを出力します。**処理領域数が増えるほど品質は保証できません。**

1. 検出にはImpact Pack/Subpack、複数キャラクターの照合にはタガーの依存関係が必要です。
2. **NAI検出モデル結合ローダー → NAIマルチキャラクターディテーラー**へ接続します。既定の顔SEGMがなければ初回実行でダウンロードし、ファイル名・進捗率・受信量を表示します。
3. **T2I画像 + NAIコンテキスト → I2I → ディテーラー**を接続します。キャラクターはT2Iへ1回、タガーはディテーラーへ接続します。
4. シード・強度・処理数・Anlas保護は各ノードで設定します。コンテキストOFFでも手動値で補正します。Vibe/Precise画像は必要な段階に別途接続します。
5. I2Iを**Bypass**にすると画像とコンテキストがT2Iから直接渡ります。両方の接続が必要です。Muteは異なる動作です。

SEGM選択時はBBOX/SAMのダウンロード・ロード・推論を省略します。SEGM OFFではBBOX単独かBBOX+SAMを使います。OFFモデルはロードしません。顔・目・服・手・肌・髪・人物全体を選べます。追加モデルは既存フォルダーに置き、一覧を更新してください。目を主対象にする場合は主SEGM/BBOX欄で目モデルを選びます。

既定は穴・凹み補修 → 8ピクセル拡張 → 境界のぼかしです。折りたたんだ設定も有効です。最大22キャラクター・64領域、既定5領域。人数を減らすときはキャラクター数と**共通プロンプトの人数表現も**変更します。非表示スロットは保存されますがリクエストには含みません。

試験版の名前と削除されたプレビュー入力は読み込み時に移行し、シード・Anlas保護などの値と残りの接続を維持します。**読み込みだけでは実行しませんが、実行時は実際に補正します。** サンプルはAnlas保護が有効です。I2I・補正の前に該当ノードで確認してください。従来のFace Detailerは既存動作を維持します。
