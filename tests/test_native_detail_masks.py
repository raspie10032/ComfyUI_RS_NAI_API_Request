"""Offline regressions from the SAM3/native SEGM review (no NovelAI transport)."""
import base64
import io
import json
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np
import torch
from PIL import Image

import test_detailer as fixtures
from ComfyUI_RS_NAI_API_Request import detailer
from ComfyUI_RS_NAI_API_Request.generators import NAIFaceDetailerNode, NAIFaceDetailerSegmNode


class NativeMaskTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = fixtures.PipelineTests()
        self.pipeline.setUp()
        self.addCleanup(self.pipeline.doCleanups)

    def run_masks(self, masks, **kwargs):
        options = dict(primary_detector=None, secondary_detector=None, sam_model=None,
                       mask_source="external_mask", detail_mask=masks,
                       matching_mode="shared", characterPrompts=None)
        options.update(kwargs)
        return self.pipeline.run_detail(**options)

    @staticmethod
    def branched_masks():
        masks = torch.zeros((2, 64, 128))
        masks[0, 10:54, 12:28] = 1
        masks[0, 40:54, 12:100] = 1
        masks[1, 12:30, 66:84] = 1
        return masks

    @staticmethod
    def pixels(mask):
        return mask[0, :, :, 0].numpy() > 0

    def test_sam3_empty_batch_and_black_mask_are_no_detections(self):
        source = torch.full((1, 64, 128, 3), 0.5)
        for masks in (torch.zeros(0, 64, 128), torch.zeros(1, 64, 128), torch.zeros(64, 128)):
            for preview in (False, True):
                with self.subTest(shape=masks.shape, preview=preview), mock.patch.object(
                    detailer, "get_nai_token", side_effect=AssertionError("token accessed")
                ):
                    out, mask, report = self.run_masks(masks, image=source, preview_only=preview)
                    self.assertTrue(torch.equal(out, source))
                    self.assertEqual(float(mask.max()), 0)
                    self.assertEqual(json.loads(report)["status"], "no_detections")
        self.pipeline.post.assert_not_called()

    def test_empty_batch_still_validates_spatial_size_and_invalid_masks(self):
        cases = [torch.zeros(0, 32, 128), torch.zeros(0, 0, 128), torch.zeros(0),
                 torch.zeros(1, 1, 64, 128), torch.full((1, 64, 128), float("nan")),
                 torch.full((1, 64, 128), -0.1), torch.full((1, 64, 128), 1.1)]
        for masks in cases:
            with self.subTest(shape=masks.shape), self.assertRaises(ValueError):
                self.run_masks(masks)
        self.pipeline.post.assert_not_called()

    def test_disjoint_branches_keep_all_2036_pixels_and_preview_matches_execution(self):
        masks = self.branched_masks()
        expected = masks.numpy().max(0) > 0
        self.assertEqual(int(expected.sum()), 2036)
        with mock.patch.object(detailer, "get_nai_token", side_effect=AssertionError("token accessed")):
            _, preview, _ = self.run_masks(masks, crop_factor=1, preview_only=True)
        self.pipeline.post.assert_not_called()
        out, used, report = self.run_masks(masks, crop_factor=1)
        np.testing.assert_array_equal(self.pixels(used), expected)
        self.assertTrue(torch.equal(preview, used))
        np.testing.assert_array_equal(self.pixels(out), np.zeros_like(expected))  # mocked response is blue
        self.assertTrue(torch.equal(out[0, :, :, 2] > 0, torch.from_numpy(expected)))
        self.assertEqual(sum(r["mask_pixels"] for r in json.loads(report)), 2036)
        self.assertEqual(len(self.pipeline.payloads), 2)

    def test_overlap_is_assigned_once_and_skipped_instances_keep_their_pixels(self):
        masks = torch.zeros(2, 64, 128)
        masks[0, 10:50, 10:80] = 1
        masks[1, 10:50, 50:110] = 1
        out, used, report = self.run_masks(masks, matching_mode="wd14", characterPrompts=fixtures.characters())
        expected = masks.numpy().max(0) > 0
        np.testing.assert_array_equal(self.pixels(used), expected)
        self.assertEqual(sum(r["mask_pixels"] for r in json.loads(report)), int(expected.sum()))
        np.testing.assert_array_equal(out[0, 30, 55].numpy(), [1, 0, 0])
        np.testing.assert_array_equal(out[0, 30, 70].numpy(), [0, 0, 1])
        _, limited, limited_report = self.run_masks(masks, max_regions=1)
        _, preview, _ = self.run_masks(masks, max_regions=1, preview_only=True)
        self.assertTrue(torch.equal(preview, limited))
        self.assertEqual(float(limited[0, 30, 70, 0]), 0)
        self.assertEqual(float(limited[0, 30, 55, 0]), 1)
        self.assertEqual(json.loads(limited_report)[1]["status"], "skipped")

    def test_identical_masks_have_stable_ties_and_no_duplicate_request(self):
        masks = torch.zeros(2, 64, 128)
        masks[:, 10:40, 10:40] = 1
        _, used, report = self.run_masks(masks)
        self.assertEqual([r["status"] for r in json.loads(report)], ["edited", "empty_mask"])
        self.assertEqual(int(self.pixels(used).sum()), 900)
        self.assertEqual(len(self.pipeline.payloads), 1)

    def test_native_segm_uses_same_plan_for_soft_masks_holes_and_eye_context(self):
        masks = self.branched_masks().numpy()
        masks[0, 15:22, 15:22] = 0  # hole must remain untouched
        masks[0, 22:25, 15:22] = 0.2  # below threshold
        segs = [SimpleNamespace(bbox=(12, 10, 100, 54), crop_region=(0, 0, 128, 64), cropped_mask=masks[0]),
                SimpleNamespace(bbox=(66, 12, 84, 30), crop_region=(0, 0, 128, 64), cropped_mask=masks[1])]
        detector = SimpleNamespace(detect=lambda *a, **k: ((64, 128), segs))
        eye = SimpleNamespace(detect=mock.Mock(return_value=((512, 1024), [
            SimpleNamespace(bbox=(120, 160, 140, 180), crop_region=(50, 100, 210, 250))])))
        kwargs = dict(primary_detector=detector, primary_uses_native_mask=True, mask_source="segm", eye_bbox_detector=eye)
        with mock.patch.object(detailer, "get_nai_token", side_effect=AssertionError("token accessed")):
            _, preview, _ = self.run_masks(None, preview_only=True, **kwargs)
        _, used, _ = self.run_masks(None, **kwargs)
        self.assertTrue(torch.equal(preview, used))
        np.testing.assert_array_equal(self.pixels(used), masks.max(0) >= 0.3)
        self.assertEqual(eye.detect.call_count, 4)

    def test_thin_downscaled_members_stay_covered_by_whole_api_cells(self):
        masks = torch.zeros(1, 64, 2048)
        masks[0, 10, 3:2043] = 1
        masks[0, 54, 2043] = 1
        source = torch.zeros(1, 64, 2048, 3)
        _, used, report = self.run_masks(masks, image=source, crop_factor=1)
        np.testing.assert_array_equal(self.pixels(used), masks[0].numpy() > 0)
        payload = self.pipeline.payloads[0]["parameters"]
        request = Image.open(io.BytesIO(base64.b64decode(payload["mask"])))
        array = np.array(request)
        cells = array.reshape(request.height // 8, 8, request.width // 8, 8)
        np.testing.assert_array_equal(cells.max((1, 3)), cells.min((1, 3)))
        x0, y0, x1, y1 = json.loads(report)[0]["crop"]
        local = np.array(request.resize((x1 - x0, y1 - y0), Image.Resampling.NEAREST)) > 0
        self.assertTrue(local[masks[0, y0:y1, x0:x1].numpy() > 0].all())

    def test_full_frame_strict_guard_and_references_still_stop_before_token(self):
        with mock.patch.object(detailer, "get_nai_token", side_effect=AssertionError("token accessed")):
            with self.assertRaisesRegex(RuntimeError, "focused crop"):
                self.run_masks(torch.ones(1, 64, 128), limit_opus_free=True)
        self.pipeline.post.assert_not_called()

    def test_legacy_widget_order_is_an_exact_prefix_for_both_detailers(self):
        # Released 2.5.0 positional widgets, excluding frontend-generated seed control.
        old = ["prompt", "negative_prompt", "model", "strength", "threshold", "sampler", "steps",
               "cfg_scale", "bbox_threshold", "dilation", "crop_factor", "scheduler", "seed",
               "limit_opus_free", "detail_mode", "matching_mode", "match_min_score", "match_min_margin",
               "match_crop_factor", "max_regions", "preview_only", "normalize_vibe_strengths"]
        for node in (NAIFaceDetailerNode, NAIFaceDetailerSegmNode):
            names = [name for group in ("required", "optional") for name, spec in node.INPUT_TYPES()[group].items()
                     if isinstance(spec[0], list) or spec[0] in {"STRING", "INT", "FLOAT", "BOOLEAN"}]
            self.assertEqual(names, old + ["mask_source"])


if __name__ == "__main__":
    unittest.main()
