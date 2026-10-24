// Optional DOM integration test: npm install playwright, then run this file.
// RS_NAI_TEST_PYTHON selects a Python environment with the node's dependencies.
import assert from "node:assert/strict";
import { checkInterfaceModes } from "./interface_mode_checks.mjs";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const directory = fileURLToPath(new URL("../../", import.meta.url));
const schema = JSON.parse(execFileSync(process.env.RS_NAI_TEST_PYTHON ?? "python3", ["-c", `
import sys,json
sys.path.insert(0,'..')
from ComfyUI_RS_NAI_API_Request.combined_detailer import NAIMultiCharacterDetailer
print(json.dumps(NAIMultiCharacterDetailer.INPUT_TYPES()))
`], { cwd: directory, encoding: "utf8" }));

const appModule = `export const app = window.testApp = {
    extensions: [], registerExtension(e) { this.extensions.push(e); }, canvas: {},
    ui: {settings: {getSettingValue: () => window.locale}}, graph: {getNodeById: () => window.node},
};`;
const widgetsModule = `export const ComfyWidgets = {STRING(node, name) {
    const w = node.widget(name, '', 'STRING', {}); w.inputEl = document.createElement('textarea');
    w.onRemove = () => w.inputEl.remove(); node.widgets.push(w); return {widget: w};
}};`;
const apiModule = `export const api = window.testApi = {
    handlers: {}, addEventListener(name, fn) {(this.handlers[name] ??= []).push(fn);},
    dispatch(name, detail) {for (const fn of this.handlers[name] ?? []) fn({detail});},
};`;
const html = `<!doctype html><html lang="ko"><meta charset="utf-8"><style>
body {margin:0;background:#11161e;color:#ddd;font:13px system-ui;padding:32px;}
#node {width:440px;margin:auto;border:1px solid #5c7391;border-radius:12px;background:#292f39;padding:10px;}
.node-title {font-weight:600;background:#35445a;margin:-10px -10px 12px;padding:10px;border-radius:12px 12px 0 0;}
.sockets {color:#b6c2d4;font-size:11px;display:flex;justify-content:space-between;padding:0 6px 14px;}
#panel {height:610px;} .rs-nai-detailer-panel {height:610px;}
</style><div id="node"><div class="node-title">NAI Multi-Character Detailer</div>
<div class="sockets"><span>● image &nbsp; ● detectors &nbsp; ● nai_context</span><span>image ● &nbsp; mask ●</span></div><div id="panel"></div></div>
<script type="module">
window.locale = new URL(location).searchParams.get('locale') ?? 'ko';
const schema = ${JSON.stringify(schema)};
const fields = {...schema.required, ...schema.optional};
const {app} = await import('/scripts/app.js');
const order = new URL(location).searchParams.get('order') === 'reverse'
    ? ['generation_context','combined_detailer'] : ['combined_detailer','generation_context'];
for (const file of [...order,'notices','request_delay']) await import('/web/'+file+'.js');
class Node {
    constructor() {
        this.widgets=[]; this.inputs=[]; this.properties={}; this.size=[440,700];
        this.graph = {beforeChange: () => this.before=(this.before??0)+1, afterChange: () => this.after=(this.after??0)+1};
        for (const [name,[type,options={}]] of Object.entries(fields)) {
            if (Array.isArray(type) || ['STRING','INT','FLOAT','BOOLEAN'].includes(type)) {
                this.widgets.push(this.widget(name, options.default ?? (Array.isArray(type)?type[0]:''), type, options));
                if (name === 'seed') this.widgets.push(this.widget('control_after_generate','fixed',['fixed','increment','decrement','randomize'],{}));
            } else this.inputs.push({name,type,link:['image','detectors','nai_context'].includes(name)?1:null});
        }
        this.originalOrder=this.widgets.map(w=>w.name);
    }
    widget(name,value,type,options) {
        return {name,value,type:Array.isArray(type)?'combo':type==='STRING'?'text':type==='BOOLEAN'?'toggle':'number',
            options:{...options,...(Array.isArray(type)?{values:type}:{})}, computeSize:()=>[350,24],
            callback(){this.calls=(this.calls??0)+1;}};
    }
    addDOMWidget(name,type,element,options) {
        const w={name,type,element,options}; this.widgets.push(w);
        document.getElementById('panel').append(element); return w;
    }
    addWidget(type,name,value,callback,options={}) {
        const w={name,type,value,callback,options,computeSize:()=>[350,24]};this.widgets.push(w);return w;
    }
    computeSize(){return [440, this.widgets.reduce((s,w)=>s+(w.computeSize?.()[1]??24)+4,40)];}
    setSize(value){this.size=value;}
    setDirtyCanvas(){}
}
const nodeData={name:'NAIMultiCharacterDetailer',category:'RS_NovelAI_API',input:schema};
for (const ext of app.extensions) await ext.beforeRegisterNodeDef?.(Node,nodeData);
window.node=new Node(); app.graph._nodes=[window.node]; window.node.onNodeCreated();
for (const ext of app.extensions) ext.setup?.();
window.getWidget=name=>node.widgets.find(w=>w.name===name);
window.change=(name,value)=>{const w=getWidget(name);w.value=value;w.callback?.(value);node.onDrawForeground?.();};
window.save=()=>node.widgets.filter(w=>w.serialize!==false&&w.options?.serialize!==false).map(w=>w.value);
window.ready=true;
</script></html>`;
const server = createServer((req, res) => {
    const path = new URL(req.url, "http://localhost").pathname;
    if (path === "/") { res.setHeader("Content-Type", "text/html; charset=utf-8"); res.end(html); return; }
    res.setHeader("Content-Type", "text/javascript; charset=utf-8");
    const stubs = { "/scripts/app.js": appModule, "/scripts/widgets.js": widgetsModule, "/scripts/api.js": apiModule };
    if (stubs[path]) res.end(stubs[path]);
    else if (/^\/web\/[a-z_]+\.js$/.test(path)) {
        try { res.end(readFileSync(directory + path.slice(1))); }
        catch { res.writeHead(404); res.end(); }
    } else { res.writeHead(404); res.end(); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const browser = await chromium.launch({ headless: true, executablePath: process.env.RS_NAI_CHROMIUM });
let cases = 0;
try {
    for (const order of ["normal", "reverse"]) for (const locale of ["ko", "en", "ja"]) {
        const page = await browser.newPage({viewport:{width:1100,height:1050}});
        const errors = []; page.on("pageerror", e => errors.push(e.message));
        await page.route("**/*", route => route.request().url().startsWith(`http://127.0.0.1:${server.address().port}/`) ? route.continue() : route.abort());
        await page.goto(`http://127.0.0.1:${server.address().port}/?order=${order}&locale=${locale}`);
        await page.waitForFunction(() => window.ready);
        const root = page.locator(".rs-nai-detailer-panel");
        const field = name => root.locator(`[data-field="${name}"]`);
        assert.equal(await root.getByRole("tab").count(), 5);
        assert.equal(await field("model").locator("select").count(), 0, "inherited model is not a misleading editable value");
        await field("strength").locator("input[type=number]").fill("0.37");
        await field("strength").locator("input").dispatchEvent("change");
        assert.equal(await page.evaluate(() => getWidget("strength").value), .37);
        assert.equal(await page.evaluate(() => getWidget("strength").calls), 1);
        assert.equal(await page.evaluate(() => node.before === node.after), true);
        await field("max_regions").locator("input").fill("999");
        await field("max_regions").locator("input").dispatchEvent("change");
        assert.equal(await page.evaluate(() => getWidget("max_regions").value), 64);
        assert.equal(await field("max_regions").locator("input").inputValue(), "64");
        await root.getByRole("tab").nth(1).click();
        await field("dilation").locator("input").fill("12");
        await field("dilation").locator("input").dispatchEvent("change");
        await root.getByRole("tab").nth(2).click();
        await field("matching_mode").locator("select").selectOption("wd14");
        assert.equal(await page.evaluate(() => getWidget("matching_mode").value), "wd14");
        await root.getByRole("tab").nth(3).click();
        await field("context_mode").locator("select").selectOption("override_selected");
        await field("steps").locator("input[type=checkbox]").check();
        await field("steps").locator("input[type=number]").fill("23");
        await field("steps").locator("input[type=number]").dispatchEvent("change");
        await field("prompt").locator("input[type=checkbox]").check();
        const prompt = 'portrait, 2::red hair::, <img src=x onerror="alert(1)">';
        await field("prompt").locator("textarea").fill(prompt);
        await field("prompt").locator("textarea").dispatchEvent("change");
        assert.equal(await page.evaluate(() => getWidget("prompt").value), prompt);
        assert.equal(await root.locator("img").count(), 0);
        // Connected scalar values have no second, competing editor.
        await page.evaluate(() => {node.inputs.push({name:'steps',link:7});node.onConnectionsChange();});
        assert.equal(await field("steps").locator("input[type=number]").count(), 0);
        await page.evaluate(() => {node.inputs=node.inputs.filter(i=>i.name!=='steps');node.onConnectionsChange();});
        assert.equal(await field("steps").locator("input[type=number]").inputValue(), "23");
        await field("characterPrompts").locator("input[type=checkbox]").check();
        assert.match(await field("characterPrompts").textContent(), /clears|비웁니다|消去/);
        const saved = await page.evaluate(() => save());
        await page.evaluate(() => node.onConfigure());
        assert.deepEqual(await page.evaluate(() => save()), saved, "configure preserves serialized values");
        assert.deepEqual(await page.evaluate(() => node.widgets.filter(w=>node.originalOrder.includes(w.name)).map(w=>w.name)), await page.evaluate(() => node.originalOrder));
        assert.equal(await page.evaluate(() => getWidget("rs_nai_detailer_panel").serialize), false);
        await page.evaluate(() => {
            node.onExecuted({rs_nai_notice:['One region skipped <script>alert(1)</script>'],rs_nai_parameters:[{model:'nai-diffusion-5-full-inpainting',action:'infill',width:512,height:512,seed:42,steps:23,characters:2,coordinates:true,negative_mode:'input'}]});
            testApi.dispatch('rs_nai_request_wait',{node:1,remaining:5,retry:false});node.onDrawForeground();
        });
        assert.match(await root.locator('[role=status]').innerText(), /5s/);
        assert.equal(await page.evaluate(() => getWidget("rs_nai_request_wait").hidden), true);
        await root.getByRole("tab").nth(4).click();
        assert.match(await root.locator("pre").allTextContents().then(v=>v.join("\n")), /nai-diffusion-5-full-inpainting/);
        await field("save_format").locator("select").selectOption("WebP lossy");
        assert.equal(await field("webp_quality").count(), 1);
        await field("save_format").locator("select").selectOption("PNG");
        assert.equal(await field("webp_quality").count(), 0);
        await page.evaluate(() => {testApi.dispatch('execution_success',{});node.onDrawForeground();});
        assert.equal(await root.locator('[role=status]').isVisible(), false);
        // Value changes from a queue/another extension are reflected without overwriting them.
        await page.evaluate(() => change('seed',1234));
        await root.getByRole("tab").nth(0).click();
        assert.equal(await field("seed").locator("input").inputValue(), "1234");
        await page.evaluate(() => {node.inputs.find(i=>i.name==='nai_context').link=null;node.onConnectionsChange();});
        assert.equal(await field("model").locator("select").count(), 1);
        assert.equal(await field("prompt").locator("textarea").inputValue(), prompt);
        await page.evaluate(() => {node.inputs.find(i=>i.name==='nai_context').link=1;node.onConnectionsChange();change('context_mode','inherit_all');});
        assert.equal(await field("prompt").locator("textarea").count(), 0);
        // All schema widgets remain available through one of the five tabs.
        assert.deepEqual(await page.evaluate(() => node.widgets.filter(w=>node.originalOrder.includes(w.name)&&!w.hidden).map(w=>w.name)), []);
        await root.getByRole("tab").nth(0).focus(); await page.keyboard.press("ArrowRight");
        assert.equal(await root.getByRole("tab").nth(1).getAttribute("aria-selected"), "true");
        await checkInterfaceModes(page);
        if (process.env.RS_NAI_PANEL_SCREENSHOT && locale === "ko" && order === "normal") {
            await page.evaluate(() => {
                node.onExecuted({rs_nai_notice:[]});
                change('strength', .55); change('seed', -1); change('max_regions',5);
            });
            await root.getByRole("tab").nth(0).click();
            await page.locator("#node").screenshot({path:process.env.RS_NAI_PANEL_SCREENSHOT});
        }
        assert.deepEqual(errors, []);
        await page.close(); cases++;
    }
    console.log(`PASS: detailer panel browser integration (${cases} locale/extension-order combinations); edits, inheritance, sockets, serialization, reports, countdown, keyboard navigation and Panel/Classic switching`);
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
