"""Selective context changes through actual nodes with only transport mocked."""
import copy
import json
from pathlib import Path
import unittest
from unittest import mock

from PIL import Image

import test_generation_context as context_tests
import test_detailer as detailing
from ComfyUI_RS_NAI_API_Request import generators as g, combined_detailer as combined, detailer
from ComfyUI_RS_NAI_API_Request.detector_bundle import DetectionBundle
from ComfyUI_RS_NAI_API_Request.generation_context import INHERITED_FIELDS
from ComfyUI_RS_NAI_API_Request.metadata import inspect_metadata


class ContextOverrideTests(unittest.TestCase):
    setUp = context_tests.ContextTests.setUp
    source = context_tests.ContextTests.source
    i2i = context_tests.ContextTests.i2i

    def test_each_replacement_preserves_other_fields_and_source(self):
        image, source = self.source(prefer_brownian=True)
        original = copy.deepcopy(source)
        manual = dict(prompt="replacement style", negative_prompt="", model="NAI Diffusion V4.5 Full",
                      sampler="k_euler_ancestral", steps=17, cfg_scale=2.5, scheduler="native",
                      cfg_rescale=0.0, prefer_brownian=False, variety_boost=False,
                      characterPrompts=[])
        for field in INHERITED_FIELDS:
            with self.subTest(field=field):
                _, updated = self.i2i(image, source, **manual, context_mode="override_selected",
                                      **{f"override_{field}": True})
                expected = source.settings()
                expected[field] = manual[field]
                self.assertEqual(updated.settings(), expected)
                self.assertEqual(updated.source_seed, 456)
                self.assertEqual(updated.source_size, (128, 64))
                self.assertEqual(source, original)

    def test_selected_i2i_changes_reach_next_detailer_and_saved_metadata(self):
        image, source = self.source()
        _, updated = self.i2i(image, source, context_mode="override_selected",
                              override_steps=True, steps=19, override_cfg_scale=True, cfg_scale=3.5)
        # Use actual detailer execution and its mock transport, not a fake resolver.
        pipeline = detailing.PipelineTests()
        pipeline.setUp()
        self.addCleanup(pipeline.doCleanups)
        from dataclasses import replace
        context = replace(updated, characters=())
        combined.NAIMultiCharacterDetailer().detail(
            image=pipeline.image, detectors=DetectionBundle(None, pipeline.detector),
            prompt="ignored", model="NAI Diffusion V4.5 Full",
            nai_context=context, limit_opus_free=False, seed=909,
            context_mode="override_selected", override_cfg_scale=True, cfg_scale=4.5,
            override_negative_prompt=True, negative_prompt="")
        self.assertEqual(len(pipeline.payloads), 2)
        for payload in pipeline.payloads:
            self.assertEqual(payload["parameters"]["steps"], 19)
            self.assertEqual(payload["parameters"]["scale"], 4.5)
            self.assertEqual(payload["parameters"]["negative_prompt"], "")
            self.assertEqual(payload["input"], source.prompt)
        saved = next(Path(pipeline.temp.name).rglob("*.png"))
        with Image.open(saved) as img:
            record = inspect_metadata(img)["record"]
        self.assertEqual(record["base_generation"]["parameters"]["scale"], 3.5)
        self.assertEqual(record["base_generation"]["parameters"]["steps"], 19)
        self.assertEqual(record["base_generation"]["input"], source.prompt)
        for edit in record["edits"]:
            self.assertEqual(edit["request"]["parameters"]["scale"], 4.5)
            self.assertEqual(edit["request"]["parameters"]["negative_prompt"], "")
        self.assertEqual(context.cfg_scale, 3.5)

    def test_detailer_replaces_entire_character_list_or_clears_it(self):
        _, source = self.source()
        detector = DetectionBundle(None, object())
        replacement = g.CharacterPromptSelect().build_character_prompt(character1="green hair")[0]
        for characters in (None, replacement):
            with self.subTest(characters=characters), mock.patch.object(detailer, "run_face_detail", return_value=(None, None, "[]")) as run:
                combined.NAIMultiCharacterDetailer().detail(
                    image=context_tests.torch.zeros((1, 64, 64, 3)), detectors=detector,
                    prompt="ignored", negative_prompt="ignored", model="NAI Diffusion V4.5 Full",
                    nai_context=source, context_mode="override_selected",
                    override_characterPrompts=True, characterPrompts=characters)
                self.assertEqual(run.call_args.kwargs["characterPrompts"], characters or [])
                self.assertEqual(run.call_args.kwargs.get("matching_mode", "shared"), "shared")
                self.assertIs(run.call_args.kwargs["nai_context"], source)
                self.assertFalse(any(k.startswith("override_") for k in run.call_args.kwargs))

    def test_modes_disconnection_and_stale_flags(self):
        image, source = self.source()
        manual = dict(context_mode="override_selected", override_steps=True, steps=13)
        self.assertEqual(self.i2i(image, source, **manual)[1].steps, 13)
        self.assertEqual(self.i2i(image, source, **{**manual, "context_mode": "inherit_all"})[1].steps, source.steps)
        for context in (None, object(), source):
            # The manual default model is Medium: effective steps must be 14.
            self.assertEqual(self.i2i(image, context, use_context_settings=False, **manual)[1].steps, 14)
        self.assertEqual(self.i2i(image, None, **manual)[1].steps, 14)
        self.assertEqual(self.i2i(image, source, context_mode="override_selected")[1].settings(), source.settings())

    def test_medium_limits_override_manual_choices_and_context_tracks_effective_values(self):
        image, source = self.source()
        _, updated = self.i2i(image, source, context_mode="override_selected",
            override_model=True, model=context_tests.generation.MEDIUM,
            override_steps=True, steps=40, override_sampler=True, sampler="k_euler",
            override_cfg_rescale=True, cfg_rescale=.8,
            override_negative_prompt=True, negative_prompt="custom rejected uc")
        self.assertEqual((updated.steps, updated.sampler, updated.cfg_rescale), (14, "k_euler_ancestral", 0))
        self.assertNotIn("custom rejected uc", updated.negative_prompt)
        self.assertTrue(all(c.uc == "" for c in updated.characters))

    def test_invalid_model_combination_and_selection_fail_before_request(self):
        image, source = self.source()
        for options, error in (
            ({"override_model": True, "model": "NAI Diffusion V3"}, "characterPrompts requires"),
            ({"context_mode": "unsupported"}, "context mode"),
            ({"override_steps": "false"}, "override selection"),
        ):
            self.transport.post.reset_mock()
            with mock.patch.object(g, "get_nai_token", side_effect=AssertionError("token read")):
                with self.assertRaisesRegex(ValueError, error):
                    self.i2i(image, source, **{ "context_mode": "override_selected", **options })
            self.transport.post.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, "image-to-image"):
            self.i2i(image, source, context_mode="override_selected", override_steps=True, steps=13, limit_opus_free=True)
        self.transport.post.assert_not_called()

    def test_old_schema_is_an_unchanged_prefix(self):
        old = json.loads((Path(__file__).parent / "fixtures/context-input-order-2.8.0.json").read_text())
        for cls in (g.NAIImg2ImgNode, combined.NAIMultiCharacterDetailer):
            current = cls.INPUT_TYPES()
            for group in ("required", "optional"):
                self.assertEqual(list(current[group])[:len(old[cls.__name__][group])], old[cls.__name__][group])
            self.assertEqual(current["optional"]["context_mode"][1]["default"], "inherit_all")


if __name__ == "__main__":
    unittest.main()
