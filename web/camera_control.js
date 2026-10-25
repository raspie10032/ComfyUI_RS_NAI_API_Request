// SPDX-License-Identifier: GPL-3.0-only
import { app } from "../../scripts/app.js";

const defaults = {azimuth: 0, elevation: 0, distance: .5, roll: 0, strength: 1.2, enabled: true, layout_sync:"fixed", canvas_aspect:1};
const ranges = {azimuth: [-180, 180], elevation: [-90, 90], distance: [0, 1], roll: [-45, 45], strength: [0, 5]};
const clamp = (v, low, high) => Math.max(low, Math.min(high, v));
const widget = (node, name) => node.widgets?.find(w => w.name === name);
const linked = (node, name) => node.inputs?.some(i => i.name === name && i.link != null);

// Rename in place so old workflows keep socket indices and their link IDs.
export function migrateCameraPipe(node) {
    for (const slot of [...(node.inputs ?? []), ...(node.outputs ?? []).slice(0, 1)]) {
        if (slot.name === "context") {
            slot.name = "building_pipe";
            delete slot.label;
            delete slot.localized_name;
        }
    }
}
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

// Separate bearing from height: raising a camera must not look like moving it behind the subject.
export function cameraDiagram({azimuth=0, elevation=0, distance=.5} = {}) {
    const yaw=azimuth*Math.PI/180, pitch=elevation*Math.PI/180, radius=65+35*distance;
    return {top:[164+radius*Math.sin(yaw),164+radius*Math.cos(yaw)],
        side:[456+radius*Math.cos(pitch),164-radius*Math.sin(pitch)],
        sector:((Math.round(azimuth/45)%8)+8)%8};
}

// Canvas coordinates, independent of CSS size and graph zoom. The centre has no bearing.
export function cameraPointerAngle(axis, x, y) {
    const dx=x-(axis === "azimuth" ? 164 : 456), dy=y-164;
    if (Math.hypot(dx,dy) < 8) return {};
    return axis === "azimuth" ? {azimuth:Math.atan2(dx,dy)*180/Math.PI} :
        {elevation:clamp(Math.atan2(-dy,dx)*180/Math.PI,-90,90)};
}

