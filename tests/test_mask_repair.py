import importlib.util
from pathlib import Path
import unittest

import numpy as np
from scipy import ndimage

import test_detailer
from ComfyUI_RS_NAI_API_Request import mask_repair as repair


def notch():
    mask = np.zeros((100, 100), bool)
    mask[10:90, 10:90] = 1
    # A six-pixel mouth connected to the exterior through the side, near an eye.
    mask[40:46, 10:30] = 0
    return mask


class RepairTests(unittest.TestCase):
    def test_hole_fill_cannot_restore_open_notch(self):
        m = notch()
        np.testing.assert_array_equal(ndimage.binary_fill_holes(m), m)
        fixed, _ = repair.repair_instance(m, .15, .3, .1, False)
        self.assertGreater(int((fixed & ~m).sum()), 0)
        self.assertTrue(fixed[43, 28])
        self.assertFalse(fixed[43, 9])

    def test_off_preserves_masks_and_sources_are_not_mutated(self):
        masks = notch()[None]
        saved = masks.copy()
        orig, fixed, _ = repair.plan_masks(masks, "off")
        np.testing.assert_array_equal(fixed, masks)
        repair.plan_masks(masks)
        np.testing.assert_array_equal(masks, saved)

    def test_zero_budget_no_additions(self):
        m = notch()
        fixed, _ = repair.repair_instance(m, .15, .3, 0, False)
        np.testing.assert_array_equal(fixed, m)

    def test_large_occlusion_is_not_convex_hulled(self):
        m = notch()
        m[10:65, 35:65] = 0
        fixed, _ = repair.repair_instance(m, .12, .25, .08, False)
        self.assertFalse(fixed[45, 45])
        self.assertLessEqual(int((fixed & ~m).sum()), int(m.sum() * .08))

    def test_closed_holes_are_optional(self):
        m = np.zeros((100,100), bool)
        m[10:90,10:90] = 1
        m[40:46,40:46] = 0
        fixed, _ = repair.repair_instance(m, .15, .3, .1, False)
        np.testing.assert_array_equal(fixed, m)
        filled, _ = repair.repair_instance(m, .15, .3, .1, True)
        self.assertTrue(filled[42,42])

    def test_top_hairline_hole_is_rejected(self):
        m = np.zeros((100,100), bool)
        m[10:90,10:90] = 1
        m[13:18,40:45] = 0
        fixed, _ = repair.repair_instance(m, .15, .3, .1, True)
        self.assertFalse(fixed[15,42])

    def test_neighbor_original_has_priority_over_repairs(self):
        a = notch()
        b = np.zeros_like(a)
        b[41:45,24:28] = 1
        original, final, _ = repair.plan_masks(np.stack([a,b]), notch_width=.15, notch_depth=.3)
        np.testing.assert_array_equal(final[1][b], np.ones(b.sum(), bool))
        self.assertFalse(final[0][b].any())
        self.assertFalse((final.sum(0) > 1).any())

    def test_overlapping_and_identical_masks_have_single_owner(self):
        a=notch();b=np.roll(a,15,axis=1)
        for masks in (np.stack([a,b]),np.stack([a,a])):
            original,final,_=repair.plan_masks(masks)
            self.assertFalse((final.sum(0)>1).any())
            self.assertTrue(np.all(final.any(0)[masks.any(0)]))
            self.assertTrue(np.all(final[original]))

    def test_disconnected_components_do_not_bridge(self):
        m=np.zeros((100,100),bool)
        m[10:90,10:48]=1;m[10:90,51:90]=1
        fixed,_=repair.repair_instance(m,.5,.5,.5,True)
        self.assertFalse(fixed[:,48:51].any())

    def test_border_and_single_pixel_do_not_erode(self):
        for m in (np.ones((40,40),bool),np.eye(40,dtype=bool)):
            fixed,_=repair.repair_instance(m,.15,.3,.1,False)
            self.assertTrue(np.all(fixed[m]))

    def test_disconnected_repairs_are_translation_invariant(self):
        component = notch()
        expected, rejected = repair.repair_instance(component, .15, .3, .1, True)
        mask = np.zeros((240, 330), bool)
        mask[5:105, 7:107] = component
        mask[130:230, 220:320] = component
        saved = mask.copy()
        fixed, total_rejected = repair.repair_instance(mask, .15, .3, .1, True)
        combined = np.zeros_like(mask)
        combined[5:105, 7:107] = expected
        combined[130:230, 220:320] = expected
        np.testing.assert_array_equal(fixed, combined)
        np.testing.assert_array_equal(mask, saved)
        self.assertEqual(total_rejected, 2 * rejected)

    def test_noise_components_do_not_change_face_repair(self):
        mask = np.zeros((256, 320), bool)
        mask[80:180, 100:200] = notch()
        expected, rejected = repair.repair_instance(mask, .15, .3, .1, True)
        noise = np.zeros_like(mask)
        noise[::8, :80:8] = True
        fixed, noisy_rejected = repair.repair_instance(mask | noise, .15, .3, .1, True)
        np.testing.assert_array_equal(fixed, expected | noise)
        self.assertEqual(noisy_rejected, rejected)

    def test_nested_components_do_not_merge_when_repairs_are_disabled(self):
        mask = np.zeros((100, 100), bool)
        mask[10:90, 10:90] = True
        mask[20:80, 20:80] = False
        mask[40:60, 40:60] = True
        fixed, rejected = repair.repair_instance(mask, .15, .3, .1, False, close_notches=False)
        np.testing.assert_array_equal(fixed, mask)
        self.assertEqual(rejected, 0)

    def test_empty_masks(self):
        for m in (np.zeros((0,20,30),bool),np.zeros((2,20,30),bool)):
            before,after,_=repair.plan_masks(m)
            self.assertEqual(after.shape,m.shape)
            self.assertFalse(after.any())

    def test_feather_never_leaks_outside_mask(self):
        m=notch()
        for f in (0,1,8,64):
            alpha=repair.inside_alpha(m,f)
            self.assertFalse(alpha[~m].any())
            self.assertTrue(np.all((alpha>=0)&(alpha<=1)))

    def test_invalid_masks_fail_with_context(self):
        for m in (np.zeros((4,5)),np.zeros((1,1,20,30)),np.full((20,30),np.nan),np.full((20,30),1.1)):
            with self.assertRaisesRegex(ValueError,'MASK'):
                repair.validate_masks(m,20,30)

    def test_dilation_provides_room_with_repair_disabled(self):
        m = np.zeros((25, 25), bool)
        m[10:15, 10:15] = True
        original, final, reports = repair.plan_masks(m[None], "off", dilation=3)
        np.testing.assert_array_equal(original[0], m)
        self.assertTrue(final[0, 12, 7])
        self.assertFalse(final[0, 12, 6])
        self.assertTrue(final[0][m].all())
        self.assertEqual(reports[0]["repair_added_pixels"], 0)
        self.assertGreater(reports[0]["dilation_candidate_pixels"], 0)

    def test_dilation_is_after_closing_and_not_limited_by_repair_budget(self):
        m = notch()
        _, fixed, _ = repair.plan_masks(m[None], notch_width=.15, notch_depth=.3,
                                       max_added_ratio=.1, dilation=3)
        # Closing fills the 6-pixel notch, then dilation extends its outer edge.
        self.assertTrue(fixed[0, 43, 8])
        _, expanded, report = repair.plan_masks(m[None], max_added_ratio=0, dilation=3)
        self.assertEqual(report[0]["repair_added_pixels"], 0)
        self.assertTrue(expanded[0, 20, 7])

    def test_dilation_preserves_neighbor_sources_and_single_ownership(self):
        masks = np.zeros((3, 50, 70), bool)
        masks[0, 10:40, 5:25] = True
        masks[1, 10:40, 27:47] = True
        masks[2, 10:40, 49:69] = True
        saved = masks.copy()
        original, final, _ = repair.plan_masks(masks, dilation=12)
        np.testing.assert_array_equal(masks, saved)
        self.assertFalse((final.sum(0) > 1).any())
        self.assertTrue(final[original].all())
        # Even an unselected neighbor remains reserved if only region 0 is sampled.
        self.assertFalse(final[0][masks[1:].any(0)].any())

    def test_dilation_clips_at_canvas_and_keeps_empty_masks_empty(self):
        for masks in (np.zeros((0, 20, 30), bool), np.zeros((2, 20, 30), bool)):
            _, final, _ = repair.plan_masks(masks, dilation=8)
            self.assertEqual(final.shape, masks.shape)
            self.assertFalse(final.any())
        m = np.zeros((20, 30), bool)
        m[0, 0] = True
        _, final, _ = repair.plan_masks(m[None], "off", dilation=8)
        self.assertTrue(final[0, 0, 8])
        self.assertFalse(final[0, -1, -1])
        self.assertFalse(repair.inside_alpha(final[0], 8)[~final[0]].any())

    def test_invalid_dilation_fails_with_context(self):
        for dilation in (-1, 129, 1.5, True, float("nan")):
            with self.assertRaisesRegex(ValueError, "dilation"):
                repair.plan_masks(notch()[None], dilation=dilation)


if __name__ == '__main__':
    unittest.main()
