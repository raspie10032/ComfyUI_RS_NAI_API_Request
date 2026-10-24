import { app } from "../../scripts/app.js";
import { addSettingsPanel } from "./detailer_panel.js";

// Presentation only: never change INPUT_TYPES, socket types or widget order.
const titles = {
    NovelAIGenerator: ["NAI 이미지 생성", "NAI Image Generation", "NAI画像生成"],
    NAIImg2ImgNode: ["NAI 이미지 변형", "NAI Image to Image", "NAI画像変換"],
    NAIInpaintNode: ["NAI 인페인트", "NAI Inpaint", "NAIインペイント"],
    NAIReferenceInsetGenerate: ["NAI 레퍼런스 인셋 생성", "NAI Reference Inset Generation", "NAI参照インセット生成"],
    NAIFaceDetailerNode: ["NAI 얼굴 디테일러", "NAI Face Detailer", "NAI顔ディテーラー"],
    NAIFaceDetailerSegmNode: ["NAI SEGM 디테일러", "NAI SEGM Detailer", "NAI SEGMディテーラー"],
    NAIDetectionCombineLoader: ["감지 모델", "Detection Models", "検出モデル"],
    RSWDTaggerLoader: ["캐릭터 매칭 태거", "Character Matching Tagger", "キャラクター照合タガー"],
    NAIVibeTransfer: ["바이브 레퍼런스", "Vibe Reference", "Vibe参照"],
    NAIPreciseReference: ["정밀 레퍼런스", "Precise Reference", "精密参照"],
    NAIReferenceInset: ["레퍼런스 캔버스 준비", "Prepare Reference Canvas", "参照キャンバスの準備"],
    NAICharacterAssetSave: ["캐릭터 에셋 저장", "Save Character Asset", "キャラクター素材の保存"],
};
const labels = {
    width: ["너비", "Width", "幅"], height: ["높이", "Height", "高さ"],
    strength: ["변경 강도", "Strength", "変更強度"], noise: ["노이즈", "Noise", "ノイズ"],
    face_segm_model: ["SEGM 모델", "SEGM model", "SEGMモデル"], face_bbox_model: ["BBOX 모델", "BBOX model", "BBOXモデル"],
    sam_model: ["SAM 모델", "SAM model", "SAMモデル"], eye_bbox_model: ["보조 눈 감지", "Extra eye detection", "補助の目検出"],
    rs_detector_plan: ["현재 선택의 실행 방식", "Selected execution plan", "現在の実行方式"],
    rs_tagger_status: ["모델 준비 상태", "Model preparation", "モデル準備状況"],
    model_name: ["태거 모델", "Tagger model", "タガーモデル"], device: ["실행 장치", "Device", "実行デバイス"], batch_size: ["배치 크기", "Batch size", "バッチサイズ"],
    mask: ["마스크", "Mask", "マスク"], detail_mask: ["외부 마스크", "External mask", "外部マスク"],
    bbox_detector: ["BBOX 감지기", "BBOX detector", "BBOX検出器"], segm_detector: ["SEGM 감지기", "SEGM detector", "SEGM検出器"],
    eye_bbox_detector: ["보조 눈 감지기", "Extra eye detector", "補助の目検出器"],
    mask_source: ["마스크 선택 방식", "Mask source", "マスクの選択"], preview_only: ["미리보기만 실행", "Preview only", "プレビューのみ"],
    vibes: ["바이브", "Vibes", "Vibe"], references: ["정밀 레퍼런스", "Precise references", "精密参照"], inset: ["인셋 캔버스", "Inset canvas", "インセットキャンバス"],
    enabled: ["사용", "Enabled", "有効"], information_extracted: ["추출할 정보량", "Information extracted", "抽出情報量"],
    reference_type: ["참조할 요소", "Reference type", "参照する要素"], fidelity: ["원본 충실도", "Fidelity", "忠実度"],
    canvas_width: ["전체 캔버스 너비", "Full canvas width", "全体キャンバスの幅"], canvas_height: ["전체 캔버스 높이", "Full canvas height", "全体キャンバスの高さ"],
    placement: ["레퍼런스 위치", "Reference placement", "参照の位置"], reference_percent: ["레퍼런스 비율 (%)", "Reference share (%)", "参照の割合 (%)"],
    name: ["에셋 이름", "Asset name", "素材名"],
};
const sampling = ["sampler", "steps", "cfg_scale", "scheduler", "cfg_rescale", "prefer_brownian", "variety_boost", "noise", "normalize_vibe_strengths"];
const save = ["save_format", "webp_quality", "request_delay_seconds"];
const reports = ["rs_nai_context_status", "rs_nai_notice", "rs_nai_parameters"];
const modes = {
    generation: {
        pages: [["use_context_settings", "context_mode", "model", "width", "height", "strength", "seed", "control_after_generate", "limit_opus_free"], ["prompt", "negative_prompt", "characterPrompts"], sampling, save],
        tabs: [["생성", "Generation", "生成"], ["프롬프트", "Prompts", "プロンプト"], ["샘플링", "Sampling", "サンプリング"], ["저장·결과", "Save & results", "保存・結果"]],
        hints: [["프롬프트와 크기를 먼저 정하세요. 연결된 컨텍스트의 항목은 가져오고, 선택한 항목만 직접 변경합니다.", "Start with prompts and size. Connected context supplies inherited fields; override only selected fields.", "プロンプトとサイズを設定します。接続コンテキストを継承し、選択した項目だけ変更できます。"], ["공통 프롬프트·네거티브와 캐릭터 파이프를 설정합니다.", "Configure common prompts, negatives and the character pipe.", "共通プロンプト・ネガティブとキャラクターパイプを設定します。"], ["샘플링 세부 설정입니다. 다른 탭의 설정도 계속 적용됩니다.", "Sampling details. Settings on other tabs still apply.", "サンプリングの詳細設定です。他のタブの設定も適用されます。"], ["실행 후 마지막으로 성공한 요청의 실제 값을 확인하세요.", "Inspect the actual values of the last successful request after execution.", "実行後、最後に成功したリクエストの実際の値を確認します。"]],
        height: 610,
    },
    detailer: {
        pages: [["preview_only", "strength", "seed", "control_after_generate", "detail_mode", "max_regions", "limit_opus_free", "model", "prompt", "negative_prompt"], ["mask_source", "bbox_threshold", "threshold", "crop_factor", "dilation"], ["matching_mode", "match_min_score", "match_min_margin", "match_crop_factor"], sampling, save],
        tabs: [["보정", "Correction", "補正"], ["영역·마스크", "Regions & masks", "領域・マスク"], ["캐릭터 매칭", "Character matching", "キャラクター照合"], ["샘플링", "Sampling", "サンプリング"], ["저장·결과", "Save & results", "保存・結果"]],
        hints: [["미리보기로 감지 영역을 확인한 뒤 강도와 영역 수를 조절하세요.", "Preview detected regions, then adjust strength and the region limit.", "検出領域をプレビューしてから強度と領域数を調整します。"], ["크롭은 문맥, 확장은 수정 범위를 조절합니다.", "Crop controls context; dilation controls the edit area.", "クロップは文脈、拡張は編集範囲を調整します。"], ["태거는 연결된 원본 캐릭터를 선택합니다. 추정 태그는 프롬프트에 추가하지 않습니다.", "The tagger selects connected original characters; inferred tags are never added to prompts.", "タガーは元のキャラクターを選択します。推定タグは追加しません。"], ["보정 요청의 샘플링 설정입니다.", "Sampling settings for correction requests.", "補正リクエストのサンプリング設定です。"], ["저장 설정과 실제 요청 결과를 확인하세요.", "Save settings and actual request results.", "保存設定と実際のリクエスト結果を確認します。"]],
        height: 610,
    },
    detection: {
        pages: [["face_segm_model", "face_bbox_model", "sam_model", "eye_bbox_model"]],
        tabs: [["감지 모델", "Detection", "検出"]],
        hints: [["SEGM을 선택하면 BBOX·SAM은 건너뜁니다. SEGM을 OFF로 두면 BBOX 또는 BBOX+SAM을 사용합니다.", "SEGM takes priority and skips BBOX/SAM. With SEGM OFF, use BBOX or BBOX + SAM.", "SEGM優先時はBBOX・SAMを使いません。SEGMがOFFならBBOXまたはBBOX+SAMを使います。"]], height: 440,
    },
    tagger: {
        pages: [["model_name", "device", "batch_size"]], tabs: [["태거", "Tagger", "タガー"]],
        hints: [["선택한 모델만 실행 시 준비합니다. 캐릭터 매칭에 사용하며 프롬프트는 바꾸지 않습니다.", "Only the selected model is prepared at execution. Matches characters without rewriting prompts.", "実行時に選択モデルのみ準備します。プロンプトを変えずキャラクターを照合します。"]], height: 350,
    },
    reference: {
        pages: [["enabled", "reference_type", "strength", "fidelity", "information_extracted"]], tabs: [["레퍼런스", "Reference", "参照"]],
        hints: [["사용을 끄면 이 이미지 추가만 건너뜁니다. 연결된 이전 레퍼런스는 유지됩니다.", "Disabling skips this image while preserving earlier references in the chain.", "無効にするとこの画像だけ追加せず、接続済みの参照は維持します。"]], height: 410,
    },
    inset: {
        pages: [["canvas_width", "canvas_height", "placement", "reference_percent"]], tabs: [["배치", "Layout", "配置"]],
        hints: [["로컬에서 캔버스를 준비합니다. 생성 결과 크기는 레퍼런스 영역을 제외한 크기입니다.", "Prepare the canvas locally. Output dimensions exclude the reference area.", "ローカルでキャンバスを準備します。出力サイズは参照領域を除いたサイズです。"]], height: 420,
    },
    asset: {
        pages: [["name", "prompt", "negative_prompt"]], tabs: [["에셋 저장", "Save asset", "素材の保存"]],
        hints: [["연결된 이미지와 프롬프트를 캐릭터 에셋으로 저장합니다.", "Save the connected image and prompts as a character asset.", "接続画像とプロンプトをキャラクター素材として保存します。"]], height: 460,
    },
};
const index = lang => lang === "ko" ? 0 : lang === "ja" ? 2 : 1;
const modeFor = name => name.includes("FaceDetailer") ? "detailer" : ({
    NAIDetectionCombineLoader: "detection", RSWDTaggerLoader: "tagger", NAIVibeTransfer: "reference", NAIPreciseReference: "reference", NAIReferenceInset: "inset", NAICharacterAssetSave: "asset",
})[name] ?? "generation";

