import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

for (const order of [["combined_detailer", "generation_context"], ["generation_context", "combined_detailer"]]) {
    const extensions = [];
    const app = { registerExtension(e) { extensions.push(e); }, ui: { settings: { getSettingValue: () => "ko" } } };
    const widget = (name, value) => ({ name, value, type: "number", hidden: false, options: {}, computeSize: () => [100, 20] });
    const ComfyWidgets = { STRING(node, name) {
        const w = { ...widget(name, ""), inputEl: {} };
        node.widgets.push(w); return { widget: w };
    } };
    for (const file of order) vm.runInNewContext(readFileSync(new URL(`../web/${file}.js`, import.meta.url), "utf8").replace(/^import .*;\n/gm, ""), { app, ComfyWidgets });
    for (const name of ["NAIImg2ImgNode", "NAICombinedFaceDetailerTest"]) {
        class Node {
            constructor() {
                this.widgets = Object.entries({ prompt: "keep me", model: "NAI Diffusion V5 Full", seed: 222,
                    width: 768, strength: .3, sampler: "k_euler", show_advanced: false,
                    limit_opus_free: true, use_context_settings: true }).map(([k, v]) => widget(k, v));
                this.inputs = [{ name: "nai_context", link: null }]; this.size = [300, 200];
            }
            computeSize() { return [300, 100]; }
            setSize(s) { this.size = s; }
            setDirtyCanvas() {}
        }
        for (const e of extensions) await e.beforeRegisterNodeDef(Node, { name });
        const n = new Node(); n.onNodeCreated();
        const get = key => n.widgets.find(w => w.name === key);
        const values = n.widgets.filter(w => w.serialize !== false).map(w => w.value);
        assert.equal(get("prompt").hidden, false);
        n.inputs[0].link = 42; n.onConnectionsChange();
        for (const key of ["prompt", "model", "sampler"]) assert.equal(get(key).hidden, true);
        for (const key of ["seed", "strength", "limit_opus_free", "use_context_settings"]) assert.equal(get(key).hidden, false);
        get("show_advanced").value = true; get("show_advanced").callback?.();
        assert.equal(get("prompt").hidden, true);
        n.onConfigure(); assert.equal(get("model").hidden, true);
        get("use_context_settings").value = false; get("use_context_settings").callback();
        assert.equal(get("prompt").hidden, false);
        get("use_context_settings").value = true; get("use_context_settings").callback();
        n.inputs[0].link = null; n.onConnectionsChange();
        assert.equal(get("prompt").value, "keep me"); assert.equal(get("prompt").hidden, false);
        get("show_advanced").value = false;
        assert.deepEqual(n.widgets.filter(w => w.serialize !== false).map(w => w.value), values);
        assert.equal(get("rs_nai_context_status").serializeValue(), undefined);
        assert.equal(n.widgets.filter(w => w.name === "rs_nai_context_status").length, 1);
    }
}
console.log("PASS: context folding, independent seeds, manual fallback and extension load order");
