"""Regressions found while reviewing every Comfy.ICU node page. Offline only."""

import builtins
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ComfyUI_RS_NAI_API_Request import converters, generators, nai_api, wd_tagger
from ComfyUI_RS_NAI_API_Request.image_utils import mask_to_pil


class TaggerPreflightTests(unittest.TestCase):
    def test_loader_reports_missing_or_broken_dependencies_before_cache_creation(self):
        original_import = builtins.__import__
        for problem in (ModuleNotFoundError("No module named timm"), RuntimeError("operator torchvision::nms does not exist")):
            def broken(name, *args, **kwargs):
                if name == "timm":
                    raise problem
                return original_import(name, *args, **kwargs)
            with self.subTest(problem=str(problem)), mock.patch("builtins.__import__", side_effect=broken):
                with mock.patch.object(wd_tagger, "WDTagger") as constructor:
                    with self.assertRaises(RuntimeError) as caught:
                        wd_tagger.WDTaggerLoader().load()
                    self.assertIn(sys.executable, str(caught.exception))
                    self.assertIn("requirements-tagger.txt", str(caught.exception))
                    constructor.assert_not_called()

    def test_loader_only_checks_imports_and_reuses_instance_without_loading_weights(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(sys.modules, {"folder_paths": mock.Mock(models_dir=folder)}):
            with mock.patch.object(wd_tagger, "check_dependencies") as check, mock.patch.object(wd_tagger.WDTagger, "_load") as load:
                loader = wd_tagger.WDTaggerLoader()
                first, = loader.load("cpu", 2)
                again, = loader.load("cpu", 2)
                self.assertIs(first, again)
                self.assertEqual(check.call_count, 2)
                load.assert_not_called()


class NoticeTests(unittest.TestCase):
    def test_converter_reports_loss_without_changing_output_or_socket(self):
        node = converters.ComfyUIToNovelAIV4Converter()
        result = node.convert_prompt("a, (tag:o), b", unique_id="12")
        self.assertEqual(result["result"], ("a, b",))
        self.assertIn("Dropped", result["ui"]["rs_nai_notice"][0])
        self.assertIn("(tag:o)", result["ui"]["rs_nai_notice"][0])
        self.assertEqual(node.RETURN_TYPES, ("STRING",))
        self.assertEqual(node.convert_prompt("a, b"), ("a, b",))
        clean = node.convert_prompt("a, b", unique_id="12")
        self.assertEqual(clean["ui"]["rs_nai_notice"], [])

    def test_unrepresentable_weight_and_v4_suffix_are_visible(self):
        result = converters.NovelAIV4ToOldNAIConverter().convert_prompt("0::bird ::", unique_id="1")
        self.assertEqual(result["result"], ("[bird]",))
        self.assertIn("cannot represent", result["ui"]["rs_nai_notice"][0])
        result = converters.NovelAIV4ToComfyUIConverter().convert_prompt("1.5::bird:: sky", unique_id="2")
        self.assertIn("dropped", result["ui"]["rs_nai_notice"][0])

    def test_old_coordinates_warn_without_guessing_migration(self):
        result = generators.CharacterPromptSelect().build_character_prompt(
            character1="bird", character1_x=3, character1_y=0.5, unique_id="1"
        )
        self.assertEqual(result["result"][0][0].center["x"], 1)
        self.assertIn("3 becomes 0.3", result["ui"]["rs_nai_notice"][0])
        with self.assertRaisesRegex(ValueError, "finite"):
            generators.CharacterPromptSelect().build_character_prompt(character1="bird", character1_x=float("nan"))


class InputBoundaryTests(unittest.TestCase):
    def options(self):
        return dict(prompt="bird", negative_prompt="bad", model="NAI Diffusion V3",
                    width=64, height=64, sampler="k_euler", steps=20, cfg_scale=5, seed=1,
                    limit_opus_free=False)

    def test_character_input_on_v3_is_rejected_before_token_encoding_or_network(self):
        cs = [generators.CharacterPrompt("bird", "bad", 0.5, 0.5)]
        for node, extra in (
            (generators.NovelAIGenerator, {}),
            (generators.NAIImg2ImgNode, dict(image=None, strength=0.5)),
            (generators.NAIInpaintNode, dict(image=None, mask=None, strength=0.5)),
        ):
            with self.subTest(node=node.__name__), mock.patch.object(generators, "get_nai_token") as token, mock.patch.object(generators, "reference_parameters") as refs:
                with self.assertRaisesRegex(ValueError, "characterPrompts requires"):
                    node().generate(**self.options(), **extra, characterPrompts=cs)
                token.assert_not_called()
                refs.assert_not_called()

    def test_image_and_mask_batches_fail_before_paid_request_preparation(self):
        image = torch.zeros((1, 64, 64, 3))
        for node, extra in (
            (generators.NAIImg2ImgNode, dict(image=image.repeat(2, 1, 1, 1), strength=0.5)),
            (generators.NAIInpaintNode, dict(image=image, mask=torch.ones((2, 64, 64)), strength=0.5)),
            (generators.NAIInpaintNode, dict(image=image, mask=torch.zeros((1, 64, 64)), strength=0.5)),
        ):
            with self.subTest(node=node.__name__), mock.patch.object(generators, "get_nai_token") as token:
                with self.assertRaises(ValueError):
                    node().generate(**self.options(), **extra)
                token.assert_not_called()

    def test_unknown_model_cannot_silently_select_a_different_model(self):
        with self.assertRaisesRegex(ValueError, "Unknown"):
            nai_api.get_model_id("removed model")

    def test_invalid_mask_pixels_are_rejected_but_soft_masks_preserved(self):
        for value in (float("nan"), float("inf"), -0.1, 1.1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                mask_to_pil(torch.full((1, 8, 8), value))
        self.assertEqual(mask_to_pil(torch.full((8, 8), 0.5)).getpixel((0, 0)), 127)


class StorageTests(unittest.TestCase):
    def archive(self, entries):
        result = io.BytesIO()
        with zipfile.ZipFile(result, "w") as zipped:
            for name, value in entries:
                zipped.writestr(name, value)
        return result.getvalue()

    def test_zip_metadata_before_png_does_not_break_image_decode(self):
        png = io.BytesIO()
        Image.new("RGB", (8, 8), "cyan").save(png, "PNG")
        archive = self.archive([("metadata.json", b"{}"), ("images/", b""), ("images/0.PNG", png.getvalue())])
        self.assertEqual(nai_api.zip_to_png_bytes(archive), png.getvalue())

    def test_empty_or_multiple_image_archives_are_not_silently_accepted(self):
        for entries in ([], [("meta.json", b"{}")], [("0.png", b"a"), ("1.png", b"b")]):
            with self.subTest(entries=entries), self.assertRaisesRegex(ValueError, "exactly one PNG"):
                nai_api.zip_to_png_bytes(self.archive(entries))

    def test_autosave_does_not_overwrite_when_timestamp_is_identical(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(generators, "datetime") as clock:
            clock.now.return_value.strftime.return_value = "same_time"
            paths = []
            for index in range(3):
                parent, name = generators.NovelAIGenerator._get_save_path("NAI", folder)
                path = parent / (name + ".png")
                path.write_bytes(bytes([index]))
                paths.append(path)
            self.assertEqual(len(set(paths)), 3)
            self.assertEqual([p.read_bytes() for p in paths], [b"\0", b"\1", b"\2"])


if __name__ == "__main__":
    unittest.main()
