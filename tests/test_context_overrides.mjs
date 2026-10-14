import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const helper = readFileSync(new URL("../web/context_controls.js", import.meta.url), "utf8").replace(/^export /gm, "");
const fields = ["prompt", "negative_prompt", "model", "sampler", "steps", "cfg_scale", "scheduler", "cfg_rescale", "prefer_brownian", "variety_boost", "characterPrompts"];
for (const order of [["combined_detailer", "generation_context"], ["generation_context", "combined_detailer"]]) {
    for (const locale of ["en", "ko", "ja"]) {
        const extensions = [];
        const app = { registerExtension: e => extensions.push(e), ui: { settings: { getSettingValue: () => locale } } };
        const widget = (name, value) => ({ name, value, type: "number", hidden: false, options: {}, inputEl: {}, computeSize: () => [100, 20] });
        const ComfyWidgets = { STRING(node, name) { const w = widget(name, ""); node.widgets.push(w); return { widget: w }; } };
        for (const file of order) vm.runInNewContext(helper + "\n" + readFileSync(new URL(`../web/${file}.js`, import.meta.url), "utf8").replace(/^import .*;\n/gm, ""), { app, ComfyWidgets });
        for (const name of ["NovelAIGenerator", "NAIImg2ImgNode", "NAIMultiCharacterDetailer"]) {
            class Node {
                constructor() {
                    this.widgets = Object.entries({ prompt: "original", negative_prompt: "bad", model: "NAI Diffusion V5 Full", sampler: "k_euler", steps: 17, cfg_scale: 3.5, scheduler: "native", cfg_rescale: 0, prefer_brownian: false, variety_boost: false, seed: 789, strength: .3, limit_opus_free: true, show_advanced: false, use_context_settings: true, context_mode: "inherit_all", ...Object.fromEntries(fields.map(k => [`override_${k}`, false])) }).map(([k,v]) => widget(k,v));
                    this.inputs = [{ name: "nai_context", link: 1 }, { name: "characterPrompts", link: null }];
                    this.size = [400, 400];
                }
                computeSize() { return [400, 400]; }
                setSize(v) { this.size = v; }
                setDirtyCanvas() {}
            }
            for (const ext of extensions) await ext.beforeRegisterNodeDef(Node, { name });
            const node = new Node(); node.onNodeCreated();
            const get = name => node.widgets.find(w => w.name === name);
            const set = (name, value) => { get(name).value = value; get(name).callback?.(value); };
            assert.equal(get("context_mode").hidden, false);
            assert.equal(get("override_steps").hidden, true);
            set("context_mode", "override_selected");
            assert.equal(get("override_steps").hidden, false);
            assert.equal(get("steps").hidden, true);
            for (const field of fields) {
                set(`override_${field}`, true);
                if (get(field)) { assert.equal(get(field).hidden, false, `${name}: ${field}`); assert.equal(get(field).inputEl.hidden, false); }
                node.onConfigure();
                if (get(field)) assert.equal(get(field).hidden, false);
                set(`override_${field}`, false);
                if (get(field)) assert.equal(get(field).hidden, true);
            }
            set("override_characterPrompts", true);
            assert.match(get("rs_nai_context_status").value, /cleared|비웁니다|消去/);
            node.inputs[1].link = 2; node.onConnectionsChange();
            assert.match(get("rs_nai_context_status").value, /replaces|교체|置き換え/);
            set("override_steps", true); set("override_cfg_scale", true);
            const saved = node.widgets.filter(w => w.serialize !== false).map(w => w.value);
            node.onConfigure();
            assert.deepEqual(node.widgets.filter(w => w.serialize !== false).map(w => w.value), saved);
            assert.equal(get("steps").hidden, false); assert.equal(get("prompt").hidden, true);
            set("context_mode", "inherit_all");
            assert.equal(get("steps").hidden, true); assert.equal(get("steps").value, 17);
            set("context_mode", "override_selected");
            assert.equal(get("steps").hidden, false);
            set("use_context_settings", false);
            assert.equal(get("context_mode").hidden, true); assert.equal(get("override_steps").hidden, true);
            assert.equal(get("prompt").hidden, false);
            set("use_context_settings", true);
            node.inputs[0].link = null; node.onConnectionsChange();
            assert.equal(get("context_mode").hidden, true); assert.equal(get("override_steps").hidden, true);
            node.inputs[0].link = 1; node.onConnectionsChange();
            assert.equal(get("steps").hidden, false);
            assert.equal(get("seed").value, 789);
            assert.deepEqual(node.widgets.filter(w => w.serialize !== false).map(w => w.value), saved);
        }
    }
}
console.log("PASS: selective fields, collapsed detailer, switch-back, disconnect/reconnect, character clear warning, serialization, 3 locales, both extension orders");
