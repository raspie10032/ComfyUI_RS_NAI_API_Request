// Offline checks for setting application: no API or browser requests.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const nodes = new Map();
let nextId = 10, added = 0;
function node(type, values) {
    return {type, pos:[500,100], widgets:Object.entries(values).map(([name,value])=>({name,value,options:{}})),
        inputs:[], outputs:[{links:[]}], setDirtyCanvas(){},
        connect(slot,target,index){ target.inputs[index].link=99;app.graph.links[99]={origin_id:this.id};this.outputs[0].links.push(99); },
        disconnectInput(index){this.inputs[index].link=null;}};
}
function characters() {
    const values={character_count:5};
    for(let i=1;i<=22;i++)Object.assign(values,{[`character${i}`]:'old',[`character${i}_uc`]:'old',[`character${i}_x`]:.5,[`character${i}_y`]:.5,...(i>1?{[`character${i}_enable`]:true}:{})});
    return node('CharacterPromptSelect',values);
}
const app={registerExtension(){},graph:{links:{},getNodeById(id){return nodes.get(id)},add(n){n.id=nextId++;nodes.set(n.id,n);added++},beforeChange(){},afterChange(){}}};
const context={app,api:{},LiteGraph:{createNode:characters},console};
vm.createContext(context);
vm.runInContext(readFileSync(new URL('../web/metadata.js',import.meta.url),'utf8').replace(/^import .*;\n/gm,'')+'\nglobalThis.testApply=applyMetadata;globalThis.testQuality=qualityVisibility;',context);
const target=()=>{const n=node('NovelAIGenerator',{prompt:'old',negative_prompt:'old',model:'NAI Diffusion V5 Full',seed:-1,control_after_generate:'randomize',width:832,limit_opus_free:true,save_format:'PNG',webp_quality:90});n.inputs=[{name:'characterPrompts',link:null}];return n};
const value=(n,key)=>n.widgets.find(w=>w.name===key).value;
const fixture=()=>({settings:{prompt:'日本語, 한국어',seed:123,limit_opus_free:false,save_format:'WebP lossy'},characters_present:true,characters:[{prompt:'alice',negative_prompt:'hat',centers:[{x:.3,y:.5}]}],warnings:[]});
let t=target(),data=fixture();
context.testApply(data,t);
assert.equal(value(t,'prompt'),data.settings.prompt);assert.equal(value(t,'seed'),123);assert.equal(value(t,'control_after_generate'),'fixed');assert.equal(value(t,'limit_opus_free'),true);assert.equal(value(t,'save_format'),'PNG');
const c=nodes.get(app.graph.links[t.inputs[0].link].origin_id);
assert.equal(value(c,'character_count'),1);assert.equal(value(c,'character1'),'alice');assert.equal(value(c,'character1_x'),.3);assert.equal(added,1);
context.testApply({...data,characters:[],characters_present:false},t);assert.equal(t.inputs[0].link,99);
c.outputs[0].links.push(100);data.characters[0].prompt='must not overwrite shared';
assert.equal(context.testApply(data,t).characters,false);assert.equal(value(c,'character1'),'alice');
for(const coords of [[{x:.34,y:.5}],[],[{x:.3,y:.5},{x:.7,y:.5}]]){
    t=target();data=fixture();data.characters[0].centers=coords;
    assert.equal(context.testApply(data,t).characters,false);assert.equal(t.inputs[0].link,null);
}
t=target();data=fixture();data.warnings=['automatic_coordinates'];assert.equal(context.testApply(data,t).characters,false);
t=target();t.widgets.find(w=>w.name==='model').value='NAI Diffusion V4 Full';data=fixture();data.characters=Array(7).fill(data.characters[0]);assert.equal(context.testApply(data,t).characters,false);
t=target();t.inputs.push({name:'prompt',link:4});data=fixture();assert.ok(context.testApply(data,t).skipped.includes('prompt'));assert.equal(value(t,'prompt'),'old');
for(const operation of ['detailer','inset']){t=target();context.testApply({...fixture(),operation},t);assert.equal(value(t,'prompt'),'old');assert.equal(t.inputs[0].link,null);}
// Only the backend's explicit whole-image context allows composite restoration.
t=target();data={...fixture(),operation:'detailer',settings_origin:'nai_context'};
context.testApply(data,t);assert.equal(value(t,'prompt'),data.settings.prompt);assert.equal(value(t,'seed'),123);assert.equal(t.inputs[0].link,99);
t=target();context.testApply({...data,operation:'inset'},t);assert.equal(value(t,'prompt'),'old');
t=target();const q=t.widgets.find(w=>w.name==='webp_quality');q.type='number';context.testQuality(t);assert.equal(q.hidden,true);t.widgets.find(w=>w.name==='save_format').value='WebP lossy';context.testQuality(t);assert.equal(q.type,'number');assert.ok(!q.hidden);assert.equal(q.value,90);
console.log('PASS: metadata apply, fixed seed, spending/save preservation, character connection, shared/linked/missing inputs, unsupported coordinates/count, composite/inset exclusion, quality toggle');
// Context-owned values must not be falsely reported as applied by the image loader.
t=target();t.type='NAIImg2ImgNode';t.inputs.push({name:'nai_context',link:5});t.widgets.push({name:'use_context_settings',value:true,options:{}});
const inheritedResult=context.testApply(fixture(),t);
assert.ok(inheritedResult.skipped.includes('prompt'));assert.equal(inheritedResult.characters,false);assert.equal(value(t,'prompt'),'old');assert.equal(value(t,'seed'),123);assert.equal(t.inputs[0].link,null);
