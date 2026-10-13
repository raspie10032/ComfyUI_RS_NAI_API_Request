import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

let extension;
const sandbox = { app: { registerExtension: value => extension = value } };
vm.runInNewContext(readFileSync(new URL("../web/detailer_migration.js", import.meta.url), "utf8")
    .replace(/^import .*;\n/gm, "").replace(/^export /gm, ""), sandbox);

for (const preview of [true, false]) {
    const tail = [false, true, "all", "wd14", 0.25, 0.08, 1.3, 5, true, "WebP lossy", 87];
    const graph = {
        nodes: [
            { id: 1, type: "Boolean", outputs: [{ links: [10] }] },
            { id: 2, type: "NAICombinedFaceDetailerTest", title: "My detailer",
              widgets_values: ["style", "negative", "NAI Diffusion V5 Full", 0.35, 123, "fixed", preview, ...tail],
              inputs: [{ name: "image", link: 9 }, { name: "preview_only", link: 10 }, { name: "limit_opus_free", link: 11 }],
              properties: { "Node name for S&R": "NAICombinedFaceDetailerTest" } },
            { id: 3, type: "NAIDetectorCombineLoaderTest", widgets_values: ["segm/face.pt", false, "OFF", "OFF", "OFF"] },
        ],
        links: [[9, 4, 0, 2, 0, "IMAGE"], [10, 1, 0, 2, 1, "BOOLEAN"], [11, 5, 0, 2, 2, "BOOLEAN"]],
    };
    extension.beforeConfigureGraph(graph);
    assert.equal(graph.nodes[1].type, "NAIMultiCharacterDetailer");
    assert.equal(graph.nodes[1].title, "My detailer");
    assert.deepEqual(graph.nodes[1].widgets_values.slice(6), tail);
    assert.equal(graph.nodes[1].widgets_values[4], 123);
    assert.equal(graph.nodes[1].inputs[1].name, "limit_opus_free");
    assert.equal(graph.links[1][4], 1);
    assert.equal(graph.nodes[0].outputs[0].links.length, 0);
    assert.equal(graph.nodes[2].type, "NAIDetectionCombineLoader");
    const serialized = JSON.stringify(graph);
    extension.beforeConfigureGraph(graph);
    assert.equal(JSON.stringify(graph), serialized);
    const nested = { definitions: { subgraphs: [JSON.parse(serialized)] } };
    nested.definitions.subgraphs[0].nodes[2].type = "NAIDetectorCombineLoaderTest";
    extension.beforeConfigureGraph(nested);
    assert.equal(nested.definitions.subgraphs[0].nodes[2].type, "NAIDetectionCombineLoader");
}

const named = { nodes: [{ id: "2", type: "NAICombinedFaceDetailerTest",
    widgets_values: { seed: 99, preview_only: true, limit_opus_free: true },
    inputs: [{ name: "preview_only" }, { name: "steps" }] }],
    links: [{ id: 7, origin_id: 1, origin_slot: 0, target_id: 2, target_slot: 1 }] };
extension.beforeConfigureGraph(named);
assert.equal(named.nodes[0].widgets_values.preview_only, undefined);
assert.equal(named.nodes[0].widgets_values.limit_opus_free, true);
assert.equal(named.links[0].target_slot, 0);
console.log("PASS: legacy preview true/false, seed and Anlas values, converted sockets, nested graphs, object links, idempotent reload");
