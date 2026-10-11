import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

function language() {
    const locale = app.extensionManager?.setting?.get("Comfy.Locale") ?? "en";
    return String(locale).startsWith("ko") ? "ko" : String(locale).startsWith("ja") ? "ja" : "en";
}
const labels = {
    en: { canvas: "Canvas", output: "Cropped output", local: "Local preview · no Anlas", linked: "Linked dimensions: run to preview", refresh: "Refresh assets", failure: "Could not refresh assets. Check the ComfyUI connection.", empty: "No assets yet. Save one, then refresh." },
    ko: { canvas: "전체 캔버스", output: "잘라낸 결과", local: "로컬 미리보기 · Anlas 소모 없음", linked: "연결된 크기: 실행해서 확인하세요", refresh: "에셋 목록 새로고침", failure: "에셋 목록을 갱신하지 못했습니다. ComfyUI 연결을 확인하세요.", empty: "저장된 에셋이 없습니다. 저장 후 새로고침하세요." },
    ja: { canvas: "全体キャンバス", output: "切り抜き結果", local: "ローカルプレビュー · Anlas不要", linked: "接続されたサイズ: 実行して確認", refresh: "アセット一覧を更新", failure: "アセット一覧を更新できません。ComfyUIの接続を確認してください。", empty: "アセットがありません。保存後に更新してください。" },
};

function sizeOf(node) {
    const names = ["canvas_width", "canvas_height", "placement", "reference_percent"];
    if (node.inputs?.some(i => names.includes(i.name) && i.link != null)) return node.rsNaiInsetSize;
    const value = name => node.widgets?.find(w => w.name === name)?.value;
    const width = Number(value("canvas_width")), height = Number(value("canvas_height"));
    const vertical = ["left", "right"].includes(value("placement"));
    const split = Math.floor((vertical ? width : height) * Number(value("reference_percent")) / 100 + 0.5);
    return [width, height, vertical ? width - split : width, vertical ? height : height - split];
}

app.registerExtension({
    name: "RS.NovelAI.Inset",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!["NAIReferenceInset", "NAICharacterAssetLoad"].includes(nodeData.name)) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = created?.apply(this, arguments);
            if (nodeData.name === "NAIReferenceInset") {
                this.addCustomWidget({
                    name: "rs_nai_inset_dimensions", type: "rs_nai_display", serialize: false,
                    options: { serialize: false }, serializeValue: () => undefined,
                    computeSize: () => [260, 66],
                    draw: (ctx, node, width, y) => {
                        const text = labels[language()];
                        const size = sizeOf(node);
                        ctx.save();
                        ctx.fillStyle = "#b9dfe8";
                        ctx.font = "12px sans-serif";
                        const lines = size ? [`${text.canvas}: ${size[0]} × ${size[1]}`, `${text.output}: ${size[2]} × ${size[3]}`, text.local] : [text.linked, text.local];
                        lines.forEach((line, i) => ctx.fillText(line, 12, y + 17 + i * 19, width - 24));
                        ctx.restore();
                    },
                });
                for (const widget of this.widgets ?? []) {
                    if (!["canvas_width", "canvas_height", "placement", "reference_percent"].includes(widget.name)) continue;
                    const callback = widget.callback;
                    widget.callback = (...args) => {
                        callback?.apply(widget, args);
                        delete this.rsNaiInsetSize;
                        this.imgs = null;
                        this.setDirtyCanvas(true, true);
                    };
                }
            } else {
                const button = this.addWidget("button", labels[language()].refresh, null, async () => {
                    const text = labels[language()];
                    try {
                        const response = await api.fetchApi("/object_info/NAICharacterAssetLoad");
                        if (!response.ok) throw new Error("object_info failed");
                        const data = await response.json();
                        const files = data.NAICharacterAssetLoad.input.required.asset_file[0];
                        const combo = this.widgets.find(w => w.name === "asset_file");
                        combo.options.values = files;
                        if (!files.includes(combo.value)) combo.value = files[0];
                        button.name = files.some(Boolean) ? text.refresh : text.empty;
                        this.setDirtyCanvas(true, true);
                    } catch {
                        button.name = text.failure;
                        this.setDirtyCanvas(true, true);
                    }
                }, { serialize: false });
                button.serialize = false;
                button.serializeValue = () => undefined;
            }
            return result;
        };
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const result = executed?.apply(this, arguments);
            this.rsNaiInsetSize = message?.rs_nai_inset_size;
            this.setDirtyCanvas(true, true);
            return result;
        };
    },
});
