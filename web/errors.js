import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

const detailMarker = "\n\nTechnical details:\n";
const nodeTypes = new Set();

function language() {
    const locale = String(app.ui.settings.getSettingValue("Comfy.Locale") ?? "en").toLowerCase();
    return locale.startsWith("ko") ? "ko" : locale.startsWith("ja") ? "ja" : "en";
}

function clearError(node) {
    const widget = node?.widgets?.find(w => w.name === "rs_nai_error");
    if (!widget) return;
    widget.onRemove?.();
    node.widgets.splice(node.widgets.indexOf(widget), 1);
    node.setDirtyCanvas(true, true);
}

function showError(node, text, locale) {
    if (!node) return;
    let widget = node.widgets?.find(w => w.name === "rs_nai_error");
    if (!widget) {
        widget = ComfyWidgets.STRING(node, "rs_nai_error", ["STRING", { multiline: true }], app).widget;
        widget.options.serialize = false;
        widget.serialize = false;
        widget.serializeValue = () => undefined;
        widget.inputEl.readOnly = true;
    }
    widget.label = { ko: "오류 원인과 해결 방법", ja: "エラーの原因と対処方法", en: "Error and next steps" }[locale];
    widget.value = text;
    const needed = node.computeSize();
    node.setSize([Math.max(node.size[0], needed[0]), Math.max(node.size[1], needed[1])]);
    node.setDirtyCanvas(true, true);
}

app.registerExtension({
    name: "RS.NovelAI.Errors",
    async setup() {
        let messages;
        try {
            const response = await fetch(new URL("./error_messages.json", import.meta.url));
            if (!response.ok) return; // The backend's English explanation remains available.
            messages = await response.json();
        } catch {
            return;
        }
        // Capture runs before ComfyUI's normal dialog/history listeners.
        // Mutate only this node pack's marked errors, leaving traceback/type intact.
        api.addEventListener("execution_error", event => {
            const detail = event.detail;
            if (!nodeTypes.has(detail?.node_type)) return;
            const source = String(detail.exception_message ?? "");
            const match = /\[RS NAI:([A-Z][A-Z0-9_]+)\]/.exec(source);
            const split = source.indexOf(detailMarker);
            if (!match || split < 0 || !messages.en[match[1]]) return;
            const locale = language();
            const [title, action] = (messages[locale] ?? messages.en)[match[1]] ?? messages.en[match[1]];
            const label = { ko: "상세 정보", ja: "詳細情報", en: "Technical details" }[locale];
            const text = `[RS NAI:${match[1]}] ${title}\n${action}\n\n${label}:\n${source.slice(split + detailMarker.length)}`;
            detail.exception_message = text;
            showError(app.graph?.getNodeById(detail.node_id), text, locale);
        }, { capture: true });
        api.addEventListener("executing", event => {
            const id = event.detail?.node ?? event.detail;
            if (id != null) clearError(app.graph?.getNodeById(id));
        });
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!nodeData.category?.startsWith("RS_NovelAI_API/")) return;
        nodeTypes.add(nodeData.name);
        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function () {
            clearError(this);
            return onExecuted?.apply(this, arguments);
        };
    },
});
