# RS Camera Control / 공통 카메라 시점

Development candidate, validated on 2026-10-25; not yet a published release.

This node adds view/framing captions to either an RS finalized character pipe or an NAI context. Optional layout sync scales/rotates character regions or projects their common flat plane for azimuth/elevation; it does not move a 3D camera or enforce generated anatomy. Negative prompts, LoRAs and model settings remain attached to the context.

## Connect

`Finalize Character Pipe or NAI context → RS Camera Control → character_pipe or nai_context`

Connect the existing scene to `base_prompt` if the finalized character pipe does not contain a scene. The node raises a readable error instead of silently replacing that missing scene with camera tags. A supplied `base_prompt` explicitly replaces the context's scene. With no context, connect `prompt` to the generator's common prompt; the context output is empty. The `camera_prompt` STRING contains just the added camera captions.

Default `scene_and_characters` adds the view to both common and character captions. This matters for regional Anima generation, where a common-only view can be suppressed by character conditions. `scene_only` leaves character captions untouched. Text regions do not receive camera captions. By default (`layout_sync=fixed`) position/mask coordinates remain fixed. Enable `distance_and_roll` to zoom and rotate every character region together around the canvas center. Set the downstream generator to inherit the connected context.

The connected context determines ComfyUI or NovelAI prompt syntax. Without context, select `prompt_syntax`. Select `plain` for a text path that does not parse numerical prompt weights; it selects dominant tags rather than emitting numerical syntax. Both packages ship the same node ID and identical implementation; installing both registers one editor.

## Controls and captions

| Control | Range / default | Meaning |
| --- | --- | --- |
| azimuth | −180…180° / 0 | 0 front, −90 left-side caption, +90 right-side caption, ±180 rear |
| elevation | −90…90° / 0 | Positive: from above; negative: from below |
| distance | 0…1 / 0.5 | 0 extreme close-up, 0.25 close-up, 0.5 medium shot, 0.75 full body, 1 wide shot |
| roll | −45…45° / 0 | Magnitude adds `dutch angle`; the text cannot guarantee a tilt direction |
| strength | 0…5 / 1.2 | Caption weight multiplier; start around 0.8–1.4 |
| enabled | true | OFF passes through without adding camera captions |

Drag the in-node diagram to adjust horizontal/vertical view. Wheel adjusts distance; Shift+wheel adjusts tilt. Arrow keys adjust the view. Preset buttons set front/side/above/below or near/far; Reset restores numeric defaults and enables the node. Connected numerical inputs are not overwritten by these gestures; their effective values resolve at execution. The diagram is a caption guide. Small graphs show normalized weights; the separate numerical strength multiplies them. The text below shows weights, then the server's exact camera caption after execution.

Neighboring tags use `s(t) = (1 − cos(πt)) / 2`, with complementary weights `1−s` and `s`. Horizontal captions are multiplied by `0.85 × cos(elevation)²`, vertical by `0.8`, distance by `1`, and tilt by `0.6 × |roll| / 45`, all times strength. Turning strength to 0 or disabling the node adds no camera captions. ±180 have equal rear captions; at ±90 elevation horizontal captions vanish. String formatting rounds to two decimals and omits weights below 0.005, so the smooth mathematical curves can still have small textual quantization steps.

## Validation and limitations

Python and JavaScript calculations matched at 301 mixed coordinates. Tests cover knot continuity, distance-weight conservation, invalid numbers, disabled/zero behavior, both syntax forms, immutable character/context fields, plain mode, interaction/serialization, five editor locales, duplicate-editor suppression, and real local/NAI context round trips.

Final generation comparison used 1216×832, the same scene/characters/seed 26102504 and strength 1.2. Anima used RSCV5 0.9, Euler Ancestral / SGM Uniform / 30 steps / CFG 4. NovelAI used V5 Full / 23 steps / CFG scale 6 / native noise schedule with `limit_opus_free=True`. Seven Anima and four NAI final images were generated successfully, following 16 exploratory images. The request graphs and histories are kept in the local validation artifact directory; they are not a statistically representative benchmark.

Both models visibly changed toward side/above and near/far compositions. Anima's rear example retained a side-looking face; its wide example assigned different apparent sizes to the two characters and changed the background. Side captions can turn each person independently rather than orbiting a shared camera. These are observed limits, not failures to dispatch the node. Results do not prove precise degrees, tilt direction, same-scale people, or support/quality across every model family. The numerical weights describe caption influence, not measured image angles or model adherence. No camera model, ControlNet or new inference pass is loaded.

