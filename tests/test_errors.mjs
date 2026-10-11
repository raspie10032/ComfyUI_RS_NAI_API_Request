import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

let extension, locale = "ko";
const listeners = new Map();
const api = { addEventListener(type, callback, options) {
    listeners.set(type, { callback, options });
} };
class Node {
    constructor() { this.widgets = [{ name: "prompt", value: "saved" }]; this.size = [400, 300]; }
    onExecuted() { this.original = true; }
    computeSize() { return [200, 200]; }
    setSize(size) { this.size = size; }
    setDirtyCanvas() {}
}
const node = new Node();
const app = {
    registerExtension(value) { extension = value; },
    ui: { settings: { getSettingValue() { return locale; } } },
    graph: { getNodeById() { return node; } },
};
const ComfyWidgets = { STRING(node, name) {
    const widget = { name, options: {}, inputEl: {}, onRemove() { this.removed = true; } };
    node.widgets.push(widget);
    return { widget };
} };
const messages = JSON.parse(readFileSync(new URL("../web/error_messages.json", import.meta.url)));
const source = readFileSync(new URL("../web/errors.js", import.meta.url), "utf8")
    .replace(/^import .*;\n/gm, "").replaceAll("import.meta.url", '"https://test.invalid/errors.js"');
vm.runInNewContext(source, { app, api, ComfyWidgets, URL,
    fetch: async () => ({ ok: true, json: async () => messages }) });
await extension.setup();
await extension.beforeRegisterNodeDef(Node, { name: "NovelAIGenerator", category: "RS_NovelAI_API/Generation" });
assert.equal(listeners.get("execution_error").options.capture, true);
const message = "[RS NAI:NAI_PAYMENT] fallback\n\nTechnical details:\nHTTPError: HTTP 402; server message";
const dispatch = (type = "NovelAIGenerator", text = message) => {
    const event = { detail: { node_type: type, node_id: "1", exception_message: text, traceback: ["original stack"] } };
    listeners.get("execution_error").callback(event);
    return event.detail;
};
for (const choice of ["ko", "ja", "en", "de", "ko-KR"]) {
    locale = choice;
    const detail = dispatch();
    const expected = messages[choice.startsWith("ko") ? "ko" : choice === "ja" ? "ja" : "en"].NAI_PAYMENT[0];
    assert(detail.exception_message.includes(expected));
    assert(detail.exception_message.includes("HTTP 402; server message"));
    assert.deepEqual(detail.traceback, ["original stack"]);
    assert.equal(node.widgets.length, 2);
    const widget = node.widgets[1];
    assert.equal(widget.serialize, false);
    assert.equal(widget.options.serialize, false);
    assert.equal(widget.serializeValue(), undefined);
    assert.equal(widget.inputEl.readOnly, true);
    listeners.get("executing").callback({ detail: "1" });
    assert.equal(widget.removed, true);
    assert.equal(node.widgets.length, 1);
}
assert.equal(dispatch("AnotherNode").exception_message, message);
assert.equal(dispatch("NovelAIGenerator", "unmarked native error").exception_message, "unmarked native error");
locale = "ko";
assert(dispatch("NovelAIGenerator", message.replace("NAI_PAYMENT", "V5_ALLOWANCE")).exception_message.includes(messages.ko.V5_ALLOWANCE[0]));
dispatch(); node.onExecuted();
assert.equal(node.widgets.length, 1);
assert.equal(node.original, true);
console.log("PASS: locale selection, preserved details, capture ordering request, pack isolation, widget lifecycle and no serialization");
