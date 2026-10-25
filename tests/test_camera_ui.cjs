// SPDX-License-Identifier: GPL-3.0-only
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),cp=require('child_process');
const source=fs.readFileSync('web/camera_control.js','utf8').replace(/^import[^\n]*\n/gm,'').replaceAll('export function','function');
const extensions=[];let locale='en';
const app={extensionManager:{setting:{get:()=>locale}},registerExtension:e=>extensions.push(e)};
const context2d=new Proxy({}, {get:(obj,name)=>obj[name] ?? (()=>{}),set:(obj,name,value)=>(obj[name]=value,true)});
const element=()=>({style:{},children:[],listeners:{},append(...items){this.children.push(...items);},setAttribute(){},addEventListener(name,fn){this.listeners[name]=fn;},getContext(){return context2d;},setPointerCapture(){}});
const sandbox={app,document:{createElement:element},console,atob:s=>Buffer.from(s,'base64').toString('binary')};
vm.runInNewContext(source,sandbox);
const coordinates=[];
for(let i=0;i<301;i++) coordinates.push({azimuth:-180+360*i/300,elevation:-90+180*(i%37)/36,distance:(i%61)/60,roll:-45+90*(i%17)/16,strength:5*(i%13)/12});
const python=cp.spawnSync(process.env.CAMERA_PYTHON||'python',['-c','import json,sys;from camera_control import camera_weights;print(json.dumps([camera_weights(**v) for v in json.load(sys.stdin)]))'],{input:JSON.stringify(coordinates),encoding:'utf8'});
assert.equal(python.status,0,python.stderr);
const expected=JSON.parse(python.stdout);
const captionProbes=coordinates.flatMap(v=>['ComfyUI','NovelAI'].flatMap(syntax=>['weighted','plain'].map(weighting=>({weights:sandbox.cameraWeights(v),syntax,weighting}))));
const captionsPython=cp.spawnSync(process.env.CAMERA_PYTHON||'python',['-c','import json,sys;from camera_control import camera_caption;print(json.dumps([camera_caption(**v) for v in json.load(sys.stdin)]))'],{input:JSON.stringify(captionProbes),encoding:'utf8'});
assert.equal(captionsPython.status,0,captionsPython.stderr);
assert.deepEqual(captionProbes.map(p=>sandbox.cameraCaption(p.weights,p.syntax,p.weighting)),JSON.parse(captionsPython.stdout));

const seeds=[0,1,12345,0x7fffffff,0xffffffff];
const randomProbes=['balanced','full'].flatMap(mode=>seeds.map(seed=>({mode,seed})));
const randomPython=cp.spawnSync(process.env.CAMERA_PYTHON||'python',['-c','import json,sys;from camera_control import random_camera;print(json.dumps([random_camera(**v) for v in json.load(sys.stdin)]))'],{input:JSON.stringify(randomProbes),encoding:'utf8'});
assert.equal(randomPython.status,0,randomPython.stderr);
assert.deepEqual(JSON.parse(JSON.stringify(randomProbes.map(v=>sandbox.randomCamera(v.mode,v.seed)))),JSON.parse(randomPython.stdout));
const layoutProbes=coordinates.map((v,i)=>[.2,.7,v.distance,v.roll,[1,1.5,2/3][i%3]]);
const layoutPython=cp.spawnSync(process.env.CAMERA_PYTHON||'python',['-c','import json,sys;from camera_layout import project,framing;print(json.dumps([project(x,y,framing(d,r,a)) for x,y,d,r,a in json.load(sys.stdin)]))'],{input:JSON.stringify(layoutProbes),encoding:'utf8'});
assert.equal(layoutPython.status,0,layoutPython.stderr);
JSON.parse(layoutPython.stdout).forEach((p,i)=>p.forEach((v,j)=>assert.ok(Math.abs(v-sandbox.projectLayout(...layoutProbes[i])[j])<1e-12)));

