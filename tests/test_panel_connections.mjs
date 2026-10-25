import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

class Element {
    constructor() { this.children = []; this.dataset = {}; this.classList = { add() {} }; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    setAttribute() {}
    addEventListener() {}
    querySelectorAll() { return []; }
}
const app = { ui: { settings: { getSettingValue: () => "en" } } };
const sandbox = { document: { createElement: () => new Element() } };
vm.runInNewContext(["context_controls", "detailer_panel"].map(file => readFileSync(new URL(`../web/${file}.js`, import.meta.url), "utf8")
    .replace(/^import .*;\n/gm, "").replace(/^export /gm, "")).join("\n") + "\nthis.addPanel=addSettingsPanel;", sandbox);

for (const initialLink of [null, 3]) {
    const size = () => [200, 90];
    const prompt = { name: "prompt", type: "text", value: "original", hidden: false, inputEl: { hidden: false }, computeSize: size };
    // Current ComfyUI reports connection suppression through hidden as well.
    const steps = { name: "steps", type: "number", value: 28, hidden: true, visibility: { suppression: { byExtension: false } } };
    const inputs = [{ name: "prompt", widget: { name: "prompt" }, link: initialLink }, { name: "steps", widget: { name: "steps" }, link: 4 }];
    const node = {
        widgets: [prompt, steps], inputs, properties: {}, size: [400, 700],
        addDOMWidget(name, type, element, options) { const w = { name, type, element, options }; this.widgets.push(w); return w; },
        addWidget(type, name, value, callback) { const w = { name, type, value, callback }; this.widgets.push(w); return w; },
        setSize(v) { this.size = v; }, computeSize() { return this.size; }, setDirtyCanvas() {},
    };
    sandbox.addPanel(node, app, { name: "NovelAIGenerator", input: { required: { prompt: ["STRING", { multiline: true }], steps: ["INT"] } } }, { pages: [["prompt", "steps"]], connections: [] });
    const panel = node.rsNaiSettingsPanel;
    assert.equal(steps.type, "number");
    assert.equal(steps.hidden, false, "connected native widgets keep a row even when initially connection-suppressed");
    assert.equal(steps.computeSize()[1], 20);
    for (let cycle = 0; cycle < 3; cycle++) {
        inputs[0].link = 3; panel.refresh();
        assert.equal(prompt.type, "text");
        assert.equal(prompt.hidden, false);
        assert.equal(prompt.computeSize()[1], 20, "connected text gets a compact socket row");
        assert.equal(prompt.inputEl.hidden, true, "native text editor stays inside the panel");
        panel.setMode("classic");
        assert.equal(prompt.computeSize, size, "classic restores the original sizing function");
        assert.equal(steps.computeSize, undefined, "classic restores an absent sizing function");
        assert.equal(steps.hidden, false, "connection suppression must not become extension suppression");
        panel.setMode("panel");
        inputs[0].link = null; panel.refresh();
        assert.equal(prompt.type, "rs-nai-panel-hidden");
        assert.equal(prompt.computeSize()[1], -4, "disconnect releases the socket row");
        panel.setMode("classic");
        assert.equal(prompt.type, "text");
        assert.equal(prompt.hidden, false);
        assert.equal(prompt.inputEl.hidden, false);
        assert.equal(prompt.computeSize, size);
        panel.setMode("panel");
    }
    assert.equal(prompt.value, "original");
    assert.equal(steps.value, 28);
    assert.equal(node.inputs, inputs);
    assert.equal(inputs[1].link, 4);
    assert.equal(node.widgets.filter(w => w.serialize === false).length, 2);
}
console.log("PASS: connected text/numeric socket rows, loaded connections, disconnect/reconnect, classic restoration, values and input identity");