function fixed(name, { get, linked, state, lang }) {
    if (linked("model") || state.active && !state.selected.has("model")) return null;
    if (!String(get("model")?.value).includes("Medium Effort")) return null;
    const values = { steps: "14", sampler: "Euler Ancestral", cfg_rescale: "0", negative_prompt: "Heavy UC" };
    if (!(name in values)) return null;
    return ["Medium 고정", "Fixed by Medium", "Medium固定"][index(lang)] + ` · ${values[name]}`;
}

export function panelSpec(nodeData) {
    const mode = modeFor(nodeData.name), layout = modes[mode];
    const definitions = { ...nodeData.input?.required, ...nodeData.input?.optional };
    const pages = layout.pages.map(p => p.filter(n => n in definitions || n === "control_after_generate" || n === "characterPrompts" && "override_characterPrompts" in definitions));
    const assigned = new Set(pages.flat());
    // New server settings stay reachable without duplicating override switches.
    for (const [name, [type]] of Object.entries(definitions)) {
        if (!assigned.has(name) && !name.startsWith("override_") && !["show_optional_models", "show_advanced"].includes(name) && (Array.isArray(type) || ["STRING", "INT", "FLOAT", "BOOLEAN"].includes(type))) pages[pages.length - 1].push(name);
    }
    const copy = Object.fromEntries(["ko", "en", "ja"].map(lang => [lang, {
        title: titles[nodeData.name][index(lang)], subtitle: ["연결 → 설정 → 실행 결과", "Connect → configure → results", "接続 → 設定 → 実行結果"][index(lang)],
        tabs: layout.tabs.map(t => t[index(lang)]), hints: layout.hints.map(t => t[index(lang)]),
    }]));
    return {
        widget: "rs_nai_settings_panel", property: "rsNaiSettingsTab", pages, copy, labels, height: layout.height,
        hidden: ["show_optional_models", "show_advanced"], watch: ["model"], fixed,
        reports: mode === "detection" ? ["rs_detector_plan", "rs_tagger_status", "rs_nai_notice"] : mode === "tagger" ? ["rs_tagger_status", "rs_nai_notice"] : mode === "generation" || mode === "detailer" ? reports : ["rs_nai_notice"],
        connections: Object.entries(definitions).filter(([, [t]]) => typeof t === "string" && !["STRING", "INT", "FLOAT", "BOOLEAN"].includes(t)).map(([name]) => name),
    };
}

app.registerExtension({
    name: "RS.NovelAI.NodePanels",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (!(nodeData.name in titles)) return;
        for (const hook of ["onNodeCreated", "onConfigure", "onConnectionsChange", "onExecuted"]) {
            const previous = nodeType.prototype[hook];
            nodeType.prototype[hook] = function () {
                const result = previous?.apply(this, arguments);
                if (hook === "onNodeCreated") addSettingsPanel(this, app, nodeData, panelSpec(nodeData));
                this.rsNaiSettingsPanel?.refresh();
                if (this.rsNaiSettingsPanel && hook !== "onExecuted") {
                    const size = this.computeSize();
                    this.setSize([Math.max(this.size[0], 390, size[0]), size[1]]);
                }
                return result;
            };
        }
    },
});
