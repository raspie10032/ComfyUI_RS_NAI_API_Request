import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

let extension, update;
const node = {
    comfyClass: "RSWDTaggerLoader", widgets: [{ name: "model_name", value: "WD ViT v3" }], size: [400, 200],
    computeSize: () => [250, 250], setSize(size) { this.size = size; }, setDirtyCanvas() {},
};
const app = { registerExtension(e) { extension = e; }, graph: { getNodeById(id) { return id === "7" ? node : null; } } };
const api = { addEventListener(type, cb) { assert.equal(type, "rs_nai_tagger_progress"); update = cb; } };
const ComfyWidgets = { STRING(n, name) { const widget = { name, options: {}, inputEl: {} }; n.widgets.push(widget); return { widget }; } };
const source = readFileSync(new URL("../web/tagger_progress.js", import.meta.url), "utf8");
vm.runInNewContext(source.replace(/^import .*;\n/gm, ""), { app, api, ComfyWidgets });
extension.setup();
update({ detail: { node: "missing", text: "ignored" } });
assert.equal(node.widgets.length, 1);
update({ detail: { node: "7", text: "Downloading model.safetensors: 25% (100 / 400 MiB)" } });
const widget = node.widgets[1];
assert.match(widget.value, /25%/);
assert.equal(widget.serialize, false);
assert.equal(widget.options.serialize, false);
assert.equal(widget.serializeValue(), undefined);
assert.equal(widget.inputEl.readOnly, true);
update({ detail: { node: "7", text: "Loading PixAI on CPU…" } });
update({ detail: { node: "7", text: "Ready: PixAI Tagger v1.0" } });
assert.equal(widget.value, "Ready: PixAI Tagger v1.0");
assert.equal(node.widgets.length, 2);
assert.equal(node.widgets[0].value, "WD ViT v3");
console.log("PASS: loader progress updates, routing, read-only and excluded from workflow values");

node.comfyClass = "NAIDetectorCombineLoaderTest";
update({ detail: { node: "7", text: "Downloading face SEGM: 50% (3.3 / 6.6 MiB)" } });
assert.match(widget.value, /50%/);
update({ detail: { node: "7", text: "Ready: SEGM (face BBOX / SAM skipped)" } });
assert.match(widget.value, /SAM skipped/);
assert.equal(widget.serializeValue(), undefined);
