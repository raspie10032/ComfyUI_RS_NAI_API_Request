import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

let extension, locale = "ko";
const listeners = new Map();
const node = {widgets:[{name:"request_delay_seconds", value:5}], size:[400,200],
    computeSize:()=>[300,300], setSize(size){this.size=size}, setDirtyCanvas(){}};
const app = {registerExtension(e){extension=e},
    ui:{settings:{getSettingValue:()=>locale}},
    graph:{_nodes:[node],getNodeById:id=>id==="1"?node:null}};
const api = {addEventListener(name, handler){listeners.set(name, handler)}};
const ComfyWidgets = {STRING(n,name){const widget={name,options:{},inputEl:{}};n.widgets.push(widget);return {widget}}};
vm.runInNewContext(readFileSync(new URL("../web/request_delay.js",import.meta.url),"utf8").replace(/^import .*;\n/gm,""), {app,api,ComfyWidgets});
extension.setup();
const update = detail=>listeners.get("rs_nai_request_wait")({detail});
update({node:"missing",remaining:5});assert.equal(node.widgets.length,1);
for (const [lang,label] of [["ko","요청 전 대기"],["ja","リクエスト前の待機"],["en","Waiting before request"]]) {
    locale=lang;update({node:"1",remaining:5,retry:false});
    const widget=node.widgets[1];
    assert.equal(widget.value,`${label}: 5s`);
    assert.equal(widget.serialize,false);assert.equal(widget.options.serialize,false);
    assert.equal(widget.serializeValue(),undefined);assert.equal(widget.inputEl.readOnly,true);
    update({node:"1",remaining:4});assert.equal(node.widgets.length,2);
    update({node:"1",remaining:0});assert.equal(node.widgets.length,1);
}
update({node:"1",remaining:60,retry:true});assert.equal(node.widgets[1].value,"Waiting to retry: 60s");
for (const event of ["execution_start","execution_interrupted","execution_error","execution_success"]) {
    update({node:"1",remaining:5});listeners.get(event)();assert.equal(node.widgets.length,1);
}
assert.equal(node.widgets[0].value,5);
console.log("PASS: request countdown routing, three languages, retry, cleanup, excluded from saved widgets");