function drawCameraDiagram(c, v) {
    c.clearRect(0,0,640,350);
    const label=(s,x,y,color="#dce7f4",size=19)=>{c.fillStyle=color;c.font=`${size}px sans-serif`;c.textAlign="center";c.fillText(s,x,y);};
    const line=(x,y,tx,ty,color="#526379")=>{c.strokeStyle=color;c.lineWidth=2;c.beginPath();c.moveTo(x,y);c.lineTo(tx,ty);c.stroke();};
    const arrow=(x,y,tx,ty,color)=>{
        line(x,y,tx,ty,color);const a=Math.atan2(ty-y,tx-x);
        c.fillStyle=color;c.beginPath();c.moveTo(tx,ty);c.lineTo(tx-10*Math.cos(a-.5),ty-10*Math.sin(a-.5));c.lineTo(tx-10*Math.cos(a+.5),ty-10*Math.sin(a+.5));c.closePath();c.fill();
    };
    const camera=(p,target)=>{
        const [x,y]=p,[tx,ty]=target,a=Math.atan2(ty-y,tx-x);
        // View cone and arrow explicitly point from the yellow camera to the blue subject.
        c.fillStyle="#ffca6a20";c.beginPath();c.moveTo(x,y);c.lineTo(tx+19*Math.sin(a),ty-19*Math.cos(a));c.lineTo(tx-19*Math.sin(a),ty+19*Math.cos(a));c.closePath();c.fill();
        arrow(x,y,x+(tx-x)*.7,y+(ty-y)*.7,"#ffca6a");
        c.save();c.translate(x,y);c.rotate(a);c.fillStyle="#ffca6a";c.fillRect(-13,-9,22,18);
        c.beginPath();c.moveTo(9,-5);c.lineTo(18,-11);c.lineTo(18,11);c.lineTo(9,5);c.closePath();c.fill();c.restore();
    };
    const {top,side,sector}=cameraDiagram(v);
    label(text("TOP · direction","위에서 본 방향","上面・方向","俯视 · 方向","俯視 · 方向"),164,25);
    label(text("SIDE · height","옆에서 본 높이","側面・高さ","侧视 · 高度","側視 · 高度"),472,25);
    line(324,10,324,284);
    c.strokeStyle="#526379";c.lineWidth=2;c.beginPath();c.arc(164,164,100,0,Math.PI*2);c.stroke();
    line(64,164,264,164);line(164,64,164,264);
    label(text("FRONT","정면","正面","正面"),164,288);
    label(text("BACK","후면","背面","背面"),164,55);
    label(text("LEFT","좌측","左側","左侧","左側"),29,170);
    label(text("RIGHT","우측","右側","右侧","右側"),295,170);
    c.fillStyle="#7db6ce";c.beginPath();c.arc(164,164,16,0,Math.PI*2);c.fill();
    arrow(164,181,164,207,"#7db6ce");
    c.strokeStyle="#526379";c.beginPath();c.arc(456,164,100,-Math.PI/2,Math.PI/2);c.stroke();
    line(420,164,585,164);line(456,64,456,264);
    label(text("ABOVE","위에서","上から","俯视","俯視"),472,55);
    label(text("BELOW","아래에서","下から","仰视","仰視"),472,288);
    // The profile's head sits on the eye-level axis, independently of horizontal bearing.
    c.fillStyle="#7db6ce";c.beginPath();c.arc(456,164,14,0,Math.PI*2);c.fill();
    c.fillRect(445,183,22,29);line(456,212,445,237,"#7db6ce");line(456,212,467,237,"#7db6ce");
    camera(top,[164,164]);camera(side,[456,164]);
    const directions=[
        ["Front","정면","正面","正面"],["Front-right","우전방","右前方","右前方"],
        ["Right side","우측면","右側面","右侧面","右側面"],["Rear-right","우후방","右後方","右后方","右後方"],
        ["Behind","후면","背面","背面"],["Rear-left","좌후방","左後方","左后方","左後方"],
        ["Left side","좌측면","左側面","左侧面","左側面"],["Front-left","좌전방","左前方","左前方"],
    ];
    const height=v.elevation>2?text("above","위에서","上から","俯视","俯視"):v.elevation< -2?text("below","아래에서","下から","仰视","仰視"):text("eye level","눈높이","目線","平视","平視");
    label(`${text("Camera","카메라","カメラ","相机","相機")}: ${text(...directions[sector])} · ${height} (${v.azimuth.toFixed(0)}° / ${v.elevation.toFixed(0)}°)`,320,318,"#ffca6a");
    label(text("Blue = subject, arrow = facing front · Yellow = camera aiming at subject",
        "파랑=인물, 화살표=정면 · 노랑=인물을 바라보는 카메라",
        "青=人物・矢印=正面方向 · 黄=人物に向くカメラ",
        "蓝色=人物，箭头=正面 · 黄色=朝向人物的相机",
        "藍色=人物，箭頭=正面 · 黃色=朝向人物的相機"),320,343,"#b7c6d9",17);
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
        [["Back", "후면", "背面", "背面"], {azimuth:180,elevation:0}],
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
    canvas.width = 640; canvas.height = 350; canvas.tabIndex = 0;
    canvas.setAttribute("aria-label", "Camera view control");
    canvas.style.cssText = "width:100%;height:auto;aspect-ratio:640/350;display:block;touch-action:none;cursor:crosshair";
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
        drawCameraDiagram(c,v);
        canvas.setAttribute("aria-label",text(
            "Click or drag from each centre: left sets direction, right sets height. Wheel: distance; Shift+wheel: tilt.",
            "각 중심에서 마우스 방향으로 클릭·드래그: 왼쪽은 방향, 오른쪽은 높이. 휠: 거리, Shift+휠: 기울기.",
            "各中心からマウス方向へクリック・ドラッグ。左:方向、右:高さ。ホイール:距離、Shift:傾き。",
            "从各中心朝鼠标方向点击或拖动。左:方向，右:高度。滚轮:距离，Shift+滚轮:倾斜。",
            "從各中心朝滑鼠方向點擊或拖曳。左:方向，右:高度。滾輪:距離，Shift+滾輪:傾斜。"));
        const links=[...Object.keys(defaults),"random_mode","random_seed"].filter(k=>linked(node,k));
        notice.textContent = links.length ? text("Linked controls resolve on execution: ","연결 항목은 실행 시 확정: ","接続項目は実行時に確定: ","连接项在执行时确定: ","連接項在執行時確定: ")+links.join(", ") :
            text("Click/drag from centre: left = direction, right = height. Wheel: distance · Shift+wheel: tilt. Layout sync is optional.",
                "중심에서 마우스 방향으로 클릭·드래그: 왼쪽=방향, 오른쪽=높이. 휠: 거리 · Shift+휠: 기울기. 마스크 배치는 선택 연동입니다.",
                "中心からクリック・ドラッグ。左=方向、右=高さ。ホイール:距離・Shift:傾き。配置連動は任意です。",
                "从中心朝鼠标方向点击或拖动。左=方向，右=高度。滚轮:距离 · Shift+滚轮:倾斜。可选区域布局联动。",
                "從中心朝滑鼠方向點擊或拖曳。左=方向，右=高度。滾輪:距離 · Shift+滾輪:傾斜。可選區域配置聯動。");
        if ((widget(node,"random_mode")?.value ?? "off") !== "off") notice.textContent += " " + text(
            "Random view: fixed seed repeats; randomize changes each run. Drag/presets return to manual.",
            "랜덤 구도: fixed는 유지, randomize는 매번 변경. 드래그·프리셋은 수동으로 전환합니다.",
            "ランダム: fixedで再現、randomizeで毎回変更。ドラッグ・プリセットで手動に戻ります。",
            "随机视角: fixed重复，randomize每次改变。拖动或预设切回手动。",
            "隨機視角: fixed重複，randomize每次改變。拖曳或預設切回手動。");
        const syntax=linked(node,"building_pipe") && resolvedSyntax ? resolvedSyntax : widget(node,"prompt_syntax")?.value ?? "ComfyUI";
        output.textContent = !v.enabled || !v.strength ? text("Camera OFF", "카메라 꺼짐", "カメラOFF", "相机已关闭", "相機已關閉") :
            executed ?? cameraCaption(cameraWeights(v), syntax, widget(node,"weighting")?.value ?? "weighted");
        if(linked(node,"building_pipe") && !resolvedSyntax) notice.textContent += " " + text(
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
    function pointerPosition(e) {
        const r=canvas.getBoundingClientRect();
        if (!(r.width>0 && r.height>0)) return null;
        return [(e.clientX-r.left)*canvas.width/r.width,(e.clientY-r.top)*canvas.height/r.height];
    }
    function applyPointer(e,p) {
        const change=cameraPointerAngle(drag.axis,...p);
        if (Object.keys(change).length) {
            const {azimuth,elevation,distance,roll}=drag;
            setCameraValues(node,{random_mode:"off",azimuth,elevation,distance,roll,...change});
            render();
        }
        e.preventDefault();
    }
    canvas.onpointerdown=e=>{
        if(e.button!==0)return;
        const p=pointerPosition(e);if(!p)return;
        const axis=p[0]<324 ? "azimuth" : "elevation", cx=axis === "azimuth" ? 164 : 456;
        if(Math.hypot(p[0]-cx,p[1]-164)>120)return;
        drag={axis,pointerId:e.pointerId,...values(node)};
        canvas.setPointerCapture(e.pointerId);canvas.focus();applyPointer(e,p);
    };
    canvas.onpointermove=e=>{
        if(!drag || e.pointerId!==drag.pointerId)return;
        const p=pointerPosition(e);if(p)applyPointer(e,p);
    };
    canvas.onpointerup=canvas.onpointercancel=e=>{if(e.pointerId===drag?.pointerId)drag=null;};
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
    custom.computeSize=()=>[360,640];custom.serialize=false;
    const previous=node.onExecuted;
    node.onExecuted=function(message){const result=previous?.apply(this,arguments);resolvedSyntax=message.camera_syntax?.[0] ?? null;executed=message.camera_caption?.[0] ?? null;executedView=message.camera_values?.[0] ?? null;executedLayout=message.camera_layout?.[0]??null;regions=message.camera_regions?.[0]??[];render();return result;};
    const configured=node.onConfigure;
    node.onConfigure=function(){const result=configured?.apply(this,arguments);migrateCameraPipe(this);executed=null;executedView=null;executedLayout=null;resolvedSyntax=null;regions=[];render();return result;};
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
            // Keep the server API alias out of new nodes' visible sockets.
            if(nodeData.input?.optional) delete nodeData.input.optional.context;
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
            if(nodeData.input?.optional) delete nodeData.input.optional.context;
            const previous=nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated=function(){
                const result=previous?.apply(this,arguments);addCameraEditor(this);
                this.setSize?.([Math.max(380,this.size[0]),this.computeSize()[1]]);return result;
            };
        },
    });
}
