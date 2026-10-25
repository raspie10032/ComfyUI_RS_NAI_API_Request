// UI controls proxy the original widgets. Never reorder or replace serialized inputs.
import { contextFields, contextState } from "./context_controls.js";

const copy = {
    ko: {
        title: "멀티 캐릭터 디테일러", subtitle: "감지 → 캐릭터 매칭 → NAI 보정",
        tabs: ["보정", "영역·마스크", "캐릭터 매칭", "생성 설정", "저장·결과"],
        hints: ["보정 강도와 처리할 영역 수를 먼저 조절하세요. 영역 수는 생성할 인원수가 아닙니다.", "크롭은 주변 문맥, 확장은 수정 범위, 부드러움은 합성 경계를 조절합니다. 단위는 원본 이미지 픽셀입니다.", "태거는 원본 캐릭터 프롬프트를 고릅니다. 추정 태그를 프롬프트에 추가하지 않으며 불확실한 매칭은 건너뜁니다. 컨텍스트에 여러 캐릭터가 있으면 자동 매칭을 사용합니다.", "컨텍스트의 값을 가져오거나 선택한 항목만 바꿀 수 있습니다. 접힌 설정도 계속 적용됩니다.", "마지막으로 성공한 요청의 실제 설정과 안내를 확인하세요. 연결 입력의 최종값은 실행할 때 결정됩니다."],
        connected: "연결됨", missing: "연결 없음", inherited: "컨텍스트에서 가져옴 · 실행 시 결정", linked: "연결된 입력에서 설정", override: "직접 변경", manual: "이 노드의 값 사용", context: "NAI 컨텍스트", contextSource: "컨텍스트 설정 사용", clears: "연결 없음 · 기존 캐릭터를 모두 비웁니다", limit: "최대", regions: "영역", last: "마지막으로 성공한 NAI 요청", notices: "실행 안내", source: "설정 출처와 적용 안내", empty: "실행 후 실제 사용한 설정이 여기에 표시됩니다.", protection: "Anlas 보호 켜짐", paid: "Anlas 보호 꺼짐", image: "이미지", detectors: "감지 모델", tagger: "태거", chars: "캐릭터 파이프", external: "실행 시 결정", options: { inherit_all: "전체 컨텍스트 사용", override_selected: "선택 항목만 변경", all: "전체 영역", first: "첫 영역만", shared: "공통 프롬프트", wd14: "태거로 캐릭터 매칭", fixed: "고정", increment: "증가", decrement: "감소", randomize: "무작위" },
    },
    en: {
        title: "Multi-Character Detailer", subtitle: "Detect → match characters → correct with NAI",
        tabs: ["Correction", "Regions & masks", "Character matching", "Generation", "Save & results"],
        hints: ["Start with strength and the region limit. Regions are correction targets, not the number of people to generate.", "Crop adds context; dilation expands the edit; feather blends its edge. Pixel units refer to the source image.", "The tagger selects original character prompts, never adds inferred tags, and skips uncertain matches. Multiple characters in context activate automatic matching.", "Inherit context or replace selected fields. Settings on other tabs still apply.", "Inspect the settings actually used by the last successful request. Connected values are resolved at execution."],
        connected: "Connected", missing: "Not connected", inherited: "From context · resolved at execution", linked: "Set by connected input", override: "Override", manual: "Using this node's values", context: "NAI context", contextSource: "Using context settings", clears: "No connection · clears all inherited characters", limit: "Up to", regions: "regions", last: "Last successful NAI request", notices: "Execution notices", source: "Setting sources and restrictions", empty: "The actual request settings appear here after execution.", protection: "Anlas protection on", paid: "Anlas protection off", image: "Image", detectors: "Detectors", tagger: "Tagger", chars: "Character pipe", external: "Resolved at execution", options: { inherit_all: "Inherit all", override_selected: "Override selected", all: "All regions", first: "First region", shared: "Shared prompt", wd14: "Match with tagger" },
    },
    ja: {
        title: "マルチキャラクターディテーラー", subtitle: "検出 → キャラクター照合 → NAI補正",
        tabs: ["補正", "領域・マスク", "キャラクター照合", "生成設定", "保存・結果"],
        hints: ["補正強度と領域数から調整します。領域数は生成する人数ではありません。", "クロップは周辺文脈、拡張は編集範囲、ぼかしは合成境界を調整します。ピクセルは元画像基準です。", "タガーは元のキャラクタープロンプトを選択します。推定タグは追加せず、不確実な照合はスキップします。コンテキストに複数キャラクターがあると自動照合を使います。", "コンテキストを継承するか、選択した項目を変更します。他のタブの設定も適用されます。", "最後に成功したリクエストの実際の設定を確認します。接続値は実行時に決まります。"],
        connected: "接続済み", missing: "未接続", inherited: "コンテキストから継承・実行時に確定", linked: "接続元で設定", override: "手動変更", manual: "このノードの値を使用", context: "NAIコンテキスト", contextSource: "コンテキスト設定を使用", clears: "未接続・継承キャラクターをすべて消去", limit: "最大", regions: "領域", last: "最後に成功したNAIリクエスト", notices: "実行のお知らせ", source: "設定の取得元と適用条件", empty: "実行後に実際の設定が表示されます。", protection: "Anlas保護オン", paid: "Anlas保護オフ", image: "画像", detectors: "検出モデル", tagger: "タガー", chars: "キャラクターパイプ", external: "実行時に確定", options: { inherit_all: "全項目を継承", override_selected: "選択項目のみ変更", all: "全領域", first: "最初の領域", shared: "共通プロンプト", wd14: "タガーで照合" },
    },
};

