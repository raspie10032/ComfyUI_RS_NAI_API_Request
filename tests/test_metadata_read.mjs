// Exercise loader lifecycle and out-of-order local metadata responses offline.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../web/metadata.js", import.meta.url), "utf8");
function harness() {
    const timers = new Map(), requests = [];
    let extension, nextTimer = 0, removed = 0, root;
    const document = { createElement(tag) {
        return {tag, style: {}, children: [], textContent: "", append(child) {this.children.push(child);},
            replaceChildren() {this.children = [];}, addEventListener() {}, setAttribute() {}};
    }};
    const app = {registerExtension(value) {extension = value;}, graph: {_nodes: []},
        extensionManager: {setting: {get: () => "en"}}};
    const api = {fetchApi(url, options) {
        return new Promise((resolve, reject) => requests.push({url, options, resolve, reject}));
    }};
    const sandbox = {app, api, document, AbortController,
        setTimeout(fn) {timers.set(++nextTimer, fn); return nextTimer;},
        clearTimeout(id) {timers.delete(id);}};
    vm.runInNewContext(source.replace(/^import .*;\n/gm, ""), sandbox);
    class Loader {
        widgets = [{name: "image", value: "old.png"}, {name: "context_model", value: "from_metadata"}];
        addDOMWidget(name, type, element) {root = element; return {};}
        setSize() {}
        onRemoved() {removed++; return "previous hook";}
    }
    extension.beforeRegisterNodeDef(Loader, {name: "NAILoadImage"});
    const node = new Loader();
    node.onNodeCreated();
    return {node, requests, timers, removed: () => removed,
        content: () => JSON.stringify(root),
        flushTimers() {for (const [id, fn] of timers) {timers.delete(id); fn();}}};
}
const drain = async () => {for (let i = 0; i < 5; i++) await Promise.resolve();};
const respond = (request, marker) => request.resolve({ok: true, json: async () => ({status: "empty", warnings: [marker]})});

// Loading a saved graph configures it before the deferred creation read.
let h = harness();
h.node.onConfigure();
h.flushTimers();
assert.equal(h.requests.length, 1, "one read on graph load, not creation + configuration");
assert.equal(h.requests[0].options.cache, "no-store");
respond(h.requests[0], "current-file"); await drain();
assert.ok(h.content().includes("current-file"));

// A new image cancels the older HTTP read; even a late uncancellable response
// must not replace the latest image's information.
h.node.widgets[0].value = "second.png";
h.node.widgets[0].callback();
const second = h.requests.at(-1);
h.node.widgets[0].value = "third.png";
h.node.widgets[0].callback();
assert.equal(second.options.signal.aborted, true);
assert.ok(!h.content().includes("current-file"), "old apply controls disappear immediately");
respond(h.requests.at(-1), "third-file"); await drain();
respond(second, "stale-second-file"); await drain();
assert.ok(h.content().includes("third-file"));
assert.ok(!h.content().includes("stale-second-file"));

// Changing model rereads context; clearing the image cancels and clears it.
h.node.widgets[1].value = "NAI Diffusion V5 Full";
h.node.widgets[1].callback();
assert.ok(h.requests.at(-1).url.includes("context_model=NAI%20Diffusion%20V5%20Full"));
const modelRead = h.requests.at(-1);
h.node.widgets[0].value = "";
h.node.widgets[0].callback();
assert.equal(modelRead.options.signal.aborted, true);
respond(modelRead, "stale-model"); await drain();
assert.ok(h.content().includes("Select an image"));
assert.ok(!h.content().includes("stale-model"));

// Removal preserves earlier hooks and cancels both deferred and in-flight work.
h = harness();
assert.equal(h.node.onRemoved(), "previous hook"); h.flushTimers();
assert.equal(h.requests.length, 0); assert.equal(h.removed(), 1);
h = harness(); h.flushTimers();
assert.equal(h.requests.length, 1);
const pending = h.requests[0], before = h.content();
h.node.onRemoved(); assert.equal(pending.options.signal.aborted, true);
respond(pending, "removed-node"); await drain();
assert.equal(h.content(), before);

// The same filename can be overwritten; completed reads are never cached.
h = harness(); h.flushTimers();
respond(h.requests[0], "first-content"); await drain();
h.node.widgets[0].callback();
assert.equal(h.requests.length, 2);
h.requests[1].reject(new Error("read failed")); await drain();
assert.ok(h.content().includes("Could not read this image"));
console.log("PASS: single initialization read, cancellation, stale responses, model/empty input, node removal, refresh and failure");
