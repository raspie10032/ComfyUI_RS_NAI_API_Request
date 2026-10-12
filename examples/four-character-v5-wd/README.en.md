# Generate four NAI characters and refine their faces in ComfyUI

[한국어](README.md) · **English** · [日本語](README.ja.md)

This guide generates four characters in one image, crops it to the desired aspect ratio, enlarges it by 1.5× with img2img, and refines each face using its original character prompt. The included workflows already have their nodes connected and configured.

The recorded test used **NAI nodes 2.6.0 · V5 Full · WD ViT v3**. The screenshots and shared workflow use custom Korean node titles. Match the numbered steps to the node-name table below when following this English guide. Search for the original names when adding nodes yourself.

**Generate at 1216×832 → center crop to 1152×768 → img2img at 1728×1152 → refine four faces**

## Download the workflows

| File to download | Purpose |
|---|---|
| [Matching preview PNG](NAI_4characters_V5_WD_preview.png?raw=true) · [JSON](NAI_4characters_V5_WD_preview.json?raw=true) | Generate and enlarge the image, then check which character matches each face |
| [Full workflow PNG](NAI_4characters_V5_WD.png?raw=true) · [JSON](NAI_4characters_V5_WD.json?raw=true) | Continue through actual face correction and saving |

**Both PNGs contain ComfyUI `workflow` metadata.** Save the original file, then drag it into ComfyUI. On a GitHub file page, use **Download raw file**. A screenshot or a resized copy from an image service may lose the workflow. Download the JSON files as originals in the same way.

