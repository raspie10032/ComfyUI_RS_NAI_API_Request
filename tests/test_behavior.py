import os
import sys
import unittest
from unittest import mock


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from ComfyUI_RS_NAI_API_Request.converters import parse_comfyui
from ComfyUI_RS_NAI_API_Request.generators import CharacterPromptSelect
from ComfyUI_RS_NAI_API_Request.nai_api import (
    MODEL_DISPLAY_LIST,
    MODEL_ID_MAP,
    apply_v4_parameters,
    build_common_parameters,
    build_nai_payload,
    build_v4_prompt,
    get_nai_token,
)


class CharacterPromptSelectTests(unittest.TestCase):
    def test_coordinates_keep_unit_scale_and_one_decimal_in_api_prompt(self):
        node = CharacterPromptSelect()
        schema = node.INPUT_TYPES()
        inputs = {**schema["required"], **schema["optional"]}
        for i in range(1, 6):
            for axis in ("x", "y"):
                kind, options = inputs[f"character{i}_{axis}"]
                self.assertEqual(kind, "FLOAT")
                self.assertEqual((options["min"], options["max"]), (0.0, 1.0))
                self.assertEqual((options["step"], options["round"]), (0.1, 0.1))
            with self.subTest(character=i):
                prompts = node.build_character_prompt(**{
                    "character1_enable": False,
                    f"character{i}_enable": True,
                    f"character{i}": "character",
                    f"character{i}_uc": "uc",
                    f"character{i}_x": 0.34,
                    f"character{i}_y": 0.76,
                })[0]
                parameters = build_v4_prompt("scene", "bad", prompts)
                for key in ("v4_prompt", "v4_negative_prompt"):
                    center = parameters[key]["caption"]["char_captions"][0]["centers"][0]
                    self.assertEqual(center, {"x": 0.3, "y": 0.8})
        for x, y in ((0.0, 1.0), (-0.1, 1.1)):
            prompts = node.build_character_prompt(character1_x=x, character1_y=y)[0]
            self.assertEqual(prompts[0].center, {"x": 0.0, "y": 1.0})


class ConverterTests(unittest.TestCase):
    def test_comfy_weighted_literal_parentheses_with_colon_is_preserved(self):
        self.assertEqual(parse_comfyui(r"(e\(f: g h\):1.2)"), [("e(f: g h)", 1.2)])

    def test_malformed_unescaped_colon_group_is_still_dropped(self):
        self.assertEqual(parse_comfyui("(tag:o)"), [])


class NaiApiTests(unittest.TestCase):
    def test_v5_models_are_exposed_with_api_ids(self):
        self.assertEqual(MODEL_DISPLAY_LIST[:2], ["NAI Diffusion V5 Curated", "NAI Diffusion V5 Full"])
        self.assertEqual(MODEL_ID_MAP["NAI Diffusion V5 Curated"], "nai-diffusion-5-curated")
        self.assertEqual(MODEL_ID_MAP["NAI Diffusion V5 Full"], "nai-diffusion-5-full")

    def test_v5_uses_v4_prompt_shape_and_params_version_four(self):
        parameters = build_common_parameters(
            832, 1216, 123, "k_euler_ancestral", 23, 7.0, "bad quality",
            model_id="nai-diffusion-5-full",
        )
        v45_parameters = build_common_parameters(
            832, 1216, 123, "k_euler_ancestral", 23, 7.0, "bad quality",
            model_id="nai-diffusion-4-5-curated",
        )
        apply_v4_parameters(parameters, "nai-diffusion-5-full", "1girl", "bad quality")

        self.assertEqual(parameters["params_version"], 4)
        self.assertEqual(v45_parameters["params_version"], 3)
        self.assertEqual(parameters["v4_prompt"]["caption"]["base_caption"], "1girl")
        self.assertFalse(parameters["v4_prompt"]["legacy_uc"])
        self.assertFalse(parameters["v4_negative_prompt"]["legacy_uc"])

    def test_v5_curated_inpainting_uses_official_v45_fallback(self):
        curated = build_nai_payload("prompt", "nai-diffusion-5-curated", "infill", {}, inpainting=True)
        full = build_nai_payload("prompt", "nai-diffusion-5-full", "infill", {}, inpainting=True)

        self.assertEqual(curated["model"], "nai-diffusion-4-5-curated-inpainting")
        self.assertEqual(full["model"], "nai-diffusion-5-full-inpainting")

    def test_v2_model_is_not_exposed(self):
        self.assertNotIn("NAI Diffusion V2", MODEL_DISPLAY_LIST)
        self.assertNotIn("NAI Diffusion V2", MODEL_ID_MAP)

    def test_missing_token_raises_before_request(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                get_nai_token()


if __name__ == "__main__":
    unittest.main()