const fieldLabels = {
    strength: ["보정 강도", "Strength", "変更強度"], seed: ["시드", "Seed", "シード"],
    control_after_generate: ["실행 후 시드", "Seed after generation", "実行後のシード"],
    max_regions: ["최대 처리 영역", "Maximum regions", "最大処理領域"], detail_mode: ["처리할 영역", "Regions to process", "処理領域"],
    limit_opus_free: ["Anlas 보호", "Anlas protection", "Anlas保護"],
    prompt: ["공통 프롬프트", "Common prompt", "共通プロンプト"], negative_prompt: ["공통 네거티브", "Common negative", "共通ネガティブ"],
    model: ["NAI 모델", "NAI model", "NAIモデル"],
    threshold: ["마스크 임계값", "Mask threshold", "マスクしきい値"], bbox_threshold: ["검출 신뢰도", "Detection confidence", "検出信頼度"],
    crop_factor: ["보정 크롭 배율", "Correction crop factor", "補正クロップ倍率"], closing: ["작은 요철 채우기", "Close small notches", "小さな凹みを補修"],
    fill_holes: ["홀 채우기", "Fill holes", "穴埋め"], dilation: ["마스크 확장 (px)", "Mask dilation (px)", "マスク拡張 (px)"], mask_feather: ["경계 부드러움 (px)", "Mask feather (px)", "境界ぼかし (px)"],
    matching_mode: ["캐릭터 선택 방식", "Character selection", "キャラクター選択"], match_min_score: ["최소 매칭 점수", "Minimum match score", "最小照合スコア"], match_min_margin: ["최소 후보 점수 차이", "Minimum score margin", "最小スコア差"], match_crop_factor: ["매칭 크롭 배율", "Matching crop factor", "照合クロップ倍率"],
    use_context_settings: ["연결된 컨텍스트 사용", "Use connected context", "接続コンテキストを使用"], context_mode: ["컨텍스트 적용 방식", "Context mode", "コンテキストの適用"],
    sampler: ["샘플러", "Sampler", "サンプラー"], steps: ["스텝", "Steps", "ステップ"], cfg_scale: ["CFG", "CFG", "CFG"], scheduler: ["스케줄러", "Scheduler", "スケジューラー"], cfg_rescale: ["CFG 리스케일", "CFG Rescale", "CFGリスケール"], prefer_brownian: ["브라운 운동 우선", "Prefer Brownian", "ブラウン運動を優先"], variety_boost: ["다양성 강화", "Variety Boost", "多様性強化"],
    characterPrompts: ["캐릭터 목록", "Character list", "キャラクター一覧"], normalize_vibe_strengths: ["바이브 강도 정규화", "Normalize vibe strengths", "Vibe強度を正規化"],
    save_format: ["자동 저장 형식", "Autosave format", "自動保存形式"], webp_quality: ["WebP 품질", "WebP quality", "WebP品質"],
    request_delay_seconds: ["요청 전 대기 (초)", "Wait before request (s)", "リクエスト前の待機（秒）"],
};
const detailerPages = [
    ["strength", "seed", "control_after_generate", "detail_mode", "max_regions", "limit_opus_free", "use_context_settings", "model", "prompt", "negative_prompt"],
    ["bbox_threshold", "threshold", "crop_factor", "closing", "fill_holes", "dilation", "mask_feather"],
    ["matching_mode", "match_min_score", "match_min_margin", "match_crop_factor"],
    ["use_context_settings", "context_mode", ...contextFields, "normalize_vibe_strengths"],
    ["save_format", "webp_quality", "request_delay_seconds"],
];
const statusFields = ["rs_nai_context_status", "rs_nai_notice", "rs_nai_parameters"];
export function addDetailerPanel(node, app, nodeData) {
    return addSettingsPanel(node, app, nodeData);
}

