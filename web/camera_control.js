// SPDX-License-Identifier: GPL-3.0-only
import { app } from "../../scripts/app.js";

const defaults = {azimuth: 0, elevation: 0, distance: .5, roll: 0, strength: 1.2, enabled: true};
const ranges = {azimuth: [-180, 180], elevation: [-90, 90], distance: [0, 1], roll: [-45, 45], strength: [0, 5]};
const clamp = (v, low, high) => Math.max(low, Math.min(high, v));
const widget = (node, name) => node.widgets?.find(w => w.name === name);
const linked = (node, name) => node.inputs?.some(i => i.name === name && i.link != null);
const lang = () => String(app.extensionManager?.setting?.get?.("Comfy.Locale") ?? "en");
const text = (en, ko, ja, zh, tw = zh) => lang().startsWith("ko") ? ko : lang().startsWith("ja") ? ja : lang().startsWith("zh-TW") ? tw : lang().startsWith("zh") ? zh : en;

export function blendStops(value, positions, labels) {
    for (let i = 0; i < positions.length-1; i++) {
        if (value <= positions[i+1]) {
            const t = Math.max(0, (value-positions[i])/(positions[i+1]-positions[i]));
            const mix = (1-Math.cos(Math.PI*t))/2;
            return [[labels[i], 1-mix], [labels[i+1], mix]];
        }
    }
    return [[labels.at(-1), 1]];
}

export function cameraWeights({azimuth=0, elevation=0, distance=.5, roll=0, strength=1.2} = {}) {
    const weights = {};
    const add = (tag, v) => weights[tag] = (weights[tag] ?? 0) + v*strength;
    const yawScale = Math.cos(elevation*Math.PI/180)**2;
    const side = azimuth < 0 ? "viewed from the left side" : "viewed from the right side";
    for (const [tag, v] of blendStops(Math.abs(azimuth), [0, 90, 180], ["from front", side, "from behind"])) add(tag, v*.85*yawScale);
    if (elevation) {
        for (const [tag, v] of blendStops(Math.abs(elevation), [0, 60, 90],
            ["eye level", elevation > 0 ? "from above" : "from below", elevation > 0 ? "overhead view" : "worm's-eye view"])) {
            if (tag !== "eye level") add(tag, v*.8);
        }
    }
    for (const [tag, v] of blendStops(distance, [0, .25, .5, .75, 1], ["extreme close-up", "close-up", "medium shot", "full body", "wide shot"])) add(tag, v);
    if (roll) add("dutch angle", .6*Math.abs(roll)/45);
    return Object.fromEntries(Object.entries(weights).filter(([, v]) => v > 1e-12));
}

function values(node) {
    const v = Object.fromEntries(Object.entries(defaults).map(([k, v]) => [k, widget(node, k)?.value ?? v]));
    const mode = widget(node, "random_mode")?.value ?? "off";
    return v.enabled && v.strength && mode !== "off" ? {...v, ...randomCamera(mode, widget(node, "random_seed")?.value ?? 0)} : v;
}

export function randomCamera(mode, seed) {
    const ranges = {balanced:[[-90,90],[-35,35],[.25,.85],[-10,10]], full:[[-180,180],[-90,90],[0,1],[-45,45]]};
    if (!ranges[mode] || !Number.isInteger(seed) || seed < 0 || seed > 0xffffffff) return {};
    let state = seed;
    return Object.fromEntries(["azimuth","elevation","distance","roll"].map((name,i) => {
        state = (Math.imul(1664525,state)+1013904223) >>> 0;
        const [low, high] = ranges[mode][i];
        return [name, low+(high-low)*(state/4294967296)];
    }));
}

export function setCameraValues(node, changes) {
    for (const [name, value] of Object.entries(changes)) {
        const w = widget(node, name);
        if (!w || linked(node, name)) continue;
        w.value = ranges[name] ? clamp(value, ...ranges[name]) : value;
        w.callback?.(w.value);
    }
    node.setDirtyCanvas?.(true, true);
}

