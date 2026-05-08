# Third-Party Notices

This file lists third-party projects referenced or depended upon by ComfyUI_RS_NAI_API_Request.
This is provided for informational purposes and does not constitute legal advice.

---

## bedovyy/ComfyUI_NAIDGenerator

- **URL**: https://github.com/bedovyy/ComfyUI_NAIDGenerator
- **License**: SPDX-License-Identifier: GPL-3.0-only
- **Use**: Reference for Opus free-generation limit behavior (pixel cap and step cap logic). No source code from this project is bundled in this repository.
- **Bundled**: No (reference only)

---

## ComfyUI-Impact-Pack

- **URL**: https://github.com/ltdrdata/ComfyUI-Impact-Pack
- **License**: SPDX-License-Identifier: GPL-3.0-only
- **Use**: External ComfyUI custom node package providing BBOX_DETECTOR and SAM_MODEL types consumed by the NAI Face Detailer node. Required as an external workflow dependency; no source code from this project is bundled in this repository.
- **Bundled**: No (external runtime dependency; must be installed separately)

---

## ComfyUI-Impact-Subpack

- **URL**: https://github.com/ltdrdata/ComfyUI-Impact-Subpack
- **License**: SPDX-License-Identifier: GPL-3.0-only
- **Use**: Sub-package of ComfyUI-Impact-Pack providing BBOX_DETECTOR types consumed by the NAI Face Detailer node. Bbox loading moved to this package. Required as an external workflow dependency; no source code from this project is bundled in this repository.
- **Bundled**: No (external runtime dependency; must be installed separately)

---

## segment-anything

- **URL**: https://github.com/facebookresearch/segment-anything
- **License**: SPDX-License-Identifier: Apache-2.0
- **Use**: SAM (Segment Anything Model) segmentation library used at runtime by the NAI Face Detailer node for precise mask generation. Installed as a Python package dependency via requirements.txt.
- **Bundled**: No (installed as a package dependency; not vendored)

---

## NovelAI API

- **URL**: https://novelai.net
- **License**: Proprietary external service
- **Use**: Remote image generation API accessed over HTTPS. No NovelAI code or assets are bundled in this repository. Usage is subject to NovelAI's own Terms of Service.
- **Bundled**: No (external service API; no code included)

---

## requests

- **URL**: https://github.com/psf/requests
- **License**: SPDX-License-Identifier: Apache-2.0
- **Use**: HTTP client library used for all NovelAI API calls.
- **Bundled**: No (installed as a package dependency; not vendored)

---

## python-dotenv

- **URL**: https://github.com/theskumar/python-dotenv
- **License**: SPDX-License-Identifier: BSD-3-Clause
- **Use**: Loads `NAI_ACCESS_TOKEN` / `NAI_API_TOKEN` from a `.env` file at startup.
- **Bundled**: No (installed as a package dependency; not vendored)

---

## numpy

- **URL**: https://github.com/numpy/numpy
- **License**: SPDX-License-Identifier: BSD-3-Clause
- **Use**: Array operations for image tensor manipulation.
- **Bundled**: No (installed as a package dependency; not vendored)

---

## Pillow

- **URL**: https://github.com/python-pillow/Pillow
- **License**: SPDX-License-Identifier: HPND (Historical Permission Notice and Disclaimer — Pillow variant)
- **Use**: Image encoding/decoding and format conversion (PNG, JPEG, base64 round-trips).
- **Bundled**: No (installed as a package dependency; not vendored)

---

## torch (PyTorch)

- **URL**: https://github.com/pytorch/pytorch
- **License**: SPDX-License-Identifier: BSD-3-Clause (license to verify for specific build variants)
- **Use**: Tensor type used for ComfyUI IMAGE and MASK values in image_utils helpers.
- **Bundled**: No (external dependency provided by the host ComfyUI environment; not installed by this package)
