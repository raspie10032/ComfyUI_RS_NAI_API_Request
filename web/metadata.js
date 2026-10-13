import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const targets = new Set(["NovelAIGenerator", "NAIImg2ImgNode", "NAIInpaintNode"]);
const saveNodes = new Set([...targets, "NAIReferenceInsetGenerate", "NAIFaceDetailerNode", "NAIFaceDetailerSegmNode"]);
const labels = {
    en: { select: "Select an image to read its NAI information.", loading: "Reading image…", empty: "No NAI generation information found. The image can still be loaded.", fail: "Could not read this image. Check the file and ComfyUI connection.", prompt: "Prompt", negative: "Negative prompt", characters: "Characters", settings: "Generation settings", history: "Detailing history", missing: "Missing", target: "Apply to…", refresh: "Refresh targets", apply: "Apply settings", applied: "Applied", skipped: "Not applied", copy: "Copy", copied: "Copied", copyFail: "Select the text and copy it manually.", choose: "Choose a generation node first.", detail: "This is a composite of face edits. The original image's generation information is unavailable. Crop prompts are shown in the history, not applied as whole-image prompts.", charSkip: "Characters were not applied: linked/shared inputs, automatic or unsupported coordinates, or the model's character limit. You can copy the text below.", insetSkip: "Inset metadata uses canvas coordinates. Recreate the reference canvas first; automatic application is unavailable.", warnings: {
        unknown_model: "The model could not be identified. Choose it yourself.", automatic_coordinates: "NAI used automatic character positions; this node uses explicit positions.", invalid_exif: "Some EXIF information is damaged.", invalid_hidden_metadata: "Hidden metadata is damaged.", invalid_comment: "Generation information is not valid JSON.", invalid_record: "Additional generation information is damaged.", invalid_characters: "Some character information could not be read.", references_omitted: "Reference images are not embedded. Reconnect them yourself.", source_image_required: "The original source image and mask are not included.", inset_canvas_coordinates: "Character coordinates and requested size refer to the full reference canvas.", detailer_not_base: "The final face request does not describe the whole image."
    } },
    ko: { select: "이미지를 선택하면 NAI 정보를 읽습니다.", loading: "이미지 정보 읽는 중…", empty: "NAI 생성 정보가 없습니다. 이미지는 그대로 불러올 수 있어요.", fail: "이미지를 읽지 못했습니다. 파일과 ComfyUI 연결을 확인하세요.", prompt: "공통 프롬프트", negative: "네거티브", characters: "캐릭터", settings: "생성 설정", history: "얼굴 보정 이력", missing: "없는 정보", target: "적용할 노드 선택", refresh: "대상 목록 새로고침", apply: "설정 적용", applied: "적용됨", skipped: "적용하지 못함", copy: "복사", copied: "복사됨", copyFail: "텍스트를 선택해서 직접 복사하세요.", choose: "적용할 생성 노드를 먼저 선택하세요.", detail: "여러 얼굴을 보정한 합성 이미지입니다. 원본 이미지의 생성 정보는 없습니다. 얼굴별 프롬프트는 보정 이력에서 확인하며 전체 그림 설정으로 적용하지 않습니다.", charSkip: "캐릭터를 적용하지 못했습니다: 입력 연결·공유, 자동 또는 지원하지 않는 좌표, 모델의 캐릭터 수 제한을 확인하세요. 아래 텍스트는 복사할 수 있습니다.", insetSkip: "인셋 정보는 전체 캔버스 기준입니다. 참조 캔버스를 다시 준비해야 하므로 자동 적용은 지원하지 않습니다.", warnings: {
        unknown_model: "모델을 식별하지 못했습니다. 직접 선택하세요.", automatic_coordinates: "NAI에서 캐릭터 자동 배치를 사용했습니다. 현재 캐릭터 노드는 명시적 좌표를 사용합니다.", invalid_exif: "EXIF 정보 일부가 손상되었습니다.", invalid_hidden_metadata: "숨김 메타데이터가 손상되었습니다.", invalid_comment: "생성 정보의 JSON 형식이 올바르지 않습니다.", invalid_record: "추가 생성 정보가 손상되었습니다.", invalid_characters: "일부 캐릭터 정보를 읽지 못했습니다.", references_omitted: "참조 이미지 원본은 파일에 없습니다. 다시 연결하세요.", source_image_required: "원본 입력 이미지와 마스크는 포함되어 있지 않습니다.", inset_canvas_coordinates: "캐릭터 좌표와 요청 크기는 참조 이미지를 포함한 전체 캔버스 기준입니다.", detailer_not_base: "마지막 얼굴 보정 요청은 전체 그림의 생성 정보가 아닙니다."
    } },
    ja: { select: "画像を選ぶとNAI情報を読み取ります。", loading: "画像情報を読み込み中…", empty: "NAI生成情報がありません。画像は読み込めます。", fail: "画像を読み取れません。ファイルとComfyUIの接続を確認してください。", prompt: "共通プロンプト", negative: "ネガティブ", characters: "キャラクター", settings: "生成設定", history: "顔補正の履歴", missing: "不足情報", target: "適用先を選択", refresh: "適用先を更新", apply: "設定を適用", applied: "適用済み", skipped: "適用できなかった項目", copy: "コピー", copied: "コピー済み", copyFail: "テキストを選択してコピーしてください。", choose: "先に生成ノードを選択してください。", detail: "複数の顔を補正した合成画像です。元画像の生成情報はありません。顔ごとのプロンプトは履歴に表示し、全体の設定には適用しません。", charSkip: "キャラクターを適用できません。入力の接続・共有、自動または未対応の座標、モデルの人数制限を確認してください。テキストはコピーできます。", insetSkip: "インセット情報は全体キャンバス基準です。参照キャンバスの再準備が必要なため、自動適用には対応していません。", warnings: {
        unknown_model: "モデルを識別できません。手動で選んでください。", automatic_coordinates: "NAIの自動配置が使われています。現在のノードは明示的な座標を使います。", invalid_exif: "EXIF情報の一部が破損しています。", invalid_hidden_metadata: "隠しメタデータが破損しています。", invalid_comment: "生成情報のJSONが不正です。", invalid_record: "追加の生成情報が破損しています。", invalid_characters: "一部のキャラクター情報を読み取れません。", references_omitted: "参照画像は含まれません。接続し直してください。", source_image_required: "元の入力画像とマスクは含まれません。", inset_canvas_coordinates: "座標と要求サイズは参照画像を含む全体キャンバス基準です。", detailer_not_base: "最後の顔補正リクエストは画像全体の生成情報ではありません。"
    } },
};
function text() {
    const locale = String(app.extensionManager?.setting?.get("Comfy.Locale") ?? "en");
    return labels[locale.startsWith("ko") ? "ko" : locale.startsWith("ja") ? "ja" : "en"];
}
function setValue(node, name, value) {
    const widget = node.widgets?.find(w => w.name === name);
    if (!widget || node.inputs?.some(i => i.name === name && i.link != null)) return false;
    const options = widget.options ?? {};
    if (Array.isArray(options.values) && !options.values.includes(value)) return false;
    if (typeof widget.value !== typeof value) return false;
    if (typeof value === "number" && (!Number.isFinite(value) || value < (options.min ?? -Infinity) || value > (options.max ?? Infinity))) return false;
    widget.value = value;
    widget.callback?.(value);
    return true;
}
function applyMetadata(data, target) {
    const result = { applied: [], skipped: [], characters: true };
    if (!targets.has(target.comfyClass ?? target.type) || data.operation === "detailer" || data.operation === "inset" || data.warnings?.includes("inset_canvas_coordinates")) return result;
    const usesContext = target.inputs?.some(i => i.name === "nai_context" && i.link != null) &&
        target.widgets?.find(w => w.name === "use_context_settings")?.value !== false;
    const inherited = new Set(["prompt", "negative_prompt", "model", "sampler", "scheduler", "steps", "cfg_scale", "cfg_rescale", "prefer_brownian", "variety_boost"]);
    const allowed = new Set(["prompt", "negative_prompt", "model", "width", "height", "seed", "sampler", "scheduler", "steps", "cfg_scale", "cfg_rescale", "prefer_brownian", "variety_boost", "strength", "noise"]);
    // Do not touch spending protection, reference connections, autosave or queue state.
    app.graph.beforeChange?.();
    for (const [key, value] of Object.entries(data.settings ?? {})) {
        if (!allowed.has(key)) continue;
        const applied = !(usesContext && inherited.has(key)) && setValue(target, key, value);
        (applied ? result.applied : result.skipped).push(key);
        if (key === "seed" && applied) setValue(target, "control_after_generate", "fixed");
    }
    const chars = data.characters ?? [];
    const input = target.inputs?.find(i => i.name === "characterPrompts");
    let linked = input?.link != null ? app.graph.links[input.link] : null;
    let characterNode = linked ? app.graph.getNodeById(linked.origin_id) : null;
    const model = target.widgets?.find(w => w.name === "model")?.value ?? "";
    const curatedInpaint = model.includes("V5 Curated") && (target.comfyClass ?? target.type) === "NAIInpaintNode";
    const limit = curatedInpaint ? 6 : model.includes("V5") ? 22 : model.includes("V4") ? 6 : 0;
    const supported = chars.length <= limit && !data.warnings?.includes("automatic_coordinates") && chars.every(c =>
        typeof c.prompt === "string" && typeof c.negative_prompt === "string" && c.centers?.length === 1 &&
        [c.centers[0]?.x, c.centers[0]?.y].every(v => typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 1 && Math.abs(v * 10 - Math.round(v * 10)) < 1e-6));
    const editable = !characterNode || ((characterNode.comfyClass ?? characterNode.type) === "CharacterPromptSelect" &&
        !characterNode.inputs?.some(i => i.link != null) && (characterNode.outputs?.[0]?.links?.length ?? 0) <= 1);
    if (usesContext) { result.characters = data.characters_present === false; }
    else if (data.characters_present === false) { /* Missing character metadata leaves connections intact. */ }
    else if ((chars.length || linked) && (!input || !supported || !editable)) result.characters = false;
    else if (!chars.length && linked) { target.disconnectInput(target.inputs.indexOf(input)); }
    else if (chars.length) {
        if (!characterNode) {
            characterNode = globalThis.LiteGraph.createNode("CharacterPromptSelect");
            if (characterNode) {
                characterNode.pos = [target.pos[0] - 420, target.pos[1]];
                app.graph.add(characterNode);
                characterNode.connect(0, target, target.inputs.indexOf(input));
            }
        }
        if (!characterNode) result.characters = false;
        else {
            setValue(characterNode, "character_count", chars.length);
            chars.forEach((c, i) => {
                const prefix = `character${i + 1}`;
                if (i) setValue(characterNode, `${prefix}_enable`, true);
                setValue(characterNode, prefix, c.prompt);
                setValue(characterNode, `${prefix}_uc`, c.negative_prompt);
                setValue(characterNode, `${prefix}_x`, c.centers[0].x);
                setValue(characterNode, `${prefix}_y`, c.centers[0].y);
            });
            result.applied.push(`characters (${chars.length})`);
        }
    }
    target.setDirtyCanvas?.(true, true);
    app.graph.afterChange?.();
    return result;
}
function qualityVisibility(node) {
    const quality = node.widgets?.find(w => w.name === "webp_quality");
    if (!quality) return;
    const hide = node.widgets.find(w => w.name === "save_format")?.value !== "WebP lossy";
    if (hide && !quality.rsVisible && !quality.type?.startsWith("converted-widget")) {
        quality.rsVisible = { type: quality.type, computeSize: quality.computeSize, hidden: quality.hidden };
        quality.type = "rs-nai-hidden"; quality.hidden = true; quality.computeSize = () => [0, -4];
    } else if (!hide && quality.rsVisible) { Object.assign(quality, quality.rsVisible); delete quality.rsVisible; }
    node.setDirtyCanvas?.(true, true);
}
function element(tag, content, parent) {
    const el = document.createElement(tag);
    if (content != null) el.textContent = content;
    if (tag === "strong") el.style.cssText = "display:block;margin:8px 0 4px;";
    if (tag === "button" || tag === "select") el.style.cssText = "margin:4px 5px 6px 0;padding:4px 7px;border:1px solid #626775;border-radius:4px;background:#353b48;color:#eee;font:inherit;cursor:pointer;";
    if (tag === "summary") el.style.cssText = "padding:4px 0;cursor:pointer;";
    parent?.append(el);
    return el;
}
function panel(node) {
    const root = element("div");
    root.style.cssText = "overflow:auto;padding:10px;box-sizing:border-box;background:#20232a;color:#eee;font:13px sans-serif;line-height:1.5;pointer-events:auto;";
    for (const event of ["pointerdown", "wheel", "keydown"]) root.addEventListener(event, e => e.stopPropagation());
    const widget = node.addDOMWidget("nai_metadata", "rs_nai_metadata", root, { serialize: false, getValue: () => undefined, setValue: () => {} });
    widget.serialize = false;
    widget.computeSize = () => [390, 380];
    let data, sequence = 0;
    function block(title, value, parent = root) {
        element("strong", title, parent);
        const area = element("textarea", null, parent);
        area.value = value; area.readOnly = true; area.rows = Math.min(6, Math.max(2, Math.ceil(value.length / 50)));
        area.style.cssText = "display:block;width:100%;box-sizing:border-box;resize:vertical;background:#15181d;color:#eee;";
        const button = element("button", text().copy, parent);
        button.onclick = async () => { try { await navigator.clipboard.writeText(area.value); button.textContent = text().copied; } catch { button.textContent = text().copyFail; area.select(); } };
    }
    function render(value) {
        data = value; root.replaceChildren();
        const t = text();
        if (!data) { element("p", t.select, root); return; }
        if (data.status === "empty") element("p", t.empty, root);
        if (data.operation === "detailer") element("p", t.detail, root);
        for (const code of data.warnings ?? []) element("p", t.warnings[code] ?? code, root);
        if (data.missing?.length) element("p", `${t.missing}: ${data.missing.join(", ")}`, root);
        const settings = data.settings ?? {};
        if (typeof settings.prompt === "string") block(t.prompt, settings.prompt);
        if (typeof settings.negative_prompt === "string") block(t.negative, settings.negative_prompt);
        (data.characters ?? []).forEach((c, i) => {
            const details = element("details", null, root); element("summary", `${t.characters} ${i + 1} · ${JSON.stringify(c.centers)}`, details);
            block(t.prompt, c.prompt, details); block(t.negative, String(c.negative_prompt ?? ""), details);
        });
        const details = element("details", null, root); element("summary", t.settings, details);
        block(t.settings, JSON.stringify(Object.fromEntries(Object.entries(settings).filter(([k]) => !["prompt", "negative_prompt"].includes(k))), null, 2), details);
        if (data.operation === "detailer") {
            const history = element("details", null, root); element("summary", t.history, history);
            block(t.history, JSON.stringify(data.record?.edits ?? data.detailer_regions ?? [], null, 2), history);
            return;
        }
        if (data.operation === "inset" || data.warnings?.includes("inset_canvas_coordinates")) { element("p", t.insetSkip, root); return; }
        if (!Object.keys(settings).length) return;
        const select = element("select", null, root);
        select.setAttribute("aria-label", t.target);
        const refresh = () => {
            const previous = select.value; select.replaceChildren(); element("option", t.target, select).value = "";
            for (const target of app.graph._nodes ?? []) {
                if (!targets.has(target.comfyClass ?? target.type)) continue;
                element("option", `#${target.id} ${target.title}`, select).value = String(target.id);
            }
            select.value = previous;
        };
        refresh(); element("button", t.refresh, root).onclick = refresh;
        const apply = element("button", t.apply, root);
        const status = element("p", "", root);
        apply.onclick = () => {
            const target = app.graph.getNodeById(select.value);
            if (!target) { status.textContent = t.choose; return; }
            const result = applyMetadata(data, target);
            status.textContent = `${t.applied}: ${result.applied.join(", ") || "—"}. ${t.skipped}: ${result.skipped.join(", ") || "—"}. ${result.characters ? "" : t.charSkip}`;
        };
    }
    async function read() {
        const current = ++sequence;
        // Clear old data before awaiting: the Apply button cannot use the previous image.
        data = null; root.replaceChildren(); element("p", text().loading, root);
        const file = node.widgets?.find(w => w.name === "image")?.value;
        if (!file) { render(null); return; }
        try {
            const response = await api.fetchApi(`/rs_nai/metadata?image=${encodeURIComponent(file)}`, { cache: "no-store" });
            if (!response.ok) throw new Error("metadata");
            const value = await response.json();
            if (current === sequence) render(value);
        } catch { if (current === sequence) { root.replaceChildren(); element("p", text().fail, root); } }
    }
    node.rsReadMetadata = read;
    const image = node.widgets?.find(w => w.name === "image");
    if (image) { const callback = image.callback; image.callback = function () { const result = callback?.apply(this, arguments); read(); return result; }; }
    render(null);
    setTimeout(read, 0);
}
app.registerExtension({
    name: "RS.NovelAI.Metadata",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "NAILoadImage" && !saveNodes.has(nodeData.name)) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = created?.apply(this, arguments);
            if (nodeData.name === "NAILoadImage") { panel(this); this.setSize([420, 620]); }
            else {
                const format = this.widgets?.find(w => w.name === "save_format");
                if (format) { const callback = format.callback; format.callback = function () { const result = callback?.apply(this, arguments); qualityVisibility(thisNode); return result; }; }
                const thisNode = this;
                qualityVisibility(this);
            }
            return result;
        };
        const configured = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = configured?.apply(this, arguments);
            if (nodeData.name === "NAILoadImage") this.rsReadMetadata?.(); else qualityVisibility(this);
            return result;
        };
    },
});
