import base64
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import mock

import numpy as np
import requests
import torch
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from ComfyUI_RS_NAI_API_Request import detailer, nai_api
from ComfyUI_RS_NAI_API_Request.detailer_matching import (
    match_characters,
    selected_prompts,
)
from ComfyUI_RS_NAI_API_Request.generators import (
    CharacterPrompt,
    NAIFaceDetailerNode,
    NAIFaceDetailerSegmNode,
    NovelAIGenerator,
)
from ComfyUI_RS_NAI_API_Request.wd_tagger import WDTagger


def characters():
    return [
        CharacterPrompt(
            "alice (series_a), blonde hair, blue eyes", "alice negative", 0.25, 0.5
        ),
        CharacterPrompt(
            "bob (series_b), black hair, red eyes", "bob negative", 0.75, 0.5
        ),
    ]


class MatchingTests(unittest.TestCase):
    def test_visual_tags_select_original_character_and_never_become_prompts(self):
        cs = characters()
        match = match_characters(
            {
                "blonde_hair": 0.99,
                "black_hair": 0.01,
                "blue_eyes": 0.01,
                "red_eyes": 0.99,
                "injected_character": 1.0,
            },
            cs,
        )
        self.assertEqual(match.character_index, 0)
        p, n = selected_prompts("shared", "negative", cs, match)
        self.assertEqual(p, "shared, " + cs[0].prompt)
        self.assertEqual(n, "negative, alice negative")
        self.assertNotIn("injected", p)
        self.assertNotIn("red eyes", p)

    def test_character_name_and_franchise_qualifier_match_without_rewriting(self):
        cs = characters()
        match = match_characters({"alice_(series_a)": 0.98, "bob_(series_b)": 0.02}, cs)
        self.assertEqual(match.character_index, 0)
        self.assertEqual(selected_prompts("", "", cs, match)[0], cs[0].prompt)

    def test_unknown_identity_preserved_when_matched_by_hair(self):
        cs = characters()
        cs[0].prompt = "new_character (new_franchise), blonde hair"
        match = match_characters({"blonde_hair": 0.9, "black_hair": 0.1}, cs)
        self.assertIn(
            "new_character (new_franchise)", selected_prompts("", "", cs, match)[0]
        )

    def test_shared_features_do_not_force_match(self):
        cs = [
            CharacterPrompt("alice, long hair", "", 0, 0),
            CharacterPrompt("bob, long hair", "", 1, 1),
        ]
        self.assertIsNone(match_characters({"long_hair": 0.99}, cs).character_index)

    def test_low_margin_stays_unmatched(self):
        self.assertIsNone(
            match_characters(
                {"blonde_hair": 0.9, "black_hair": 0.88}, characters()
            ).character_index
        )

    def test_extra_original_attributes_do_not_bias_mixed_identity_crop(self):
        cs = [
            CharacterPrompt("alice, messy hair", "", 0, 0),
            CharacterPrompt("bob", "", 1, 1),
        ]
        self.assertIsNone(
            match_characters(
                {"alice": 0.987, "messy_hair": 0.627, "bob": 0.951}, cs
            ).character_index
        )

    def test_eye_color_alone_cannot_force_identity(self):
        self.assertIsNone(
            match_characters(
                {"blue_eyes": 0.99, "red_eyes": 0.01}, characters()
            ).character_index
        )

    def test_multiple_regions_can_match_same_character(self):
        for _ in range(2):
            self.assertEqual(
                match_characters(
                    {"blonde_hair": 0.9, "black_hair": 0.1}, characters()
                ).character_index,
                0,
            )

    def test_nan_scores_cannot_force_match(self):
        self.assertIsNone(
            match_characters(
                {"blonde_hair": float("nan")}, characters()
            ).character_index
        )


