"""T2I context consumption through request assembly and autosave; HTTP is mocked."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest import mock

from PIL import Image

import test_generation_context as context_tests
from ComfyUI_RS_NAI_API_Request import generators as g
from ComfyUI_RS_NAI_API_Request.generation_context import INHERITED_FIELDS
from ComfyUI_RS_NAI_API_Request.metadata import inspect_metadata


class T2IContextTests(unittest.TestCase):
    setUp = context_tests.ContextTests.setUp
    source = context_tests.ContextTests.source
    i2i = context_tests.ContextTests.i2i

    def t2i(self, context, **overrides):
        args = dict(self.transport.options(), nai_context=context, prompt="manual scene",
                    characterPrompts=None, seed=789, width=128, height=64, limit_opus_free=False)
        args.update(overrides)
        return g.NovelAIGenerator().generate(**args)

    def test_inherits_all_from_either_generation_action_but_seed_size_and_references_stay_local(self):
        _, source = self.source()
        for action in ("generate", "img2img", "infill"):
            with self.subTest(source_action=action):
                incoming = replace(source, source_action=action, references_omitted=True)
                _, result = self.t2i(incoming)
                payload = self.transport.post.call_args.kwargs["json"]
                self.assertEqual(result.settings(), incoming.settings())
                self.assertEqual((result.source_action, result.source_seed, result.source_size),
                                 ("generate", 789, (128, 64)))
                self.assertEqual(payload["action"], "generate")
                for key in ("image", "mask", "strength", "reference_image_multiple", "director_reference_images"):
                    self.assertFalse(payload["parameters"].get(key), key)
                self.assertFalse(result.references_omitted)
        with mock.patch.object(g.np.random, "randint", return_value=2468):
            self.assertEqual(self.t2i(source, seed=-1)[1].source_seed, 2468)

    def test_each_override_and_empty_zero_false_preserve_unselected_fields(self):
        _, source = self.source(prefer_brownian=True)
        original = copy.deepcopy(source)
        manual = dict(prompt="replacement scene", negative_prompt="", model="NAI Diffusion V4.5 Full",
                      sampler="k_euler_ancestral", steps=17, cfg_scale=0.0, scheduler="native",
                      cfg_rescale=0.0, prefer_brownian=False, variety_boost=False, characterPrompts=None)
        for field in INHERITED_FIELDS:
            with self.subTest(field=field):
                _, result = self.t2i(source, **manual, context_mode="override_selected",
                                     **{f"override_{field}": True})
                expected = source.settings()
                expected[field] = [] if field == "characterPrompts" else manual[field]
                self.assertEqual(result.settings(), expected)
                self.assertEqual(source, original)

    def test_character_replacement_preserves_negatives_positions_and_removes_old_slots(self):
        _, source = self.source()
        replacement = [g.CharacterPrompt("green hair", "red eyes", .2, .8)]
        _, result = self.t2i(source, context_mode="override_selected",
                             override_characterPrompts=True, characterPrompts=replacement)
        self.assertEqual([(c.prompt, c.uc, c.x, c.y) for c in result.characters],
                         [("green hair", "red eyes", .2, .8)])
        payload = self.transport.post.call_args.kwargs["json"]
        self.assertEqual(len(payload["parameters"]["v4_prompt"]["caption"]["char_captions"]), 1)
        self.assertEqual(len(source.characters), 2)

    def test_manual_mode_disconnection_and_stale_flags(self):
        _, source = self.source()
        manual = dict(context_mode="override_selected", override_steps=True, steps=13)
        self.assertEqual(self.t2i(source, **manual)[1].steps, 13)
        self.assertEqual(self.t2i(source, **{**manual, "context_mode": "inherit_all"})[1].steps, source.steps)
        self.assertEqual(self.t2i(source, context_mode="override_selected")[1].settings(), source.settings())
        for context in (None, object(), source):
            result = self.t2i(context, use_context_settings=False, **manual)[1]
            self.assertEqual(result.prompt, "manual scene")
            self.assertEqual(result.characters, ())
            self.assertEqual(result.steps, 14)  # manual model is Medium
        self.assertEqual(self.t2i(None, **manual)[1].steps, 14)

    def test_medium_and_opus_limits_are_applied_after_context_merge(self):
        _, source = self.source()
        _, result = self.t2i(source, context_mode="override_selected",
            override_model=True, model=context_tests.generation.MEDIUM,
            override_steps=True, steps=40, override_sampler=True, sampler="k_euler",
            override_cfg_rescale=True, cfg_rescale=.8,
            override_negative_prompt=True, negative_prompt="custom rejected uc")
        self.assertEqual((result.steps, result.sampler, result.cfg_rescale), (14, "k_euler_ancestral", 0))
        self.assertNotIn("custom rejected uc", result.negative_prompt)
        self.assertTrue(all(c.uc == "" for c in result.characters))
        _, result = self.t2i(source, context_mode="override_selected",
            override_steps=True, steps=50, width=2048, height=2048, limit_opus_free=True)
        self.assertEqual(result.steps, 28)
        self.assertEqual(result.source_size, (1024, 1024))
        self.assertEqual(result.source_seed, 789)
        self.assertEqual(source.steps, 24)

    def test_bad_context_and_model_combinations_fail_before_auth_or_request(self):
        _, source = self.source()
        for options, error_type, error in (
            ({"override_model": True, "model": "NAI Diffusion V3"}, ValueError, "characterPrompts requires"),
            ({"context_mode": "unknown"}, ValueError, "context mode"),
            ({"override_steps": "false"}, ValueError, "override selection"),
            ({"override_step": True}, TypeError, "Unknown context input"),
            ({"nai_context": {}}, ValueError, "NAI context"),
        ):
            with self.subTest(options=options):
                self.transport.post.reset_mock()
                context = options.get("nai_context", source)
                values = {k: v for k, v in options.items() if k != "nai_context"}
                with mock.patch.object(g, "get_nai_token", side_effect=AssertionError("token read")):
                    with self.assertRaisesRegex(error_type, error):
                        self.t2i(context, **{"context_mode": "override_selected", **values})
                self.transport.post.assert_not_called()

    def test_strict_guard_rejects_references_and_unqualified_subscription(self):
        _, source = self.source()
        for reference in ("vibes", "references"):
            self.transport.post.reset_mock()
            with mock.patch.object(g, "get_nai_token", side_effect=AssertionError("token read")), \
                    mock.patch.object(g, "reference_parameters", side_effect=AssertionError("reference encoding")):
                with self.assertRaisesRegex(RuntimeError, "blocks Vibe and Precise Reference"):
                    self.t2i(source, limit_opus_free=True, **{reference: [object()]})
            self.transport.post.assert_not_called()
        self.transport.get.return_value = context_tests.generation.response(
            json.dumps({"active": False, "tier": 0}).encode())
        with self.assertRaises(RuntimeError):
            self.t2i(source, limit_opus_free=True, context_mode="override_selected",
                      override_steps=True, steps=10)
        self.transport.post.assert_not_called()

    def test_changed_t2i_values_reach_i2i_and_autosave_in_all_formats(self):
        _, source = self.source()
        for format_name, glob in (("PNG", "*.png"), ("WebP lossless", "*.webp"), ("WebP lossy", "*.webp")):
            with self.subTest(format=format_name):
                before = set(Path(self.transport.temp.name).rglob(glob))
                image, updated = self.t2i(source, save_format=format_name,
                    context_mode="override_selected", override_prompt=True, prompt="new scene",
                    override_cfg_scale=True, cfg_scale=3.0, override_negative_prompt=True, negative_prompt="")
                added = set(Path(self.transport.temp.name).rglob(glob)) - before
                self.assertEqual(len(added), 1)
                with Image.open(added.pop()) as saved:
                    restored = inspect_metadata(saved)
                self.assertEqual(restored["settings"]["prompt"], updated.prompt)
                self.assertEqual(restored["settings"]["negative_prompt"], "")
                self.assertEqual(restored["settings"]["seed"], 789)
                self.assertEqual([c["prompt"] for c in restored["characters"]],
                                 [c.prompt for c in updated.characters])
                _, next_context = self.i2i(image, updated)
                self.assertEqual(next_context.settings(), updated.settings())
                self.assertEqual(next_context.source_seed, 456)

    def test_t2i_context_controls_have_korean_and_japanese_translations(self):
        for lang in ("ko", "ja"):
            data = json.loads((Path(__file__).parents[1] / "locales" / lang / "nodeDefs.json").read_text())
            inputs = data["NovelAIGenerator"]["inputs"]
            for name in ("nai_context", "use_context_settings", "context_mode",
                         *(f"override_{field}" for field in INHERITED_FIELDS)):
                self.assertTrue(inputs[name]["name"])
                self.assertTrue(inputs[name]["tooltip"])


if __name__ == "__main__":
    unittest.main()
