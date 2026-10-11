"""Character capacity, hidden-slot semantics and request limits (offline)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from ComfyUI_RS_NAI_API_Request import generators, nai_api


class CharacterCapacityTests(unittest.TestCase):
    def build(self, count=22):
        values = {f"character{i}": f"character_{i} (series)" for i in range(1, 23)}
        values.update({f"character{i}_enable": True for i in range(2, 23)})
        return generators.CharacterPromptSelect().build_character_prompt(character_count=count, **values)[0]

    def test_all_slots_preserve_order_and_last_slot_coordinates(self):
        values = {f"character{i}": f"character {i}" for i in range(1, 23)}
        values.update({f"character{i}_enable": True for i in range(2, 23)})
        values.update(character22_x=0.7, character22_y=0.2, character22_uc="last negative")
        cs, = generators.CharacterPromptSelect().build_character_prompt(character_count=22, **values)
        self.assertEqual([c.prompt for c in cs], [f"character {i}" for i in range(1, 23)])
        self.assertEqual(cs[-1].center, {"x": 0.7, "y": 0.2})
        self.assertEqual(cs[-1].uc, "last negative")

    def test_default_count_and_hidden_slots_excluded_without_erasing_input(self):
        values = dict(character1="first", character6="sixth", character6_enable=True)
        node = generators.CharacterPromptSelect()
        self.assertEqual([c.prompt for c in node.build_character_prompt(**values)[0]], ["first"])
        self.assertEqual([c.prompt for c in node.build_character_prompt(character_count=6, **values)[0]], ["first", "sixth"])
        values["character6_enable"] = False
        self.assertEqual(len(node.build_character_prompt(character_count=6, **values)[0]), 1)

    def test_invalid_counts_rejected(self):
        for count in (0, 23, -1, 5.5, True, "22"):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, "character_count"):
                self.build(count)

    def test_model_limit_applies_to_both_captions_and_effective_inpainting_model(self):
        for model, limit in (("nai-diffusion-4-full", 6), ("nai-diffusion-4-5-full", 6),
                             ("nai-diffusion-5-curated", 22), ("nai-diffusion-5-full", 22),
                             ("nai-diffusion-5-full-medium", 22)):
            with self.subTest(model=model):
                cs = self.build()[:limit]
                params = nai_api.apply_v4_parameters({}, model, "group", "negative", cs)
                payload = nai_api.build_nai_payload("group", model, "generate", params)
                self.assertEqual(len(payload["parameters"]["v4_prompt"]["caption"]["char_captions"]), limit)
                with self.assertRaisesRegex(ValueError, f"at most {limit}"):
                    nai_api.apply_v4_parameters({}, model, "group", "", cs + [cs[0]])
                params["v4_negative_prompt"]["caption"]["char_captions"].append({})
                with self.assertRaisesRegex(ValueError, f"at most {limit}"):
                    nai_api.build_nai_payload("group", model, "generate", params)
        params = nai_api.apply_v4_parameters({}, "nai-diffusion-5-curated", "group", "", self.build())
        with self.assertRaisesRegex(ValueError, "at most 6"):
            nai_api.build_nai_payload("group", "nai-diffusion-5-curated", "infill", params, inpainting=True)

    def test_all_generators_reject_overflow_before_token_encoding_or_network(self):
        for node, extra in ((generators.NovelAIGenerator, {}),
                            (generators.NAIImg2ImgNode, dict(image=None, strength=0.5)),
                            (generators.NAIInpaintNode, dict(image=None, mask=None, strength=0.5))):
            for model, limit in (("NAI Diffusion V4.5 Full", 6), ("NAI Diffusion V5 Full", 22)):
                with self.subTest(node=node.__name__, model=model), mock.patch.object(generators, "get_nai_token") as token, mock.patch.object(generators, "reference_parameters") as refs, mock.patch.object(generators, "post_nai") as post:
                    cs = self.build()[:limit] + self.build(1)
                    with self.assertRaisesRegex(ValueError, f"at most {limit}"):
                        node().generate(prompt="group", negative_prompt="", model=model, width=512,
                            height=512, sampler="k_euler", steps=20, cfg_scale=5, seed=1,
                            characterPrompts=cs, limit_opus_free=False, **extra)
                    token.assert_not_called()
                    refs.assert_not_called()
                    post.assert_not_called()
        with mock.patch.object(generators, "get_nai_token") as token:
            with self.assertRaisesRegex(ValueError, "at most 6"):
                generators.NAIInpaintNode().generate(image=None, mask=None, strength=0.5,
                    prompt="group", negative_prompt="", model="NAI Diffusion V5 Curated",
                    width=512, height=512, sampler="k_euler", steps=20, cfg_scale=5, seed=1,
                    characterPrompts=self.build(7), limit_opus_free=False)
            token.assert_not_called()


if __name__ == "__main__":
    unittest.main()
