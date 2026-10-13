import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

function clear(node) {
    const widget = node?.widgets?.find(w => w.name === "rs_nai_request_wait");
    if (!widget) return;
    widget.onRemove?.();
    node.widgets.splice(node.widgets.indexOf(widget), 1);
    node.setDirtyCanvas(true, true);
}

app.registerExtension({
    name: "RS.NovelAI.RequestDelay",
    setup() {
        api.addEventListener("rs_nai_request_wait", ({ detail }) => {
            const node = app.graph?.getNodeById(detail.node);
            if (!node?.widgets?.some(w => w.name === "request_delay_seconds")) return;
            if (detail.remaining <= 0) { clear(node); return; }
            const locale = String(app.ui.settings.getSettingValue("Comfy.Locale") ?? "en");
            const language = locale.startsWith("ko") ? "ko" : locale.startsWith("ja") ? "ja" : "en";
            const labels = {
                en: ["Waiting before request", "Waiting to retry"],
                ko: ["요청 전 대기", "재요청 대기"],
                ja: ["リクエスト前の待機", "再試行の待機"],
            };
            let widget = node.widgets.find(w => w.name === "rs_nai_request_wait");
            if (!widget) {
                widget = ComfyWidgets.STRING(node, "rs_nai_request_wait", ["STRING", { multiline: true }], app).widget;
                widget.options.serialize = false;
                widget.serialize = false;
                widget.serializeValue = () => undefined;
                widget.inputEl.readOnly = true;
                const needed = node.computeSize();
                node.setSize([Math.max(node.size[0], needed[0]), Math.max(node.size[1], needed[1])]);
            }
            widget.value = `${labels[language][detail.retry ? 1 : 0]}: ${detail.remaining}s`;
            node.setDirtyCanvas(true, true);
        });
        for (const event of ["execution_start", "execution_error", "execution_interrupted", "execution_success"]) {
            api.addEventListener(event, () => {
                for (const node of app.graph?._nodes ?? []) clear(node);
            });
        }
    },
});
