import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

const modelFields = ["face_segm_model", "face_bbox_model", "sam_model", "eye_bbox_model"];
const labels = {
    en: ["SEGM model", "BBOX model", "SAM model", "Eye context (optional)", "Next run", "SEGM only. BBOX / SAM are skipped.", "BBOX + SAM masks.", "BBOX rectangles (SAM OFF).", "Select SEGM or BBOX. SAM alone cannot detect regions.", "Extra eye context is enabled.", "Connected model inputs are resolved when the workflow runs."],
    ko: ["SEGM 모델", "BBOX 모델", "SAM 모델", "보조 눈 감지 (선택)", "현재 선택의 실행 방식", "SEGM만 사용합니다. BBOX·SAM은 건너뜁니다.", "BBOX로 감지하고 SAM으로 마스크를 만듭니다.", "BBOX 사각 영역을 사용합니다 (SAM OFF).", "SEGM 또는 BBOX를 선택하세요. SAM만으로는 영역을 감지할 수 없습니다.", "보조 눈 감지를 추가로 사용합니다.", "연결된 모델 입력은 실행할 때 결정됩니다."],
    ja: ["SEGM モデル", "BBOX モデル", "SAM モデル", "補助の目検出（任意）", "現在の選択での実行方法", "SEGMのみ使用。BBOX・SAMはスキップします。", "BBOXで検出し、SAMでマスクを作成します。", "BBOXの矩形領域を使用（SAM OFF）。", "SEGMまたはBBOXを選択してください。SAM単独では領域を検出できません。", "補助の目検出も使用します。", "接続されたモデル入力は実行時に決まります。"],
};

function updateLoader(node, clearProgress = false) {
    const locale = String(app.ui?.settings?.getSettingValue("Comfy.Locale") ?? "en").slice(0, 2);
    const text = labels[locale] ?? labels.en;
    const enabled = name => {
        const value = node.widgets?.find(w => w.name === name)?.value;
        return value && !["OFF", "None"].includes(value);
    };
    for (const [index, name] of modelFields.entries()) {
        const widget = node.widgets?.find(w => w.name === name);
        if (widget) widget.label = text[index];
    }
    let plan = node.widgets?.find(w => w.name === "rs_detector_plan");
    if (!plan) {
        plan = ComfyWidgets.STRING(node, "rs_detector_plan", ["STRING", { multiline: true }], app).widget;
        plan.options.serialize = false;
        plan.serialize = false;
        plan.serializeValue = () => undefined;
        plan.inputEl.readOnly = true;
    }
    plan.label = text[4];
    const connected = node.inputs?.some(input => modelFields.includes(input.name) && input.link != null);
    plan.value = connected ? text[10] : text[enabled("face_segm_model") ? 5 : enabled("face_bbox_model") ? (enabled("sam_model") ? 6 : 7) : 8];
    if (!connected && enabled("eye_bbox_model")) plan.value += "\n" + text[9];
    if (clearProgress) {
        const status = node.widgets?.find(w => w.name === "rs_tagger_status");
        if (status) {
            status.onRemove?.();
            node.widgets.splice(node.widgets.indexOf(status), 1);
        }
    }
}

const targets = {
    NAIDetectorCombineLoaderTest: ["show_optional_models", new Set(["face_segm_model", "face_bbox_model", "sam_model", "show_optional_models"])],
    NAICombinedFaceDetailerTest: ["show_advanced", new Set(["prompt", "negative_prompt", "model", "strength", "seed", "control_after_generate", "preview_only", "show_advanced", "limit_opus_free", "use_context_settings"])],
};

function update(node, toggle, basic) {
    const expanded = Boolean(node.widgets?.find(w => w.name === toggle)?.value);
    const inherited = node.inputs?.some(i => i.name === "nai_context" && i.link != null) &&
        node.widgets?.find(w => w.name === "use_context_settings")?.value !== false;
    const fields = new Set(["prompt", "negative_prompt", "model", "sampler", "steps", "cfg_scale", "scheduler", "cfg_rescale", "prefer_brownian", "variety_boost"]);
    for (const widget of node.widgets ?? []) {
        if (widget.options?.serialize === false) continue;
        const hide = (inherited && fields.has(widget.name)) || (!basic.has(widget.name) &&
            (!expanded || (widget.name === "webp_quality" &&
            node.widgets.find(w => w.name === "save_format")?.value !== "WebP lossy")));
        if (hide && !widget.rsNaiDetectionVisible && !widget.type?.startsWith("converted-widget")) {
            widget.rsNaiDetectionVisible = { type: widget.type, computeSize: widget.computeSize, hidden: widget.hidden };
            widget.type = "rs-nai-detection-hidden";
            widget.hidden = true;
            widget.computeSize = () => [0, -4];
            if (widget.inputEl) widget.inputEl.hidden = true;
        } else if (!hide && widget.rsNaiDetectionVisible) {
            if (widget.type === "rs-nai-detection-hidden") Object.assign(widget, widget.rsNaiDetectionVisible);
            delete widget.rsNaiDetectionVisible;
            if (widget.inputEl) widget.inputEl.hidden = false;
        }
    }
    const size = node.computeSize();
    node.setSize([Math.max(node.size[0], size[0]), size[1]]);
    node.setDirtyCanvas(true, true);
}

app.registerExtension({
    name: "RS.NovelAI.DetectionBundle",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const spec = targets[nodeData.name];
        if (!spec) return;
        const [toggle, basic] = spec;
        for (const hook of ["onNodeCreated", "onConfigure"]) {
            const previous = nodeType.prototype[hook];
            nodeType.prototype[hook] = function () {
                const result = previous?.apply(this, arguments);
                if (nodeData.name === "NAIDetectorCombineLoaderTest" && hook === "onConfigure") {
                    for (const widget of this.widgets ?? []) {
                        if (["face_segm_model", "face_bbox_model", "sam_model", "eye_bbox_model"].includes(widget.name) && widget.value === "None") {
                            widget.value = "OFF";
                        }
                    }
                }
                if (hook === "onNodeCreated") {
                    for (const name of [toggle, "save_format", "use_context_settings", ...(nodeData.name === "NAIDetectorCombineLoaderTest" ? modelFields : [])]) {
                        const widget = this.widgets?.find(w => w.name === name);
                        if (widget) {
                            const callback = widget.callback;
                            widget.callback = (...args) => {
                                callback?.apply(widget, args);
                                if (nodeData.name === "NAIDetectorCombineLoaderTest") updateLoader(this, modelFields.includes(name));
                                update(this, toggle, basic);
                            };
                        }
                    }
                }
                if (nodeData.name === "NAIDetectorCombineLoaderTest") updateLoader(this, hook === "onConfigure");
                update(this, toggle, basic);
                return result;
            };
        }
        {
            const previous = nodeType.prototype.onConnectionsChange;
            nodeType.prototype.onConnectionsChange = function () {
                const result = previous?.apply(this, arguments);
                if (nodeData.name === "NAIDetectorCombineLoaderTest") updateLoader(this, true);
                update(this, toggle, basic);
                return result;
            };
        }
    },
});
