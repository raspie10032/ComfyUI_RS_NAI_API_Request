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
    get_nai_token,
)


class CharacterPromptSelectTests(unittest.TestCase):
    def test_coordinates_map_zero_to_ten_scale_to_unit_float(self):
        prompt = CharacterPromptSelect().build_character_prompt(
            character1="character",
            character1_uc="uc",
            character1_x=5,
            character1_y=10,
        )[0][0]

        self.assertEqual(prompt.center, {"x": 0.5, "y": 1.0})


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