const perspectiveProbes=coordinates.filter(v=>Math.abs(Math.cos(v.azimuth*Math.PI/180)*Math.cos(v.elevation*Math.PI/180))>1e-6).flatMap((v,i)=>[[.2,.3],[.8,.7]].map(([x,y])=>[x,y,v.distance,v.roll,[1,1.5,2/3][i%3],v.azimuth,v.elevation]));
const perspectivePython=cp.spawnSync(process.env.CAMERA_PYTHON||'python',['-c','import json,sys;from camera_layout import project,perspective_framing;print(json.dumps([project(x,y,perspective_framing(d,r,a,yaw,pitch)) for x,y,d,r,a,yaw,pitch in json.load(sys.stdin)]))'],{input:JSON.stringify(perspectiveProbes),encoding:'utf8'});
assert.equal(perspectivePython.status,0,perspectivePython.stderr);
JSON.parse(perspectivePython.stdout).forEach((p,i)=>p.forEach((v,j)=>assert.ok(Math.abs(v-sandbox.projectLayout(...perspectiveProbes[i],true)[j])<1e-12)));
for(let i=0;i<coordinates.length;i++){
  const actual=sandbox.cameraWeights(coordinates[i]);
  for(const tag of new Set([...Object.keys(expected[i]),...Object.keys(actual)])) assert.ok(Math.abs((actual[tag]||0)-(expected[i][tag]||0))<1e-10,`${i}: ${tag}`);
}
class Node{
 constructor(){this.inputs=[];this.size=[340,200];this.widgets=Object.entries({azimuth:0,elevation:0,distance:.5,roll:0,strength:1.2,enabled:true,weighting:'weighted',prompt_syntax:'ComfyUI',random_mode:'off',random_seed:0,layout_sync:'fixed',canvas_aspect:1}).map(([name,value])=>({name,value,callback(){return 42;}}));}
 addDOMWidget(name,type,element,options){const w={name,type,element,options};this.widgets.push(w);return w;}
 setSize(size){this.size=size;}
 computeSize(){return [380,700];}
 setDirtyCanvas(){}
 onConfigure(){return 'configured';}
 onExecuted(){return 'executed';}
}
(async()=>{
 const extension=extensions.find(e=>e.name==='RS.CameraControl');
 await extension.beforeRegisterNodeDef(Node,{name:'RSCameraControl'});
 class NAINode extends Node {}
 const nai=extensions.find(e=>e.name==='RS.NAICameraControl');
 assert.ok(nai);
 await nai.beforeRegisterNodeDef(NAINode,{name:'NAICameraControl'});
 const naiNode=new NAINode();naiNode.onNodeCreated();naiNode.onNodeCreated();
 assert.equal(naiNode.widgets.filter(w=>w.name==='rs_camera_editor').length,1);
 // An old companion editor guard cannot suppress the NAI-specific editor.
 const prior=[];const oldFirst={app:{...app,registerExtension:e=>prior.push(e)},document:{createElement:element},console};
 vm.runInNewContext('globalThis[Symbol.for("raspie.camera.editor")]=true;'+source,oldFirst);
 assert.deepEqual(prior.map(e=>e.name),['RS.NAICameraControl']);
 const node=new Node();node.onNodeCreated();node.onNodeCreated();
 assert.equal(node.widgets.filter(w=>w.name==='rs_camera_editor').length,1);
 const editor=node.rsCameraEditor,custom=node.widgets.at(-1);
 assert.equal(custom.serialize,false);assert.equal(custom.options.serialize,false);
 const [toolbar,canvas,notice,output,layoutNotice,layoutCanvas]=editor.root.children;
 const value=name=>node.widgets.find(w=>w.name===name).value;
 const before=node.widgets.filter(w=>w.serialize!==false).map(w=>[w.name,w.value]);
 sandbox.setCameraValues(node,{prompt_syntax:'NovelAI'});assert.match(output.textContent,/::from front::/);
 sandbox.setCameraValues(node,{weighting:'plain'});assert.equal(output.textContent,'from front, medium shot');
 sandbox.setCameraValues(node,{strength:0});assert.match(output.textContent,/OFF/);
 sandbox.setCameraValues(node,{strength:1.2,weighting:'weighted',prompt_syntax:'ComfyUI'});
 node.inputs=[{name:'context',link:12}];editor.render();assert.match(notice.textContent,/Context syntax/);
 node.onExecuted({camera_caption:['NAI caption'],camera_syntax:['NovelAI']});
 sandbox.setCameraValues(node,{distance:.75});assert.match(output.textContent,/::full body::/);
 node.onConnectionsChange();assert.match(notice.textContent,/Context syntax/);
 node.inputs=[];sandbox.setCameraValues(node,{distance:.5});

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
 toolbar.children.at(-2).onclick();assert.equal(value('random_mode'),'balanced');assert.ok(Number.isInteger(value('random_seed')));
 const sampled=sandbox.randomCamera('balanced',value('random_seed'));
 canvas.onpointerdown({button:0,clientX:0,clientY:0,pointerId:2});
 canvas.onpointermove({clientX:2,clientY:0,preventDefault(){}});canvas.onpointerup();
 assert.equal(value('random_mode'),'off');assert.equal(value('azimuth'),sampled.azimuth+2);assert.equal(value('distance'),sampled.distance);assert.equal(value('roll'),sampled.roll);
 node.widgets.find(w=>w.name==='random_mode').value='full';toolbar.children.at(-2).onclick();assert.equal(value('random_mode'),'full');
 node.onExecuted({camera_caption:['random server caption'],camera_values:[{azimuth:10,elevation:20,distance:.3,roll:2}]});
 assert.equal(output.textContent,'random server caption');
 toolbar.children.at(-1).onclick();assert.equal(value('random_mode'),'off');
 node.onExecuted({camera_regions:[[{id:1,x:.3,y:.5,mask:{width:2,height:2,bits:'wA=='}},{id:2,x:.7,y:.5,box:[.5,.2,.8,.8]},{id:3,x:.5,y:.1,kind:'text',box:[.1,0,.9,.2]}]],camera_layout:[{mode:'distance_and_roll',aspect:1.5}]});
 assert.match(layoutNotice.textContent,/distance|거리|距離|距离/);assert.equal(layoutCanvas.height,427);
 sandbox.setCameraValues(node,{layout_sync:'distance_and_roll',canvas_aspect:2,distance:.8,roll:25});
 assert.equal(layoutCanvas.height,320);
 sandbox.setCameraValues(node,{layout_sync:'perspective',azimuth:45,elevation:25});assert.match(layoutNotice.textContent,/perspective|원근|遠近|透[视視]/);
 sandbox.setCameraValues(node,{enabled:false});editor.render();
 assert.equal(node.onConfigure(),'configured');
 vm.runInNewContext(source,{app,document:{createElement:element},console});
 console.log('Camera: 301 Python/JS curve matches; localized editor, drag/wheel/keyboard, linked controls, reset and serialization passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
