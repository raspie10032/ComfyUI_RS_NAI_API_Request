"""Exercise node inputs through the HTTP boundary without paid API calls."""

import base64
import copy
from contextlib import ExitStack
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

import requests
import torch
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from ComfyUI_RS_NAI_API_Request import generators, nai_api


MEDIUM = "NAI Diffusion V5 Full — Medium Effort"


def response(content, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = content
    result._content_consumed = True
    return result


class MediumNodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(
            generators.NovelAIGenerator, "_get_output_directory", return_value=self.temp.name
        ))
        self.token = self.stack.enter_context(mock.patch.object(
            generators, "get_nai_token", return_value="test-only"
        ))
        self.get = self.stack.enter_context(mock.patch.object(
            nai_api._session, "get", return_value=response(json.dumps({
                "active": True, "tier": 3,
                "usage": {"percent": 15, "isNegative": False},
            }).encode())
        ))
        png = io.BytesIO()
        Image.new("RGB", (64, 64), "cyan").save(png, format="PNG")
        self.png = png.getvalue()
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("image_0.png", self.png)
        self.post = self.stack.enter_context(mock.patch.object(
            nai_api._session, "post", return_value=response(archive.getvalue())
        ))
        self.stack.enter_context(mock.patch.object(nai_api, "wait_until"))
        self.stack.enter_context(mock.patch.object(nai_api, "_next_request_at", 0))
        self.characters = generators.CharacterPromptSelect().build_character_prompt(
            character1="blue bird", character1_uc="custom character negative",
            character1_x=0.3, character1_y=0.5,
        )[0]

    def options(self):
        return dict(
            prompt="bird on a branch", negative_prompt="custom base negative",
            model=MEDIUM, width=64, height=64, sampler="k_dpmpp_2m",
            steps=50, cfg_scale=6.5, cfg_rescale=0.7, seed=123,
            characterPrompts=self.characters,
        )

    def test_all_generators_send_22_medium_characters_without_truncation(self):
        self.characters = [generators.CharacterPrompt(f"bird {i}", f"negative {i}", 0.5, 0.5) for i in range(22)]
        for node, extra in (
            (generators.NovelAIGenerator, {}),
            (generators.NAIImg2ImgNode, {"image": torch.zeros((1, 64, 64, 3)), "strength": 0.5}),
            (generators.NAIInpaintNode, {"image": torch.zeros((1, 64, 64, 3)), "mask": torch.ones((1, 64, 64)), "strength": 0.5}),
        ):
            with self.subTest(node=node.__name__):
                output, *_ = node().generate(**self.options(), **extra, limit_opus_free=False)
                self.assertEqual(tuple(output.shape), (1, 64, 64, 3))
                params = self.post.call_args.kwargs["json"]["parameters"]
                self.assertEqual([c["char_caption"] for c in params["v4_prompt"]["caption"]["char_captions"]],
                                 [c.prompt for c in self.characters])
                self.assertEqual([c["char_caption"] for c in params["v4_negative_prompt"]["caption"]["char_captions"]], [""] * 22)

    def test_all_nodes_send_medium_settings_decode_and_autosave(self):
        image = torch.zeros((1, 64, 64, 3))
        mask = torch.zeros((1, 64, 64))
        mask[:, 16:48, 16:48] = 1
        cases = [
            (generators.NovelAIGenerator, "generate", {}, True),
            (generators.NAIImg2ImgNode, "img2img", {"image": image, "strength": 0.5}, False),
            (generators.NAIInpaintNode, "infill", {"image": image, "mask": mask, "strength": 0.5}, False),
        ]
        for node, action, extra, strict in cases:
            with self.subTest(action=action):
                self.get.reset_mock()
                self.post.reset_mock()
                output, *_ = node().generate(**self.options(), **extra, limit_opus_free=strict)
                self.assertEqual(tuple(output.shape), (1, 64, 64, 3))
                self.assertEqual(output[0, 0, 0].tolist(), [0.0, 1.0, 1.0])
                self.post.assert_called_once()
                payload = self.post.call_args.kwargs["json"]
                self.assertEqual(payload["action"], action)
                self.assertEqual(payload["model"], "nai-diffusion-5-full-medium" + (
                    "-inpainting" if action == "infill" else ""
                ))
                params = payload["parameters"]
                self.assertEqual((params["steps"], params["sampler"], params["cfg_rescale"]),
                                 (14, "k_euler_ancestral", 0.0))
                self.assertEqual(params["scale"], 6.5)
                expected_uc = "nsfw, " + nai_api.MEDIUM_EFFORT_UNDESIRED_CONTENT
                self.assertEqual(params["negative_prompt"], expected_uc)
                negative = params["v4_negative_prompt"]["caption"]
                self.assertEqual(negative["base_caption"], expected_uc)
                self.assertEqual(negative["char_captions"][0]["char_caption"], "")
                character = params["v4_prompt"]["caption"]["char_captions"][0]
                self.assertEqual(character["char_caption"], "blue bird")
                self.assertEqual(character["centers"], [{"x": 0.3, "y": 0.5}])
                self.assertEqual(self.get.call_count, int(strict))
                if action == "img2img":
                    self.assertEqual(params["strength"], 0.5)
                    self.assertNotIn("img2img", params)
                if action == "infill":
                    self.assertEqual(params["img2img"], {"strength": 0.5, "color_correct": True})
                    decoded_mask = Image.open(io.BytesIO(base64.b64decode(params["mask"])))
                    self.assertEqual(decoded_mask.getpixel((0, 0)), 0)
                    self.assertEqual(decoded_mask.getpixel((32, 32)), 255)
        saved = list(Path(self.temp.name).rglob("*.png"))
        self.assertEqual(len(saved), 3)
        for path in saved:
            with Image.open(path) as stored, Image.open(io.BytesIO(self.png)) as original:
                self.assertEqual(stored.tobytes(), original.tobytes())
                self.assertEqual(stored.info.get("Comment"), original.info.get("Comment"))
                self.assertIn("rs_nai", stored.info)
        self.assertEqual(self.characters[0].uc, "custom character negative")

    def test_medium_paid_nodes_fail_before_token_or_image_encoding(self):
        with mock.patch.object(generators, "tensor_to_pil") as encode:
            for node, extra in [
                (generators.NAIImg2ImgNode, {"image": None, "strength": 0.5}),
                (generators.NAIInpaintNode, {"image": None, "mask": None, "strength": 0.5}),
            ]:
                with self.subTest(node=node.__name__), self.assertRaisesRegex(RuntimeError, "spend Anlas"):
                    node().generate(**self.options(), **extra, limit_opus_free=True)
            encode.assert_not_called()
        self.token.assert_not_called()
        self.get.assert_not_called()
        self.post.assert_not_called()

    def test_paid_request_error_does_not_retry_or_save_an_image(self):
        self.post.return_value = response(b'{"message":"Insufficient Anlas"}', status=402)
        with self.assertRaises(Exception):
            generators.NAIImg2ImgNode().generate(
                **self.options(), image=torch.zeros((1, 64, 64, 3)),
                strength=0.5, limit_opus_free=False,
            )
        self.post.assert_called_once()
        self.assertEqual(list(Path(self.temp.name).rglob("*.png")), [])

    def test_invalid_image_response_is_not_saved_as_success(self):
        self.post.return_value = response(b"not a PNG archive")
        with self.assertRaises(zipfile.BadZipFile):
            generators.NovelAIGenerator().generate(**self.options(), limit_opus_free=True)
        self.post.assert_called_once()
        self.assertEqual(list(Path(self.temp.name).rglob("*.png")), [])

    def test_medium_mutated_settings_fail_before_any_http(self):
        params = nai_api.build_common_parameters(
            512, 512, 123, "k_euler", 28, 6, "bad",
            model_id="nai-diffusion-5-full-medium",
        )
        nai_api.apply_v4_parameters(params, "nai-diffusion-5-full-medium", "bird", "bad", self.characters)
        changes = [
            lambda p: p.update(steps=15),
            lambda p: p.update(sampler="k_euler"),
            lambda p: p.update(cfg_rescale=0.1),
            lambda p: p.update(negative_prompt="custom"),
            lambda p: p["v4_negative_prompt"]["caption"].update(base_caption="custom"),
            lambda p: p["v4_negative_prompt"]["caption"]["char_captions"][0].update(char_caption="custom"),
        ]
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                modified = copy.deepcopy(params)
                change(modified)
                payload = nai_api.build_nai_payload("bird", "nai-diffusion-5-full-medium", "generate", modified)
                with self.assertRaises(RuntimeError):
                    nai_api.post_nai("test-only", payload, limit_opus_free=True)
        self.get.assert_not_called()
        self.post.assert_not_called()