class RequestTests(unittest.TestCase):
    def setUp(self):
        nai_api._next_request_at = 0

    def tearDown(self):
        nai_api._next_request_at = 0

    def response(self, status=200, retry=None):
        response = requests.Response()
        response.status_code = status
        response._content = b"png"
        response._content_consumed = True
        if retry is not None:
            response.headers["Retry-After"] = retry
        return response

    def test_two_second_gap_is_from_completion_not_start(self):
        now = [100.0]
        starts = []

        def wait(deadline):
            now[0] = max(now[0], deadline)

        def post(*args, **kwargs):
            starts.append(now[0])
            self.assertEqual(kwargs["timeout"], (10, 300))
            now[0] += 7
            return self.response()

        with (
            mock.patch.object(nai_api.time, "monotonic", side_effect=lambda: now[0]),
            mock.patch.object(nai_api, "wait_until", side_effect=wait),
            mock.patch.object(nai_api._session, "post", side_effect=post),
        ):
            nai_api.post_nai("test", {})
            nai_api.post_nai("test", {})
        self.assertEqual(starts, [100, 109])

    def test_requests_from_two_threads_never_overlap(self):
        active = 0
        peak = 0
        guard = threading.Lock()

        def post(*args, **kwargs):
            nonlocal active, peak
            with guard:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with guard:
                active -= 1
            return self.response()

        with (
            mock.patch.object(nai_api, "NAI_REQUEST_INTERVAL", 0.01),
            mock.patch.object(nai_api._session, "post", side_effect=post),
        ):
            with ThreadPoolExecutor(2) as pool:
                self.assertEqual(
                    list(pool.map(lambda _: nai_api.post_nai("test", {}), range(2))),
                    [b"png"] * 2,
                )
        self.assertEqual(peak, 1)

    def test_retry_after_is_respected_and_retry_is_bounded(self):
        now = [100.0]
        starts = []

        def wait(deadline):
            now[0] = max(now[0], deadline)

        def post(*args, **kwargs):
            starts.append(now[0])
            return self.response(429, "120")

        with (
            mock.patch.object(nai_api.time, "monotonic", side_effect=lambda: now[0]),
            mock.patch.object(nai_api, "wait_until", side_effect=wait),
            mock.patch.object(nai_api._session, "post", side_effect=post),
        ):
            with self.assertRaises(requests.HTTPError):
                nai_api.post_nai("test", {})
        self.assertEqual(starts, [100, 220])
        self.assertEqual(nai_api._next_request_at, 340)

    def test_http_date_and_invalid_retry_after(self):
        with mock.patch.object(nai_api.time, "time", return_value=0):
            self.assertEqual(
                nai_api._retry_delay(
                    self.response(429, "Thu, 01 Jan 1970 00:01:00 GMT")
                ),
                60,
            )
        for value in ("invalid", "nan", "inf"):
            self.assertEqual(nai_api._retry_delay(self.response(429, value)), 60)
        self.assertEqual(nai_api._retry_delay(self.response(429, "0")), 2)

    def test_transport_failure_releases_lock_and_sets_cooldown(self):
        with (
            mock.patch.object(nai_api._session, "post", side_effect=requests.Timeout),
            mock.patch.object(nai_api.time, "monotonic", return_value=100),
            mock.patch.object(nai_api, "wait_until"),
        ):
            with self.assertRaises(requests.Timeout):
                nai_api.post_nai("test", {})
        self.assertEqual(nai_api._next_request_at, 102)
        self.assertFalse(nai_api._request_lock.locked())

    def test_cancellation_during_cooldown_does_not_send_request(self):
        with (
            mock.patch.object(
                nai_api, "wait_until", side_effect=RuntimeError("cancelled")
            ),
            mock.patch.object(nai_api._session, "post") as post,
        ):
            with self.assertRaises(RuntimeError):
                nai_api.post_nai("test", {})
        post.assert_not_called()
        self.assertFalse(nai_api._request_lock.locked())