The [Arca Live post](https://arca.live/b/aiart/185683009) has the original Korean explanation and screenshots. Read this document on GitHub, or download the repository using **Code → Download ZIP**, extract it, and open `index.en.html` in this folder for image zoom and an interactive before/after comparison. GitHub's HTML file viewer does not run the guide.

## 0. Start with this sequence

1. Install the requirements below, then drag `NAI_4characters_V5_WD_preview.json` into ComfyUI.
2. For the first run, keep the example prompts and seeds. Allow the WD model download to finish if this is your first use.
3. In **⑤ WD matching preview** and its report, check that all four faces match the correct character slots.
4. If the matches are correct, load and run `NAI_4characters_V5_WD.json`. This file also performs face correction.
5. After checking the result, customize the character prompts and scene.

**This example includes an img2img step that can spend Anlas.** The matching-preview workflow also runs the initial generation and img2img steps. The recorded test on 2026-10-12 spent 18 Anlas in total; this is not a fixed price. Check one run at a time before queuing more.

The full workflow runs both the preview and actual correction. **It does not stop automatically for you to approve the preview**, so use the matching-preview file for your first check.

## 1. Install the requirements and load the workflow

- Install ComfyUI and `ComfyUI_RS_NAI_API_Request` version 2.6.0 or later.
- Install `ComfyUI-Impact-Pack` and `ComfyUI-Impact-Subpack` through Manager.
- Place the face detector `face_yolov8m.pt` in `ComfyUI/models/ultralytics/bbox/` and the SAM model `sam_vit_b_01ec64.pth` in `ComfyUI/models/sams/`. You can search for these filenames in model management to install them.
- Set your own `NAI_ACCESS_TOKEN` in `.env` in the NAI custom-node folder, then restart ComfyUI. The shared files contain no token.
- The tagger is set to `WD ViT v3`. Its required files download on first execution, with progress shown on the loader node.

See the [NAI node README](https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request#configuration-api-token) for installation and token setup. If optional tagger packages are missing, run the installation command shown by the node **in the Python environment used by ComfyUI**, then restart.

| File | Purpose |
|---|---|
| `NAI_4characters_V5_WD_preview.json` | Generate, enlarge, and check face matching |
| `NAI_4characters_V5_WD.json` | Run through face correction and saving |
| `NAI_4characters_V5_WD.png` | PNG containing the same workflow as the full JSON |
| `NAI_4characters_V5_WD_preview.png` | PNG containing the same workflow as the preview JSON |

**Start by dragging the matching-preview PNG or JSON into ComfyUI.** When sharing on Arca Live, upload the original PNG with **Preserve Exif data** (`Exif 데이터 유지`) enabled. Readers must also open the image and save its original PNG. The workflow is stored in the PNG's `workflow` text metadata; the site's Exif-preservation option preserves that information too.

| Step / custom title in the screenshots | Original node name to search for |
|---|---|
| ① Character prompts / 캐릭터 프롬프트 | `NAI Character Prompt Select` |
| ② Initial generation / 기본 생성 | `NAI Image Generator` |
| ③ Center crop / 중앙 크롭 | `ImageCrop` |
| ④ 1.5× img2img / 1.5배 img2img | `NAI Img2Img` |
| Face detection / 얼굴 검출 | `UltralyticsDetectorProvider` |
| Face mask / 얼굴 마스크 | `SAMLoader` |
| Character matching / 캐릭터 판별 | `NAI WD Tagger Loader (PyTorch)` |
| ⑤ WD matching preview / WD 매칭 미리보기; ⑥ Face correction / 얼굴 보정 | `NAI Face Detailer` |

This example uses **a face detector + SAM ViT-B**. You do not need to download SAM3 or a SEGM model for this workflow.

![Complete workflow in ComfyUI](screenshots/01-workflow-overview.png)

## 2. Set up four character prompts

One character-prompt node feeds the initial generator, img2img, and both detailers. It uses **`character_count=4`, with characters 2–4 enabled (`True`)**.

| Character | Distinguishing features | X / Y |
|---|---|---|
| 1 | Blonde hair, long hair, green eyes | 0.2 / 0.5 |
| 2 | Blue hair, short hair, yellow eyes | 0.4 / 0.5 |
| 3 | Red hair, long hair, blue eyes | 0.6 / 0.5 |
| 4 | Black hair, short hair, purple eyes | 0.8 / 0.5 |

All characters in the example are adults. The coordinates are placement hints for the initial generation. WD matching compares tag scores from each cropped face against the original character prompts. Use distinguishing features such as different hair colors. The tagger's predicted tags are not appended to generation prompts.

Put **the scene and composition in the global prompt** and **individual features in the character slots**. Avoid putting all four characters' appearances into one global prompt. The example uses these character prompts:

| Slot | Prompt |
|---|---|
| 1 | `1girl, adult, blonde hair, long hair, green eyes, white shirt` |
| 2 | `1girl, adult, blue hair, short hair, yellow eyes, white shirt` |
| 3 | `1girl, adult, red hair, long hair, blue eyes, white shirt` |
| 4 | `1girl, adult, black hair, short hair, purple eyes, white shirt` |

The global prompt uses `four women standing side by side in a single row` for the arrangement, and `heads fully in frame, generous margins, all faces visible` to help keep heads inside the frame. The complete prompt is stored in the JSON. When changing the scene, check **the global prompts in both the initial generator and img2img nodes**. The character slots are shared through one node.

![Four character prompts and placement settings](screenshots/02-character-prompts.png)

## 3. Crop and enlarge with 1.5× img2img

| Step | Settings |
|---|---|
| Initial generation | V5 Full / 1216×832 / 28 steps / CFG 5 |
| Center crop | 1152×768 / X=32 / Y=32 |
| img2img | 1728×1152 / strength=0.30 / noise=0 / 28 steps / CFG 5 |

Both width and height increase by 1.5×. NAI img2img generates a new image rather than simply resizing pixels. A higher `strength` may change the composition and characters more substantially.

The crop removes 32 pixels from each edge to produce a **3:2 aspect ratio**. Check it first: heads or arms near the edges may be cut off. Then set `1152 × 1.5 = 1728` and `768 × 1.5 = 1152`. Each dimension grows by 1.5×, so the total pixel count grows by 2.25×.

**`limit_opus_free=False` on img2img allows paid requests.** Running this example can spend Anlas. The initial generator and detailer have protection set to True. The detailer uses small Focused Inpainting crops that must meet the protection requirements; requests may be blocked if the account or settings do not qualify. Read the error guidance before deciding to disable protection.

![Initial generation, center crop, and img2img settings](screenshots/03-generation-crop-img2img.png)

## 4. Match faces to characters with WD

| Setting | Value / meaning |
|---|---|
| Face detector | `bbox/face_yolov8m.pt` |
| Mask | `sam_vit_b_01ec64.pth`, `mask_source=sam` |
| WD model | `WD ViT v3` |
| `batch_size` | `4` — number of face crops analyzed together |
| `detail_mode` | `all` — process multiple regions, not only the first face |
| `matching_mode` | `wd14` — select an original character prompt using tagger scores |
| `max_regions` | `4` — maximum number of regions to process |
| Matching thresholds | Minimum score `0.25`; gap between the top two candidates `0.08` |
| Correction strength | `strength=0.35` |

The face detector locates faces, SAM creates masks, and WD selects characters. `max_regions=4` does not force the detector to find four faces. Faces with uncertain character matches are skipped without correction.

**`batch_size=4` is not the number of recognized characters.** It groups four face crops for one tagger batch. If memory is tight, reducing it to 1 still lets the tagger analyze all four faces in sequence. `character_count` controls the candidate character slots; `max_regions` limits the detected regions to process.

Character numbers refer to **the slots you wrote**. Region 1 is not automatically assigned to character 1: each face's scores determine its slot. Matching does not force a unique slot onto each face, so check that all four faces match the intended, distinct characters.

![WD loader and detailer settings](screenshots/04-wd-detailer-settings.png)

**Run `NAI_4characters_V5_WD_preview.json` first.** It omits the actual correction node and its outputs. Check character numbers in the green boxes and report, then load the full JSON. The full JSON enables correction and runs through the final result with one execution. The preview does not automatically approve or block correction.

The preview detailer itself sends no NAI request, but upstream generation and img2img run if they have not run yet or their cache is unavailable. **The preview workflow as a whole is not necessarily free.** In the same ComfyUI session, unchanged inputs and seeds may allow the full workflow to reuse cached upstream results.

After changing settings, apply the **same values to both ⑤ preview and ⑥ actual correction** in the full workflow. They are separate nodes and do not synchronize automatically. Edits in the preview file are not automatically imported into the full file either.

Start with these fields in the report:

| Field | How to read it |
|---|---|
| `region` / `character` | Face region number / selected character slot number |
| `score` / `margin` | Matching score / gap to the next candidate. These are not probabilities of correctness. |
| `status: planned` | Preview plans to use this character |
| `status: edited` | Actual correction completed |
| `status: skipped` | Correction skipped; see `reason` and `explanation` |

The SAM preview in this example is for **checking face detection and character matching**. Inspect `06-used-mask.png` from the final run for the actual SAM edit mask.

![Recorded WD matching result](04-wd-preview.png)

## 5. Saved results

The workflow saves the initial generation, crop, img2img result, WD preview, final image, and actual edit mask under `ComfyUI/output/RS_NAI_4characters/`. This example folder also contains the six recorded result images.

![Output nodes in the actual ComfyUI run](screenshots/05-result-nodes.png)

In the recorded test, the four faces matched character slots 1, 2, 3, and 4 respectively, and all four were corrected. The final image was **1728×1152**, with **0 changed pixels outside the edit mask**. This does not guarantee four correct matches for every image. Overlapping faces or similar appearances can make matching harder.

![Final generated image after face correction](05-final.png)

Seed control is saved as `fixed`. Change the initial generator's seed to create a new image. Even identical settings may produce different results after server-side model changes.

Test date: 2026-10-12, Korea Standard Time. Including one extra initial generation to adjust composition, the observed total deduction was **18 Anlas**: 18 for img2img and 0 for the other steps. Cost varies by account and conditions.

## 6. Troubleshooting

| Symptom | First thing to check |
|---|---|
| Red or unknown nodes | Check that the NAI nodes, Impact Pack, and Impact Subpack are installed; restart ComfyUI. |
| Face detector or SAM model missing from the list | Check the filenames and model folders above, then restart and select them again. |
| Tagger download takes a long time | Check progress on the loader. Follow the specific node guidance for missing packages or download errors. |
| Tagger runs out of memory | Lower `batch_size` to 1. If needed, set the tagger device to `cpu`; CPU inference can be slower. |
| Only three faces are detected | Check the img2img result for hidden, small, or cropped faces. Raising `max_regions` does not create missing detections. |
| Four faces are found, but characters get mixed up | Check distinguishing features such as hair colors and the `characterPrompts` connections. Check whether a matching crop includes a neighboring character. |
| Report says `skipped` | Read its reason first. Lowering thresholds immediately can cause correction with the wrong character prompt. |
| Preview and actual correction choose different characters | Check that both detailers have the same image, character and tagger connections, and matching settings. |
| Correction changes a face too much | Lower `strength` on the actual correction node. Check that the shared correction prompt does not include another character's features. |
| Anlas protection stops execution | Read which step was blocked. Only img2img has protection disabled in this example; the other nodes retain it. |
| Dropping the PNG does not load a workflow | The site or image service may have stripped metadata. Use the included JSON. |

To **recheck matching only** using an already enlarged image, load the saved `03-img2img` result with `Load Image` and use a separate workflow that connects it **only to the preview detailer's image input**. Keep the character slots, detector, and tagger, and leave only preview outputs active. Save nodes still connected to generation or actual correction can cause those branches to execute too.

## 7. Files to include when sharing

Share the workflow PNGs/JSONs, recorded results, and this guide together. **Extract the repository ZIP and open `examples/four-character-v5-wd/index.en.html`** to read the guide and enlarge screenshots without installing a viewer. Keep the entire `four-character-v5-wd` folder together; copying the HTML file alone loses its images.

- **Post text:** `README.en.md` — copy it into your forum editor and attach screenshots at the corresponding positions.
- **Five screenshots:** `screenshots/01` overview → `02` characters → `03` crop/img2img → `04` WD settings → `05` outputs.
- **Key results:** `04-wd-preview.png` and `05-final.png` show matching and the final result.
- **Attachments:** Both full and matching-preview PNGs, plus the two matching JSON files. Preserve metadata when uploading PNGs.

Do not include tokens or `.env` in shared files. Model weights are not bundled; each user installs the models in their own environment.
