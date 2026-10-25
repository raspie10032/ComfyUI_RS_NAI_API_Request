# In-node controls / 노드 내부 설정 / ノード内設定

The panel edits the node's original widgets, including their original callbacks. It never replaces server inputs or changes their order. Panel state is stored in node properties; the panel and reports do not serialize as API inputs. Values on other tabs still apply.

Each tab/card settings panel has a native **View: Panel → Classic widgets** button outside the panel. Click it again to return to the panel. The default is Panel; the selection is saved per node in the workflow (`properties.rsNaiInterfaceMode`) without adding API parameters or positional widget values. Classic mode collapses the DOM panel's layout space and restores the original widgets, including context inheritance, optional/advanced controls, and conditional WebP quality. Values, links, and the selected panel tab survive the switch.

**한국어:** 노드의 `보기: 패널 → 기존 위젯` 버튼으로 전환하고, 같은 버튼으로 돌아옵니다. 노드별 선택은 워크플로에 저장합니다. 값·연결·선택한 탭은 유지하며, 기존 모드에서는 원래의 상세 설정·컨텍스트 상속·WebP 품질 표시 규칙을 사용합니다.

**日本語:** ノードの `表示：パネル → 従来ウィジェット` ボタンで切り替え、同じボタンで戻れます。選択はノードごとにワークフローへ保存され、値・接続・選択タブを保持します。

| Nodes | Layout |
| --- | --- |
| T2I, I2I, inpaint, reference-inset generation | Generation / Prompts / Sampling / Save & results |
| Multi-character detailer | Correction / Regions & masks / Character matching / Generation / Save & results |
| Legacy face and SEGM detailers | Correction / Regions & masks / Character matching / Sampling / Save & results |
| Detection loader, tagger, Vibe / Precise Reference, inset preparation, asset saving | Compact single-page cards |

Inherited fields show their source. With selective context overrides, enable the checkbox beside a field to edit its local value. Connected scalar inputs display their source instead of a competing editor. Clearing the character-list override without connecting another list clears all inherited characters; the row explains that effect.

Connected widget inputs keep compact native socket rows above the panel, independent of the selected tab. Their ports and labels remain separate from the panel; disconnecting removes the unused row. Switching to Classic restores the original widget sizing.

**한국어:** 외부에서 연결한 프롬프트·수치 입력은 패널 위에 포트와 이름을 각각 표시합니다. 탭을 바꿔도 연결이 보이며, 연결을 해제하면 해당 행은 접힙니다. 기존 위젯 보기로 돌아가면 원래 크기를 복원합니다.

**日本語:** 外部接続したプロンプト・数値入力は、パネルの上にポートと名前を個別に表示します。タブを切り替えても接続が見え、切断するとその行を折りたたみます。従来表示では元のウィジェットサイズに戻ります。

For a locally selected Medium Effort model, steps, sampler, CFG Rescale and the common negative show the fixed NAI value. Stored manual values are preserved and become editable again when switching models. If the model comes from a connected input or context, its final value is resolved at execution. The last successful request report remains the authority for actual sent parameters.

WebP quality appears for lossy WebP, or when save format comes from a connected input. Status reports, request countdowns and loader download progress appear inside the panel. Original image previews and inset-dimension previews stay native.

**한국어:** 생성 노드는 생성·프롬프트·샘플링·저장/결과로 나눕니다. 항목이 적은 노드는 한 장으로 표시합니다. 컨텍스트를 쓰면 가져오는 값의 출처를 표시하고, ‘선택 항목만 변경’에서 체크한 항목만 직접 입력합니다. 연결된 항목은 연결 쪽에서 수정합니다. Medium의 고정값은 안내로 보여주며 이전 입력값은 보존합니다. 실제로 전송한 설정은 실행 후 ‘마지막으로 성공한 NAI 요청’에서 확인하세요. 다른 탭에 있는 설정도 적용되고 기존 워크플로 값·입력 순서·연결은 유지합니다.

**日本語:** 生成ノードは生成・プロンプト・サンプリング・保存/結果に分け、項目の少ないノードは一枚にまとめます。継承値の取得元を表示し、「選択項目のみ変更」でチェックした値を編集できます。接続値は接続元で変更します。Mediumの固定値を案内し、手動値は保持します。実際に送信した値は実行後の「最後に成功したNAIリクエスト」で確認できます。他のタブの設定も適用され、既存ワークフローの値・入力順・接続を維持します。

## Validation

Run the existing JS regression scripts with `node tests/test_*.mjs` individually, or a shell loop. Browser checks require Playwright and a Python environment with this package's runtime dependencies:

```bash
RS_NAI_TEST_PYTHON=/path/to/python node tests/browser/detailer_panel.mjs
RS_NAI_TEST_PYTHON=/path/to/python node tests/browser/node_panels.mjs
```

`RS_NAI_CHROMIUM` optionally selects an existing Chromium executable. `RS_NAI_PANELS_SCREENSHOTS` saves the twelve Korean panel screenshots to an existing directory.

The browser harness uses actual Python input schemas and production JS extensions in a small simulated ComfyUI host. Installed detector discovery is replaced with an empty inventory; the real model catalog is retained. It checks all 12 additional node types in three languages and both extension loading orders, including values, order, configure/reload, context controls, connected inputs, Medium restrictions, progress and preview preservation. Browser requests are limited to its local fixture server. These checks do not establish compatibility with every ComfyUI frontend version or execute real models or NovelAI requests.

Both suites also check repeated Panel/Classic switching, native advanced/optional controls, property restoration, edits in Classic reflected in Panel, and unchanged widget values/order and links.
