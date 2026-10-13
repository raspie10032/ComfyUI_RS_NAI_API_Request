"""Detection-only loader and NovelAI routing; transport is mocked."""
import json
import itertools
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
from ComfyUI_RS_NAI_API_Request.detection_models import CATALOG, DEFAULT_SEGM


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

    def test_segm_bypasses_bbox_and_sam_even_with_all_three_in_bundle(self):
        class SAM:
            def __init__(self,model): pass
            def set_image(self,image): pass
            def predict(inner,**kwargs): return self.mask[None]>0,None,None
        bbox=SimpleNamespace(detect=mock.Mock(return_value=((64,128),[self.seg])))
        with mock.patch.dict(sys.modules,{'segment_anything':SimpleNamespace(SamPredictor=SAM)}):
            _,mask,report=self.run_node(detectors=DetectionBundle(self.detector,bbox,object()))
        bbox.detect.assert_not_called()
        self.detector.detect.assert_called_once()
        self.assertEqual(json.loads(report)[0]['mask_repair']['source'],'segm')
        self.assertEqual(json.loads(report)[0]['mask_source'],'segm')
        self.assertEqual(float(mask[0,31,51,0]),1)

    def test_loader_loads_only_enabled_models_for_every_combination(self):
        yolo=SimpleNamespace(INPUT_TYPES=lambda:{'required':{'model_name':(['segm/face.pt','bbox/face.pt','bbox/eyes.pt'],)}})
        yolo_instance=SimpleNamespace(doit=mock.Mock(return_value=('bbox','segm')))
        yolo_cls=mock.Mock(return_value=yolo_instance)
        yolo_cls.INPUT_TYPES=yolo.INPUT_TYPES
        sam_cls=mock.Mock()
        sam_cls.INPUT_TYPES=lambda:{'required':{'model_name':(['sam_vit_b.pth'],)}}
        sam_cls.return_value.load_model.return_value=('sam',)
        with mock.patch.dict(sys.modules,{'nodes':SimpleNamespace(NODE_CLASS_MAPPINGS={'UltralyticsDetectorProvider':yolo_cls,'SAMLoader':sam_cls})}):
            for segm, bbox, sam, eye in itertools.product((False, True), repeat=4):
                with self.subTest(segm=segm,bbox=bbox,sam=sam,eye=eye):
                    yolo_cls.reset_mock(); yolo_instance.doit.reset_mock(); sam_cls.reset_mock()
                    bundle=NAIDetectorCombineLoaderTest().load(
                        'segm/face.pt' if segm else 'OFF',
                        face_bbox_model='bbox/face.pt' if bbox else 'OFF',
                        sam_model='sam_vit_b.pth' if sam else 'OFF',
                        eye_bbox_model='bbox/eyes.pt' if eye else 'OFF')[0]
                    self.assertEqual((bundle.segm_detector,bundle.bbox_detector,bundle.sam_model,bundle.eye_bbox_detector),
                                     ('segm' if segm else None,'bbox' if bbox and not segm else None,'sam' if sam and bbox and not segm else None,'bbox' if eye else None))
                    expected=[mock.call(name) for enabled,name in ((segm,'segm/face.pt'),(bbox and not segm,'bbox/face.pt'),(eye,'bbox/eyes.pt')) if enabled]
                    self.assertEqual(yolo_instance.doit.call_args_list,expected)
                    self.assertEqual(yolo_cls.call_count,int(segm or bbox or eye))
                    self.assertEqual(sam_cls.call_count,int(sam and bbox and not segm))
                    if sam and bbox and not segm: sam_cls.return_value.load_model.assert_called_once_with('sam_vit_b.pth','CPU')
            for kw in ({'face_segm_model':'missing.pt'}, {'sam_model':'ESAM'}, {'face_bbox_model':'segm/face.pt'}, {'eye_bbox_model':'missing.pt'}):
                yolo_cls.reset_mock(); sam_cls.reset_mock()
                with self.assertRaises(ValueError): NAIDetectorCombineLoaderTest().load(**({'face_segm_model':'OFF','face_bbox_model':'bbox/face.pt'}|kw))
                yolo_cls.assert_not_called(); sam_cls.assert_not_called()
            yolo_instance.doit.reset_mock()
            NAIDetectorCombineLoaderTest().load('OFF',face_bbox_model='bbox/eyes.pt',eye_bbox_model='bbox/eyes.pt')
            yolo_instance.doit.assert_called_once_with('bbox/eyes.pt')

    def test_all_off_needs_no_provider_and_legacy_none_remains_valid(self):
        with mock.patch('ComfyUI_RS_NAI_API_Request.detector_bundle.provider', side_effect=AssertionError('provider')):
            for off in ('OFF','None'):
                self.assertEqual(NAIDetectorCombineLoaderTest().load(off,sam_model=off,face_bbox_model=off,eye_bbox_model=off)[0], DetectionBundle())

    def test_schema_allows_off_without_installed_models(self):
        with mock.patch.dict(sys.modules,{'nodes':SimpleNamespace(NODE_CLASS_MAPPINGS={})}):
            schema=NAIDetectorCombineLoaderTest.INPUT_TYPES()
        for key in ('face_segm_model','face_bbox_model','sam_model','eye_bbox_model'):
            item=(schema['required']|schema['optional'])[key]
            self.assertEqual(item[0][0], 'OFF')
            expected = {x for x in CATALOG if x.startswith('segm/' if key=='face_segm_model' else 'bbox/')} if key!='sam_model' else set()
            self.assertEqual(set(item[0][1:]), expected)
            self.assertEqual(item[1]['default'],DEFAULT_SEGM if key=='face_segm_model' else 'OFF')

    def test_detailer_face_source_for_every_segm_bbox_sam_combination(self):
        class SAM:
            def __init__(self, model): pass
            def set_image(self, image): pass
            def predict(inner, **kwargs): return self.mask[None]>0,None,None
        # No cropped_mask: a standalone BBOX detector only needs coordinates.
        bbox=SimpleNamespace(detect=mock.Mock(return_value=((64,128),[SimpleNamespace(bbox=self.seg.bbox,crop_region=self.seg.crop_region)])))
        with mock.patch.dict(sys.modules,{'segment_anything':SimpleNamespace(SamPredictor=SAM)}), mock.patch.object(detailer,'get_nai_token',side_effect=AssertionError('token')):
            for segm, box, sam in itertools.product((False,True),repeat=3):
                with self.subTest(segm=segm,bbox=box,sam=sam):
                    self.detector.detect.reset_mock(); bbox.detect.reset_mock()
                    bundle=DetectionBundle(self.detector if segm else None,bbox if box else None,object() if sam else None)
                    if not segm and not box:
                        with self.assertRaisesRegex(ValueError,'SEGM or BBOX'): self.run_node(detectors=bundle)
                        self.detector.detect.assert_not_called(); bbox.detect.assert_not_called()
                        continue
                    _, mask, report=self.run_node(detectors=bundle,closing=False,fill_holes=False,dilation=0)
                    face_source='segm' if segm else 'bbox'
                    entry=json.loads(report)[0]
                    self.assertEqual(entry['mask_repair']['face_detector'],face_source)
                    self.assertEqual(entry['mask_source'],'sam' if sam and not segm else face_source)
                    self.assertEqual(bbox.detect.call_count,int(face_source=='bbox'))
                    self.assertEqual(self.detector.detect.call_count,int(face_source=='segm'))
                    if not sam and not segm:
                        expected=np.zeros((64,128),bool); expected[8:56,16:100]=True
                        np.testing.assert_array_equal(mask[0,:,:,0].numpy()>0,expected)
        self.pipeline.post.assert_not_called()

    def test_bbox_only_generation_uses_nai_and_preserves_outside_mask(self):
        source=torch.full_like(self.pipeline.image,128/255)
        out,mask,report=self.run_node(image=source,detectors=DetectionBundle(bbox_detector=self.detector),preview_only=False)
        self.assertEqual(self.pipeline.payloads[0]['action'],'infill')
        self.assertEqual(json.loads(report)[0]['mask_source'],'bbox')
        self.assertTrue(torch.equal(out[0][mask[0,:,:,0]==0],source[0][mask[0,:,:,0]==0]))


if __name__=='__main__': unittest.main()
