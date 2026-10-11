# V5 Full Medium Effort

Select **NAI Diffusion V5 Full — Medium Effort** in the existing model input. Existing node names, input order, and the default model remain unchanged.

| Setting | Medium behavior |
| --- | --- |
| General generation / img2img model | `nai-diffusion-5-full-medium` |
| Inpainting / detailer model | `nai-diffusion-5-full-medium-inpainting` |
| Steps | Always 14 |
| Sampler | Always Euler Ancestral |
| CFG Rescale | Always 0 |
| Undesired Content | Fixed Heavy preset; custom base/character negatives are ignored |
| Positive character prompts and positions | Preserved |
| Prompt Guidance / seed | User controlled |
| Inpainting strength below 1 | Sent as `img2img.strength`, with `color_correct=true` |
| Inpainting strength of 1 | Full infill; no nested img2img configuration |

The fixed negative prompt gains an `nsfw` prefix unless the base positive prompt contains `nsfw`, matching the official client. Selecting Medium does not change the stored settings used by other models.

`limit_opus_free=True` verifies an active Opus subscription and available V5 usage before each request attempt. It blocks general img2img, general inpainting, and references before processing images. In this local Linux integration, the existing Focused Inpainting exception remains limited to internally produced detail crops; its nested strength must exactly match the validated crop settings, and unknown fields fail closed. To intentionally allow image-input requests that may cost Anlas, set it to `False`. The preflight checks run within this Python process and do not constitute a server-side spending cap or billing guarantee.

## Validation

The offline suite exercises all three generation nodes through the mocked HTTP boundary, verifies decoded tensor output and raw PNG autosaves, checks character conditioning and mask pixels, and rejects modified Medium settings before any HTTP request. It also verifies Medium requests in the multi-region detailer and the existing V3/V4/V4.5/V5 regression suite.

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

Live validation requires a supplied NovelAI environment token. Image-input validation requires an explicit Anlas budget; the offline suite never calls the live API. The original 2.3.0 release was live-tested for 512×512 Medium text generation only. Image-input results for this patch are recorded after their live checks complete; source or mocked success does not establish live API behavior.

## Protocol references

- [Official Effort documentation](https://docs.novelai.net/en/image/effort/)
- [Official inpainting documentation](https://docs.novelai.net/en/image/inpaint/)
- [NovelAI web client](https://novelai.net/image), checked on 2026-10-11: model IDs and fixed settings in `_app-b1c0ffe38c343809.js`; the `inpaintImg2ImgStrength` to `img2img.strength` conversion in `2952-8caf894fb1bb5206.js`. Client bundle names may change as NovelAI deploys updates.
