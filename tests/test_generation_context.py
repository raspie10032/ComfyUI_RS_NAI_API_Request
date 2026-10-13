"""Context propagation through real node code; generation transport is mocked."""
import copy
from dataclasses import FrozenInstanceError
import json
from types import SimpleNamespace
import unittest
from unittest import mock

import torch

import test_medium_nodes as generation
import test_detailer as detailing
from ComfyUI_RS_NAI_API_Request import generators as g, detailer
from ComfyUI_RS_NAI_API_Request.combined_detailer import NAICombinedFaceDetailerTest
from ComfyUI_RS_NAI_API_Request.detector_bundle import DetectionBundle
from ComfyUI_RS_NAI_API_Request.generation_context import inherit_context


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.transport = generation.MediumNodeTests()
        self.transport.setUp()
        self.addCleanup(self.transport.doCleanups)

    def source(self, **overrides):
        args = self.transport.options()
        args.update(model="NAI Diffusion V5 Full", steps=24, characterPrompts=detailing.characters())
        args.update(overrides)
        return g.NovelAIGenerator().generate(**args)

    def i2i(self, image, context, **overrides):
        args = dict(self.transport.options(), image=image, strength=.3, seed=456,
                    limit_opus_free=False, nai_context=context, prompt="manual text",
                    characterPrompts=None, width=128, height=64)
        args.update(overrides)
        return g.NAIImg2ImgNode().generate(**args)

    def test_chain_uses_local_seeds_and_only_selected_original_character(self):
        image, source = self.source()
        _, updated = self.i2i(image, source)
        p = self.transport.post.call_args.kwargs["json"]["parameters"]
        self.assertEqual(p["seed"], 456)
        self.assertEqual(p["extra_noise_seed"], 456)
        self.assertEqual((p["width"], p["height"], p["strength"]), (128, 64, .3))
        self.assertEqual(updated.source_seed, 456)
        self.assertEqual(source.source_seed, 123)
        self.assertEqual(updated.characters, source.characters)
        self.assertEqual(updated.source_action, "img2img")
        self.assertEqual(updated.source_size, (128, 64))
        pipeline = detailing.PipelineTests()
        pipeline.setUp()
        self.addCleanup(pipeline.doCleanups)
        tagger = SimpleNamespace(score=lambda images: [
            {"blonde_hair": .99, "black_hair": .01, "invented tag": 1},
            {"blonde_hair": .01, "black_hair": .99, "invented tag": 1},
        ][:len(images)])
        kwargs = dict(image=pipeline.image, detectors=DetectionBundle(None, pipeline.detector),
                      prompt="unused manual", negative_prompt="unused negative",
                      model="NAI Diffusion V4.5 Full", seed=789, nai_context=updated,
                      tagger=tagger, preview_only=False, limit_opus_free=False)
        _, mask, report = NAICombinedFaceDetailerTest().detail(**kwargs)
        self.assertEqual([r["status"] for r in json.loads(report)], ["edited", "edited"])
        self.assertEqual([p["parameters"]["seed"] for p in pipeline.payloads], [789, 790])
        for i, payload in enumerate(pipeline.payloads):
            self.assertEqual(payload["input"], source.prompt + ", " + source.characters[i].prompt)
            self.assertEqual(payload["parameters"]["negative_prompt"], source.negative_prompt + ", " + source.characters[i].uc)
            self.assertEqual(payload["model"], "nai-diffusion-5-full-inpainting")
            self.assertEqual(payload["parameters"]["sampler"], source.sampler)
            self.assertEqual(payload["parameters"]["cfg_rescale"], source.cfg_rescale)
            self.assertNotIn("invented tag", payload["input"])
        count = len(pipeline.payloads)
        kwargs.update(preview_only=True)
        with mock.patch.object(detailer, "get_nai_token", side_effect=AssertionError("token read")):
            _, preview, _ = NAICombinedFaceDetailerTest().detail(**kwargs)
        self.assertTrue(torch.equal(mask, preview))
        self.assertEqual(len(pipeline.payloads), count)
        kwargs.pop("tagger")
        with self.assertRaisesRegex(ValueError, "Tagger|tagger"):
            NAICombinedFaceDetailerTest().detail(**kwargs)

    def test_medium_snapshots_effective_values_and_local_random_seed(self):
        image, source = self.source(model=generation.MEDIUM, seed=-1, steps=50)
        self.assertGreaterEqual(source.source_seed, 0)
        self.assertEqual((source.steps, source.sampler, source.cfg_rescale), (14, "k_euler_ancestral", 0))
        self.assertTrue(all(c.uc == "" for c in source.characters))
        with mock.patch.object(g.np.random, "randint", return_value=901):
            _, updated = self.i2i(image, source, seed=-1)
        self.assertEqual(updated.source_seed, 901)
        self.assertEqual(updated.negative_prompt, source.negative_prompt)
        self.assertEqual(updated.model, source.model)

    def test_five_three_five_updates_requests_and_context_without_stale_characters(self):
        values = {f"character{i}": f"original character {i}" for i in range(1, 6)}
        values.update({f"character{i}_enable": True for i in range(2, 6)})
        saved = copy.deepcopy(values)
        selector = g.CharacterPromptSelect()
        snapshots = []
        for count in (5, 3, 5):
            with self.subTest(count=count):
                chars, = selector.build_character_prompt(character_count=count, **values)
                image, source = self.source(prompt="style, 5girls, five women", characterPrompts=chars)
                expected = [f"original character {i}" for i in range(1, count + 1)]
                def check_request():
                    p = self.transport.post.call_args.kwargs["json"]["parameters"]
                    self.assertEqual([c["char_caption"] for c in p["v4_prompt"]["caption"]["char_captions"]], expected)
                    self.assertEqual(len(p["v4_negative_prompt"]["caption"]["char_captions"]), count)
                check_request()
                _, updated = self.i2i(image, source)
                check_request()
                # The detailer's context resolver must see the same candidates,
                # whether it receives I2I's output or bypasses I2I to use T2I.
                for context in (source, updated):
                    self.assertEqual([c.prompt for c in inherit_context(context, True)["characterPrompts"]], expected)
                    self.assertEqual(context.prompt, "style, 5girls, five women")
                snapshots.append(source)
        self.assertEqual([len(c.characters) for c in snapshots], [5, 3, 5])
        self.assertEqual(values, saved)

    def test_no_context_and_disabled_context_keep_manual_values(self):
        image, source = self.source()
        for context in (source, object(), None):
            _, result = self.i2i(image, context, use_context_settings=False)
            self.assertEqual(result.prompt, "manual text")
            self.assertEqual(result.model, generation.MEDIUM)
            self.assertEqual(result.characters, ())
        self.assertEqual(self.i2i(image, None)[1].prompt, "manual text")

    def test_strict_i2i_blocks_before_context_token_encoding_or_request(self):
        image, source = self.source()
        self.transport.post.reset_mock()
        with mock.patch.object(g, "get_nai_token", side_effect=AssertionError("token")), \
             mock.patch.object(g, "pil_to_base64", side_effect=AssertionError("encoding")):
            with self.assertRaisesRegex(RuntimeError, "image-to-image"):
                self.i2i(image, source, limit_opus_free=True)
        self.transport.post.assert_not_called()

    def test_snapshot_has_no_sensitive_payload_and_cannot_mutate_source(self):
        image, source = self.source()
        cloned = copy.deepcopy(source)
        with self.assertRaises(FrozenInstanceError):
            source.source_seed = 4
        settings = source.settings()
        settings["characterPrompts"][0].center["x"] = 9
        settings["characterPrompts"].clear()
        self.assertEqual(source, cloned)
        _, updated = self.i2i(image, source)
        self.assertFalse(set(vars(updated)) & {"image", "mask", "token", "authorization", "references", "vibes", "limit_opus_free"})
        with self.assertRaisesRegex(ValueError, "NAI context"):
            inherit_context({}, True)

    def test_existing_image_slot_and_widget_order_are_preserved(self):
        for cls in (g.NovelAIGenerator, g.NAIImg2ImgNode):
            self.assertEqual(cls.RETURN_TYPES, ("IMAGE", "NAI_CONTEXT"))
        for cls in (g.NAIImg2ImgNode, NAICombinedFaceDetailerTest):
            fields = list(cls.INPUT_TYPES()["optional"])
            self.assertEqual(fields[-1], "use_context_settings")
            self.assertLess(fields.index("request_delay_seconds"), fields.index("use_context_settings"))


if __name__ == "__main__":
    unittest.main()
