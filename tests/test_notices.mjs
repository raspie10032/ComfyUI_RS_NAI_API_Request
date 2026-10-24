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

app.ui = { settings: { getSettingValue: () => 'ko' } };
node.onExecuted({ rs_nai_parameters: [{ model: 'nai-diffusion-4-5-curated-inpainting', action: 'infill',
    width: 512, height: 768, seed: 77, sampler: 'k_euler', steps: 14, scale: 5,
    cfg_rescale: 0, prefer_brownian: false, inpaintImg2ImgStrength: .4, noise: 0,
    characters: 6, coordinates: true, negative_mode: 'fixed_heavy', request_count: 3 }] });
const report = node.widgets.find(w => w.name === 'rs_nai_parameters');
assert.match(report.value, /마지막으로 성공한 NAI 요청/);
assert.match(report.value, /3 회 요청 중 마지막 설정/);
assert.match(report.value, /캐릭터 수: 6/);
assert.match(report.value, /변경 강도: 0.4/);
assert.match(report.value, /노이즈: 0/);
assert.match(report.value, /Heavy 고정/);
assert.doesNotMatch(report.value, /Vibe 이미지|Precise 참조/);
assert.equal(report.serializeValue(), undefined);
node.onExecuted({ rs_nai_notice: [] });
assert.equal(node.widgets.find(w => w.name === 'rs_nai_parameters'), undefined);
console.log('PASS: final request settings, Korean labels, optional fields, multiple requests and clearing');

// The multi-character detailer lives directly in the root category.
class RootNode extends Node {}
RootNode.prototype.onExecuted = function () { this.chained = true; };
await extension.beforeRegisterNodeDef(RootNode, { category: 'RS_NovelAI_API' });
const root = new RootNode();
root.rsNaiDetailerPanel = { refresh() { root.refreshed = true; } };
root.onExecuted({ rs_nai_notice: ['Skipped region'] });
assert.equal(root.chained, true);
assert.equal(root.refreshed, true);
assert.equal(root.widgets.find(w => w.name === 'rs_nai_notice').value, 'Skipped region');
class Unrelated extends Node {}
Unrelated.prototype.onExecuted = function () {};
const original = Unrelated.prototype.onExecuted;
await extension.beforeRegisterNodeDef(Unrelated, { category: 'RS_NovelAI_API_Unrelated' });
assert.equal(Unrelated.prototype.onExecuted, original);
console.log('PASS: root-category detailer notices, panel refresh and unrelated-category exclusion');
