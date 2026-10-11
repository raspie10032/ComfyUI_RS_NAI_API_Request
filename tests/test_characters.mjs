import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

let extension;
const app = { registerExtension(e) { extension = e; } };
vm.runInNewContext(readFileSync(new URL("../web/characters.js", import.meta.url), "utf8").replace(/^import .*;\n/gm, ""), { app });
class Node {
    constructor() {
        this.size = [400, 3000];
        this.widgets = [];
        for (let i = 1; i <= 22; i++) {
            if (i === 6) this.widgets.push({ name: "character_count", value: 5, type: "number" });
            for (const suffix of (i === 1 ? ["", "_uc", "_x", "_y"] : ["_enable", "", "_uc", "_x", "_y"])) {
                this.widgets.push({ name: `character${i}${suffix}`, value: `saved-${i}${suffix}`, type: "text", inputEl: { hidden: false } });
            }
        }
        this.onNodeCreated();
    }
    onNodeCreated() { this.created = true; }
    onConfigure() { this.configured = true; }
    computeSize() { return [320, this.widgets.reduce((h, w) => h + (w.computeSize?.()[1] ?? 20) + 4, 30)]; }
    setSize(size) { this.size = size; }
    setDirtyCanvas() {}
}
await extension.beforeRegisterNodeDef(Node, { name: "CharacterPromptSelect" });
const node = new Node();
const original = node.widgets.map(w => w.value);
const names = node.widgets.map(w => w.name);
const count = node.widgets.find(w => w.name === "character_count");
const height5 = node.size[1];
assert(node.created);
assert.equal(node.widgets.filter(w => w.type !== "rs-nai-hidden").length, 25);
assert.equal(node.widgets.find(w => w.name === "character22").inputEl.hidden, true);
assert.equal(node.widgets.find(w => w.name === "character22").hidden, true);
count.value = 22;
count.callback();
assert(node.size[1] > height5);
assert.equal(node.widgets.filter(w => w.type === "rs-nai-hidden").length, 0);
node.widgets.find(w => w.name === "character22").value = "last edited";
count.value = 1;
count.callback();
assert(node.size[1] < height5);
assert.equal(node.widgets.filter(w => w.type !== "rs-nai-hidden").length, 5);
const saved = node.widgets.map(w => w.value);
const loaded = new Node();
loaded.widgets.forEach((w, i) => w.value = saved[i]);
loaded.onConfigure();
assert(loaded.configured);
assert.equal(loaded.widgets.find(w => w.name === "character22").type, "rs-nai-hidden");
loaded.widgets.find(w => w.name === "character_count").value = 22;
loaded.widgets.find(w => w.name === "character_count").callback();
assert.equal(loaded.widgets.find(w => w.name === "character22").value, "last edited");
assert.equal(loaded.widgets.find(w => w.name === "character22").type, "text");
assert.equal(loaded.widgets.find(w => w.name === "character22").inputEl.hidden, false);
assert.equal(loaded.widgets.find(w => w.name === "character22").hidden, undefined);
assert.deepEqual(loaded.widgets.map(w => w.name), names);
const legacy = new Node();
legacy.widgets.forEach((w, i) => { if (i < 24) w.value = original[i]; });
legacy.onConfigure();
assert.equal(legacy.size[1], height5);
assert.deepEqual(legacy.widgets.slice(0, 24).map(w => w.value), original.slice(0, 24));
const converted = loaded.widgets.find(w => w.name === "character22");
converted.type = "converted-widget";
converted.computeSize = () => [0, -4];
const convertedSize = converted.computeSize;
loaded.widgets.find(w => w.name === "character_count").value = 5;
loaded.onConfigure();
loaded.widgets.find(w => w.name === "character_count").value = 22;
loaded.onConfigure();
assert.equal(converted.type, "converted-widget");
assert.equal(converted.computeSize, convertedSize);
console.log("PASS: 1/5/22 visible slots, resize, preserved order/hidden values, save/reload, legacy values, converted inputs");
