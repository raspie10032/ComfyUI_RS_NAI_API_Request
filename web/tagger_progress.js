import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

app.registerExtension({
    name: "RS.NovelAI.TaggerProgress",
    setup() {
        api.addEventListener("rs_nai_tagger_progress", ({ detail }) => {
            const node = app.graph?.getNodeById(detail.node);
            if (node?.comfyClass !== "RSWDTaggerLoader") return;
            let widget = node.widgets?.find(w => w.name === "rs_tagger_status");
            if (!widget) {
                widget = ComfyWidgets.STRING(node, "rs_tagger_status", ["STRING", { multiline: true }], app).widget;
                widget.options.serialize = false;
                widget.serialize = false;
                widget.serializeValue = () => undefined;
                widget.inputEl.readOnly = true;
            }
            widget.value = detail.text;
            const needed = node.computeSize();
            node.setSize([Math.max(node.size[0], needed[0]), Math.max(node.size[1], needed[1])]);
            node.setDirtyCanvas(true, true);
        });
    },
});