class FakeSAM:
    def __init__(self, model):
        pass

    def set_image(self, image):
        self.height, self.width = image.shape[:2]

    def predict(self, box, multimask_output):
        x0, y0, x1, y1 = [int(x) for x in box[0]]
        mask = np.zeros((1, self.height, self.width), dtype=bool)
        mask[0, y0:y1, x0:x1] = True
        return mask, None, None


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.image = torch.zeros((1, 64, 128, 3))
        # Overlapping crop rectangles, separate character boxes, reverse detector order.
        self.segs = [
            SimpleNamespace(bbox=(84, 20, 108, 44), crop_region=(48, 0, 128, 64)),
            SimpleNamespace(bbox=(20, 20, 44, 44), crop_region=(0, 0, 80, 64)),
        ]
        self.detector = SimpleNamespace(
            detect=mock.Mock(return_value=((64, 128), self.segs))
        )
        self.payloads = []
        self.addCleanup(mock.patch.stopall)
        mock.patch.dict(
            sys.modules, {"segment_anything": SimpleNamespace(SamPredictor=FakeSAM)}
        ).start()
        mock.patch.object(detailer, "get_nai_token", return_value="test").start()
        mock.patch.object(
            NovelAIGenerator, "_get_output_directory", return_value=self.temp.name
        ).start()
        self.post = mock.patch.object(
            detailer, "post_nai", side_effect=self.fake_post
        ).start()

    def fake_post(self, token, payload):
        self.payloads.append(payload)
        p = payload["parameters"]
        color = "red" if "alice" in payload["input"] else "blue"
        img = Image.new("RGB", (p["width"], p["height"]), color)
        png = io.BytesIO()
        img.save(png, format="PNG")
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as zipped:
            zipped.writestr("image.png", png.getvalue())
        return data.getvalue()

    def run_detail(self, **kwargs):
        options = dict(
            image=self.image,
            primary_detector=self.detector,
            secondary_detector=None,
            sam_model=object(),
            prompt="eye detail",
            negative_prompt="bad quality",
            model="NAI Diffusion V5 Full",
            strength=0.4,
            threshold=0.3,
            sampler="k_euler",
            steps=20,
            cfg_scale=5,
            bbox_threshold=0.5,
            dilation=0,
            crop_factor=3,
            scheduler="karras",
            seed=123,
            detail_mode="all",
            matching_mode="wd14",
            characterPrompts=characters(),
            tagger=SimpleNamespace(
                score=lambda images: [
                    {"blonde_hair": 0.99, "black_hair": 0.01},
                    {"blonde_hair": 0.01, "black_hair": 0.99},
                ][: len(images)]
            ),
        )
        options.update(kwargs)
        return detailer.run_face_detail(**options)

    def test_two_regions_original_prompts_and_masked_cumulative_composite(self):
        out, mask, report = self.run_detail()
        self.assertEqual(len(self.payloads), 2)
        for payload in self.payloads:
            encoded = Image.open(
                io.BytesIO(base64.b64decode(payload["parameters"]["mask"]))
            )
            self.assertEqual(encoded.mode, "L")
            pixels = np.array(encoded)
            cells = pixels.reshape(encoded.height // 8, 8, encoded.width // 8, 8)
            self.assertTrue(
                np.array_equal(cells.max(axis=(1, 3)), cells.min(axis=(1, 3)))
            )
        self.assertEqual(
            self.payloads[0]["input"], "eye detail, " + characters()[0].prompt
        )
        self.assertEqual(
            self.payloads[1]["input"], "eye detail, " + characters()[1].prompt
        )
        self.assertNotIn("alice", self.payloads[1]["parameters"]["negative_prompt"])
        np.testing.assert_array_equal(out[0, 32, 32].numpy(), [1, 0, 0])
        np.testing.assert_array_equal(out[0, 32, 96].numpy(), [0, 0, 1])
        np.testing.assert_array_equal(out[0, 0, 64].numpy(), [0, 0, 0])
        self.assertEqual(out.shape, self.image.shape)
        self.assertEqual(mask.shape, self.image.shape)
        self.assertTrue(all(r["status"] == "edited" for r in json.loads(report)))
        self.assertEqual([p["parameters"]["seed"] for p in self.payloads], [123, 124])
        # Second crop still comes from original black image, not first edit.
        second = Image.open(
            io.BytesIO(base64.b64decode(self.payloads[1]["parameters"]["image"]))
        )
        self.assertEqual(np.array(second).max(), 0)

    def test_wd_observations_cannot_enter_payload(self):
        tagger = SimpleNamespace(
            score=mock.Mock(
                return_value=[
                    {"blonde_hair": 0.99, "black_hair": 0.01, "hacked_tag": 1.0},
                    {"blonde_hair": 0.01, "black_hair": 0.99, "hacked_tag": 1.0},
                ]
            )
        )
        self.run_detail(matching_mode="wd14", tagger=tagger)
        self.assertEqual(len(self.payloads), 2)
        for p in self.payloads:
            self.assertNotIn("hacked_tag", json.dumps(p))
        tagger.score.assert_called_once()

    def test_preview_needs_no_token_or_sam_and_sends_no_requests(self):
        with mock.patch.object(
            detailer, "get_nai_token", side_effect=AssertionError("token read")
        ):
            _, _, report = self.run_detail(preview_only=True)
        self.post.assert_not_called()
        self.assertEqual([r["character"] for r in json.loads(report)], [1, 2])

    def test_ambiguous_regions_are_skipped(self):
        tagger = SimpleNamespace(
            score=lambda images: [{"blonde_hair": 0.8, "black_hair": 0.8}] * len(images)
        )
        out, _, report = self.run_detail(matching_mode="wd14", tagger=tagger)
        self.post.assert_not_called()
        self.assertTrue(torch.equal(out, self.image))
        self.assertTrue(all(r["status"] == "skipped" for r in json.loads(report)))

    def test_empty_masks_do_not_send_requests(self):
        with mock.patch.object(
            FakeSAM, "predict", return_value=(np.zeros((1, 768, 1024)), None, None)
        ):
            # Dimensions are 1024x768 for 80x64 crop (64-pixel floor rounding).
            _, _, report = self.run_detail(threshold=0)
        self.post.assert_not_called()
        self.assertTrue(all(r["status"] == "empty_mask" for r in json.loads(report)))

    def test_uncertain_context_automatically_retries_tighter_crop(self):
        tagger = SimpleNamespace(
            score=mock.Mock(
                side_effect=[
                    [
                        {"blonde_hair": 0.9, "black_hair": 0.88},
                        {"blonde_hair": 0.1, "black_hair": 0.9},
                    ],
                    [{"blonde_hair": 0.95, "black_hair": 0.1}],
                ]
            )
        )
        _, _, report = self.run_detail(tagger=tagger, preview_only=True)
        self.assertEqual(tagger.score.call_count, 2)
        self.assertEqual(json.loads(report)[0]["reason"], "tag_match_tight")
        context = tagger.score.call_args_list[0].args[0][0]
        tight = tagger.score.call_args_list[1].args[0][0]
        self.assertLess(tight.width, context.width)
        self.post.assert_not_called()

    def test_first_mode_preserves_original_detector_selection(self):
        _, _, report = self.run_detail(
            detail_mode="first", matching_mode="shared", characterPrompts=None
        )
        self.assertEqual(len(self.payloads), 1)
        self.assertEqual(json.loads(report)[0]["bbox"], [84, 20, 108, 44])

    def test_single_region_request_preserves_original_grid_without_resampling(self):
        self.detector.detect.return_value = ((64, 128), [self.segs[1]])
        from ComfyUI_RS_NAI_API_Request.generators import mask_to_grid_boxes

        raw = np.zeros((768, 1024), dtype=np.uint8)
        raw[240:528, 256:563] = 255
        expected = np.array(mask_to_grid_boxes(raw, 1024, 768, 0.3))
        self.run_detail(matching_mode="shared", characterPrompts=None)
        actual = np.array(
            Image.open(
                io.BytesIO(base64.b64decode(self.payloads[0]["parameters"]["mask"]))
            )
        )
        np.testing.assert_array_equal(actual, expected)

    def test_max_regions_limits_requests(self):
        self.run_detail(max_regions=1)
        self.assertEqual(len(self.payloads), 1)

    def test_overlapping_masks_are_clipped_to_disjoint_region_ownership(self):
        with mock.patch.object(
            FakeSAM, "predict", return_value=(np.ones((1, 768, 1024)), None, None)
        ):
            out, _, _ = self.run_detail()
        np.testing.assert_array_equal(out[0, 32, 60].numpy(), [1, 0, 0])
        np.testing.assert_array_equal(out[0, 32, 70].numpy(), [0, 0, 1])
        mask = Image.open(
            io.BytesIO(base64.b64decode(self.payloads[1]["parameters"]["mask"]))
        )
        self.assertEqual(np.array(mask)[:, :100].max(), 0)

    def test_secondary_boxes_are_assigned_to_one_primary_region(self):
        secondary = SimpleNamespace(
            detect=lambda *args, **kwargs: ((64, 128), self.segs)
        )
        with mock.patch.object(
            FakeSAM, "predict", autospec=True, side_effect=FakeSAM.predict
        ) as predict:
            self.run_detail(secondary_detector=secondary)
        # One primary + its own secondary per region, not all secondary boxes.
        self.assertEqual(predict.call_count, 4)

    def test_no_manual_matching_option_exposed(self):
        for cls in (NAIFaceDetailerNode, NAIFaceDetailerSegmNode):
            options = cls.INPUT_TYPES()["optional"]
            self.assertNotIn("manual_mapping", options)
            self.assertNotIn("manual", options["matching_mode"][0])

    def test_missing_tagger_fails_before_any_request(self):
        with self.assertRaises(ValueError):
            self.run_detail(tagger=None)
        self.post.assert_not_called()

    def test_no_detections_does_not_need_token(self):
        self.detector.detect.return_value = ((64, 128), [])
        out, _, report = self.run_detail()
        self.assertTrue(torch.equal(out, self.image))
        self.assertEqual(json.loads(report)["status"], "no_detections")
        self.post.assert_not_called()

    def test_both_nodes_expose_new_options_and_keep_first_two_outputs(self):
        for cls in (NAIFaceDetailerNode, NAIFaceDetailerSegmNode):
            self.assertEqual(cls.RETURN_TYPES[:2], ("IMAGE", "IMAGE"))
            self.assertIn("tagger", cls.INPUT_TYPES()["optional"])
            self.assertIn("preview_only", cls.INPUT_TYPES()["optional"])


class TaggerTests(unittest.TestCase):
    def test_preprocessing_bgr_scores_and_offload(self):
        class Model(torch.nn.Module):
            def forward(self, batch):
                # Input red image -> red in channel 2 after RGB -> BGR.
                self.seen = batch.clone()
                return torch.tensor([[0.0, 1.0, 2.0]]).repeat(batch.shape[0], 1)

        tagger = WDTagger("unused", "cpu", 2)
        tagger._model = Model()
        tagger._labels = [
            {"name": "rating", "category": "9"},
            {"name": "red_hair", "category": "0"},
            {"name": "alice", "category": "4"},
        ]
        tagger._transform = lambda im: (
            torch.from_numpy(np.array(im).copy()).permute(2, 0, 1).float() / 255
        )
        result = tagger.score([Image.new("RGB", (8, 8), "red")])
        self.assertEqual(set(result[0]), {"red_hair", "alice"})
        self.assertAlmostEqual(
            result[0]["red_hair"], torch.sigmoid(torch.tensor(1.0)).item()
        )
        self.assertEqual(tagger._model.seen[0, 2].min(), 1)
        self.assertEqual(tagger._model.seen[0, 0].max(), 0)


if __name__ == "__main__":
    unittest.main()