class InpaintingStrengthTests(unittest.TestCase):
    def test_v4_and_v5_inpainting_use_api_strength_without_mutating_input(self):
        for model in ("nai-diffusion-4-full", "nai-diffusion-4-5-full",
                      "nai-diffusion-5-curated", "nai-diffusion-5-full",
                      "nai-diffusion-5-full-medium"):
            for strength in (0.25, 0.5, 1.0):
                with self.subTest(model=model, strength=strength):
                    params = {"inpaintImg2ImgStrength": strength, "img2img": {"strength": 0.9}}
                    before = copy.deepcopy(params)
                    payload = nai_api.build_nai_payload("bird", model, "infill", params, inpainting=True)
                    if strength == 1.0:
                        self.assertNotIn("img2img", payload["parameters"])
                    else:
                        self.assertEqual(payload["parameters"]["img2img"],
                                         {"strength": strength, "color_correct": True})
                    self.assertEqual(params, before)

    def test_regular_img2img_and_v3_do_not_gain_v4_inpainting_parameters(self):
        for model, inpainting, action in (("nai-diffusion-5-full-medium", False, "img2img"),
                                         ("nai-diffusion-3", True, "infill")):
            params = {"strength": 0.5, "inpaintImg2ImgStrength": 0.25}
            payload = nai_api.build_nai_payload("bird", model, action, params, inpainting=inpainting)
            self.assertNotIn("img2img", payload["parameters"])
            self.assertEqual(payload["parameters"]["strength"], 0.5)


if __name__ == "__main__":
    unittest.main()
