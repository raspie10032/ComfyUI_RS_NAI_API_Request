"""Reference geometry, real node payloads with mocked HTTP, and asset persistence."""

import base64
from contextlib import ExitStack
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo
import requests
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ComfyUI_RS_NAI_API_Request import assets, generators, inset, nai_api


class InsetTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(mock.patch.object(inset, "_preview_directory", return_value=self.root / "preview"))
        self.stack.enter_context(mock.patch.object(generators.NovelAIGenerator, "_get_output_directory", return_value=self.root / "output"))
        self.token = self.stack.enter_context(mock.patch.object(inset, "get_nai_token", return_value="dummy"))
        self.post = self.stack.enter_context(mock.patch.object(nai_api._session, "post"))
        self.stack.enter_context(mock.patch.object(nai_api, "wait_until"))
        self.stack.enter_context(mock.patch.object(nai_api, "_next_request_at", 0))
        self.source = torch.zeros((1, 80, 40, 3))
        self.source[..., 0] = 1

    def prepare(self, side="left", width=128, height=128, percent=50):
        return inset.NAIReferenceInset().prepare(self.source, width, height, side, percent, unique_id="1")

    def options(self, value):
        return dict(inset=value, prompt="blue bird", negative_prompt="bad", model="NAI Diffusion V5 Full",
                    seed=123, steps=28, cfg_scale=6, limit_opus_free=False)

    def response(self, size=(128, 128)):
        pixels = np.zeros((size[1], size[0], 3), dtype=np.uint8)
        pixels[..., 0] = np.arange(size[0]) % 256
        pixels[..., 1] = np.arange(size[1])[:, None] % 256
        image = Image.fromarray(pixels)
        metadata = PngInfo()
        metadata.add_text("Comment", '{"seed":123}')
        data = io.BytesIO()
        image.save(data, format="PNG", pnginfo=metadata)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("image_0.png", data.getvalue())
        response = requests.Response()
        response.status_code = 200
        response._content = archive.getvalue()
        response._content_consumed = True
        self.post.return_value = response
        return pixels

    def test_four_directions_partition_canvas_and_crop_exact_coordinates(self):
        boxes = {"left": (64, 0, 128, 128), "right": (0, 0, 64, 128), "top": (0, 64, 128, 128), "bottom": (0, 0, 128, 64)}
        for side, box in boxes.items():
            with self.subTest(side=side):
                result = self.prepare(side)
                value, canvas, mask = result["result"]
                self.assertEqual(value.target_box, box)
                expected_mask = np.zeros((128, 128), dtype=np.uint8)
                x0, y0, x1, y1 = box
                expected_mask[y0:y1, x0:x1] = 255
                np.testing.assert_array_equal(np.asarray(value.mask), expected_mask)
                self.assertEqual(mask.sum().item(), 8192)
                self.assertEqual(result["ui"]["rs_nai_inset_size"], [128, 128, x1-x0, y1-y0])
                self.assertEqual(result["ui"]["rs_nai_notice"], [])
                self.assertTrue((self.root / "preview" / result["ui"]["images"][0]["filename"]).is_file())
                pixels = self.response()
                cropped, full, prompt = inset.NAIReferenceInsetGenerate().generate(**self.options(value))
                np.testing.assert_allclose(cropped[0].numpy(), pixels[y0:y1, x0:x1] / 255, atol=1e-7)
                keep = expected_mask == 0
                np.testing.assert_allclose(full[0].numpy()[keep], canvas[0].numpy()[keep])
                self.assertEqual(prompt, "reference inset, blue bird")

    def test_portrait_is_fitted_without_stretching_and_alpha_composites_white(self):
        value = self.prepare()["result"][0]
        array = np.array(value.canvas)
        ys, xs = np.where((array[..., 0] == 255) & (array[..., 1] == 0))
        self.assertEqual((xs.max()-xs.min()+1, ys.max()-ys.min()+1), (60, 120))
        self.source = torch.cat((self.source, torch.zeros((1,80,40,1))), dim=-1)
        value = self.prepare()["result"][0]
        self.assertEqual(value.canvas.getpixel((32,64)), (255,255,255))
        self.token.assert_not_called()
        self.post.assert_not_called()

    def test_output_size_and_fractional_split_are_not_silently_resized(self):
        result = self.prepare(width=1216, height=832, percent=33)
        self.assertEqual(result["ui"]["rs_nai_inset_size"], [1216,832,815,832])
        result = self.prepare(width=64, height=64, percent=10)
        self.assertEqual(result["result"][0].target_box, (6,0,64,64))

    def test_extreme_aspect_ratio_still_fits_small_reference_area(self):
        for shape in ((1, 1, 1024, 3), (1, 1024, 1, 3)):
            self.source = torch.zeros(shape)
            result = self.prepare(width=64, height=64, percent=10)
            self.assertEqual(result["result"][0].canvas.size, (64,64))

    def test_strict_guard_precedes_token_encoding_and_network(self):
        with mock.patch.object(inset, "pil_to_base64") as encode:
            with self.assertRaisesRegex(RuntimeError, "RS NAI:PAID_BLOCKED"):
                inset.NAIReferenceInsetGenerate().generate(**{**self.options(None), "limit_opus_free": True})
        self.token.assert_not_called()
        encode.assert_not_called()
        self.post.assert_not_called()

    def test_full_and_medium_payloads_map_characters_and_preserve_metadata(self):
        value = self.prepare()["result"][0]
        character = generators.CharacterPrompt("blue wings", "red wings", 0.5, 0.25)
        for medium in (False, True):
            with self.subTest(medium=medium):
                self.response()
                options = self.options(value)
                if medium: options["model"] = "NAI Diffusion V5 Full — Medium Effort"
                options["characterPrompts"] = [character]
                inset.NAIReferenceInsetGenerate().generate(**options)
                payload = self.post.call_args.kwargs["json"]
                p = payload["parameters"]
                self.assertEqual(payload["model"], "nai-diffusion-5-full" + ("-medium" if medium else "") + "-inpainting")
                self.assertEqual(payload["action"], "infill")
                self.assertEqual(p["inpaintImg2ImgStrength"], 1)
                self.assertNotIn("img2img", p)
                self.assertEqual(p["steps"], 14 if medium else 28)
                self.assertEqual(p["n_samples"], 1)
                self.assertEqual(p["v4_prompt"]["caption"]["char_captions"][0]["centers"], [{"x":0.75,"y":0.25}])
                self.assertEqual(character.center, {"x":0.5,"y":0.25})
                decoded = Image.open(io.BytesIO(base64.b64decode(p["mask"])))
                np.testing.assert_array_equal(np.array(decoded), np.array(value.mask))
        saved = list((self.root/"output").rglob("*.png"))
        self.assertEqual(len(saved),4)
        for path in saved:
            with Image.open(path) as image:
                self.assertEqual(json.loads(image.info["Comment"]), {"seed":123})
                self.assertEqual(json.loads(image.info["rs_nai_inset"])["crop_box"], [64,0,128,128])

    def test_bad_response_size_stops_before_autosave_and_does_not_retry(self):
        self.response((64,64))
        with self.assertRaisesRegex(RuntimeError, "RS NAI:INSET_RESPONSE"):
            inset.NAIReferenceInsetGenerate().generate(**self.options(self.prepare()["result"][0]))
        self.post.assert_called_once()
        self.assertFalse((self.root/"output").exists())

    def test_http_failure_keeps_friendly_error_and_single_request(self):
        self.response()
        self.post.return_value.status_code = 402
        self.post.return_value._content = b'{"message":"Insufficient Anlas"}'
        with self.assertRaisesRegex(requests.HTTPError, "RS NAI:NAI_PAYMENT"):
            inset.NAIReferenceInsetGenerate().generate(**self.options(self.prepare()["result"][0]))
        self.post.assert_called_once()
        self.assertFalse((self.root/"output").exists())

    def test_model_character_limit_and_bad_input_fail_before_token(self):
        value = self.prepare()["result"][0]
        for model, count in (("NAI Diffusion V5 Full", 23), ("NAI Diffusion V5 Curated", 7)):
            from ComfyUI_RS_NAI_API_Request.local_bridge import prepare_characters
            chars = [generators.CharacterPrompt("bird", "", .5, .5)] * count
            self.assertEqual(len(prepare_characters(inset.get_model_id(model), chars, inpainting=True)),
                             6 if "Curated" in model else 22)
        for width, side in ((65, "left"), (128, "unknown")):
            with self.assertRaisesRegex(ValueError, "RS NAI:INSET_LAYOUT"):
                self.prepare(side=side,width=width)
        self.source = self.source.repeat(2,1,1,1)
        with self.assertRaisesRegex(ValueError, "RS NAI:IMAGE_INPUT"):
            self.prepare()
        self.token.assert_not_called()
        self.post.assert_not_called()

    def test_reference_tag_added_once_and_weighted_forms_unchanged(self):
        for prompt in ("reference inset, bird", "{reference inset}, bird", "1.2::reference inset::, bird", "REFERENCE INSET, bird"):
            self.assertEqual(inset.reference_prompt(prompt), prompt)
        self.assertEqual(inset.reference_prompt(""), "reference inset")


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "assets"
        self.patch = mock.patch.object(assets, "asset_directory", return_value=self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.image = torch.rand((1,20,30,4))

    def save(self, name="이름/名前"):
        return assets.NAICharacterAssetSave().save(self.image, name, "original (series), キャラ, 캐릭터", "bad pose", unique_id="1")

    def test_png_roundtrip_preserves_image_alpha_prompts_and_local_ui(self):
        saved = self.save()
        filename, = saved["result"]
        image, prompt, uc = assets.NAICharacterAssetLoad().load(filename)
        self.assertEqual(prompt,"original (series), キャラ, 캐릭터")
        self.assertEqual(uc, "bad pose")
        self.assertTrue(torch.allclose(image, (self.image*255).to(torch.uint8)/255))
        with Image.open(self.root/filename) as png:
            self.assertEqual(set(png.info), {assets.ASSET_KEY})
        self.assertEqual(saved["ui"]["images"][0]["type"], "input")
        self.assertTrue(saved["ui"]["rs_nai_notice"])

    def test_names_cannot_escape_or_overwrite_and_refresh_sees_new_assets(self):
        self.assertEqual(assets.NAICharacterAssetLoad.INPUT_TYPES()["required"]["asset_file"][0], [""])
        for name in ("../../escape", "CON", "same", "same"):
            self.save(name)
        files = list(self.root.glob("*.png"))
        self.assertEqual(len(files),4)
        self.assertTrue(all(p.resolve().parent==self.root.resolve() for p in files))
        self.assertEqual(set(assets.NAICharacterAssetLoad.INPUT_TYPES()["required"]["asset_file"][0]), {p.name for p in files})
        for filename in ("../escape.png", "/tmp/escape.png", "..\\escape.png", ""):
            with self.assertRaisesRegex(ValueError, "ASSET_FILE"):
                assets.NAICharacterAssetLoad().load(filename)

    def test_symlink_escape_missing_metadata_and_corrupt_json_are_rejected(self):
        self.root.mkdir()
        outside = self.root.parent/"outside.png"
        Image.new("RGB",(8,8)).save(outside)
        (self.root/"linked.png").symlink_to(outside)
        with self.assertRaisesRegex(ValueError,"ASSET_FILE"):
            assets.NAICharacterAssetLoad().load("linked.png")
        self.assertNotIn("linked.png", assets.NAICharacterAssetLoad.INPUT_TYPES()["required"]["asset_file"][0])
        for raw in ("null", "{broken", '{"version":99}', '{"version":1,"name":"n","prompt":[],"negative_prompt":""}'):
            metadata=PngInfo();metadata.add_text(assets.ASSET_KEY,raw)
            Image.new("RGB",(8,8)).save(self.root/"invalid.png",pnginfo=metadata)
            with self.assertRaisesRegex(ValueError,"ASSET_FILE"):
                assets.NAICharacterAssetLoad().load("invalid.png")

    def test_truncated_asset_and_file_permission_keep_actionable_error(self):
        name = self.save()["result"][0]
        path = self.root / name
        path.write_bytes(path.read_bytes()[:-100])
        with self.assertRaisesRegex(OSError, "RS NAI:ASSET_FILE"):
            assets.NAICharacterAssetLoad().load(name)
        with mock.patch.object(Image, "open", side_effect=PermissionError("access denied")):
            with self.assertRaisesRegex(PermissionError, "RS NAI:FILE_PERMISSION"):
                assets.NAICharacterAssetLoad().load(name)

    def test_replacing_asset_changes_execution_cache(self):
        name=self.save()["result"][0]
        old=assets.NAICharacterAssetLoad.IS_CHANGED(name)
        self.assertEqual(old,assets.NAICharacterAssetLoad.IS_CHANGED(name))
        self.image=torch.zeros_like(self.image)
        second=self.save()["result"][0]
        (self.root/name).write_bytes((self.root/second).read_bytes())
        self.assertNotEqual(old,assets.NAICharacterAssetLoad.IS_CHANGED(name))

    def test_failed_save_leaves_no_selectable_partial_png(self):
        with mock.patch.object(Image.Image,"save",side_effect=OSError("disk write failed")):
            with self.assertRaises(OSError): self.save()
        self.assertEqual(list(self.root.iterdir()),[])


if __name__ == "__main__":
    unittest.main()
