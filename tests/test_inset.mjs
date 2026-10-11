import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

let extension, locale = "ko", fail = false, files = ["one.png"];
const app = { registerExtension(e) { extension = e; }, extensionManager: { setting: { get() { return locale; } } } };
const api = { async fetchApi() { return { ok: !fail, async json() { return { NAICharacterAssetLoad: { input: { required: { asset_file: [files] } } } }; } }; } };
vm.runInNewContext(readFileSync(new URL("../web/inset.js", import.meta.url), "utf8").replace(/^import .*;\n/gm, ""), { app, api });
class Node {
    constructor() { this.widgets = []; this.inputs = []; }
    addCustomWidget(widget) { this.widgets.push(widget); }
    addWidget(type, name, value, callback, options) { const w = { type, name, value, callback, options }; this.widgets.push(w); return w; }
    setDirtyCanvas() {}
    onExecuted() { this.executed = true; }
}
class Prepare extends Node {}
class Load extends Node {}
await extension.beforeRegisterNodeDef(Prepare, { name: "NAIReferenceInset" });
await extension.beforeRegisterNodeDef(Load, { name: "NAICharacterAssetLoad" });
const node = new Prepare();
node.widgets = Object.entries({ canvas_width: 1216, canvas_height: 832, placement: "left", reference_percent: 50 }).map(([name, value]) => ({ name, value }));
node.onNodeCreated();
const size = node.widgets.at(-1);
let lines = [];
const context = { save() {}, restore() {}, fillText(t) { lines.push(t); } };
size.draw(context, node, 400, 10);
assert(lines.some(t => t.includes("608 × 832")));
assert(lines.some(t => t.includes("전체 캔버스")));
node.widgets.find(w => w.name === "placement").value = "top";
node.widgets.find(w => w.name === "reference_percent").value = 33;
lines = [];
locale = "ja";
size.draw(context, node, 400, 10);
assert(lines.some(t => t.includes("1216 × 557")));
assert(lines.some(t => t.includes("切り抜き結果")));
node.onExecuted({ rs_nai_inset_size: [1216,832,608,832] });
assert(node.executed);
node.widgets[0].callback();
assert.equal(node.rsNaiInsetSize, undefined);
node.inputs = [{ name: "canvas_width", link: 3 }];
lines = [];
size.draw(context, node, 400, 10);
assert(lines.some(t => t.includes("実行して確認")));
node.onExecuted({ rs_nai_inset_size: [1216,832,608,832] });
lines = [];
size.draw(context, node, 400, 10);
assert(lines.some(t => t.includes("608 × 832")));
assert.equal(size.serialize, false);
assert.equal(size.serializeValue(), undefined);
const load = new Load();
load.widgets = [{ name: "asset_file", value: "", options: { values: [""] } }];
load.onNodeCreated();
const refresh = load.widgets[1];
await refresh.callback();
assert.equal(load.widgets[0].value, "one.png");
files = ["one.png", "two.png"];
await refresh.callback();
assert.equal(load.widgets[0].value, "one.png");
assert.equal(load.widgets[0].options.values.length, 2);
files = [""];
await refresh.callback();
assert.equal(load.widgets[0].value, "");
assert(refresh.name.includes("保存後"));
fail = true;
await refresh.callback();
assert(refresh.name.includes("接続"));
assert.equal(refresh.serializeValue(), undefined);
console.log("PASS: localized dimensions, linked sizes, nonserialized display, asset refresh/preservation/empty/network failure");
