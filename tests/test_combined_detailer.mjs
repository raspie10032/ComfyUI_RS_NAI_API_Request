import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

let extension;
const app = { registerExtension(e) { extension = e; } };
vm.runInNewContext(readFileSync(new URL("../web/combined_detailer.js", import.meta.url), "utf8")
    .replace(/^import .*;\n/gm, ""), { app });

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
const optional = widget("sam_model", "sam_vit_b.pth");
const toggle = widget("show_optional_models", false, "toggle");
const node = await make("NAIDetectorCombineLoaderTest", [widget("face_segm_model", "segm/face.pt"), toggle, optional]);
const values = node.widgets.map(w => w.value);
assert.equal(optional.hidden, true);
assert.equal(optional.value, "sam_vit_b.pth");
toggle.value = true; toggle.callback(true);
assert.equal(optional.hidden, false); assert.equal(optional.type, "combo");
toggle.value = false; toggle.callback(false); node.onConfigure();
assert.deepEqual(node.widgets.map(w => w.value), values);
assert.equal(optional.options.serialize, undefined);
toggle.value = true; node.onConfigure(); assert.equal(optional.hidden, false);

const advanced = widget("show_advanced", false, "toggle");
const format = widget("save_format", "PNG");
const quality = widget("webp_quality", 92, "number");
const converted = widget("steps", 28, "converted-widget");
const notice = widget("notice", "error", "text"); notice.options.serialize = false;
const detail = await make("NAICombinedFaceDetailerTest", [advanced, format, quality, converted, notice, widget("limit_opus_free", true, "toggle")]);
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