Reference: [Anima camera-tag helper](https://arca.live/b/aiart/179423561) and the inspected `ComfyUI-KR-Camera-Control` package. That package credits `ComfyUI_bsk_UI` / 灰暗x for its camera prompt algorithm and interaction design. The RS/NAI implementation uses its own continuous formulas, context integration and region transforms. Reference default weights and discontinuities were compared; the inspected code/archive is not distributed here. See [camera reference attribution](../THIRD_PARTY_NOTICES.md#camera-control-references) for the inspected package's license and the reference scope.


## 원본에서 접목한 기능 / Reference-to-feature mapping

참고 원문은 [아카라이브 카메라 제어 소개](https://arca.live/b/aiart/179423561)이며, 실제 검토한 패키지는 `ComfyUI-KR-Camera-Control`입니다. 해당 패키지는 카메라 프롬프트 알고리즘과 조작 설계의 출처를 `ComfyUI_bsk_UI` / 灰暗x로 표기합니다. 아래 표는 참고한 아이디어가 **RS 카메라 시점·NAI 카메라 시점에 어떻게 접목됐는지**를 설명합니다.

| 원본에서 참고한 기능 | 두 확장에 접목한 방식 |
| --- | --- |
| 좌우 방향을 정면·측면·후면 태그로 바꾸기 | 좌우 시점 각도를 받아 공통 장면과 캐릭터 프롬프트에 방향 태그를 가중치와 함께 추가합니다. |
| 높이에 따라 위·아래에서 보는 태그 만들기 | 상하 시점 각도에서 위·아래 시점 태그를 연속적으로 섞고, 극단 각도에는 내려다보기·올려다보기 태그를 사용합니다. |
| 극근접·근접·중간·전신·원경의 거리 구분 | 같은 다섯 구도 어휘를 0~1 거리 조절에 연결하고, 인접한 구도 태그를 부드럽게 섞습니다. |
| 롤을 `dutch angle` 태그로 표현하기 | 기울기 크기를 태그 강도로 변환합니다. 선택형 영역 연동에서는 실제 캐릭터 영역도 함께 회전합니다. |
| 노드 안에서 드래그·휠로 조작하고 프롬프트 확인하기 | 드래그로 시점, 휠로 거리, Shift+휠로 기울기를 바꾸며 계산된 태그와 실행된 프롬프트를 표시합니다. |
| 가중치 유무 선택·프리셋·랜덤 구도 | 가중치/일반 태그 출력, 기본 시점 버튼, 카메라 전용 시드와 balanced/full 랜덤 범위로 구성했습니다. |

**원본 수치를 그대로 이식한 것은 아닙니다.** 원본의 축별 기본 가중치 5, 데드존과 구간 전환을 비교한 뒤, 이 구현에서는 기본 강도 1.2와 별도의 연속 보간식을 사용했습니다. 원본의 사용자 프리셋 편집 체계·렌즈/심도/움직임 추가 설정·미리보기 전용 3D 카메라 조작까지 동일하게 제공하지는 않습니다.

**이번 확장에 맞춰 추가한 기능**은 공통 캐릭터 파이프·NAI 컨텍스트 입출력, ComfyUI/NovelAI 가중치 문법 전환, 공통/캐릭터 태그 적용 범위, 기존 프롬프트·LoRA·영역 자료 보존, 좌표·박스·실루엣·부위 마스크의 거리/회전/평면 원근 연동과 변환 미리보기입니다. NAI 실제 요청에는 태그와 변환된 캐릭터 중심 좌표를 보내고, 실루엣은 로컬 왕복용 컨텍스트에 보관합니다. 이 부분은 원본에 있던 기능으로 소개하지 않습니다.

The table in [third-party notices](../THIRD_PARTY_NOTICES.md#features-incorporated-from-the-camera-reference) provides the same mapping in English. Source attribution and the inspected package's license remain recorded there. The feature is a caption and flat-plane layout guide; it does not reconstruct 3D anatomy or guarantee a pose.

## 한국어 사용법

**최종 캐릭터 파이프 또는 NAI 컨텍스트 → RS 카메라 시점 → 생성 노드**로 연결합니다. 생성 노드에서 컨텍스트 상속을 켜세요. 공통 장면이 없는 파이프는 `base_prompt`에 장면 문장을 연결해야 합니다. 컨텍스트 없이 쓸 때는 `prompt` 출력만 공통 프롬프트에 연결합니다.

기본은 **공통 장면＋캐릭터**에 적용합니다. Anima는 공통 태그만 넣으면 시점이 약하게 반영돼 기본 적용 범위를 넓혔습니다. 글자 영역·좌표·마스크·LoRA·네거티브는 유지합니다. 양쪽 패키지에서 같은 노드를 쓰며 NAI 가중치 문법도 자동으로 맞춥니다.

**드래그=시점, 휠=거리, Shift+휠=기울기**입니다. 시작 강도는 1.2이며 0.8~1.4부터 조정하세요. 도식과 각도는 태그 계산을 위한 안내이며 실제 이미지의 카메라 각도 측정값은 아닙니다. 연결된 수치 입력은 마우스로 덮어쓰지 않습니다.

실제 생성에서 측면·위·거리 변화는 확인됐지만 뒤돌기·원경의 두 인물 크기는 완벽하지 않았습니다. 이 노드는 **시점 태그 유도 기능**이며, 선택형 배치 연동으로 마스크도 변형합니다. 생성된 인체를 3D 카메라처럼 강제하지는 않습니다. 두 노드를 연달아 연결하거나 이미 시점 태그가 있는 컨텍스트에 넣으면 태그가 더해지므로, 상반되는 기존 시점 문장은 직접 정리하세요.


## Random composition / 랜덤 구도

`random_mode` defaults to `off`, preserving existing workflows. Choose `balanced` for azimuth −90…90°, elevation −35…35°, distance 0.25…0.85 and roll −10…10°. `full` samples the entire four-axis range. Strength, characters, masks, placements and image seed stay under their existing controls. Randomizing a view cannot guarantee correct poses or avoid cropping, and geometry changes only when layout sync is enabled.

`random_seed` is an independent 32-bit integer. With the built-in seed control set to **fixed**, the same camera seed and mode reproduce the same captions. Select **randomize** to change the camera seed after each queued generation. API clients must send a different camera seed themselves; identical requests may use ComfyUI's cache. A single execution draws one view; a downstream image batch shares that view.

The **Random** button draws a new camera seed and uses balanced mode (or keeps full mode if selected). The diagram previews the seeded view, and the server returns the actual axes alongside its captions after execution. Manual sliders remain stored but are overridden while random mode is on. Dragging, wheel, arrow keys or a preset return to manual mode; connected controls remain authoritative. New optional controls are appended so existing widget positions keep their meaning.

**랜덤 구도**에서 `balanced`는 일반 범위, `full`은 전체 범위입니다. 카메라 시드 옆의 생성 후 동작을 **randomize**로 두면 매번 새로운 구도, **fixed**로 두면 같은 구도를 사용합니다. 이미지 생성 시드는 별개입니다. **랜덤 구도 버튼**으로 바로 다시 뽑을 수도 있습니다. 드래그·휠·화살표·프리셋은 수동 모드로 돌아갑니다. 연결 입력은 덮어쓰지 않습니다. 한 번 실행한 출력으로 이미지 배치를 만들면 배치 전체가 같은 구도 태그를 받습니다. 기본값은 마스크 고정입니다. 거리·기울기도 함께 바꾸려면 아래의 마스크 배치 연동을 켜세요. 좌우·상하 시점에는 필요에 따라 위치를 별도로 조절하세요.


## Camera and mask layout sync

Set `layout_sync=distance_and_roll` and `canvas_aspect=width/height` (e.g. 1216/832 = 1.461538). Put Camera after the final Position/Mask pipe and before the sampler. Distance 0.5 is original size; 0 zooms to 2× and 1 scales to 0.5×. Positive roll rotates clockwise in image coordinates. Character points, bounding boxes, silhouettes and body-part masks share the transform; text boxes stay fixed. Rotated boxes become their axis-aligned bounds. Portrait/landscape aspect is included so rotation does not stretch the shapes.

The editor displays thumbnails of the last executed input regions and updates their transformed preview when distance or roll changes. Run once to populate it; run again after editing upstream masks. This thumbnail is approximate; sampling uses the original-resolution transformed binary masks. Upstream source masks remain untouched. Only the visible canvas is retained in the output; a wholly invisible character raises an actionable error rather than silently becoming global conditioning. OFF or strength 0 passes through unchanged. Existing workflows default to fixed layout.

This is a 2D framing tool. In distance_and_roll mode, azimuth/elevation change captions only. Select perspective for flat-plane projection; neither mode reconstructs subject depth or occlusion. Generated framing, exact tilt and pose remain model-dependent. Random views use the same seeded distance/roll for both captions and geometry; extreme random views can crop a character entirely and require a less extreme view. Chaining two sync nodes deliberately compounds their transforms. NAI stores the local transformed masks in its return snapshot and uses the updated character centers; the NAI API itself does not consume these local masks. A local snapshot is limited to 10 characters for this conversion.

### 한국어

`마스크 배치 연동=distance_and_roll`, `생성 화면 비율=너비÷높이`로 설정합니다. 최종 포지션/마스크 파이프 뒤에 카메라를 놓으세요. 거리 0.5는 원래 크기, 0은 2배, 1은 0.5배이며 양수 기울기는 화면에서 시계 방향입니다. 캐릭터 좌표·상자·전체 마스크·부위 마스크가 함께 변환되고 글자 상자는 유지됩니다. 회전한 박스는 외접 사각형입니다.

한 번 실행하면 카메라 패널에 입력 영역이 표시되고 거리·기울기 조절에 따라 미리보기가 바뀝니다. 상위 노드 마스크를 수정했다면 다시 실행하세요. 미리보기는 축소본이고 실제 연산에는 원래 해상도의 마스크를 씁니다. 캔버스 밖만 잘라 적용하며 원본 파이프는 보존합니다. 캐릭터 전체가 밖으로 나가면 복구 안내 오류를 표시합니다. 좌우·상하 시점으로 입체 마스크를 만들어내는 기능은 아닙니다. NAI에서는 바뀐 중심 좌표를 사용하고 로컬 마스크는 왕복 복원을 위해 보관합니다.


## Flat-plane mask perspective / 마스크 평면 원근

Choose `layout_sync=perspective` to apply azimuth/elevation as a pinhole projection to the entire mask plane. Distance and roll are included. Every character silhouette, body-part mask, box and point uses the same projection; text stays fixed. A positive azimuth puts the right side nearer; positive elevation puts the top nearer. Nearer regions grow and farther regions shrink. This is a flat-plane approximation: it does not reconstruct the person's side/back silhouette, body depth or occlusions. A rear view mirrors the plane. At ±90° yaw or elevation the plane collapses to a line; execution raises an actionable error. Very near-edge views can also make a mask too small to survive rasterization. Use less extreme angles or distance_and_roll.

The projection orbits the canvas centre with coordinates X=(x−0.5)×aspect, Y=y−0.5. Before roll, U=cos(yaw)X, V=sin(yaw)sin(pitch)X+cos(pitch)Y, Z=−sin(yaw)cos(pitch)X+sin(pitch)Y. Divide U/V by 1+Z/f, with zoom s=2**(2*(0.5−distance)) and f=2×hypot(aspect,1)/s. Roll, zoom and aspect normalization produce the final screen coordinates. This keeps the whole source canvas in front of the camera. Original-resolution masks use inverse nearest-neighbor sampling; preview cells use the same projection on reduced thumbnails. Centers for sampling are the warped mask's centroid; preview markers project the input center and are approximate under perspective/clipping. Projected boxes remain their axis-aligned outer bounds, so masks preserve shape more faithfully.

**마스크 배치 연동을 perspective로 선택**하면 좌우·상하 각도에 따라 전체 마스크 평면을 원근 변형합니다. 거리·회전도 함께 적용됩니다. 가까운 쪽은 커지고 먼 쪽은 작아지며, 전체·부위 마스크와 좌표를 같은 방식으로 바꿉니다. 글자는 고정입니다. **인물 입체 형상이나 가려진 부분을 복원하는 기능은 아닙니다.** 뒤쪽에서는 평면이 좌우 반전되며, ±90°에서는 마스크가 선이 되어 오류로 안내합니다. 각도를 줄이거나 distance_and_roll을 사용하세요. 기본 fixed와 기존 거리·기울기 모드의 결과는 유지됩니다.

Perspective validation (2026-10-25): local Python 269 cases (261 passed, 8 skipped); NAI Python 300 passed; 24 cross-package cases passed; both camera editor test files passed. Forward projection matched Python/JavaScript; tests cover mask/body-part warps, edge-on rejection, zero-angle compatibility, and NAI/local round trips. Two controlled Anima images used the same camera captions/seed, 1216x832, RSCV5 0.9, 30 steps, Euler ancestral / SGM uniform (yaw 45, elevation 25, distance 0.65, roll 12). PNG-restored masks exactly matched the expected warp. An additional live UI generation at yaw 50 verified interactive preview execution. This does not establish pose fidelity or results on other model families; no live NAI request was made for perspective.


## NAI-only installation and menu entry

Find **NAI Camera Control** in **RS_NovelAI_API → Camera** (한국어: **NAI 카메라 시점**, 日本語: **NAI カメラ視点**). It uses the same camera/layout engine and interactive editor as RS Camera Control. No local diffusion model, ControlNet, extra camera weights or RS Multi-Character Sampler installation is required for native NAI character/context input. The older RS Camera Control ID remains available for existing workflows.

- Before T2I: `NAI Character Prompt → NAI Camera Control (context) → NAI Image Generator (characterPrompts or nai_context)`. Connect the scene to the camera's `base_prompt`, then enable context inheritance on the generator.
- From an image or a previous generation: `NAI Load Image / Generator (nai_context) → NAI Camera Control → NAI Generator / Img2Img / Multi-Character Detailer (nai_context)`. Enable context inheritance. Each generation stage retains its own seed, canvas, references and Anlas protection.
- The shared context output remains `RS_MC_CHARACTER_PIPE` so it can also return to local RS nodes. A native NAI context remains a native NAI context at runtime. The default STRING-only syntax in the NAI entry is NovelAI; a connected context always supplies its own syntax.
- `fixed` changes captions only; `distance_and_roll` also transforms character centers; `perspective` projects the common flat plane. Match `canvas_aspect` to generation width divided by height. NAI consumes centers, never silhouette masks. A plain NAI context has no silhouette to preview, so it shows character points.
- Local silhouette/body-part snapshots require the local extension to decode and transform them. Install both updated extensions when editing those local records. This dependency does not apply to ordinary native NAI coordinates.
- Turning the camera off passes the original context through. Camera processing itself never calls NovelAI; only executing a downstream generation/detailer node can make a request. Strict no-Anlas protection remains that downstream node's setting.

**한국어:** NAI만 설치한 환경에서도 **RS_NovelAI_API → Camera → NAI 카메라 시점**을 사용할 수 있습니다. 캐릭터 프롬프트 또는 NAI 컨텍스트를 연결하고 생성 노드의 컨텍스트 사용을 켜세요. 첫 생성 전에는 카메라의 `base_prompt`에 공통 장면을 연결합니다. NAI에 보내는 것은 시점 태그와 중심 좌표이며, 실루엣 자체를 NAI 영역 마스크로 적용하지 않습니다. 로컬 마스크를 포함한 컨텍스트를 편집할 때만 양쪽 확장이 필요합니다.

**日本語:** NAIのみの環境でも **RS_NovelAI_API → Camera → NAI カメラ視点**を使用できます。キャラクタープロンプトまたはNAIコンテキストを接続し、生成ノードのコンテキスト継承を有効にしてください。初回生成前は`base_prompt`に共通シーンを接続します。NAIへ送るのは視点タグと中心座標です。ローカルマスクを含むコンテキストを編集する場合のみ両方の拡張が必要です。


### Plain caption axis independence / 일반 태그의 축별 선택

In `plain` mode, tags are selected against half of their own axis's peak weight (azimuth, elevation, distance and roll separately). Turning the horizontal camera no longer changes distance tags when distance stays fixed. Weighted captions and the underlying continuous weights are unchanged. Plain captions discard numerical strength, so small nonzero elevation/roll can still produce a view/tilt tag; use weighted mode where supported for gradual strength. Conflicting original captions and model-specific interpretation can still prevent side/rear views.

`plain`에서는 좌우·상하·거리·기울기별 최대 가중치의 절반 이상인 태그를 선택합니다. 거리를 고정하면 좌우 각도를 바꿔도 거리 태그가 유지됩니다. 가중치 문법과 원래 연속 계산은 같습니다. 숫자 강도가 없는 일반 태그 특성상 작은 상하각·기울기도 태그로 표시될 수 있습니다. 세밀한 강도 표현이 가능한 경로에서는 weighted를 사용하세요. 기존 문장과의 충돌이나 모델 해석 때문에 측면·후면이 보장되지는 않습니다.

### MOSS side/rear prompts / MOSS 측면·후면 문장

For side/rear shots, start with a short scene and identity/outfit descriptions. Eye color, facial expression and a front-facing gesture can compete with view captions. In a same-seed MOSS native JSON check, simplified scene/character captions produced a rear view at 8 accelerated steps, while the original detailed captions stayed frontal. Several descriptions changed together, so this does not identify a single conflicting token or establish a general success rate. Keep camera captions on both scene and characters; compare simplified prompts before increasing steps or strength.

측면·후면은 짧은 장면과 캐릭터·의상 설명부터 시작하세요. 눈 색·표정·정면 동작은 시점 태그와 충돌할 수 있습니다. 같은 시드의 MOSS 네이티브 JSON 시험에서 기존 상세 문장은 정면에 머물렀지만, 문장을 줄인 조건은 8스텝 고속화에서도 후면이 나왔습니다. 여러 표현을 함께 바꾼 비교이므로 특정 단어의 원인이나 일반 성공률을 확정한 결과는 아닙니다. 공통 장면과 캐릭터 모두에 시점을 적용하고, 스텝이나 강도를 높이기 전에 문장을 줄여 비교해보세요.
