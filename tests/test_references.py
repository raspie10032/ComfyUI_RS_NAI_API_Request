import base64
import io
import json
import sys
import tempfile
import threading
import types
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest import mock

import requests
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ComfyUI_RS_NAI_API_Request import generators, references
from ComfyUI_RS_NAI_API_Request.image_utils import pil_to_tensor


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder_paths = mock.patch.dict(sys.modules, {
            "folder_paths": types.SimpleNamespace(
                models_dir=self.temp.name, get_output_directory=lambda: self.temp.name,
            )
        })
        self.folder_paths.start()
        self.addCleanup(self.folder_paths.stop)
        self.image = pil_to_tensor(Image.new("RGB", (48, 64), "red"))
        self.vibes = references.NAIVibeTransfer().build(self.image)[0]
        self.precise = references.NAIPreciseReference().build(self.image)[0]
        self.model = "nai-diffusion-4-5-full"

    def params(self, **kwargs):
        return references.reference_parameters(self.model, "test-token", **kwargs)

    def test_chaining_preserves_previous_settings_and_zero_is_disabled(self):
        chained = references.NAIVibeTransfer().build(self.image, strength=.4, vibes=self.vibes)[0]
        self.assertEqual(len(self.vibes), 1)
        self.assertEqual([v.strength for v in chained], [.6, .4])
        disabled = references.NAIVibeTransfer().build(None, vibes=chained, enabled=False)[0]
        zero = references.NAIVibeTransfer().build(None, strength=0, vibes=chained)[0]
        self.assertEqual(disabled, chained)
        self.assertEqual(zero, chained)
        self.assertEqual(references.NAIPreciseReference().build(None, enabled=False)[0], ())

    def test_bad_batches_nonfinite_values_and_excess_references_rejected(self):
        node = references.NAIVibeTransfer()
        for value in (float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                node.build(self.image, strength=value)
        for value in (-.1, 1.1):
            with self.assertRaises(ValueError):
                node.build(self.image, information_extracted=value)
        with self.assertRaises(ValueError):
            node.build(self.image.repeat(2, 1, 1, 1))
        with self.assertRaises(ValueError):
            node.build(torch.full((1, 16, 16, 3), float("nan")))
        with self.assertRaises(ValueError):
            node.build(self.image, vibes=self.vibes * 16)
        with self.assertRaises(ValueError):
            node.build(self.image, vibes=self.precise)

    def test_precise_canvas_alpha_and_fidelity_serialization(self):
        for size, expected in (((32, 64), (1024, 1536)), ((64, 32), (1536, 1024)), ((48, 48), (1472, 1472)), ((5, 4), (1536, 1024))):
            with self.subTest(size=size):
                transparent = pil_to_tensor(Image.new("RGBA", size, (255, 0, 0, 0)))
                result = references.NAIPreciseReference().build(transparent, reference_type="character&style", strength=.7, fidelity=.8)[0]
                params = self.params(references=result, inpainting=True)
                im = Image.open(io.BytesIO(base64.b64decode(params["director_reference_images"][0])))
                self.assertEqual(im.size, expected)
                self.assertEqual(im.mode, "RGB")
                self.assertEqual(im.getpixel((im.width // 2, im.height // 2)), (0, 0, 0))
                self.assertEqual(params["director_reference_descriptions"][0]["caption"], {
                    "base_caption": "character&style", "char_captions": [],
                })
                self.assertEqual(params["director_reference_information_extracted"], [1.0])
                self.assertEqual(params["director_reference_strength_values"], [.7])
                self.assertAlmostEqual(params["director_reference_secondary_strength_values"][0], .2)

    def test_negative_reference_controls_are_forwarded(self):
        ref = references.NAIPreciseReference().build(self.image, strength=-.3, fidelity=-.2)[0]
        params = self.params(references=ref)
        self.assertEqual(params["director_reference_strength_values"], [-.3])
        self.assertEqual(params["director_reference_secondary_strength_values"], [1.2])
        vibes = (replace(self.vibes[0], strength=-.8), replace(self.vibes[0], strength=.8))
        with mock.patch.object(references, "post_nai", return_value=b"vibe"):
            self.assertEqual(self.params(vibes=vibes)["reference_strength_multiple"], [-.5, .5])

    def test_unsupported_combinations_fail_before_encoding(self):
        cases = [
            ("nai-diffusion-5-full", self.vibes, None, False),
            ("nai-diffusion-5-curated", None, self.precise, True),
            ("nai-diffusion-furry", self.vibes, None, False),
            ("nai-diffusion-4-full", None, self.precise, False),
            (self.model, self.vibes, self.precise, False),
            (self.model, self.vibes, None, True),
        ]
        with mock.patch.object(references, "post_nai") as post:
            for model, vibes, precise, inpaint in cases:
                with self.subTest(model=model, inpaint=inpaint), self.assertRaises(ValueError):
                    references.reference_parameters(model, "test", vibes, precise, inpainting=inpaint)
            post.assert_not_called()

    def test_v4_encodings_cache_and_strength_normalization(self):
        vibes = (replace(self.vibes[0], strength=.8), replace(self.vibes[0], strength=.4))
        with mock.patch.object(references, "post_nai", return_value=b"vibe-binary") as post:
            first = self.params(vibes=vibes)
            second = self.params(vibes=(replace(vibes[0], strength=.3),))
            post.assert_called_once()
            self.assertEqual(post.call_args.kwargs["url"], references.ENCODE_VIBE_URL)
            self.assertEqual(post.call_args.args[1]["model"], self.model)
            self.assertEqual(first["reference_image_multiple"], [base64.b64encode(b"vibe-binary").decode()] * 2)
            self.assertAlmostEqual(first["reference_strength_multiple"][0], 2 / 3)
            self.assertAlmostEqual(first["reference_strength_multiple"][1], 1 / 3)
            self.assertEqual(second["reference_strength_multiple"], [.3])
            self.assertNotIn("reference_information_extracted_multiple", first)
        cache = list(Path(self.temp.name).rglob("*.json"))
        self.assertEqual(len(cache), 1)
        self.assertNotIn("test-token", cache[0].read_text())
        with mock.patch.object(references, "post_nai") as post:
            self.assertEqual(self.params(vibes=vibes), first)
            post.assert_not_called()

    def test_cache_key_changes_for_image_model_and_extraction(self):
        with mock.patch.object(references, "post_nai", return_value=b"vibe") as post:
            self.params(vibes=self.vibes)
            self.params(vibes=(replace(self.vibes[0], information_extracted=.5),))
            blue = references.NAIVibeTransfer().build(pil_to_tensor(Image.new("RGB", (48, 64), "blue")))[0]
            self.params(vibes=blue)
            references.reference_parameters("nai-diffusion-4-full", "test", self.vibes)
            self.assertEqual(post.call_count, 4)

    def test_concurrent_same_vibe_is_encoded_once(self):
        entered = threading.Event()
        release = threading.Event()
        def encode(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(2))
            return b"vibe"
        with mock.patch.object(references, "post_nai", side_effect=encode) as post:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(self.params, vibes=self.vibes)
                self.assertTrue(entered.wait(2))
                second = pool.submit(self.params, vibes=self.vibes)
                release.set()
                self.assertEqual(first.result(2), second.result(2))
            post.assert_called_once()

    def test_failed_or_empty_encoding_is_not_cached(self):
        for result in (RuntimeError("transport failed"), b""):
            with mock.patch.object(references, "post_nai") as post:
                if isinstance(result, Exception):
                    post.side_effect = result
                else:
                    post.return_value = result
                with self.assertRaises(RuntimeError):
                    self.params(vibes=self.vibes)
                self.assertEqual(list(Path(self.temp.name).rglob("*.json")), [])
                self.assertEqual(list(Path(self.temp.name).rglob("*.tmp")), [])
        with mock.patch.object(references, "post_nai", return_value=b"valid"):
            self.params(vibes=self.vibes)

    def test_encoding_payment_error_is_actionable_and_not_retried(self):
        response = requests.Response()
        response.status_code = 402
        with mock.patch.object(references, "post_nai", side_effect=requests.HTTPError(response=response)) as post:
            with self.assertRaisesRegex(RuntimeError, "requires more Anlas"):
                self.params(vibes=self.vibes)
            post.assert_called_once()
        self.assertEqual(list(Path(self.temp.name).rglob("*.json")), [])
        self.assertEqual(list(Path(self.temp.name).rglob("*.tmp")), [])

    def test_corrupt_cache_fails_without_another_paid_encoding(self):
        with mock.patch.object(references, "post_nai", return_value=b"valid"):
            self.params(vibes=self.vibes)
        cache = next(Path(self.temp.name).rglob("*.json"))
        data = json.loads(cache.read_text())
        data["sha256"] = "bad"
        cache.write_text(json.dumps(data))
        with mock.patch.object(references, "post_nai") as post:
            with self.assertRaisesRegex(RuntimeError, "Invalid Vibe cache"):
                self.params(vibes=self.vibes)
            post.assert_not_called()

    def test_v3_uses_png_and_extraction_without_paid_encoder(self):
        with mock.patch.object(references, "post_nai") as post:
            params = references.reference_parameters("nai-diffusion-3", "test", self.vibes, inpainting=True)
            post.assert_not_called()
        raw = base64.b64decode(params["reference_image_multiple"][0])
        self.assertEqual(Image.open(io.BytesIO(raw)).size, (448, 448))
        self.assertEqual(params["reference_information_extracted_multiple"], [1.0])
        self.assertEqual(params["reference_strength_multiple"], [.6])

    def test_empty_references_keep_existing_parameters_unchanged(self):
        with mock.patch.object(references, "post_nai") as post:
            self.assertEqual(references.reference_parameters("nai-diffusion-5-full", "test"), {})
            post.assert_not_called()

    def test_generator_routes_references_without_changing_prompts(self):
        png = io.BytesIO()
        Image.new("RGB", (64, 64), "blue").save(png, format="PNG")
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("image.png", png.getvalue())
        cases = [(generators.NovelAIGenerator, {}, "generate"),
                 (generators.NAIImg2ImgNode, {"image": self.image, "strength": .5}, "img2img"),
                 (generators.NAIInpaintNode, {"image": self.image, "mask": torch.ones((1, 64, 48)), "strength": .5}, "infill")]
        for cls, extra, action in cases:
            with self.subTest(node=cls.__name__), mock.patch.object(generators, "get_nai_token", return_value="test"), mock.patch.object(generators, "post_nai", return_value=archive.getvalue()) as post:
                cls().generate(prompt="original prompt", negative_prompt="original negative", model="NAI Diffusion V4.5 Full", width=64, height=64, sampler="k_euler", steps=1, cfg_scale=5, seed=1, references=self.precise, limit_opus_free=False, **extra)
                payload = post.call_args.args[1]
                self.assertEqual(payload["action"], action)
                self.assertEqual(payload["input"], "original prompt")
                self.assertEqual(payload["parameters"]["v4_negative_prompt"]["caption"]["base_caption"], "original negative")
                self.assertEqual(payload["parameters"]["director_reference_images"], [self.precise[0].image])
                self.assertFalse(any(k.startswith("reference_") for k in payload["parameters"]))

    def test_strict_mode_blocks_references_before_encoding_or_token_read(self):
        with (
            mock.patch.object(generators, "get_nai_token") as token,
            mock.patch.object(references, "post_nai") as encode,
            mock.patch.object(generators, "post_nai") as generate,
        ):
            for kwargs in ({"vibes": self.vibes}, {"references": self.precise}):
                with self.subTest(kwargs=list(kwargs)), self.assertRaisesRegex(RuntimeError, "spend Anlas"):
                    generators.NovelAIGenerator().generate(
                        prompt="p", negative_prompt="n", model="NAI Diffusion V4.5 Full",
                        width=832, height=1216, sampler="k_euler", steps=28,
                        cfg_scale=5, seed=1, **kwargs,
                    )
            token.assert_not_called()
            encode.assert_not_called()
            generate.assert_not_called()