// Each node supplies a layout; values, callbacks and serialization remain native.
export function addSettingsPanel(node, app, nodeData, spec = {}) {
    if (!node.addDOMWidget || typeof document === "undefined" || node.rsNaiSettingsPanel) return;
    const pages = (spec.pages ?? detailerPages).map(p => [...p]);
    const reportFields = spec.reports ?? statusFields;
    const owned = new Set([...pages.flat(), ...(spec.hidden ?? ["show_advanced"]), "rs_nai_request_wait", ...contextFields.map(n => `override_${n}`), ...reportFields]);
    const property = spec.property ?? "rsNaiDetailerTab";
    const height = spec.height ?? 610;
    const get = name => node.widgets?.find(w => w.name === name);
    const linked = name => node.inputs?.some(i => i.name === name && i.link != null);
    const definitions = { ...nodeData.input?.required, ...nodeData.input?.optional };
    node.properties ??= {};
    // A node property keeps presentation out of positional/API widget values.
    node.properties.rsNaiInterfaceMode ??= "panel";
    const isPanel = () => node.properties.rsNaiInterfaceMode !== "classic";
    const root = document.createElement("section"); root.className = "rs-nai-detailer-panel rs-nai-settings-panel";
    root.dataset.node = nodeData.name;
    const style = document.createElement("style");
    style.textContent = `
        .rs-nai-detailer-panel {box-sizing:border-box;padding:14px;color:var(--input-text,#e5eaf2);background:var(--comfy-menu-bg,#20252e);border:1px solid #59657955;border-radius:12px;font:12px/1.5 system-ui,sans-serif;width:100%;height:100%;overflow:auto;scrollbar-width:thin;}
        .rs-nai-detailer-panel * {box-sizing:border-box;}
        .rs-nai-detailer-panel .rs-title {font-size:17px;font-weight:650;letter-spacing:-.4px;}
        .rs-nai-detailer-panel .rs-muted {opacity:.7;font-size:11px;}
        .rs-nai-detailer-panel .rs-chips {display:flex;flex-wrap:wrap;gap:5px;margin:10px 0;}
        .rs-nai-detailer-panel .rs-chip {padding:3px 8px;border:1px solid #70809955;border-radius:20px;background:#70809912;font-size:11px;}
        .rs-nai-detailer-panel .rs-chip[data-connected=true] {color:#92d8bd;border-color:#92d8bd55;}
        .rs-nai-detailer-panel .rs-tabs {display:flex;flex-wrap:wrap;gap:4px;border-bottom:1px solid #70809955;padding-bottom:9px;}
        .rs-nai-detailer-panel .rs-tabs[hidden] {display:none;}
        .rs-nai-detailer-panel button {font:inherit;cursor:pointer;padding:7px 9px;border-radius:7px;border:1px solid transparent;background:transparent;color:inherit;}
        .rs-nai-detailer-panel button[aria-selected=true] {background:#6fa4e52b;color:#a4cbff;border-color:#6fa4e566;}
        .rs-nai-detailer-panel button:focus-visible,.rs-nai-detailer-panel input:focus-visible,.rs-nai-detailer-panel select:focus-visible,.rs-nai-detailer-panel textarea:focus-visible {outline:2px solid #92bfff;outline-offset:2px;}
        .rs-nai-detailer-panel .rs-hint {padding:10px 0 12px;color:inherit;opacity:.75;}
        .rs-nai-detailer-panel .rs-row {display:grid;grid-template-columns:minmax(100px,1fr) minmax(120px,1.25fr);align-items:center;gap:9px;border-top:1px solid #70809922;padding:8px 0;}
        .rs-nai-detailer-panel .rs-wide {grid-template-columns:1fr;}
        .rs-nai-detailer-panel .rs-heading {display:flex;gap:8px;align-items:center;justify-content:space-between;}
        .rs-nai-detailer-panel input:not([type=checkbox]),.rs-nai-detailer-panel select,.rs-nai-detailer-panel textarea {font:inherit;color:var(--input-text,#e5eaf2);background:var(--comfy-input-bg,#151a22);border:1px solid #70809966;border-radius:6px;width:100%;min-width:0;padding:7px;}
        .rs-nai-detailer-panel input[type=checkbox] {accent-color:#88b5ee;width:17px;height:17px;justify-self:end;}
        .rs-nai-detailer-panel textarea {resize:vertical;min-height:65px;}
        .rs-nai-detailer-panel details {border-top:1px solid #70809944;margin-top:10px;padding-top:9px;}
        .rs-nai-detailer-panel summary {cursor:pointer;font-weight:600;}
        .rs-nai-detailer-panel pre {font:11px/1.6 system-ui,sans-serif;white-space:pre-wrap;overflow-wrap:anywhere;margin:8px 0;}
        .rs-nai-detailer-panel .rs-override {font-size:10px;display:flex;align-items:center;gap:4px;white-space:nowrap;}
    `;
    root.append(style);
    const header = document.createElement("div"), title = document.createElement("div"), subtitle = document.createElement("div");
    title.className = "rs-title"; subtitle.className = "rs-muted"; header.append(title, subtitle);
    const chips = document.createElement("div"); chips.className = "rs-chips";
    const waiting = document.createElement("div"); waiting.setAttribute("role", "status");
    const nav = document.createElement("div"); nav.className = "rs-tabs"; nav.setAttribute("role", "tablist");
    nav.addEventListener("keydown", e => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
        e.preventDefault();
        node.properties[property] = e.key === "Home" ? 0 : e.key === "End" ? pages.length - 1
            : (tab + (e.key === "ArrowRight" ? 1 : -1) + pages.length) % pages.length;
        refresh(); nav.children[node.properties[property]]?.focus();
    });
    const hint = document.createElement("div"); hint.className = "rs-hint";
    const body = document.createElement("div"); body.setAttribute("role", "tabpanel");
    const reports = document.createElement("div");
    root.append(header, chips, waiting, nav, hint, body, reports);
    // Keep wheel, text selection and keyboard editing inside the panel.
    for (const event of ["pointerdown", "wheel", "keydown"]) root.addEventListener(event, e => e.stopPropagation());
    const dom = node.addDOMWidget(spec.widget ?? "rs_nai_detailer_panel", "rs-nai-settings", root, {
        serialize: false, getMinHeight: () => isPanel() ? height : 0, getMaxHeight: () => isPanel() ? height : 0,
    });
    dom.serialize = false; dom.serializeValue = () => undefined;
    dom.computeSize = () => isPanel() ? [350, height] : [0, -4];
    if (dom.options) dom.options.serialize = false;
    const modeButton = node.addWidget("button", "Panel / Classic widgets", null, () => {
        setMode(isPanel() ? "classic" : "panel");
    }, { serialize: false });
    modeButton.serialize = false; modeButton.serializeValue = () => undefined;
    function setMode(mode) {
        if (!["panel", "classic"].includes(mode) || node.properties.rsNaiInterfaceMode === mode) return;
        node.graph?.beforeChange?.();
        try {
            node.properties.rsNaiInterfaceMode = mode;
            refresh();
            // Reapply native context/advanced visibility after lifting the panel layer.
            node.onConnectionsChange?.();
            node.rsNaiRefreshQualityVisibility?.();
            const size = node.computeSize();
            node.setSize([Math.max(node.size[0], size[0]), size[1]]);
        } finally { node.graph?.afterChange?.(); }
        node.setDirtyCanvas(true, true);
    }
    let signature = "", controls = [], text, lang, tab;
    const label = name => (spec.labels?.[name] ?? fieldLabels[name])?.[lang === "ko" ? 0 : lang === "ja" ? 2 : 1] ?? get(name)?.label ?? name;
    const set = (name, value) => {
        const w = get(name);
        if (!w || linked(name) || w.type?.startsWith("converted-widget")) return;
        if (Object.is(w.value, value)) return;
        node.graph?.beforeChange?.();
        try {
            w.value = value;
            if (w.inputEl) w.inputEl.value = value;
            w.callback?.call(w, value, app.canvas, node);
        } finally { node.graph?.afterChange?.(); }
        refresh(); node.setDirtyCanvas(true, true);
    };
    const row = (name, state) => {
        const w = get(name), isContext = contextFields.includes(name);
        const overrideName = `override_${name}`;
        if (!w && !(name === "characterPrompts" && get("override_characterPrompts") && state.selective)) return;
        if (name === "context_mode" && !state.active) return;
        if (name === "use_context_settings" && node.inputs?.some(i => i.name === "nai_context") && !linked("nai_context")) return;
        if (name === "webp_quality" && !linked("save_format") && get("save_format")?.value !== "WebP lossy") return;
        const inherited = state.active && isContext && !state.selected.has(name);
        const connected = linked(name) || w?.type?.startsWith("converted-widget");
        const fixed = !inherited && !connected ? spec.fixed?.(name, { get, linked, state, lang }) : null;
        const el = document.createElement("div"); el.className = "rs-row"; el.dataset.field = name;
        if (["prompt", "negative_prompt", "model"].includes(name)) el.classList.add("rs-wide");
        const heading = document.createElement("div"); heading.className = "rs-heading";
        const caption = document.createElement("span"); caption.textContent = label(name); heading.append(caption);
        if (state.selective && isContext && get(overrideName)) {
            const toggleLabel = document.createElement("label"); toggleLabel.className = "rs-override";
            const toggle = document.createElement("input"); toggle.type = "checkbox"; toggle.checked = get(overrideName).value === true;
            toggle.disabled = linked(overrideName); toggle.setAttribute("aria-label", `${text.override}: ${label(name)}`);
            toggle.addEventListener("change", () => set(overrideName, toggle.checked));
            toggleLabel.append(toggle, document.createTextNode(text.override)); heading.append(toggleLabel);
        }
        el.append(heading);
        if (inherited || connected || !w || fixed) {
            const note = document.createElement("span"); note.className = "rs-muted";
            note.textContent = inherited ? text.inherited : fixed ?? (name === "characterPrompts" && !linked(name) ? text.clears : text.linked); el.append(note);
        } else {
            const def = definitions[name], type = def?.[0], opts = def?.[1] ?? {};
            const choices = Array.isArray(type) ? type : (typeof w.options?.values === "function" ? w.options.values(w, node) : w.options?.values);
            let input;
            if (Array.isArray(choices)) {
                input = document.createElement("select");
                for (const value of choices) {
                    const option = document.createElement("option"); option.value = String(value); option.textContent = text.options[value] ?? String(value); input.append(option);
                }
                // Preserve a saved value even when a model list is temporarily unavailable.
                if (!choices.some(v => String(v) === String(w.value))) {
                    const option = document.createElement("option"); option.value = String(w.value); option.textContent = String(w.value); input.append(option);
                }
            } else if (type === "BOOLEAN" || typeof w.value === "boolean") {
                input = document.createElement("input"); input.type = "checkbox";
            } else if (type === "INT" || type === "FLOAT" || typeof w.value === "number") {
                input = document.createElement("input"); input.type = "number";
                const options = { ...w.options, ...opts };
                if (options.min != null) input.min = String(options.min);
                if (options.max != null) input.max = String(options.max);
                // LiteGraph's numeric widget step can be scaled by ten; prefer the server schema.
                input.step = String(type === "INT" ? 1 : opts.step ?? "any");
            } else if (!["prompt", "negative_prompt"].includes(name) && (opts.multiline === false || type === "STRING" && !opts.multiline)) {
                input = document.createElement("input"); input.type = "text";
            } else { input = document.createElement("textarea"); }
            input.setAttribute("aria-label", label(name));
            input.title = opts.tooltip ?? w.tooltip ?? "";
            input.addEventListener("change", () => {
                let value = input.type === "checkbox" ? input.checked : input.value;
                if (input.type === "number") {
                    if (!input.value.trim() || !Number.isFinite(Number(value))) { sync(); return; }
                    value = Number(value);
                    if (input.min !== "") value = Math.max(Number(input.min), value);
                    if (input.max !== "") value = Math.min(Number(input.max), value);
                    if (type === "INT") value = Math.trunc(value);
                    input.value = String(value);
                }
                set(name, value);
            });
            caption.addEventListener("click", () => input.focus());
            el.append(input); controls.push({ name, input });
        }
        body.append(el);
    };
    const sync = () => {
        for (const { name, input } of controls) {
            if (document.activeElement === input) continue;
            const value = get(name)?.value;
            if (input.type === "checkbox") input.checked = value === true;
            else if (input.value !== String(value ?? "")) input.value = String(value ?? "");
        }
    };
    function refresh() {
        lang = String(app.ui?.settings?.getSettingValue("Comfy.Locale") ?? "en").slice(0, 2);
        text = { ...(copy[lang] ?? copy.en), ...(spec.copy?.[lang] ?? spec.copy?.en) };
        const panel = isPanel();
        modeButton.label = ({
            ko: panel ? "보기: 패널 → 기존 위젯" : "보기: 기존 위젯 → 패널",
            en: panel ? "View: Panel → Classic widgets" : "View: Classic widgets → Panel",
            ja: panel ? "表示：パネル → 従来ウィジェット" : "表示：従来ウィジェット → パネル",
        })[lang] ?? (panel ? "View: Panel → Classic widgets" : "View: Classic widgets → Panel");
        root.hidden = !panel; dom.hidden = !panel;
        if (!panel) for (const w of node.widgets ?? []) {
            if (!w.rsNaiPanelVisible) continue;
            const saved = w.rsNaiPanelVisible;
            Object.assign(w, { type: saved.type, computeSize: saved.computeSize, hidden: saved.hidden });
            if (w.inputEl) w.inputEl.hidden = saved.inputHidden ?? false;
            if (w.element) w.element.hidden = saved.elementHidden ?? false;
            delete w.rsNaiPanelVisible;
        }
        if (!panel) return;
        tab = Number(node.properties[property]);
        if (!Number.isInteger(tab) || tab < 0 || tab >= pages.length) tab = 0;
        const state = contextState(node);
        // Hide only widgets represented by the panel; future extension controls remain accessible.
        for (const w of node.widgets ?? []) {
            if (!owned.has(w.name) || w.type?.startsWith("converted-widget")) continue;
            // The native extensions may already have folded a widget before panel
            // creation. Lift those layers so Classic can recompute current rules.
            const layers = { "rs-nai-context-hidden": "rsNaiContextVisible", "rs-nai-detection-hidden": "rsNaiDetectionVisible", "rs-nai-hidden": "rsVisible" };
            while (w[layers[w.type]]) {
                const key = layers[w.type];
                Object.assign(w, w[key]); delete w[key];
                if (w.inputEl) w.inputEl.hidden = w.hidden === true;
            }
            if (!w.rsNaiPanelVisible) {
                w.rsNaiPanelVisible = { type: w.type, computeSize: w.computeSize, hidden: w.visibility?.suppression?.byExtension ?? w.hidden, inputHidden: w.inputEl?.hidden, elementHidden: w.element?.hidden };
            }
            // Connected widgets need a native row for their socket and label.
            // Hiding the row collapses their ports onto y=0 in current ComfyUI.
            const connected = linked(w.name), saved = w.rsNaiPanelVisible;
            if (saved.connected !== connected) {
                saved.connected = connected;
                w.type = connected ? saved.type : "rs-nai-panel-hidden";
                w.hidden = !connected;
                w.computeSize = connected ? () => [0, 20] : () => [0, -4];
            }
            if (w.inputEl) w.inputEl.hidden = true;
            if (w.element) w.element.hidden = true;
        }
        title.textContent = text.title; subtitle.textContent = text.subtitle;
        nav.hidden = pages.length === 1; subtitle.hidden = pages.length === 1;
        waiting.textContent = get("rs_nai_request_wait")?.value ?? "";
        waiting.hidden = !waiting.textContent;
        const connections = spec.connections ?? ["image", "detectors", "nai_context", "tagger", "characterPrompts"];
        const chipValues = connections.map(n => [n, linked(n)]);
        if (get("use_context_settings")) chipValues.push(["origin", linked("use_context_settings") || linked("context_mode") ? text.external : state.active ? text.contextSource : text.manual]);
        if (get("max_regions")) chipValues.push(["limit", linked("detail_mode") || linked("max_regions") ? `${text.regions} · ${text.external}` : `${text.limit} ${get("detail_mode")?.value === "first" ? 1 : get("max_regions")?.value} ${text.regions}`]);
        if (get("limit_opus_free")) chipValues.push(["protection", linked("limit_opus_free") ? text.external : get("limit_opus_free")?.value === false ? text.paid : text.protection]);
        const next = JSON.stringify([lang, tab, state.active, state.selective, [...state.selected], node.inputs?.map(i => [i.name, i.link]), node.widgets?.map(w => [w.name, w.type?.startsWith("converted-widget")]), get("save_format")?.value, ...(spec.watch ?? []).map(n => get(n)?.value)]);
        if (next !== signature) {
            signature = next; controls = []; body.replaceChildren(); nav.replaceChildren();
            for (const [i, name] of text.tabs.entries()) {
                const b = document.createElement("button"); b.type = "button"; b.textContent = name;
                b.setAttribute("role", "tab"); b.setAttribute("aria-selected", String(i === tab));
                b.tabIndex = i === tab ? 0 : -1;
                b.addEventListener("click", () => {
                    node.properties[property] = i; refresh();
                    nav.children[i]?.focus(); node.setDirtyCanvas(true, true);
                }); nav.append(b);
            }
            hint.textContent = text.hints[tab];
            for (const name of pages[tab]) row(name, state);
        }
        const chipsKey = JSON.stringify([lang, chipValues]);
        if (chips.dataset.key !== chipsKey) {
          chips.dataset.key = chipsKey; chips.replaceChildren();
          for (const [name, value] of chipValues) {
            const chip = document.createElement("span"); chip.className = "rs-chip";
            if (typeof value === "boolean") {
                chip.dataset.connected = String(value);
                chip.textContent = `${({ image: text.image, detectors: text.detectors, nai_context: text.context, tagger: text.tagger, characterPrompts: text.chars })[name] ?? label(name)} · ${value ? text.connected : text.missing}`;
            } else chip.textContent = value;
            chips.append(chip);
          }
        }
        const resultTab = spec.resultTab ?? pages.length - 1;
        const reportKey = JSON.stringify([lang, tab, ...reportFields.map(n => get(n)?.value)]);
        if (reports.dataset.key !== reportKey) {
            const opened = new Set([...reports.querySelectorAll("details[open]")].map(d => d.dataset.name));
            reports.dataset.key = reportKey; reports.replaceChildren();
            for (const name of reportFields) {
                const value = get(name)?.value;
                if (!value && !(tab === resultTab && name === "rs_nai_parameters")) continue;
                const details = document.createElement("details"), summary = document.createElement("summary"), content = document.createElement("pre");
                details.dataset.name = name; details.open = opened.has(name) || (tab === resultTab && name !== "rs_nai_context_status") || name === "rs_nai_notice";
                summary.textContent = ({ rs_nai_context_status: text.source, rs_nai_notice: text.notices, rs_nai_parameters: text.last })[name] ?? label(name);
                content.textContent = value || text.empty; details.append(summary, content); reports.append(details);
            }
        }
        sync();
    }
    node.rsNaiSettingsPanel = { refresh, root, setMode, isPanel };
    if (!spec.widget) node.rsNaiDetailerPanel = node.rsNaiSettingsPanel;
    // Queue seed controls and other extensions can change values without our input events.
    const draw = node.onDrawForeground;
    node.onDrawForeground = function () { const r = draw?.apply(this, arguments); refresh(); return r; };
    refresh();
}
