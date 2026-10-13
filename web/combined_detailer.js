import { app } from "../../scripts/app.js";

const targets = {
    NAIDetectorCombineLoaderTest: ["show_optional_models", new Set(["face_segm_model", "face_bbox_model", "sam_model", "show_optional_models"])],
    NAICombinedFaceDetailerTest: ["show_advanced", new Set(["prompt", "negative_prompt", "model", "strength", "seed", "control_after_generate", "preview_only", "show_advanced", "limit_opus_free"])],
};

function update(node, toggle, basic) {
    const expanded = Boolean(node.widgets?.find(w => w.name === toggle)?.value);
    for (const widget of node.widgets ?? []) {
        if (basic.has(widget.name) || widget.options?.serialize === false) continue;
        const hide = !expanded || (widget.name === "webp_quality" &&
            node.widgets.find(w => w.name === "save_format")?.value !== "WebP lossy");
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
                    for (const name of [toggle, "save_format"]) {
                        const widget = this.widgets?.find(w => w.name === name);
                        if (widget) {
                            const callback = widget.callback;
                            widget.callback = (...args) => { callback?.apply(widget, args); update(this, toggle, basic); };
                        }
                    }
                }
                update(this, toggle, basic);
                return result;
            };
        }
    },
});
