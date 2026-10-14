// Shared by the T2I/I2I controls and the detailer's advanced-panel folding.
export const contextFields = ["prompt", "negative_prompt", "model", "sampler", "steps", "cfg_scale", "scheduler", "cfg_rescale", "prefer_brownian", "variety_boost", "characterPrompts"];
export const contextControls = ["use_context_settings", "context_mode", ...contextFields.map(name => `override_${name}`)];
export const contextFieldLabels = {
    en: ["Prompt", "Negative prompt", "Model", "Sampler", "Steps", "CFG", "Scheduler", "CFG Rescale", "Brownian", "Variety Boost", "Character list"],
    ko: ["공통 프롬프트", "공통 네거티브", "모델", "샘플러", "스텝", "CFG", "스케줄러", "CFG 리스케일", "브라운 운동", "다양성 강화", "캐릭터 목록"],
    ja: ["共通プロンプト", "共通ネガティブ", "モデル", "サンプラー", "ステップ", "CFG", "スケジューラー", "CFGリスケール", "ブラウン運動", "多様性強化", "キャラクター一覧"],
};

export function contextState(node) {
    const value = name => node.widgets?.find(w => w.name === name)?.value;
    const active = Boolean(node.inputs?.some(i => i.name === "nai_context" && i.link != null)) && value("use_context_settings") !== false;
    const selective = active && value("context_mode") === "override_selected";
    const selected = new Set(selective ? contextFields.filter(name => value(`override_${name}`) === true) : []);
    return { active, selective, selected };
}

// undefined delegates to the node's usual manual/advanced visibility rules.
export function contextWidgetHidden(name, state) {
    if (name === "context_mode") return !state.active;
    if (contextFields.some(field => name === `override_${field}`)) return !state.selective;
    if (state.active && contextFields.includes(name)) return !state.selected.has(name);
    return undefined;
}
