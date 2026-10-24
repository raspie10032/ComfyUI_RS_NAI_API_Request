// SPDX-License-Identifier: GPL-3.0-only
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),cp=require('child_process');
const source=fs.readFileSync('web/camera_control.js','utf8').replace(/^import[^\n]*\n/gm,'').replaceAll('export function','function');
let extension,locale='en';
const app={extensionManager:{setting:{get:()=>locale}},registerExtension:e=>extension=e};
const context2d=new Proxy({}, {get:(obj,name)=>obj[name] ?? (()=>{}),set:(obj,name,value)=>(obj[name]=value,true)});
const element=()=>({style:{},children:[],listeners:{},append(...items){this.children.push(...items);},setAttribute(){},addEventListener(name,fn){this.listeners[name]=fn;},getContext(){return context2d;},setPointerCapture(){}});
const sandbox={app,document:{createElement:element},console};
vm.runInNewContext(source,sandbox);
const coordinates=[];
for(let i=0;i<301;i++) coordinates.push({azimuth:-180+360*i/300,elevation:-90+180*(i%37)/36,distance:(i%61)/60,roll:-45+90*(i%17)/16,strength:5*(i%13)/12});
const python=cp.spawnSync(process.env.CAMERA_PYTHON||'python',['-c','import json,sys;from camera_control import camera_weights;print(json.dumps([camera_weights(**v) for v in json.load(sys.stdin)]))'],{input:JSON.stringify(coordinates),encoding:'utf8'});
assert.equal(python.status,0,python.stderr);
const expected=JSON.parse(python.stdout);
for(let i=0;i<coordinates.length;i++){
  const actual=sandbox.cameraWeights(coordinates[i]);
  for(const tag of new Set([...Object.keys(expected[i]),...Object.keys(actual)])) assert.ok(Math.abs((actual[tag]||0)-(expected[i][tag]||0))<1e-10,`${i}: ${tag}`);
}
class Node{
 constructor(){this.inputs=[];this.size=[340,200];this.widgets=Object.entries({azimuth:0,elevation:0,distance:.5,roll:0,strength:1.2,enabled:true,weighting:'weighted',prompt_syntax:'ComfyUI'}).map(([name,value])=>({name,value,callback(){return 42;}}));}
 addDOMWidget(name,type,element,options){const w={name,type,element,options};this.widgets.push(w);return w;}
 setSize(size){this.size=size;}
 computeSize(){return [380,700];}
 setDirtyCanvas(){}
 onConfigure(){return 'configured';}
 onExecuted(){return 'executed';}
}
(async()=>{
 await extension.beforeRegisterNodeDef(Node,{name:'RSCameraControl'});
 const node=new Node();node.onNodeCreated();node.onNodeCreated();
 assert.equal(node.widgets.filter(w=>w.name==='rs_camera_editor').length,1);
 const editor=node.rsCameraEditor,custom=node.widgets.at(-1);
 assert.equal(custom.serialize,false);assert.equal(custom.options.serialize,false);
 const [toolbar,canvas,notice,output]=editor.root.children;
 const value=name=>node.widgets.find(w=>w.name===name).value;
 const before=node.widgets.filter(w=>w.serialize!==false).map(w=>[w.name,w.value]);
 for(const lang of ['en','ko','ja','zh','zh-TW']){locale=lang;editor.render();assert.ok(notice.textContent.length>35);assert.ok(toolbar.children[0].textContent);}
 toolbar.children[1].onclick();assert.equal(value('azimuth'),90);
 canvas.onpointerdown({button:0,clientX:0,clientY:0,pointerId:1});
 canvas.onpointermove({clientX:1000,clientY:-1000,preventDefault(){}});canvas.onpointerup();
 assert.equal(value('azimuth'),180);assert.equal(value('elevation'),90);
 canvas.listeners.wheel({deltaY:1,shiftKey:false,preventDefault(){}});assert.equal(value('distance'),.525);
 canvas.listeners.wheel({deltaY:1,shiftKey:true,preventDefault(){}});assert.equal(value('roll'),2);
 canvas.onkeydown({key:'ArrowLeft',preventDefault(){}});assert.equal(value('azimuth'),175);
 node.inputs=[{name:'azimuth',link:1}];sandbox.setCameraValues(node,{azimuth:-100});assert.equal(value('azimuth'),175);
 node.onConnectionsChange();assert.match(notice.textContent,/azimuth/);
 assert.equal(node.onExecuted({camera_caption:['server caption']}),'executed');assert.equal(output.textContent,'server caption');
 node.widgets.find(w=>w.name==='distance').callback();assert.notEqual(output.textContent,'server caption');
 node.inputs=[];toolbar.children.at(-1).onclick();
 assert.deepEqual(node.widgets.filter(w=>w.serialize!==false).map(w=>[w.name,w.value]),before);
 assert.equal(node.onConfigure(),'configured');
 vm.runInNewContext(source,{app,document:{createElement:element},console});
 console.log('Camera: 301 Python/JS curve matches; localized editor, drag/wheel/keyboard, linked controls, reset and serialization passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
