// SPDX-License-Identifier: GPL-3.0-only
import { app } from "../../scripts/app.js";

const defaults = {azimuth: 0, elevation: 0, distance: .5, roll: 0, strength: 1.2, enabled: true, layout_sync:"fixed", canvas_aspect:1};
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

const tagAxes = Object.fromEntries([
    ...["from front", "viewed from the left side", "viewed from the right side", "from behind"].map(t => [t, "azimuth"]),
    ...["from above", "from below", "overhead view", "worm's-eye view"].map(t => [t, "elevation"]),
    ...["extreme close-up", "close-up", "medium shot", "full body", "wide shot"].map(t => [t, "distance"]),
    ["dutch angle", "roll"],
]);

// Python rounds exact half-cent ties to even; JS toFixed rounds them upward.
// A binary float is an exact half-cent only at odd multiples of 1/8.
function captionNumber(value) {
    const cents = Math.floor(value * 100);
    const halfCent = Number.isInteger(value * 8) && !Number.isInteger(value * 4);
    return halfCent && cents % 2 === 0 ? cents / 100 : Number(value.toFixed(2));
}

export function cameraCaption(weights, syntax="ComfyUI", weighting="weighted") {
    const peaks = {};
    for (const [tag, value] of Object.entries(weights)) {
        const axis = tagAxes[tag] ?? tag;
        peaks[axis] = Math.max(peaks[axis] ?? 0, value);
    }
    return Object.entries(weights).filter(([tag, value]) => value >= .005 &&
        (weighting !== "plain" || value >= peaks[tagAxes[tag] ?? tag] * .5))
        .map(([tag, value]) => weighting === "plain" ? tag : syntax === "NovelAI" ?
            `${captionNumber(value)}::${tag}::` : `(${tag}:${captionNumber(value)})`).join(", ");
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

export function projectLayout(x, y, distance, roll, aspect, azimuth=0, elevation=0, perspective=false) {
    const scale=2**(2*(.5-distance)), a=roll*Math.PI/180, co=Math.cos(a), si=Math.sin(a);
    x=(x-.5)*aspect;y-=.5;
    if (perspective) {
        const yaw=azimuth*Math.PI/180, pitch=elevation*Math.PI/180;
        const ca=Math.cos(yaw), sa=Math.sin(yaw), ce=Math.cos(pitch), se=Math.sin(pitch);
        const depth=1+(-sa*ce*x+se*y)/(2*Math.hypot(aspect,1)/scale);
        const u=ca*x, v=sa*se*x+ce*y;
        return [.5+scale*(co*u-si*v)/(aspect*depth),.5+scale*(si*u+co*v)/depth];
    }
    return [.5+scale*(co*x-si*y)/aspect,.5+scale*(si*x+co*y)];
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
    const layoutNotice=document.createElement("div"), layoutCanvas=document.createElement("canvas");
    layoutNotice.style.cssText="line-height:1.45;color:#b8d8c8;margin-top:7px";
    layoutCanvas.width=640;layoutCanvas.height=360;
    layoutCanvas.setAttribute("aria-label","Camera character mask layout preview");
    layoutCanvas.style.cssText="display:block;width:100%;height:180px;object-fit:contain;background:#111820";
    root.append(layoutNotice,layoutCanvas);
    for (const event of ["pointerdown", "wheel", "keydown"]) root.addEventListener(event, e => e.stopPropagation());
    let executed = null, executedView = null, executedLayout=null, resolvedSyntax=null, regions=[];
    function render() {
        const v = {...values(node), ...executedView}, c = canvas.getContext("2d");
        for (const [b, labels] of buttons) b.textContent = text(...labels);
        c.clearRect(0,0,640,340);
        c.strokeStyle = "#526379"; c.lineWidth = 2;
        c.beginPath();c.ellipse(320,98,210,65,0,0,Math.PI*2);c.stroke();
        c.fillStyle = "#7db6ce";c.beginPath();c.arc(320,83,18,0,Math.PI*2);c.fill();
        c.fillRect(302,106,36,44);
        c.fillStyle="#dce7f4";c.font="18px sans-serif";c.fillText(text("FRONT","정면","正面","正面"),285,183);c.fillText(text("REAR","후면","背面","背面"),292,19);
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
            c.fillStyle="#dce7f4";c.fillText({azimuth:text("azimuth","좌우 시점","左右視点","水平视角","水平視角"),elevation:text("elevation","상하 시점","上下視点","垂直视角","垂直視角"),distance:text("distance","거리","距離","距离","距離")}[axis],offset+12,333);
        }
        const links=[...Object.keys(defaults),"random_mode","random_seed"].filter(k=>linked(node,k));
        notice.textContent = links.length ? text("Linked controls resolve on execution: ","연결 항목은 실행 시 확정: ","接続項目は実行時に確定: ","连接项在执行时确定: ","連接項在執行時確定: ")+links.join(", ") :
            text("Drag: view · Wheel: distance · Shift+wheel: tilt. Diagram and curves guide captions. Layout sync is optional.",
                "드래그: 시점 · 휠: 거리 · Shift+휠: 기울기. 도식·곡선은 태그 안내입니다. 마스크 배치는 별도로 연동할 수 있습니다.",
                "ドラッグ:視点・ホイール:距離・Shift:傾き。図と曲線はタグの目安です。配置連動は任意です。",
                "拖动:视角 · 滚轮:距离 · Shift+滚轮:倾斜。示意图和曲线用于提示标签，可选区域布局联动。",
                "拖曳:視角 · 滾輪:距離 · Shift+滾輪:傾斜。示意圖和曲線用於提示標籤，可選區域配置連動。");
        if ((widget(node,"random_mode")?.value ?? "off") !== "off") notice.textContent += " " + text(
            "Random view: fixed seed repeats; randomize changes each run. Drag/presets return to manual.",
            "랜덤 구도: fixed는 유지, randomize는 매번 변경. 드래그·프리셋은 수동으로 전환합니다.",
            "ランダム: fixedで再現、randomizeで毎回変更。ドラッグ・プリセットで手動に戻ります。",
            "随机视角: fixed重复，randomize每次改变。拖动或预设切回手动。",
            "隨機視角: fixed重複，randomize每次改變。拖曳或預設切回手動。");
        const syntax=linked(node,"context") && resolvedSyntax ? resolvedSyntax : widget(node,"prompt_syntax")?.value ?? "ComfyUI";
        output.textContent = !v.enabled || !v.strength ? text("Camera OFF", "카메라 꺼짐", "カメラOFF", "相机已关闭", "相機已關閉") :
            executed ?? cameraCaption(cameraWeights(v), syntax, widget(node,"weighting")?.value ?? "weighted");
        if(linked(node,"context") && !resolvedSyntax) notice.textContent += " " + text(
            "Context syntax resolves on execution; this preview uses the selected syntax.",
            "컨텍스트 문법은 실행 시 확정됩니다. 현재 미리보기는 선택한 문법을 사용합니다.",
            "接続コンテキストの構文は実行時に確定。現在は選択した構文で表示。",
            "上下文语法在执行时确定；当前预览使用所选语法。",
            "上下文語法在執行時確定；目前預覽使用所選語法。");
        const mode=executedLayout?.mode??v.layout_sync, aspect=executedLayout?.aspect??v.canvas_aspect;
        const sync=v.enabled&&v.strength&&mode!=="fixed";
        const perspective=sync&&mode==="perspective";
        layoutNotice.textContent=regions.length ? text(
            "Last executed input regions · layout mode: ",
            "마지막 실행 입력의 영역 · 배치 연동: ",
            "直前の入力領域・配置モード: ",
            "上次执行的输入区域 · 布局模式: ",
            "上次執行的輸入區域 · 配置模式: ")+(!sync ? text("fixed","고정","固定","固定") : text("distance / tilt","거리 / 기울기","距離 / 傾き","距离 / 倾斜","距離 / 傾斜")) : text(
            "Run once to load input masks. Upstream edits need another run. Set aspect = output width / height.",
            "한 번 실행하면 입력 마스크를 표시합니다. 상위 배치를 바꾸면 다시 실행하세요. 화면 비율=생성 너비÷높이.",
            "一度実行してマスクを表示。上流の変更後は再実行。比率=出力幅÷高さ。",
            "执行一次以显示蒙版。上游编辑后需重新执行。比例=输出宽÷高。",
            "執行一次以顯示遮罩。上游編輯後需重新執行。比例=輸出寬÷高。");
        if(perspective) layoutNotice.textContent=text(
            "Flat-plane perspective: near side grows, far side shrinks. No 3D silhouette/occlusion. ±90° collapses the plane; change the angle. Text stays fixed.",
            "평면 원근: 가까운 쪽은 커지고 먼 쪽은 작아집니다. 입체 형상·가림은 복원하지 않습니다. ±90°에서는 선이 되므로 각도를 바꾸세요. 글자는 고정.",
            "平面の遠近変形。近側は拡大、遠側は縮小。立体形状・遮蔽は復元しません。±90°は線になるため角度を変更。文字枠は固定。",
            "平面透视：近大远小，不重建立体轮廓或遮挡。±90°会退化成线，请调整角度。文本固定。",
            "平面透視：近大遠小，不重建立體輪廓或遮擋。±90°會退化成線，請調整角度。文字固定。")+(regions.length?"":" "+text("Run once to load masks.","입력 마스크를 보려면 한 번 실행하세요.","マスク表示は一度実行。","执行一次以加载蒙版。","執行一次以載入遮罩。"));
        const lc=layoutCanvas.getContext("2d"), W=640,H=Math.max(64,Math.round(640/aspect));
        if(layoutCanvas.height!==H)layoutCanvas.height=H;
        lc.clearRect(0,0,W,H);lc.strokeStyle="#6b7b8b";lc.strokeRect(0,0,W,H);
        const point=(x,y,isText)=>sync&&!isText?projectLayout(x,y,v.distance,v.roll,aspect,v.azimuth,v.elevation,perspective):[x,y];
        const regionColors=["#ff8d91","#81bcff","#94dd9d","#ffd27f","#c3a0ff"];
        for(const region of regions){
            const isText=region.kind==="text";lc.fillStyle=regionColors[(region.id-1)%regionColors.length];lc.strokeStyle=lc.fillStyle;lc.globalAlpha=.45;
            if(region.mask){
                const mask=region.mask,bits=atob(mask.bits);
                if(perspective&&!isText){
                    for(let y=0;y<mask.height;y++)for(let x=0;x<mask.width;x++){
                        const i=y*mask.width+x;if(!(bits.charCodeAt(i>>3)&(128>>(i%8))))continue;
                        const ps=[[x,y],[x+1,y],[x+1,y+1],[x,y+1]].map(([a,b])=>point(a/mask.width,b/mask.height,false));
                        lc.beginPath();ps.forEach(([a,b],j)=>j?lc.lineTo(a*W,b*H):lc.moveTo(a*W,b*H));lc.closePath();lc.fill();
                    }
                }else{
                lc.save();
                lc.translate(W/2,H/2);if(sync){lc.rotate(v.roll*Math.PI/180);const scale=2**(2*(.5-v.distance));lc.scale(scale,scale);}lc.translate(-W/2,-H/2);
                for(let y=0;y<mask.height;y++)for(let x=0;x<mask.width;x++){const i=y*mask.width+x;if(bits.charCodeAt(i>>3)&(128>>(i%8)))lc.fillRect(x/mask.width*W,y/mask.height*H,W/mask.width,H/mask.height);}
                lc.restore();
                }
            }else if(region.box){
                const [l,t,r,b]=region.box,ps=[[l,t],[r,t],[l,b],[r,b]].map(([x,y])=>point(x,y,isText));
                const left=Math.max(0,Math.min(...ps.map(p=>p[0]))),right=Math.min(1,Math.max(...ps.map(p=>p[0]))),top=Math.max(0,Math.min(...ps.map(p=>p[1]))),bottom=Math.min(1,Math.max(...ps.map(p=>p[1])));
                if(right>left&&bottom>top)lc.fillRect(left*W,top*H,(right-left)*W,(bottom-top)*H);
            }
            lc.globalAlpha=1;const [cx,cy]=point(region.x,region.y,isText);lc.beginPath();lc.arc(cx*W,cy*H,5,0,Math.PI*2);lc.fill();lc.font="18px sans-serif";lc.fillText(String(region.id),cx*W+8,cy*H-8);
        }
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
        w.callback=function(...args){const result=previous?.apply(this,args);executed=null;executedView=null;executedLayout=null;render();return result;};
    }
    const custom=node.addDOMWidget("rs_camera_editor","rs_camera_editor",root,{serialize:false,hideOnZoom:false});
    custom.computeSize=()=>[360,630];custom.serialize=false;
    const previous=node.onExecuted;
    node.onExecuted=function(message){const result=previous?.apply(this,arguments);resolvedSyntax=message.camera_syntax?.[0] ?? null;executed=message.camera_caption?.[0] ?? null;executedView=message.camera_values?.[0] ?? null;executedLayout=message.camera_layout?.[0]??null;regions=message.camera_regions?.[0]??[];render();return result;};
    const configured=node.onConfigure;
    node.onConfigure=function(){const result=configured?.apply(this,arguments);executed=null;executedView=null;executedLayout=null;resolvedSyntax=null;regions=[];render();return result;};
    const connections=node.onConnectionsChange;
    node.onConnectionsChange=function(){const result=connections?.apply(this,arguments);executed=null;executedView=null;executedLayout=null;resolvedSyntax=null;regions=[];render();return result;};
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

// Keep the NAI entry independent of the shared editor's registration guard:
// the companion extension may have registered an earlier shared editor first.
if(!globalThis[Symbol.for("raspie.nai.camera.editor")]){
    globalThis[Symbol.for("raspie.nai.camera.editor")]=true;
    app.registerExtension({
        name:"RS.NAICameraControl",
        async beforeRegisterNodeDef(nodeType,nodeData){
            if(nodeData.name!=="NAICameraControl")return;
            const previous=nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated=function(){
                const result=previous?.apply(this,arguments);addCameraEditor(this);
                this.setSize?.([Math.max(380,this.size[0]),this.computeSize()[1]]);return result;
            };
        },
    });
}
