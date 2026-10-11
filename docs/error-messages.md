# Execution errors and troubleshooting

Starting with 2.4.6, this package adds an explanation and a suggested next step to node execution failures. Select English, 한국어, or 日本語 in ComfyUI's language settings and refresh the page after updating. Other languages use English.

The error dialog and a read-only field on the failed node show the explanation. The field clears when that node starts again or executes successfully. It is excluded from saved workflow values and does not add an input socket. The backend log and API history retain the English fallback for tools that have no browser language setting.

## Examples

| Error code or group | What the explanation distinguishes | Next action |
| --- | --- | --- |
| `TOKEN_MISSING`, `NAI_AUTH` | Missing local token versus NovelAI HTTP 401 | Set or replace `NAI_ACCESS_TOKEN` in the node folder's `.env`, then restart ComfyUI. |
| `NAI_PAYMENT`, `NAI_FORBIDDEN` | HTTP 402 payment/capacity response versus HTTP 403 access rejection | Check the account and actual server message. A 403 alone does not establish its cause. |
| `NAI_RATE_LIMIT` | HTTP 429 after the existing bounded retry | Reduce concurrent requests and wait. |
| `NAI_TIMEOUT`, `NAI_CONNECTION`, `NAI_SERVER` | No response, lost connection, or server failure | Check connection/service status and account history before resubmitting; remote processing and charges may already have happened. |
| `SUBSCRIPTION_CHECK`, `OPUS_REQUIRED`, `V5_ALLOWANCE` | Failed preflight lookup, inactive/non-Opus subscription, or unavailable/unknown V5 allowance | Check the subscription/allowance. Generation was blocked. |
| `PAID_BLOCKED`, `FREE_CONDITIONS`, `FOCUSED_CROP` | Strict protection or Focused Inpainting requirements rejected the request | Inspect the specific requirement. Disable protection only when deliberately allowing Anlas spending. |
| `CHARACTER_MODEL`, `CHARACTER_LIMIT`, `CHARACTER_INPUT` | Unsupported character slots, too many active characters, or malformed values | Change the model, active count, or reported value. V5 allows 22, V4/V4.5 allows 6; V5 Curated inpainting uses the V4.5 limit. |
| `IMAGE_INPUT`, `MASK_INPUT`, `MASK_EMPTY` | Invalid image/batch, invalid mask, or no editable mask pixels | Connect one valid image/mask and mark the edit area white. |
| Reference and matching errors | Unsupported model/operation, mixed reference kinds, bad cache, or missing matching input | Follow the indicated connection/model/cache instruction. |
| `TAGGER_DEPENDENCY`, `TAGGER_DOWNLOAD`, `TAGGER_MODEL` | Missing/broken packages, download failure, or inconsistent model data | Use the shown Python install command or resolve the named file/download issue. |
| `MEMORY` | RAM or GPU allocation failure | Reduce tagger batch size or use CPU for inference; loading the model still needs RAM. |
| `DISK_FULL`, `FILE_PERMISSION`, `FILE_MISSING` | Full disk, denied file access, or missing path | Fix the reported path/storage issue. A save failure can occur after successful paid generation. |
| `UNKNOWN` | No supported diagnosis matched | Keep the actual exception type and traceback when reporting the issue. |

## Diagnostic details and limits

- The explanation supplements the original exception; its Python type, HTTP response, and traceback are preserved. NovelAI HTTP failures include their status, server `message`/`error` when available, and subscription/generation/Vibe encoding stage. Cancellation is not converted into a failure, and memory errors keep their ComfyUI handling.
- The change adds no generation requests and does not increase retries. Existing retry behavior for HTTP 429 is unchanged; connection failures/timeouts are not automatically resubmitted. HTTP explanations are tested with mocked responses, so tests do not spend Anlas.
- The backend uses explicit error codes at known failure sites. Unknown failures are labeled unknown instead of diagnosing from ambiguous message fragments. Details from external libraries and traceback source lines can remain in English.
- Common credential patterns and the known runtime token are masked from exception messages. Headers, request bodies and encoded images are not added to the explanation. Review a complete ComfyUI report before sharing it: ComfyUI may include workflow prompts, inputs, and unrelated logs separately.
- Browser localization applies to this package's marked execution errors. ComfyUI's own workflow validation errors (for example an unconnected required socket), other extensions' errors, and errors before the custom node imports remain under their original handlers. If the translation file cannot load, the backend English explanation remains available.
