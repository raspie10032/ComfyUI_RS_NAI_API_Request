# RS Camera Control / 공통 카메라 시점

Development candidate, validated on 2026-10-25; not yet a published release.

This node adds view/framing captions to either an RS finalized character pipe or an NAI context. It does not move a 3D camera, rotate masks, or enforce geometry. Coordinates, masks, negative prompts, LoRAs and model settings remain attached to the context.

## Connect

`Finalize Character Pipe or NAI context → RS Camera Control → character_pipe or nai_context`

Connect the existing scene to `base_prompt` if the finalized character pipe does not contain a scene. The node raises a readable error instead of silently replacing that missing scene with camera tags. A supplied `base_prompt` explicitly replaces the context's scene. With no context, connect `prompt` to the generator's common prompt; the context output is empty. The `camera_prompt` STRING contains just the added camera captions.

Default `scene_and_characters` adds the view to both common and character captions. This matters for regional Anima generation, where a common-only view can be suppressed by character conditions. `scene_only` leaves character captions untouched. Text regions do not receive camera captions. Position/mask coordinates remain fixed, even when the generated view changes. Set the downstream generator to inherit the connected context.

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

Both models visibly changed toward side/above and near/far compositions. Anima's rear example retained a side-looking face; its wide example assigned different apparent sizes to the two characters and changed the background. Side captions can turn each person independently rather than orbiting a shared camera. These are observed limits, not failures to dispatch the node. Results do not prove precise degrees, tilt direction, same-scale people, or support/quality across every model family. The numerical curves measure caption weights, not measured image angles or model adherence. No camera model, ControlNet or new inference pass is loaded.

Reference: [Anima camera-tag helper](https://arca.live/b/aiart/179423561). The shared implementation uses its own continuous formulas and context integration. The reference implementation was inspected to compare default weights and discontinuities; its code/archive is not distributed here.

## 한국어 사용법

**최종 캐릭터 파이프 또는 NAI 컨텍스트 → RS 카메라 시점 → 생성 노드**로 연결합니다. 생성 노드에서 컨텍스트 상속을 켜세요. 공통 장면이 없는 파이프는 `base_prompt`에 장면 문장을 연결해야 합니다. 컨텍스트 없이 쓸 때는 `prompt` 출력만 공통 프롬프트에 연결합니다.

기본은 **공통 장면＋캐릭터**에 적용합니다. Anima는 공통 태그만 넣으면 시점이 약하게 반영돼 기본 적용 범위를 넓혔습니다. 글자 영역·좌표·마스크·LoRA·네거티브는 유지합니다. 양쪽 패키지에서 같은 노드를 쓰며 NAI 가중치 문법도 자동으로 맞춥니다.

**드래그=시점, 휠=거리, Shift+휠=기울기**입니다. 시작 강도는 1.2이며 0.8~1.4부터 조정하세요. 아래 곡선은 태그 계산 그래프이며 실제 카메라 각도 측정값은 아닙니다. 연결된 수치 입력은 마우스로 덮어쓰지 않습니다.

실제 생성에서 측면·위·거리 변화는 확인됐지만 뒤돌기·원경의 두 인물 크기는 완벽하지 않았습니다. 이 노드는 **시점 태그 유도 기능**이며 마스크를 돌리거나 3D 카메라 위치를 강제하지 않습니다. 두 노드를 연달아 연결하거나 이미 시점 태그가 있는 컨텍스트에 넣으면 태그가 더해지므로, 상반되는 기존 시점 문장은 직접 정리하세요.


## Random composition / 랜덤 구도

`random_mode` defaults to `off`, preserving existing workflows. Choose `balanced` for azimuth −90…90°, elevation −35…35°, distance 0.25…0.85 and roll −10…10°. `full` samples the entire four-axis range. Strength, characters, masks, placements and image seed stay under their existing controls. Randomizing a view cannot guarantee correct poses or avoid cropping, and camera tags do not move masks.

`random_seed` is an independent 32-bit integer. With the built-in seed control set to **fixed**, the same camera seed and mode reproduce the same captions. Select **randomize** to change the camera seed after each queued generation. API clients must send a different camera seed themselves; identical requests may use ComfyUI's cache. A single execution draws one view; a downstream image batch shares that view.

The **Random** button draws a new camera seed and uses balanced mode (or keeps full mode if selected). The diagram previews the seeded view, and the server returns the actual axes alongside its captions after execution. Manual sliders remain stored but are overridden while random mode is on. Dragging, wheel, arrow keys or a preset return to manual mode; connected controls remain authoritative. New optional controls are appended so existing widget positions keep their meaning.

**랜덤 구도**에서 `balanced`는 일반 범위, `full`은 전체 범위입니다. 카메라 시드 옆의 생성 후 동작을 **randomize**로 두면 매번 새로운 구도, **fixed**로 두면 같은 구도를 사용합니다. 이미지 생성 시드는 별개입니다. **랜덤 구도 버튼**으로 바로 다시 뽑을 수도 있습니다. 드래그·휠·화살표·프리셋은 수동 모드로 돌아갑니다. 연결 입력은 덮어쓰지 않습니다. 한 번 실행한 출력으로 이미지 배치를 만들면 배치 전체가 같은 구도 태그를 받습니다. 마스크는 고정이므로 큰 시점 변화에서는 위치를 따로 조정하세요.
