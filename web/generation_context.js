import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";
import { contextFields, contextControls, contextFieldLabels, contextState, contextWidgetHidden } from "./context_controls.js";

const consumers = new Set(["NAIImg2ImgNode", "NAIMultiCharacterDetailer"]);
const labels = {
    en: ["Using connected prompts, characters, model and sampling settings. Seed, size, strength and Anlas protection stay local. Multiple characters in the detailer require a tagger.", "Using this node's manual settings. Connect NAI context and enable its settings to inherit them."],
    ko: ["이전 단계의 프롬프트·캐릭터·모델·샘플링 설정을 사용합니다. 시드·크기·강도·Anlas 보호는 이 노드에서 설정합니다. 여러 캐릭터의 보정에는 태거가 필요합니다.", "이 노드의 직접 입력값을 사용합니다. NAI 컨텍스트를 연결하고 설정 사용을 켜면 이전 단계의 값을 가져옵니다."],
    ja: ["接続元のプロンプト・キャラクター・モデル・サンプリング設定を使用します。シード・サイズ・強度・Anlas保護はこのノードで設定します。複数キャラクターの補正にはタガーが必要です。", "このノードの手動設定を使用します。NAIコンテキストを接続して設定の使用を有効にすると引き継げます。"],
};
const detailerModes = {
    en: "Next run: NovelAI correction for eligible regions. Anlas protection applies. Quality cannot be guaranteed as the number of processed regions increases.",
    ko: "다음 실행: 감지·매칭을 통과한 영역을 NAI로 보정합니다. Anlas 보호가 적용됩니다. 처리수가 많을수록 품질을 보장하지 못합니다.",
    ja: "次の実行：検出・照合を通過した領域をNAIで補正します。Anlas保護が適用されます。処理領域数が増えるほど品質は保証できません。",
};

function update(node, isImg2Img) {
    const state = contextState(node);
    const { active, selective, selected } = state;
    // Combined detailer owns its fold logic; never overwrite that widget state.
    if (isImg2Img) for (const widget of node.widgets ?? []) {
        if (!contextFields.includes(widget.name) && !contextControls.includes(widget.name)) continue;
        const hide = contextWidgetHidden(widget.name, state) ?? false;
        if (hide && !widget.rsNaiContextVisible && !widget.type?.startsWith("converted-widget")) {
            widget.rsNaiContextVisible = { type: widget.type, computeSize: widget.computeSize, hidden: widget.hidden };
            widget.type = "rs-nai-context-hidden";
            widget.hidden = true;
            widget.computeSize = () => [0, -4];
            if (widget.inputEl) widget.inputEl.hidden = true;
        } else if (!hide && widget.rsNaiContextVisible) {
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
    const names = contextFieldLabels[locale] ?? contextFieldLabels.en;
    const prefix = ({ en: "Override", ko: "직접 변경", ja: "手動変更" })[locale] ?? "Override";
    for (const [i, name] of contextFields.entries()) {
        const control = node.widgets?.find(w => w.name === `override_${name}`);
        if (control) control.label = `${prefix}: ${names[i]}`;
    }
    const mode = node.widgets?.find(w => w.name === "context_mode");
    if (mode) mode.label = ({ en: "Context parameters", ko: "컨텍스트 파라미터", ja: "コンテキストのパラメーター" })[locale] ?? "Context parameters";
    if (selective) {
        const changed = [...selected].map(name => names[contextFields.indexOf(name)]).join(", ");
        const selectionText = {
            en: `Manual replacements: ${changed || "none (all inherited)"}. Other fields use context. Medium model restrictions still apply.`,
            ko: `직접 변경: ${changed || "없음 (전체 컨텍스트 사용)"}. 나머지는 컨텍스트를 사용합니다. Medium 모델의 고정 설정은 계속 적용됩니다.`,
            ja: `手動変更：${changed || "なし（全項目を継承）"}。その他はコンテキストを使用します。Mediumモデルの固定設定は引き続き適用されます。`,
        };
        status.value = (selectionText[locale] ?? selectionText.en);
        if (selected.has("characterPrompts")) {
            const connected = node.inputs?.some(i => i.name === "characterPrompts" && i.link != null);
            const characterText = connected ? {
                en: "The connected character list replaces the entire inherited list.", ko: "연결한 캐릭터 목록으로 전체 목록을 교체합니다.", ja: "接続したキャラクター一覧で全体を置き換えます。",
            } : {
                en: "No character list connected: inherited characters will be cleared.", ko: "캐릭터 목록 연결 없음: 기존 컨텍스트의 캐릭터를 모두 비웁니다.", ja: "キャラクター一覧の接続なし：継承したキャラクターをすべて消去します。",
            };
            status.value += "\n" + (characterText[locale] ?? characterText.en);
        }
    }
    if (!isImg2Img) {
        status.value = (detailerModes[locale] ?? detailerModes.en) + "\n\n" + status.value;
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
                    for (const name of contextControls) {
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
