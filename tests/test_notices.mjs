// Run with node tests/test_notices.mjs. No browser or external requests.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

let extension;
const ComfyWidgets = {
    STRING(node, name) {
        const widget = { name, options: {}, inputEl: {}, onRemove() { this.removed = true; } };
        node.widgets.push(widget);
        return { widget };
    },
};
const app = { registerExtension(value) { extension = value; } };
const source = readFileSync(new URL("../web/notices.js", import.meta.url), "utf8");
vm.runInNewContext(source.replace(/^import .*;\n/gm, ""), { app, ComfyWidgets });
class Node {
    constructor() { this.widgets = [{ name: "original", value: "prompt" }]; this.size = [400, 250]; }
    onExecuted() { this.chained = true; }
    computeSize() { return [200, 200]; }
    setSize(size) { this.size = size; }
    setDirtyCanvas() { this.dirty = true; }
}
await extension.beforeRegisterNodeDef(Node, { category: "RS_NovelAI_API/Converters" });
const node = new Node();
node.onExecuted({ rs_nai_notice: ["Dropped (tag:o)"] });
assert.equal(node.chained, true);
assert.equal(node.widgets.length, 2);
const widget = node.widgets[1];
assert.equal(widget.value, "Dropped (tag:o)");
assert.equal(widget.options.serialize, false);
assert.equal(widget.serialize, false);
assert.equal(widget.serializeValue(), undefined);
assert.equal(widget.inputEl.readOnly, true);
assert.deepEqual(Array.from(node.size), [400, 250]);
node.onExecuted({ rs_nai_notice: ["<script>not HTML</script>"] });
assert.equal(node.widgets.length, 2);
assert.equal(widget.value, "<script>not HTML</script>");
node.onExecuted({ rs_nai_notice: [] });
assert.equal(widget.removed, true);
assert.deepEqual(node.widgets, [{ name: "original", value: "prompt" }]);
assert.equal(node.dirty, true);
console.log("PASS: notice lifecycle, old callback, plain text, read-only, no saved widget value, clear after clean execution");
