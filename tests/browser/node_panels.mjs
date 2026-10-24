// Optional DOM regression. Uses real INPUT_TYPES and production extensions with a
// small ComfyUI host. No NAI calls, model loads or live ComfyUI server required.
import assert from "node:assert/strict";
import { checkInterfaceModes } from "./interface_mode_checks.mjs";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";
const { chromium } = createRequire(import.meta.url)("playwright");
const directory = fileURLToPath(new URL("../../", import.meta.url));
const names = ["NovelAIGenerator", "NAIImg2ImgNode", "NAIInpaintNode", "NAIReferenceInsetGenerate", "NAIFaceDetailerNode", "NAIFaceDetailerSegmNode", "NAIDetectionCombineLoader", "RSWDTaggerLoader", "NAIVibeTransfer", "NAIPreciseReference", "NAIReferenceInset", "NAICharacterAssetSave"];
const schemas = JSON.parse(execFileSync(process.env.RS_NAI_TEST_PYTHON ?? "python3", ["-c", `
import sys,json
sys.path.insert(0,'..')
from ComfyUI_RS_NAI_API_Request import NODE_CLASS_MAPPINGS,detector_bundle
# Only installed model discovery needs the running ComfyUI host. Keep the real
# server schema and catalog, with an empty installed-model inventory.
detector_bundle.installed_models=lambda:([],[])
detector_bundle.installed_sams=lambda:[]
print(json.dumps({n:NODE_CLASS_MAPPINGS[n].INPUT_TYPES() for n in ${JSON.stringify(names)}}))
`], { cwd: directory, encoding: "utf8" }));
for (const name of names) assert.ok(schemas[name], name);
const modules = {
    "/scripts/app.js": `export const app=window.testApp={extensions:[],registerExtension(e){this.extensions.push(e)},canvas:{},ui:{settings:{getSettingValue:()=>window.locale}},extensionManager:{setting:{get:()=>window.locale}},graph:{getNodeById:()=>window.node}};`,
    "/scripts/api.js": `export const api=window.testApi={handlers:{},addEventListener(n,f){(this.handlers[n]??=[]).push(f)},dispatch(n,detail){for(const f of this.handlers[n]??[])f({detail})}};`,
    "/scripts/widgets.js": `export const ComfyWidgets={STRING(node,name){const w=node.widget(name,'','STRING',{});w.inputEl??=document.createElement('textarea');w.onRemove=()=>w.inputEl.remove();node.widgets.push(w);return{widget:w}}};`,
};
const html = `<!doctype html><meta charset="utf-8"><style>
body{margin:0;background:#10151e;color:#ddd;font:13px system-ui;padding:24px}#node{width:440px;margin:auto;border:1px solid #5c7391;border-radius:12px;background:#292f39;padding:10px}#title{font-weight:600;padding:8px 4px 15px}#native textarea{height:24px}
</style><div id="node"><div id="title"></div><div id="native"></div><div id="panel"></div></div>
<script type="module">
const params=new URL(location).searchParams; window.locale=params.get('locale');
const schemas=${JSON.stringify(schemas)}, name=params.get('name'), schema=schemas[name];
document.getElementById('title').textContent=name;
const {app}=await import('/scripts/app.js');
let files=['generation_context','combined_detailer','metadata','notices','request_delay','tagger_progress','inset','node_panels'];
if(params.get('order')==='reverse')files.reverse();
for(const f of files)await import('/web/'+f+'.js');
class Node{
 constructor(){this.id=1;this.comfyClass=name;this.widgets=[];this.inputs=[];this.properties={};this.size=[440,700];this.graph={beforeChange:()=>this.before=(this.before??0)+1,afterChange:()=>this.after=(this.after??0)+1};
 for(const [n,[t,o={}]]of Object.entries({...schema.required,...schema.optional})){
 if(Array.isArray(t)||['STRING','INT','FLOAT','BOOLEAN'].includes(t)){const w=this.widget(n,o.default??(Array.isArray(t)?t[0]:''),t,o);this.widgets.push(w);if(n==='seed')this.widgets.push(this.widget('control_after_generate','fixed',['fixed','increment','decrement','randomize'],{}));}
 else this.inputs.push({name:n,type:t,link:['image','nai_context','detectors'].includes(n)?1:null});}
 this.originalOrder=this.widgets.map(w=>w.name);this.originalValues=this.widgets.map(w=>w.value);}
 widget(name,value,type,options){const w={name,value,type:Array.isArray(type)?'combo':type==='STRING'?'text':type==='BOOLEAN'?'toggle':'number',options:{...options,...(Array.isArray(type)?{values:type}:{})},computeSize:()=>[350,24],callback(){this.calls=(this.calls??0)+1}};
 if(type==='STRING'){w.inputEl=document.createElement('textarea');document.getElementById('native').append(w.inputEl)}return w}
 addWidget(type,name,value,callback,options={}){const w={name,type,value,callback,options,computeSize:()=>[350,24]};this.widgets.push(w);return w}
 addCustomWidget(w){this.widgets.push(w);return w}
 addDOMWidget(name,type,element,options){const w={name,type,element,options};this.widgets.push(w);element.style.height=options.getMinHeight()+'px';document.getElementById('panel').append(element);return w}
 computeSize(){return[440,this.widgets.reduce((s,w)=>s+(w.computeSize?.()[1]??24)+4,40)]}setSize(v){this.size=v}setDirtyCanvas(){}
}
const data={name,category:'RS_NovelAI_API',input:schema};
for(const e of app.extensions)await e.beforeRegisterNodeDef?.(Node,data);
window.node=new Node();app.graph._nodes=[node];node.onNodeCreated();for(const e of app.extensions)e.setup?.();
window.getWidget=n=>node.widgets.find(w=>w.name===n);
window.change=(n,v)=>{const w=getWidget(n);w.value=v;w.callback?.(v);node.onDrawForeground?.()};
window.save=()=>node.widgets.filter(w=>w.serialize!==false&&w.options?.serialize!==false).map(w=>w.value);
window.ready=true;
</script>`;
const server=createServer((req,res)=>{
    const path=new URL(req.url,"http://localhost").pathname;
    res.setHeader("Content-Type",path==="/"?"text/html; charset=utf-8":"text/javascript; charset=utf-8");
    if(path==="/")res.end(html);
    else if(modules[path])res.end(modules[path]);
    else if(/^\/web\/[a-z_]+\.js$/.test(path)) {try{res.end(readFileSync(directory+path.slice(1)))}catch{res.writeHead(404);res.end()}}
    else{res.writeHead(404);res.end()}
});
await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
const browser=await chromium.launch({headless:true,executablePath:process.env.RS_NAI_CHROMIUM});
let cases=0;
try{
    for(const order of ["normal","reverse"])for(const locale of ["ko","en","ja"])for(const name of names){
        const page=await browser.newPage({viewport:{width:1000,height:1100}}),errors=[];
        page.on("pageerror",e=>errors.push(e.message));
        await page.route("**/*",r=>r.request().url().startsWith(`http://127.0.0.1:${server.address().port}/`)?r.continue():r.abort());
        await page.goto(`http://127.0.0.1:${server.address().port}/?name=${name}&locale=${locale}&order=${order}`);
        await page.waitForFunction(()=>window.ready);
        const root=page.locator(".rs-nai-settings-panel"),field=n=>root.locator(`[data-field="${n}"]`);
        assert.equal(await root.count(),1,name);
        assert.deepEqual(await page.evaluate(()=>save()),await page.evaluate(()=>node.originalValues),`${name}: creation preserves values`);
        assert.equal(await page.evaluate(()=>getWidget('rs_nai_settings_panel').serialize),false);
        const tabs=await root.getByRole('tab').count(), reachable=new Set();
        for(let tab=0;tab<Math.max(1,tabs);tab++){
            if(tabs)await root.getByRole('tab').nth(tab).click();
            for(const n of await root.locator('[data-field]').evaluateAll(els=>els.map(e=>e.dataset.field)))reachable.add(n);
        }
        const originals=await page.evaluate(()=>node.originalOrder);
        for(const n of originals)if(!n.startsWith('override_')&&!['show_optional_models','show_advanced','webp_quality'].includes(n))assert.ok(reachable.has(n),`${name}: ${n} reachable`);
        const before=await page.evaluate(()=>save());await page.evaluate(()=>node.onConfigure());
        assert.deepEqual(await page.evaluate(()=>save()),before,`${name}: reload preserves values`);
        assert.deepEqual(await page.evaluate(()=>node.widgets.filter(w=>node.originalOrder.includes(w.name)).map(w=>w.name)),originals);
        assert.deepEqual(await page.evaluate(()=>node.widgets.filter(w=>node.originalOrder.includes(w.name)&&!w.hidden).map(w=>w.name)),[],`${name}: no duplicated native settings`);
        assert.equal(await page.locator('#native textarea:not([hidden])').count(),0,`${name}/${order}: native text visibility`);
        if(['NovelAIGenerator','NAIImg2ImgNode'].includes(name)){
            await root.getByRole('tab').nth(0).click();
            assert.equal(await field('model').locator('select').count(),0,'context values read-only');
            await field('context_mode').locator('select').selectOption('override_selected');
            await root.getByRole('tab').nth(1).click();
            await field('prompt').locator('input[type=checkbox]').check();
            await field('prompt').locator('textarea').fill('2::red hair::, <script>bad()</script>');
            await field('prompt').locator('textarea').dispatchEvent('change');
            assert.match(await page.evaluate(()=>getWidget('prompt').value),/red hair/);
            await field('characterPrompts').locator('input[type=checkbox]').check();
            assert.match(await field('characterPrompts').textContent(),/비웁니다|clears|消去/);
            await page.evaluate(()=>{node.inputs.find(i=>i.name==='nai_context').link=null;node.onConnectionsChange()});
            await root.getByRole('tab').nth(0).click();
            await field('model').locator('select').selectOption('NAI Diffusion V5 Full — Medium Effort');
            await root.getByRole('tab').nth(2).click();
            assert.equal(await field('steps').locator('input[type=number]').count(),0,'Medium fixed');
            assert.match(await field('steps').textContent(),/14/);
            assert.equal(await page.evaluate(()=>getWidget('steps').value),28,'fixed display keeps saved setting');
            await page.evaluate(()=>change('model','NAI Diffusion V5 Full'));
            await field('steps').locator('input[type=number]').fill('31');await field('steps').locator('input[type=number]').dispatchEvent('change');
            assert.equal(await page.evaluate(()=>getWidget('steps').value),31);
            await page.evaluate(()=>{node.inputs.push({name:'steps',link:4});node.onConnectionsChange()});
            assert.equal(await field('steps').locator('input[type=number]').count(),0);
            await page.evaluate(()=>{node.inputs=node.inputs.filter(i=>i.name!=='steps');node.onConnectionsChange()});
            assert.equal(await field('steps').locator('input[type=number]').inputValue(),'31');
        }
        if(reachable.has('save_format')){
            await root.getByRole('tab').nth(tabs-1).click();
            await field('save_format').locator('select').selectOption('WebP lossy');
            assert.equal(await field('webp_quality').count(),1);
            await field('save_format').locator('select').selectOption('PNG');assert.equal(await field('webp_quality').count(),0);
        }
        if(name==='NAIDetectionCombineLoader'){
            assert.match((await root.locator('pre').allTextContents()).join(' '),/SEGM/);
            await field('face_segm_model').locator('select').selectOption('OFF');
            assert.match((await root.locator('pre').allTextContents()).join(' '),/Select|선택|選択/);
            await page.evaluate(()=>testApi.dispatch('rs_nai_tagger_progress',{node:1,text:'Download 42%'}));
            await page.evaluate(()=>node.onDrawForeground?.());
            assert.match((await root.locator('pre').allTextContents()).join(' '),/42%/);
        }
        if(name==='NAIReferenceInset'){
            await field('canvas_width').locator('input').fill('1024');await field('canvas_width').locator('input').dispatchEvent('change');
            assert.equal(await page.evaluate(()=>getWidget('canvas_width').value),1024);
            assert.ok(await page.evaluate(()=>getWidget('rs_nai_inset_dimensions')),'native preview retained');
        }
        if(name==='NAICharacterAssetSave'){
            await field('name').locator('input').fill('sample');await field('name').locator('input').dispatchEvent('change');
            assert.equal(await page.evaluate(()=>getWidget('name').value),'sample');
        }
        await page.evaluate(()=>node.onExecuted?.({rs_nai_notice:['<img src=x onerror=bad()>']}));
        await page.evaluate(()=>node.onDrawForeground?.());
        assert.equal(await root.locator('img,script:not([type=module])').count(),0);
        const saved=await page.evaluate(()=>save());await page.evaluate(()=>node.onConfigure());assert.deepEqual(await page.evaluate(()=>save()),saved);
        await checkInterfaceModes(page);
        if(process.env.RS_NAI_PANELS_SCREENSHOTS&&locale==='ko'&&order==='normal'){
            await page.evaluate(()=>{node.onExecuted?.({rs_nai_notice:[]});const ctx=node.inputs.find(i=>i.name==='nai_context');if(ctx){ctx.link=null;node.onConnectionsChange?.()}});
            if(tabs)await root.getByRole('tab').nth(0).click();
            await page.locator('#node').screenshot({path:`${process.env.RS_NAI_PANELS_SCREENSHOTS}/${name}.png`});
        }
        assert.deepEqual(errors,[],name);await page.close();cases++;
    }
    console.log(`PASS: ${cases} browser cases (12 node types × 3 languages × 2 extension orders): field coverage, editing, original widget order/values, reload, inherited/connected controls, Medium, WebP, progress, preview and Panel/Classic switching`);
}finally{await browser.close();await new Promise(resolve=>server.close(resolve))}
