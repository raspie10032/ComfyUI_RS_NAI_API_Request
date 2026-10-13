import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

const consumers = new Set(["NAIImg2ImgNode", "NAICombinedFaceDetailerTest"]);
const inheritedFields = new Set(["prompt", "negative_prompt", "model", "sampler", "steps", "cfg_scale", "scheduler", "cfg_rescale", "prefer_brownian", "variety_boost"]);
const labels = {
    en: ["Using connected prompts, characters, model and sampling settings. Seed, size, strength and Anlas protection stay local. Multiple characters in the detailer require a tagger.", "Using this node's manual settings. Connect NAI context and enable its settings to inherit them."],
    ko: ["이전 단계의 프롬프트·캐릭터·모델·샘플링 설정을 사용합니다. 시드·크기·강도·Anlas 보호는 이 노드에서 설정합니다. 여러 캐릭터의 보정에는 태거가 필요합니다.", "이 노드의 직접 입력값을 사용합니다. NAI 컨텍스트를 연결하고 설정 사용을 켜면 이전 단계의 값을 가져옵니다."],
    ja: ["接続元のプロンプト・キャラクター・モデル・サンプリング設定を使用します。シード・サイズ・強度・Anlas保護はこのノードで設定します。複数キャラクターの補正にはタガーが必要です。", "このノードの手動設定を使用します。NAIコンテキストを接続して設定の使用を有効にすると引き継げます。"],
};
const detailerModes = {
    en: ["Next run: preview only. Detection / matching only; no NovelAI request. Turn off 'preview_only' to generate.", "Next run: NovelAI detailing for eligible regions. Anlas protection still applies.", "Preview / generation mode is determined by the connected preview_only input at execution."],
    ko: ["다음 실행: 미리보기만. 감지·매칭만 확인하며 NAI 생성 요청은 보내지 않습니다. 보정하려면 ‘미리보기만 실행’을 끄세요.", "다음 실행: NAI 보정. 감지·매칭을 통과한 영역을 생성합니다. Anlas 보호도 적용됩니다.", "미리보기·생성 여부는 연결된 ‘미리보기만 실행’ 입력값으로 실행할 때 결정됩니다."],
    ja: ["次の実行：プレビューのみ。検出・照合だけ行い、NAIへ生成リクエストを送りません。補正するには「プレビューのみ」を無効にしてください。", "次の実行：NAIで補正。検出・照合を通過した領域を生成します。Anlas保護も適用されます。", "プレビュー・生成の選択は、接続されたpreview_only入力の値で実行時に決まります。"],
};

function update(node, isImg2Img) {
    const active = node.inputs?.some(i => i.name === "nai_context" && i.link != null) &&
        node.widgets?.find(w => w.name === "use_context_settings")?.value !== false;
    // Combined detailer owns its fold logic; never overwrite that widget state.
    if (isImg2Img) for (const widget of node.widgets ?? []) {
        if (!inheritedFields.has(widget.name)) continue;
        if (active && !widget.rsNaiContextVisible && !widget.type?.startsWith("converted-widget")) {
            widget.rsNaiContextVisible = { type: widget.type, computeSize: widget.computeSize, hidden: widget.hidden };
            widget.type = "rs-nai-context-hidden";
            widget.hidden = true;
            widget.computeSize = () => [0, -4];
            if (widget.inputEl) widget.inputEl.hidden = true;
        } else if (!active && widget.rsNaiContextVisible) {
            if (widget.type === "rs-nai-context-hidden") Object.assign(widget, widget.rsNaiContextVisible);
            delete widget.rsNaiContextVisible;
            if (widget.inputEl) widget.inputEl.hidden = false;
        }
    }
    let status = node.widgets?.find(w => w.name === "rs_nai_context_status");
    if (!status) {
        status = ComfyWidgets.STRING(node, "rs_nai_context_status", ["STRING", { multiline: true }], app).widget;
        status.options.serialize = false;
        status.serialize = false;
        status.serializeValue = () => undefined;
        status.inputEl.readOnly = true;
    }
    const locale = String(app.ui?.settings?.getSettingValue("Comfy.Locale") ?? "en").slice(0, 2);
    status.value = (labels[locale] ?? labels.en)[active ? 0 : 1];
    if (!isImg2Img) {
        const connected = node.inputs?.some(i => i.name === "preview_only" && i.link != null);
        const preview = node.widgets?.find(w => w.name === "preview_only")?.value !== false;
        status.value = (detailerModes[locale] ?? detailerModes.en)[connected ? 2 : preview ? 0 : 1] + "\n\n" + status.value;
    }
    const size = node.computeSize();
    node.setSize([Math.max(node.size[0], size[0]), size[1]]);
    node.setDirtyCanvas(true, true);
}

app.registerExtension({
    name: "RS.NovelAI.GenerationContext",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!consumers.has(nodeData.name)) return;
        for (const hook of ["onNodeCreated", "onConfigure", "onConnectionsChange"]) {
            const previous = nodeType.prototype[hook];
            nodeType.prototype[hook] = function () {
                const result = previous?.apply(this, arguments);
                if (hook === "onNodeCreated") {
                    for (const name of ["use_context_settings", "preview_only"]) {
                        const mode = this.widgets?.find(w => w.name === name);
                        if (!mode) continue;
                        const callback = mode.callback;
                        mode.callback = (...args) => {
                            callback?.apply(mode, args);
                            update(this, nodeData.name === "NAIImg2ImgNode");
                        };
                    }
                }
                update(this, nodeData.name === "NAIImg2ImgNode");
                return result;
            };
        }
    },
});
