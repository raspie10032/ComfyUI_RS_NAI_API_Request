# Reference inset and character assets

Reference inset places a reference image beside a blank generation area. NovelAI sees the reference while inpainting the blank area; the generator then crops out the new image. This implements the workflow described in [NovelAI's reference inpainting guide](https://docs.novelai.net/en/image/inpaint/#advanced-reference-inpainting).

The workflow and usability design were also informed by [NAIA 2.0](https://github.com/DNT-LAB/NAIA2.0) and its [NAIA — Reference Inset, V5 Assets introduction](https://arca.live/b/aiart/185642997). Thanks to NAIA for sharing the reference inset and character asset workflow.

## Preview first

1. Add **Load Image** and choose one reference image.
2. Connect it to **NAI Reference Inset** (`NAIReferenceInset`).
3. Choose the whole `canvas_width`/`canvas_height`, reference `placement` (left/right/top/bottom), and `reference_percent` (10–75%). The default is 1216×832 with 50% on the left.
4. The node displays both **Canvas** and **Cropped output** sizes immediately. If a size is connected from another node, execute to obtain the dimensions.
5. Execute this preparation node to see the actual reference canvas. This step is local, needs no API token, and spends no Anlas.

The reference fits without stretching or cropping. Transparent areas become white, and a small black border outlines the reference. The `generation_mask` output is white in the generated area and black on the reference side; connect it to **Convert Mask to Image** and **Preview Image** if you want to inspect it separately.

**Canvas dimensions include the reference.** At 1216×832, a 50% reference on the left gives a **608×832** result. Moving it to the top gives **1216×416**. The crop is exact and is not enlarged afterwards. Percentage splits round to the nearest pixel, so a cropped result may not be a multiple of 64; the API canvas remains a multiple of 64.

## Generate

Connect:

```text
Load Image → NAI Reference Inset → NAI Reference Inset Generate → Preview Image / Save Image
                    inset ───────────→ inset                      image
```

1. Write a prompt describing the reference character and the desired scene. The generator adds `reference inset` if the tag is absent; an existing weighted form is kept.
2. Select a model. **V5 Full** is the default. **V5 Full — Medium Effort** is also supported and uses its fixed 14 steps, Euler Ancestral sampler, and Heavy Undesired Content; its displayed custom negative prompt and step settings are ignored as with the other Medium nodes. V5 Curated currently uses the V4.5 Curated inpainting fallback.
3. Set `limit_opus_free=False` when you intend to permit possible Anlas spending. The default `True` blocks ordinary inpainting before token access or image encoding. Having a small canvas or an Opus subscription does not bypass this protection.
4. Execute. The outputs are **image** (new area only), **full_canvas** (reference plus result), and **applied_prompt** (the exact base prompt after adding the tag).

The generator uses full inpainting strength (1.0). Optional `characterPrompts` come from **NAI Character Prompt Select**. Their X/Y positions describe the cropped output and are mapped into the full canvas before sending. The original prompts are preserved, and the existing model-specific character count limits apply.

The canvas and crop are both autosaved in the normal dated `NAI_autosave` folder. Their names start with `NAI_inset`; the full canvas has `_canvas` at the end. They keep NovelAI text metadata and add `rs_nai_inset` with the full canvas size and crop box. NovelAI's own width/height metadata describes the generation canvas. Pixels outside the generation mask are restored from the prepared reference, even if the server changed them. An unexpected response size raises a specific error instead of silently resizing/cropping.

Reference consistency depends on the model, source, prompt, and available space. A simple reference background is a useful starting point. Style/background can carry into the result, and repeated panels or altered details are possible. Reducing reference space increases the output area but may weaken the reference.

## Save and reuse character assets

**NAI Character Asset Save** (`NAICharacterAssetSave`) accepts one image, a name, the original character prompt, and its negative prompt. Executing saves a PNG under `ComfyUI/input/rs_nai_assets/` and displays an image preview. The unique filename prevents overwriting earlier assets. No API request or tagging is involved.

Add **NAI Character Asset Load** (`NAICharacterAssetLoad`) and click **Refresh assets** after saving. Select the PNG; its outputs are the image and both original prompt strings. Connect the image to Reference Inset, and connect its prompt to a character slot or combine it with your scene prompt using your usual text nodes. To attach a string output to a multiline prompt widget, right-click the destination node and convert that widget to an input.

To move an asset to another ComfyUI installation, copy the PNG into that installation's `input/rs_nai_assets` folder, then refresh the loader. The asset stores only its schema version, display name, and the two supplied prompts under `rs_nai_character_asset` metadata. It does not copy source workflow metadata or API credentials. **The supplied prompts are part of the shared PNG.** Image editors or websites that remove PNG text metadata will remove its asset information.

A normal image PNG is not automatically an asset: use the Save node to attach prompts first. A missing file, invalid metadata, unsupported asset version, or broken file produces a friendly error. Replacing a selected PNG changes the execution cache, so the loader reads the new contents on the next run.

## Language and examples

Set ComfyUI's language to Korean or Japanese for translated node names, inputs, descriptions, outputs, and errors. The live size display and asset refresh button also follow this setting. Model identifiers and some execution details follow the existing English API naming.

- [Local preview workflow](../examples/reference-inset-preview.json): choose an image and execute; no generation request.
- [Generation workflow](../examples/reference-inset-generate.json): choose an image, describe the new scene, inspect output dimensions, then deliberately disable Anlas protection to generate.

The examples use only ComfyUI core nodes and this package. Replace the example image selection with your own file before running.

## Validation

The 2.5.0 implementation was checked with 136 Python regression tests and 5 JavaScript checks. Inset tests cover all four crop directions, fractional splits, extreme reference aspect ratios, alpha handling, request construction, character positions, strict pre-request Anlas blocking, API errors, exact compositing, and metadata. Asset tests cover prompt/pixel roundtrips, cache invalidation, path boundaries, corrupted files, permissions, and incomplete saves.

Both example workflows were opened and executed in ComfyUI through a browser. The preview completed; the generation example stopped with the expected default Anlas protection message. Asset saving, list refresh, loading, and all four node names in English, Korean, and Japanese were checked on the test server and the updated resident Linux server. The input/output schemas of the 15 existing nodes were unchanged. The Windows installation received matching source files; native Windows execution was not tested from Linux.

On 2026-10-11, two user-approved requests were executed through ComfyUI: **V5 Full once and V5 Full Medium Effort once**, at a 1024×768 canvas with a 50% left reference. Both returned a 512×768 crop. The saved canvas kept the reference-side pixels exactly, and the cropped result matched the generated-side pixels exactly. The observed combined Anlas balance change was **0** on the test account; this is not a free-generation guarantee for other accounts or settings. Default Anlas protection remains enabled.

Visual inspection of the blue-robot reference and both results showed the blue body, display face, and red flower carried into the new park-bench scene. Full changed the rendering style more strongly than Medium in these two samples. This is a functional smoke test, not a benchmark of character or style consistency. Other canvas sizes, reference directions, and models have source/mock coverage where noted above, not additional billed generation trials.
