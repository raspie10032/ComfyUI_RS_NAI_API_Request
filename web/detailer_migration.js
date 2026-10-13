import { app } from "../../scripts/app.js";

const replacements = {
    NAICombinedFaceDetailerTest: "NAIMultiCharacterDetailer",
    NAIDetectorCombineLoaderTest: "NAIDetectionCombineLoader",
};

export function migrateDetectionWorkflow(graph) {
    for (const node of graph.nodes ?? []) {
        const replacement = replacements[node.type];
        if (!replacement) continue;
        if (node.type === "NAICombinedFaceDetailerTest") {
            // The prototype stored seed's control_after_generate before preview_only.
            // Values after this slot include Anlas protection; never shift them blindly.
            if (Array.isArray(node.widgets_values)) node.widgets_values.splice(6, 1);
            else if (node.widgets_values) delete node.widgets_values.preview_only;
            const index = node.inputs?.findIndex(input => input.name === "preview_only") ?? -1;
            if (index >= 0) {
                const removed = new Set();
                graph.links = (graph.links ?? []).filter(link => {
                    const target = Array.isArray(link) ? link[3] : link.target_id;
                    const slot = Array.isArray(link) ? link[4] : link.target_slot;
                    if (String(target) !== String(node.id)) return true;
                    if (slot === index) {
                        removed.add(Array.isArray(link) ? link[0] : link.id);
                        return false;
                    }
                    if (slot > index) {
                        if (Array.isArray(link)) link[4]--;
                        else link.target_slot--;
                    }
                    return true;
                });
                for (const source of graph.nodes ?? []) {
                    for (const output of source.outputs ?? []) {
                        if (output.links) output.links = output.links.filter(id => !removed.has(id));
                    }
                }
                node.inputs.splice(index, 1);
            }
            node.properties = { ...node.properties, rs_nai_migrated_correction: true };
        }
        if (!node.title || /^(NAI Face Detailer \(Test\)|NAI Detection Combine Loader \(Test\)|NAI 얼굴 디테일러\(시험\)|NAI 감지 모델 콤바인 로더\(시험\))$/.test(node.title)) {
            delete node.title;
        }
        node.type = replacement;
        if (node.properties?.["Node name for S&R"]) node.properties["Node name for S&R"] = replacement;
    }
    for (const subgraph of graph.definitions?.subgraphs ?? []) migrateDetectionWorkflow(subgraph);
    return graph;
}

app.registerExtension({
    name: "RS.NovelAI.StableDetailerMigration",
    beforeConfigureGraph(graph) {
        migrateDetectionWorkflow(graph);
    },
});
