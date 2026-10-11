import { app } from "../../scripts/app.js";

// Keep widgets in their original order so saved workflows retain every value.
function updateSlots(node) {
    const count = Number(node.widgets?.find(w => w.name === "character_count")?.value ?? 5);
    for (const widget of node.widgets ?? []) {
        const match = /^character(\d+)(?:_.*)?$/.exec(widget.name);
        if (!match) continue;
        const hide = Number(match[1]) > count;
        if (hide && !widget.rsNaiVisibleState && !widget.type?.startsWith("converted-widget")) {
            widget.rsNaiVisibleState = { type: widget.type, computeSize: widget.computeSize, hidden: widget.hidden };
            widget.type = "rs-nai-hidden";
            widget.hidden = true;
            widget.computeSize = () => [0, -4];
            if (widget.inputEl) widget.inputEl.hidden = true;
        } else if (!hide && widget.rsNaiVisibleState) {
            if (widget.type === "rs-nai-hidden") {
                Object.assign(widget, widget.rsNaiVisibleState);
                if (widget.inputEl) widget.inputEl.hidden = false;
            }
            delete widget.rsNaiVisibleState;
        }
    }
    const needed = node.computeSize();
    node.setSize([Math.max(node.size[0], needed[0]), needed[1]]);
    node.setDirtyCanvas(true, true);
}

app.registerExtension({
    name: "RS.NovelAI.Characters",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "CharacterPromptSelect") return;
        const onCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onCreated?.apply(this, arguments);
            const count = this.widgets?.find(w => w.name === "character_count");
            if (count) {
                const callback = count.callback;
                count.callback = (...args) => {
                    callback?.apply(count, args);
                    updateSlots(this);
                };
            }
            updateSlots(this);
            return result;
        };
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = onConfigure?.apply(this, arguments);
            updateSlots(this);
            return result;
        };
    },
});