export function addCameraEditor(node) {
    if (node.rsCameraEditor) return;
    const root = document.createElement("div");
    root.className = "rs-camera-editor";
    root.style.cssText = "height:100%;overflow:auto;background:#1e2530;color:#eee;padding:8px;box-sizing:border-box;font:12px sans-serif";
    const toolbar = document.createElement("div");
    toolbar.style.cssText = "display:flex;flex-wrap:wrap;gap:5px";
    const presets = [
        [["Front", "정면", "正面", "正面"], {azimuth:0,elevation:0}],
        [["Side", "측면", "側面", "侧面", "側面"], {azimuth:90,elevation:0}],
        [["Above", "위에서", "上から", "俯视", "俯視"], {azimuth:0,elevation:60}],
        [["Below", "아래서", "下から", "仰视", "仰視"], {azimuth:0,elevation:-45}],
        [["Close", "가까이", "近く", "近景"], {distance:.25}],
        [["Wide", "멀리", "遠く", "远景", "遠景"], {distance:1}],
        [["Random", "랜덤 구도", "ランダム", "随机视角", "隨機視角"], null],
        [["Reset", "초기화", "リセット", "重置"], {...defaults,random_mode:"off",random_seed:0}],
    ];
    const buttons = [];
    for (const [labels, changes] of presets) {
        const b = document.createElement("button"); b.type = "button";
        b.style.cssText = "color:#eee;background:#344257;border:1px solid #60758d;border-radius:3px;padding:4px 6px;cursor:pointer";
        b.onclick = () => {
            setCameraValues(node, changes ? {...values(node),random_mode:"off", ...changes} : {
                random_mode: widget(node,"random_mode")?.value === "full" ? "full" : "balanced",
                random_seed: Math.floor(Math.random()*4294967296),
            });
            render();
        };
        buttons.push([b, labels]); toolbar.append(b);
    }
    const canvas = document.createElement("canvas");
    canvas.width = 640; canvas.height = 340; canvas.tabIndex = 0;
    canvas.setAttribute("aria-label", "Camera view and weight curves");
    canvas.style.cssText = "width:100%;height:200px;display:block;touch-action:none;cursor:grab";
    const notice = document.createElement("div"), output = document.createElement("pre");
    notice.style.cssText = "line-height:1.45;color:#bcc8d8";
    output.style.cssText = "white-space:pre-wrap;word-break:break-word;line-height:1.4;color:#99d4e8;margin:7px 0";
    root.append(toolbar, canvas, notice, output);
    for (const event of ["pointerdown", "wheel", "keydown"]) root.addEventListener(event, e => e.stopPropagation());
    let executed = null, executedView = null;
    function render() {
        const v = {...values(node), ...executedView}, c = canvas.getContext("2d");
        for (const [b, labels] of buttons) b.textContent = text(...labels);
        c.clearRect(0,0,640,340);
        c.strokeStyle = "#526379"; c.lineWidth = 2;
        c.beginPath();c.ellipse(320,98,210,65,0,0,Math.PI*2);c.stroke();
        c.fillStyle = "#7db6ce";c.beginPath();c.arc(320,83,18,0,Math.PI*2);c.fill();
        c.fillRect(302,106,36,44);
        c.fillStyle="#dce7f4";c.font="18px sans-serif";c.fillText("FRONT",285,183);c.fillText("REAR",292,19);
        const angle = v.azimuth*Math.PI/180;
        const x = 320+210*Math.sin(angle), y = 98+65*Math.cos(angle)-v.elevation*.6;
        c.strokeStyle="#ffca6a";c.beginPath();c.moveTo(320,98);c.lineTo(x,y);c.stroke();
        c.save();c.translate(x,y);c.rotate(v.roll*Math.PI/180);c.fillStyle="#ffca6a";c.fillRect(-12,-8,24,16);c.restore();
        c.fillStyle="#dce7f4";c.font="16px sans-serif";c.fillText(`${v.azimuth.toFixed(0)}° / ${v.elevation.toFixed(0)}° / ${v.distance.toFixed(2)}`,12,210);
        const axes=[['azimuth',-180,180,0,['from front','viewed from the left side','from behind','viewed from the right side']],
            ['elevation',-90,90,214,["worm's-eye view",'from below','from above','overhead view']],
            ['distance',0,1,428,['extreme close-up','close-up','medium shot','full body','wide shot']]];
        const colors=['#8dd3c7','#ffca6a','#a7afff','#f88cb8','#96d86e'];
        c.font='12px sans-serif';c.fillText(text('Normalized weights 0–1 × strength','정규화 가중치 0~1 × 시점 강도','正規化重み 0–1 × 強度','归一化权重 0–1 × 强度','正規化權重 0–1 × 強度'),225,210);
        for(const [axis,low,high,offset,tags] of axes){
            c.strokeStyle="#4c5c70";c.strokeRect(offset+8,235,196,75);
            const curves=Object.fromEntries(tags.map(tag=>[tag,[]]));
            for(let i=0;i<=80;i++){
                const w=cameraWeights({...v, strength:1, [axis]:low+(high-low)*i/80});
                for(const tag of tags) curves[tag].push([i,w[tag] ?? 0]);
            }
            let color=0;
            for(const points of Object.values(curves)){
                c.strokeStyle=colors[color++%colors.length];c.beginPath();
                points.forEach(([i,value],j)=>{const px=offset+8+i/80*196,py=310-value*75;j?c.lineTo(px,py):c.moveTo(px,py);});c.stroke();
            }
            const current=offset+8+(v[axis]-low)/(high-low)*196;
            c.strokeStyle="#fff";c.beginPath();c.moveTo(current,233);c.lineTo(current,312);c.stroke();
            c.fillStyle="#dce7f4";c.fillText(axis,offset+12,333);
        }
        const links=[...Object.keys(defaults),"random_mode","random_seed"].filter(k=>linked(node,k));
        notice.textContent = links.length ? text("Linked controls resolve on execution: ","연결 항목은 실행 시 확정: ","接続項目は実行時に確定: ","连接项在执行时确定: ","連接項在執行時確定: ")+links.join(", ") :
            text("Drag: view · Wheel: distance · Shift+wheel: tilt. Diagram and curves are caption guides; positions/masks stay fixed.",
                "드래그: 시점 · 휠: 거리 · Shift+휠: 기울기. 도식·곡선은 태그 안내이며 좌표·마스크는 유지됩니다.",
                "ドラッグ:視点・ホイール:距離・Shift:傾き。図と曲線はタグの目安です。座標・マスクは固定です。",
                "拖动:视角 · 滚轮:距离 · Shift+滚轮:倾斜。示意图和曲线用于提示标签，不改变坐标或蒙版。",
                "拖曳:視角 · 滾輪:距離 · Shift+滾輪:傾斜。示意圖和曲線用於提示標籤，不改變座標或遮罩。");
        if ((widget(node,"random_mode")?.value ?? "off") !== "off") notice.textContent += " " + text(
            "Random view: fixed seed repeats; randomize changes each run. Drag/presets return to manual.",
            "랜덤 구도: fixed는 유지, randomize는 매번 변경. 드래그·프리셋은 수동으로 전환합니다.",
            "ランダム: fixedで再現、randomizeで毎回変更。ドラッグ・プリセットで手動に戻ります。",
            "随机视角: fixed重复，randomize每次改变。拖动或预设切回手动。",
            "隨機視角: fixed重複，randomize每次改變。拖曳或預設切回手動。");
        output.textContent = executed ?? (v.enabled ? Object.entries(cameraWeights(v)).filter(([,w])=>w>=.005).map(([tag,w])=>`${tag}  ${w.toFixed(2)}`).join("\n") : text("Camera OFF", "카메라 꺼짐", "カメラOFF", "相机已关闭", "相機已關閉"));
    }
    let drag=null;
    canvas.onpointerdown=e=>{if(e.button!==0)return;drag={x:e.clientX,y:e.clientY,...values(node)};canvas.setPointerCapture(e.pointerId);};
    canvas.onpointermove=e=>{
        if(!drag)return;
        setCameraValues(node,{random_mode:"off",azimuth:drag.azimuth+(e.clientX-drag.x),elevation:drag.elevation-(e.clientY-drag.y),distance:drag.distance,roll:drag.roll});
        render();e.preventDefault();
    };
    canvas.onpointerup=canvas.onpointercancel=()=>{drag=null;};
    canvas.onlostpointercapture=()=>{drag=null;};
    canvas.addEventListener("wheel",e=>{
        e.preventDefault();const v=values(node),step=Math.sign(e.deltaY);
        setCameraValues(node,{random_mode:"off",azimuth:v.azimuth,elevation:v.elevation,distance:v.distance,roll:v.roll,
            ...(e.shiftKey?{roll:v.roll+step*2}:{distance:v.distance+step*.025})});render();
    },{passive:false});
    canvas.onkeydown=e=>{
        const v=values(node), change={ArrowLeft:{azimuth:v.azimuth-5},ArrowRight:{azimuth:v.azimuth+5},ArrowUp:{elevation:v.elevation+5},ArrowDown:{elevation:v.elevation-5}}[e.key];
        if(change){e.preventDefault();setCameraValues(node,{random_mode:"off",azimuth:v.azimuth,elevation:v.elevation,distance:v.distance,roll:v.roll,...change});render();}
    };
    for(const w of node.widgets ?? []){
        if(![...Object.keys(defaults),"weighting","prompt_syntax","scope","random_mode","random_seed"].includes(w.name))continue;
        const previous=w.callback;
        w.callback=function(...args){const result=previous?.apply(this,args);executed=null;executedView=null;render();return result;};
    }
    const custom=node.addDOMWidget("rs_camera_editor","rs_camera_editor",root,{serialize:false,hideOnZoom:false});
    custom.computeSize=()=>[360,410];custom.serialize=false;
    const previous=node.onExecuted;
    node.onExecuted=function(message){const result=previous?.apply(this,arguments);executed=message.camera_caption?.[0] ?? null;executedView=message.camera_values?.[0] ?? null;render();return result;};
    const configured=node.onConfigure;
    node.onConfigure=function(){const result=configured?.apply(this,arguments);executed=null;executedView=null;render();return result;};
    const connections=node.onConnectionsChange;
    node.onConnectionsChange=function(){const result=connections?.apply(this,arguments);executed=null;executedView=null;render();return result;};
    node.rsCameraEditor={root,render};render();
}

// Both packages ship the same node and editor; only register the editor once.
if(!globalThis[Symbol.for("raspie.camera.editor")]){
    globalThis[Symbol.for("raspie.camera.editor")]=true;
    app.registerExtension({
        name:"RS.CameraControl",
        async beforeRegisterNodeDef(nodeType,nodeData){
            if(nodeData.name!=="RSCameraControl")return;
            const previous=nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated=function(){
                const result=previous?.apply(this,arguments);addCameraEditor(this);
                this.setSize?.([Math.max(380,this.size[0]),this.computeSize()[1]]);return result;
            };
        },
    });
}
