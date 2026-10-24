import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

// Render the final successful HTTP request, never guesses from connected widgets.
function parameterText(p) {
    if (!p) return "";
    const locale = String(app.ui?.settings?.getSettingValue("Comfy.Locale") ?? "en").slice(0, 2);
    const labels = {
        en: ["Last successful NAI request", "requests; showing the last", "Model", "Action", "Size", "Seed", "Sampler", "Steps", "CFG", "Scheduler", "CFG Rescale", "Brownian", "Variety Boost", "Strength", "Noise", "Characters", "Position guidance", "Negative prompt", "Fixed Heavy (Medium)", "Input negative prompt", "Vibe images", "Precise references", "On", "Off"],
        ko: ["마지막으로 성공한 NAI 요청", "회 요청 중 마지막 설정", "모델", "작업", "크기", "시드", "샘플러", "스텝", "CFG", "스케줄러", "CFG 리스케일", "브라운 운동", "다양성 강화", "변경 강도", "노이즈", "캐릭터 수", "위치 안내", "네거티브", "Heavy 고정 (Medium)", "입력한 네거티브", "Vibe 이미지", "Precise 참조", "켜짐", "꺼짐"],
        ja: ["最後に成功したNAIリクエスト", "回のうち最後の設定", "モデル", "処理", "サイズ", "シード", "サンプラー", "ステップ", "CFG", "スケジューラー", "CFGリスケール", "ブラウン運動", "多様性強化", "変更強度", "ノイズ", "キャラクター数", "位置指定", "ネガティブ", "Heavy固定 (Medium)", "入力ネガティブ", "Vibe画像", "Precise参照", "有効", "無効"],
    };
    const l = labels[locale] ?? labels.en;
    const yes = v => l[v ? 22 : 23];
    const lines = [l[0]];
    if (p.request_count > 1) lines.push(`${p.request_count} ${l[1]}`);
    lines.push(`${l[2]}: ${p.model_name ?? p.model}`, `${l[3]}: ${({ generate: "T2I", img2img: "I2I", infill: "Inpaint" })[p.action] ?? p.action}`);
    if (p.width != null && p.height != null) lines.push(`${l[4]}: ${p.width} × ${p.height}`);
    for (const [key, index] of [["seed", 5], ["sampler", 6], ["steps", 7], ["scale", 8], ["noise_schedule", 9], ["cfg_rescale", 10]]) {
        if (p[key] != null) lines.push(`${l[index]}: ${p[key]}`);
    }
    if (p.prefer_brownian != null) lines.push(`${l[11]}: ${yes(p.prefer_brownian)}`);
    lines.push(`${l[12]}: ${yes(p.skip_cfg_above_sigma != null)}`);
    const strength = p.inpaintImg2ImgStrength ?? p.strength;
    if (strength != null) lines.push(`${l[13]}: ${strength}`);
    if (p.noise != null) lines.push(`${l[14]}: ${p.noise}`);
    lines.push(`${l[15]}: ${p.characters}`);
    if (p.characters) lines.push(`${l[16]}: ${yes(p.coordinates)}`);
    lines.push(`${l[17]}: ${l[p.negative_mode === "fixed_heavy" ? 18 : 19]}`);
    if (p.vibes) lines.push(`${l[20]}: ${p.vibes}`);
    if (p.references) lines.push(`${l[21]}: ${p.references}`);
    return lines.join("\n");
}

function showText(node, name, text) {
    let widget = node.widgets?.find(w => w.name === name);
    if (text) {
        if (!widget) {
            widget = ComfyWidgets.STRING(node, name, ["STRING", { multiline: true }], app).widget;
            widget.options.serialize = false;
            widget.serialize = false;
            widget.serializeValue = () => undefined;
            widget.inputEl.readOnly = true;
        }
        widget.value = text;
    } else if (widget) {
        widget.onRemove?.();
        node.widgets.splice(node.widgets.indexOf(widget), 1);
    }
}

app.registerExtension({
    name: "RS.NovelAI.Notices",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.category !== "RS_NovelAI_API" && !nodeData.category?.startsWith("RS_NovelAI_API/")) return;
        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);
            const text = (message?.rs_nai_notice ?? []).join("\n\n");
            const parameters = parameterText(message?.rs_nai_parameters?.[0]);
            showText(this, "rs_nai_notice", text);
            showText(this, "rs_nai_parameters", parameters);
            (this.rsNaiSettingsPanel ?? this.rsNaiDetailerPanel)?.refresh();
            if (text || parameters) {
                const needed = this.computeSize();
                this.setSize([Math.max(this.size[0], needed[0]), Math.max(this.size[1], needed[1])]);
            }
            this.setDirtyCanvas(true, true);
        };
    },
});
