import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const ctx = new Proxy({}, { get: (o, k) => o[k] ?? (() => {}) });
class Element {
    constructor(tag) { this.tag = tag; this.style = {}; this.children = []; this.events = {}; this.capture = null; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    setAttribute() {}
    addEventListener(name, fn) { this.events[name] = fn; }
    getContext() { return ctx; }
    getBoundingClientRect() { return { left: 0, top: 0, width: 480, height: 240 }; }
    setPointerCapture(id) { this.capture = id; }
    hasPointerCapture(id) { return this.capture === id; }
    releasePointerCapture() { this.capture = null; }
}
const sandbox = { document: { createElement: tag => new Element(tag) } };
vm.runInNewContext(readFileSync(new URL('../web/character_editor.js', import.meta.url), 'utf8').replace('export function', 'function') + '\nthis.editor = addCharacterEditor;', sandbox);
let root, before = 0, after = 0;
const node = {
    properties: {}, widgets: [{ name: 'character_count', value: 22 }], inputs: [],
    graph: { beforeChange: () => before++, afterChange: () => after++ },
    setDirtyCanvas() {}, addDOMWidget(name, type, element) { root = element; const w = { name }; this.widgets.push(w); return w; },
};
for (let i = 1; i <= 22; i++) for (const [suffix, value] of [['', `person ${i}`], ['_x', .5], ['_y', .5], ['_enable', true]]) node.widgets.push({ name: `character${i}${suffix}`, value });
const refresh = n => n.rsNaiEditor?.update();
sandbox.editor(node, refresh);
const [toolbar, canvas, status] = root.children;
assert.equal(toolbar.children[0].children.length, 22);
assert.match(status.textContent, /10명/);
assert.equal(node.widgets.at(-1).serialize, false);
const field = name => node.widgets.find(w => w.name === name);
const row = toolbar.children.find(w => w.textContent?.includes('Row'));
row.events.click();
assert.equal(field('character1_x').value, 0);
assert.equal(field('character22_x').value, 1);
assert.equal(node.widgets.filter(w => w.name.startsWith('character')).length, 89);
node.inputs.push({ name: 'character1_x', link: 7 });
const center = toolbar.children.find(w => w.textContent?.includes('Center'));
center.events.click();
assert.equal(field('character1_x').value, 0, 'connected coordinate must not be overwritten');
assert.equal(field('character22_x').value, .5);
node.inputs = [];
const pointer = (x, y) => ({ button: 0, pointerId: 1, clientX: x, clientY: y, preventDefault() {}, stopPropagation() {} });
canvas.events.pointerdown(pointer(18, 120));
canvas.events.pointermove(pointer(462, 222));
assert.equal(field('character1_x').value, 1);
assert.equal(field('character1_y').value, 1);
canvas.events.pointercancel(pointer(462, 222));
assert.equal(field('character1_x').value, 0);
assert.equal(field('character1_y').value, .5);
assert.equal(before, after, 'each position edit must close its graph transaction');
console.log('PASS: 22-point layout, clipping notice, linked coordinate guard, canceled drag, nonserialized controls');
