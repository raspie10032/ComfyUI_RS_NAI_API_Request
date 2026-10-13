"""Detection-only loader and NovelAI routing; transport is mocked."""
import json
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np
import torch

import test_detailer as fixtures
from ComfyUI_RS_NAI_API_Request import detailer
from ComfyUI_RS_NAI_API_Request.combined_detailer import NAICombinedFaceDetailerTest, RepairedDetector
from ComfyUI_RS_NAI_API_Request.detector_bundle import DetectionBundle, NAIDetectorCombineLoaderTest


class CombinedTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = fixtures.PipelineTests()
        self.pipeline.setUp()
        self.addCleanup(self.pipeline.doCleanups)
        self.mask = np.zeros((64,128), np.float32)
        self.mask[8:56,16:100] = 1
        self.mask[30:34,50:54] = 0
        self.mask[30:34,16:23] = 0
        self.seg = SimpleNamespace(bbox=(16,8,100,56), crop_region=(0,0,128,64), cropped_mask=self.mask)
        self.detector = SimpleNamespace(detect=mock.Mock(return_value=((64,128),[self.seg])))
        self.bundle = DetectionBundle(self.detector)

    def run_node(self, **kwargs):
        settings = dict(image=self.pipeline.image, detectors=self.bundle, prompt='eye detail',
                        negative_prompt='low quality', model='NAI Diffusion V5 Full',
                        seed=42, matching_mode='shared', limit_opus_free=False)
        settings.update(kwargs)
        return NAICombinedFaceDetailerTest().detail(**settings)

    def test_preview_fills_hole_notch_expands_crop_and_never_reads_token(self):
        with mock.patch.object(detailer, 'get_nai_token', side_effect=AssertionError('token')):
            _, mask, report = self.run_node(crop_factor=1)
        mask = mask[0,:,:,0].numpy()>0
        self.assertTrue(mask[31,51] and mask[31,21] and mask[6,50])
        self.assertEqual(json.loads(report)[0]['mask_repair']['source'], 'segm')
        self.pipeline.post.assert_not_called()

    def test_generation_is_nai_infill_and_feather_stays_inside_the_same_preview_mask(self):
        source=torch.full_like(self.pipeline.image,128/255)
        _, preview, _ = self.run_node(image=source)
        out, used, report = self.run_node(image=source, preview_only=False)
        self.assertTrue(torch.equal(preview, used))
        self.assertEqual(self.pipeline.payloads[0]['action'], 'infill')
        self.assertEqual(self.pipeline.payloads[0]['model'], 'nai-diffusion-5-full-inpainting')
        support=used[0,:,:,0]>0
        self.assertTrue(torch.equal(out[0][~support], source[0][~support]))
        red=out[0,:,:,0][support]
        self.assertTrue(torch.any((red>0)&(red<128/255)))
        self.assertEqual(json.loads(report)[0]['status'], 'edited')

    def test_holes_and_notches_can_be_toggled_independently(self):
        _, mask, _=self.run_node(closing=False, fill_holes=True, dilation=0)
        self.assertEqual(mask[0,31,51,0],1)
        self.assertEqual(mask[0,31,21,0],0)
        _, mask, _=self.run_node(closing=False, fill_holes=False, dilation=0)
        np.testing.assert_array_equal(mask[0,:,:,0].numpy()>0,self.mask>0)

    def test_no_faces_returns_source_and_no_api(self):
        self.detector.detect.return_value=((64,128),[])
        out, used, report=self.run_node(preview_only=False)
        self.assertTrue(torch.equal(out,self.pipeline.image))
        self.assertEqual(float(used.max()),0)
        self.assertEqual(json.loads(report)['status'],'no_detections')
        self.pipeline.post.assert_not_called()

    def test_strict_guard_blocks_before_api_or_token(self):
        with mock.patch.object(detailer,'get_nai_token',side_effect=AssertionError('token')):
            with self.assertRaisesRegex(RuntimeError,'(?i)(free|anlas)'):
                self.run_node(preview_only=False,limit_opus_free=True,model='NAI Diffusion V4.5 Full')
        self.pipeline.post.assert_not_called()

    def test_bad_bundle_and_batch_fail_before_detector(self):
        for kw in ({'detectors':object()},{'image':torch.zeros(2,64,128,3)}):
            with self.assertRaises(ValueError): self.run_node(**kw)
        self.detector.detect.assert_not_called()

    def test_schema_has_no_local_generation_sockets(self):
        inputs=NAICombinedFaceDetailerTest.INPUT_TYPES()
        types=[x[0] for part in ('required','optional') for x in inputs[part].values() if isinstance(x[0],str)]
        self.assertFalse(set(types)&{'MODEL','CLIP','VAE','CONDITIONING'})
        self.assertEqual(inputs['optional']['dilation'][1]['default'],8)

    def test_optional_sam_uses_boxes_and_repairs_its_mask(self):
        class SAM:
            def __init__(self,model): pass
            def set_image(self,image): pass
            def predict(inner,**kwargs): return self.mask[None]>0,None,None
        bbox=SimpleNamespace(detect=mock.Mock(return_value=((64,128),[self.seg])))
        with mock.patch.dict(sys.modules,{'segment_anything':SimpleNamespace(SamPredictor=SAM)}):
            _,mask,report=self.run_node(detectors=DetectionBundle(self.detector,bbox,object()))
        bbox.detect.assert_called_once()
        self.detector.detect.assert_not_called()
        self.assertEqual(json.loads(report)[0]['mask_repair']['source'],'sam')
        self.assertEqual(json.loads(report)[0]['mask_source'],'sam')
        self.assertEqual(float(mask[0,31,51,0]),1)

    def test_loader_only_loads_selected_detectors_and_validates_before_loading(self):
        yolo=SimpleNamespace(INPUT_TYPES=lambda:{'required':{'model_name':(['segm/face.pt','bbox/face.pt','bbox/eyes.pt'],)}})
        yolo_instance=SimpleNamespace(doit=mock.Mock(return_value=('bbox','segm')))
        yolo_cls=mock.Mock(return_value=yolo_instance)
        yolo_cls.INPUT_TYPES=yolo.INPUT_TYPES
        sam_cls=mock.Mock()
        sam_cls.INPUT_TYPES=lambda:{'required':{'model_name':(['sam_vit_b.pth'],)}}
        with mock.patch.dict(sys.modules,{'nodes':SimpleNamespace(NODE_CLASS_MAPPINGS={'UltralyticsDetectorProvider':yolo_cls,'SAMLoader':sam_cls})}):
            bundle=NAIDetectorCombineLoaderTest().load('segm/face.pt')[0]
            self.assertEqual(bundle.segm_detector,'segm')
            yolo_instance.doit.assert_called_once_with('segm/face.pt')
            sam_cls.assert_not_called()
            yolo_instance.doit.reset_mock()
            with self.assertRaisesRegex(ValueError,'requires SAM'):
                NAIDetectorCombineLoaderTest().load('segm/face.pt',face_bbox_model='bbox/face.pt')
            yolo_instance.doit.assert_not_called()


if __name__=='__main__': unittest.main()
