import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

let extension, locale = "en";
const app = { registerExtension(e) { extension = e; }, ui: { settings: { getSettingValue: () => locale } } };
const ComfyWidgets = { STRING(node, name) {
    const value = { ...widget(name, "", "text"), inputEl: {}, onRemove() { this.removed = true; } };
    node.widgets.push(value);
    return { widget: value };
} };
vm.runInNewContext(readFileSync(new URL("../web/combined_detailer.js", import.meta.url), "utf8")
    .replace(/^import .*;\n/gm, ""), { app, ComfyWidgets });

function widget(name, value, type = "combo") {
    return { name, value, type, hidden: false, options: {}, computeSize: () => [100, 20] };
}
async function make(name, widgets) {
    class Node {
        constructor() { this.widgets = widgets; this.size = [400, 200]; }
        computeSize() { return [300, 100]; }
        setSize(value) { this.size = value; }
        setDirtyCanvas() {}
    }
    await extension.beforeRegisterNodeDef(Node, { name });
    const node = new Node(); node.onNodeCreated(); return node;
}
const optional = widget("eye_bbox_model", "bbox/eye.pt");
const sam = widget("sam_model", "sam_vit_b.pth");
const bbox = widget("face_bbox_model", "OFF");
const toggle = widget("show_optional_models", false, "toggle");
const node = await make("NAIDetectionCombineLoader", [widget("face_segm_model", "segm/face.pt"), toggle, sam, bbox, optional]);
assert.equal(sam.hidden, false); assert.equal(bbox.hidden, false);
const values = node.widgets.map(w => w.value);
assert.equal(optional.hidden, true);
assert.equal(optional.value, "bbox/eye.pt");
toggle.value = true; toggle.callback(true);
assert.equal(optional.hidden, false); assert.equal(optional.type, "combo");
toggle.value = false; toggle.callback(false); node.onConfigure();
assert.deepEqual(node.widgets.map(w => w.value), values);
assert.equal(optional.options.serialize, undefined);
toggle.value = true; node.onConfigure(); assert.equal(optional.hidden, false);
sam.value = "None"; bbox.value = "None"; optional.value = "None";
node.onConfigure();
assert.deepEqual([sam.value, bbox.value, optional.value], ["OFF", "OFF", "OFF"]);
assert.equal(node.widgets[0].value, "segm/face.pt");

const plan = node.widgets.find(w => w.name === "rs_detector_plan");
assert.match(plan.value, /SEGM only/);
assert.equal(plan.hidden, false);
assert.equal(plan.inputEl.readOnly, true);
assert.equal(plan.serializeValue(), undefined);
assert.equal(plan.options.serialize, false);
const progress = ComfyWidgets.STRING(node, "rs_tagger_status").widget;
progress.value = "Ready: SEGM";
const segm = node.widgets[0];
segm.value = "OFF"; segm.callback("OFF");
assert.match(plan.value, /Select SEGM or BBOX/);
assert.equal(progress.removed, true);
assert.equal(node.widgets.includes(progress), false);
bbox.value = "bbox/hand.pt"; bbox.callback(bbox.value);
assert.match(plan.value, /BBOX rectangles/);
sam.value = "sam_vit_b.pth"; sam.callback(sam.value);
assert.match(plan.value, /BBOX \+ SAM/);
segm.value = "segm/face.pt"; segm.callback(segm.value);
assert.match(plan.value, /BBOX \/ SAM are skipped/);
assert.equal(sam.value, "sam_vit_b.pth");
assert.equal(bbox.value, "bbox/hand.pt");
for (const [code, expected] of [["ko", /SEGM만 사용/], ["ja", /SEGMのみ使用/]]) {
    locale = code; node.onConfigure(); assert.match(plan.value, expected);
}
node.inputs = [{ name: "face_segm_model", link: 10 }];
locale = "en"; node.onConnectionsChange();
assert.match(plan.value, /Connected model inputs/);
node.inputs[0].link = null; node.onConnectionsChange();
assert.match(plan.value, /SEGM only/);

const advanced = widget("show_advanced", false, "toggle");
const format = widget("save_format", "PNG");
const quality = widget("webp_quality", 92, "number");
const converted = widget("steps", 28, "converted-widget");
const notice = widget("notice", "error", "text"); notice.options.serialize = false;
const detail = await make("NAIMultiCharacterDetailer", [advanced, format, quality, converted, notice, widget("limit_opus_free", true, "toggle")]);
assert.equal(notice.hidden, false); assert.equal(converted.type, "converted-widget");
assert.equal(detail.widgets.at(-1).hidden, false);
advanced.value = true; advanced.callback(true);
assert.equal(format.hidden, false); assert.equal(quality.hidden, true);
format.value = "WebP lossy"; format.callback(format.value); assert.equal(quality.hidden, false);
advanced.value = false; advanced.callback(false); assert.equal(quality.hidden, true);
advanced.value = true; advanced.callback(true); assert.equal(quality.hidden, false);
format.value = "PNG"; format.callback(format.value); assert.equal(quality.hidden, true);
assert.equal(quality.value, 92);
console.log("PASS: optional controls fold/restore without altering saved inputs; connected inputs and notices retained; WebP quality conditional");
