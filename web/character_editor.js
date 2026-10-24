// The editor changes existing widgets only; its controls never enter API inputs.
export function addCharacterEditor(node, refresh) {
    if (!node.addDOMWidget || typeof document === "undefined") return;
    node.properties ??= {};
    node.properties.rsNaiCharacter ??= 1;
    node.properties.rsNaiShowAll ??= false;
    const value = name => node.widgets?.find(w => w.name === name);
    const count = () => Math.max(1, Math.min(22, Number(value("character_count")?.value ?? 5)));
    const linked = name => node.inputs?.some(i => i.name === name && i.link != null);
    const root = document.createElement("div");
    root.style.cssText = "display:flex;flex-direction:column;gap:6px;padding:6px;box-sizing:border-box;color:#ddd;background:#18212b;border-radius:8px;font:12px sans-serif";
    const toolbar = document.createElement("div");
    toolbar.style.cssText = "display:flex;gap:4px;flex-wrap:wrap";
    const select = document.createElement("select");
    select.setAttribute("aria-label", "Edit character / 편집할 캐릭터");
    const button = (text, action) => {
        const b = document.createElement("button"); b.textContent = text;
        b.type = "button"; b.addEventListener("click", action); toolbar.append(b); return b;
    };
    toolbar.append(select);
    const canvas = document.createElement("canvas");
    canvas.width = 480; canvas.height = 240;
    canvas.setAttribute("aria-label", "Character centers; drag numbered points / 캐릭터 중심 좌표");
    canvas.style.cssText = "display:block;width:100%;height:180px;touch-action:none;background:#101820;border-radius:6px";
    const status = document.createElement("div");
    status.style.cssText = "white-space:normal;line-height:1.5";
    root.append(toolbar, canvas, status);
    const position = i => [Number(value(`character${i}_x`)?.value ?? .5), Number(value(`character${i}_y`)?.value ?? .5)];
    const assign = (i, x, y) => {
        for (const [axis, coordinate] of [["x", x], ["y", y]]) {
            const name = `character${i}_${axis}`, w = value(name);
            if (!w || linked(name)) continue;
            w.value = Math.round(Math.max(0, Math.min(1, coordinate)) * 10) / 10;
            w.callback?.(w.value);
        }
        node.setDirtyCanvas(true, true);
    };
    const draw = () => {
        const ctx = canvas.getContext("2d"), pad = 18, width = canvas.width - 2 * pad, height = canvas.height - 2 * pad;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.strokeStyle = "#344455"; ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) {
            ctx.beginPath(); ctx.moveTo(pad + width * i / 4, pad); ctx.lineTo(pad + width * i / 4, pad + height); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(pad, pad + height * i / 4); ctx.lineTo(pad + width, pad + height * i / 4); ctx.stroke();
        }
        for (let i = 1; i <= count(); i++) {
            const [x, y] = position(i), enabled = i === 1 || value(`character${i}_enable`)?.value === true;
            const selected = i === node.properties.rsNaiCharacter;
            ctx.beginPath(); ctx.arc(pad + x * width, pad + y * height, selected ? 13 : 10, 0, Math.PI * 2);
            ctx.fillStyle = enabled ? `hsl(${(i - 1) * 137.5 % 360} 55% 40%)` : "#374151";
            ctx.fill(); ctx.strokeStyle = selected ? "#fff" : "#8796a7"; ctx.stroke();
            ctx.fillStyle = "#fff"; ctx.font = "bold 12px sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
            ctx.fillText(String(i), pad + x * width, pad + y * height);
        }
    };
    const update = () => {
        node.properties.rsNaiCharacter = Math.min(count(), Math.max(1, node.properties.rsNaiCharacter));
        select.replaceChildren();
        for (let i = 1; i <= count(); i++) {
            const option = document.createElement("option"); option.value = String(i);
            option.textContent = `${i} · ${String(value(`character${i}`)?.value ?? "").slice(0, 28)}`;
            select.append(option);
        }
        select.value = String(node.properties.rsNaiCharacter);
        const i = node.properties.rsNaiCharacter;
        status.textContent = `${i} · X/Y ${position(i).map(v => v.toFixed(3)).join(" / ")} · Drag a point / 점을 드래그하세요. 좌표는 위치 가이드입니다.${count() > 10 ? " 로컬은 앞 10명만 사용합니다." : ""}${linked(`character${i}_x`) || linked(`character${i}_y`) ? " 연결된 좌표는 입력 노드에서 수정하세요." : ""}`;
        draw();
    };
    select.addEventListener("change", () => { node.properties.rsNaiCharacter = Number(select.value); refresh(node); });
    button("접기/펼치기 · Fold", () => { node.properties.rsNaiShowAll = !node.properties.rsNaiShowAll; refresh(node); });
    const arrange = mode => {
        node.graph?.beforeChange?.();
        for (let i = 1; i <= count(); i++) assign(i, mode === "row" ? i / (count() + 1) : .5, .5);
        node.graph?.afterChange?.(); update();
    };
    button("균등 배치 · Row", () => arrange("row"));
    button("가운데 · Center", () => arrange("center"));
    let drag = null;
    const point = e => {
        const r = canvas.getBoundingClientRect();
        return [((e.clientX - r.left) / r.width * canvas.width - 18) / (canvas.width - 36),
                ((e.clientY - r.top) / r.height * canvas.height - 18) / (canvas.height - 36)];
    };
    canvas.addEventListener("pointerdown", e => {
        if (e.button !== 0 || linked("character_count")) return;
        const [x, y] = point(e);
        let hit = null, distance = 22;
        for (let i = 1; i <= count(); i++) {
            const p = position(i), d = Math.hypot((p[0] - x) * (canvas.width - 36), (p[1] - y) * (canvas.height - 36));
            if (d < distance) { distance = d; hit = i; }
        }
        if (hit == null) return;
        e.preventDefault(); e.stopPropagation();
        node.properties.rsNaiCharacter = hit;
        drag = { id: e.pointerId, character: hit, old: position(hit) };
        canvas.setPointerCapture(e.pointerId); node.graph?.beforeChange?.(); refresh(node);
    });
    canvas.addEventListener("pointermove", e => {
        if (!drag || drag.id !== e.pointerId) return;
        e.stopPropagation(); assign(drag.character, ...point(e)); update();
    });
    const finish = (e, cancel = false) => {
        if (!drag || drag.id !== e.pointerId) return;
        if (cancel) assign(drag.character, ...drag.old);
        drag = null; node.graph?.afterChange?.(); update();
        if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
    };
    canvas.addEventListener("pointerup", e => finish(e));
    canvas.addEventListener("pointercancel", e => finish(e, true));
    canvas.addEventListener("lostpointercapture", e => finish(e, true));
    const widget = node.addDOMWidget("rs_nai_character_editor", "rs-nai-layout", root, { serialize: false });
    widget.serialize = false; widget.serializeValue = () => undefined;
    widget.computeSize = () => [300, 270];
    node.rsNaiEditor = { update };
    for (const w of node.widgets ?? []) {
        if (!/^character\d/.test(w.name)) continue;
        const callback = w.callback;
        w.callback = (...args) => { const r = callback?.apply(w, args); update(); return r; };
    }
    update();
}
