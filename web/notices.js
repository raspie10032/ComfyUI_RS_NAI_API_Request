import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

app.registerExtension({
    name: "RS.NovelAI.Notices",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!nodeData.category?.startsWith("RS_NovelAI_API/")) return;
        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);
            const text = (message?.rs_nai_notice ?? []).join("\n\n");
            let widget = this.widgets?.find(w => w.name === "rs_nai_notice");
            if (text) {
                if (!widget) {
                    widget = ComfyWidgets.STRING(this, "rs_nai_notice", ["STRING", { multiline: true }], app).widget;
                    widget.options.serialize = false;
                    widget.serialize = false;
                    widget.serializeValue = () => undefined;
                    widget.inputEl.readOnly = true;
                }
                widget.value = text;
                const needed = this.computeSize();
                this.setSize([
                    Math.max(this.size[0], needed[0]),
                    Math.max(this.size[1], needed[1]),
                ]);
            } else if (widget) {
                widget.onRemove?.();
                this.widgets.splice(this.widgets.indexOf(widget), 1);
            }
            this.setDirtyCanvas(true, true);
        };
    },
});
