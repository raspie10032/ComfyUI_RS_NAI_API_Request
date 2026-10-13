"""Selected catalog detector download: cache, errors, cancellation and OFF behavior."""
import hashlib
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import test_detailer  # Standalone package fixtures, without importing ComfyUI.
from ComfyUI_RS_NAI_API_Request import detection_models as models
from ComfyUI_RS_NAI_API_Request import detector_bundle as bundle


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / models.DEFAULT_FILENAME
        self.data = b"test model" * 30000
        self.progress = mock.Mock()
        self.paths = SimpleNamespace(get_full_path=mock.Mock(return_value=None),
            get_folder_paths=lambda _: [str(self.root)], filename_list_cache={'ultralytics_segm': 1})
        for patch in (mock.patch.dict(sys.modules, {'folder_paths': self.paths}),
                      mock.patch.dict(models.CATALOG, {models.DEFAULT_SEGM: {**models.CATALOG[models.DEFAULT_SEGM], 'size': len(self.data), 'sha256': hashlib.sha256(self.data).hexdigest()}})):
            patch.start(); self.addCleanup(patch.stop)

    def test_first_download_verified_and_second_run_reuses_without_network(self):
        with mock.patch.object(models, 'urlopen', return_value=io.BytesIO(self.data)) as fetch:
            self.assertEqual(models.ensure_detection_model(models.DEFAULT_SEGM, self.progress), self.target)
            self.assertEqual(self.target.read_bytes(), self.data)
            self.assertEqual(models.ensure_detection_model(models.DEFAULT_SEGM, self.progress), self.target)
        fetch.assert_called_once_with(models.CATALOG[models.DEFAULT_SEGM]["url"], timeout=30)
        self.assertEqual(list(self.root.iterdir()), [self.target])
        self.assertGreater(self.progress.report.call_count, 2)
        self.assertNotIn('ultralytics_segm', self.paths.filename_list_cache)

    def test_custom_registered_path_is_reused_unchanged(self):
        custom = self.root / 'custom.pt'; custom.write_bytes(b'existing model')
        self.paths.get_full_path.return_value = str(custom)
        with mock.patch.object(models, 'urlopen', side_effect=AssertionError('network')):
            self.assertEqual(models.ensure_detection_model(models.DEFAULT_SEGM, self.progress), custom)
        self.assertEqual(custom.read_bytes(), b'existing model')

    def test_truncated_wrong_hash_oversized_and_network_failures_leave_no_model(self):
        for data in (b'partial', b'x'*len(self.data), self.data+b'x', None):
            with self.subTest(data_length=len(data) if data else None):
                kwargs = {'return_value': io.BytesIO(data)} if data is not None else {'side_effect': OSError('offline')}
                with mock.patch.object(models, 'urlopen', **kwargs), self.assertRaisesRegex(RuntimeError, 'Could not download'):
                    models.ensure_detection_model(models.DEFAULT_SEGM, self.progress)
                self.assertEqual(list(self.root.iterdir()), [])
        # Retrying after a failed attempt must not hang on the download lock.
        with mock.patch.object(models, 'urlopen', return_value=io.BytesIO(self.data)):
            models.ensure_detection_model(models.DEFAULT_SEGM, self.progress)

    def test_cancellation_propagates_and_cleans_partial_file(self):
        class Cancelled(Exception): pass
        calls = 0
        def check():
            nonlocal calls
            calls += 1
            if calls == 3: raise Cancelled()
        with mock.patch.object(models, 'urlopen', return_value=io.BytesIO(self.data)), \
             mock.patch.object(models, 'check_interrupted', side_effect=check), \
             mock.patch.object(models, 'is_interruption', side_effect=lambda e: isinstance(e, Cancelled)), \
             self.assertRaises(Cancelled):
            models.ensure_detection_model(models.DEFAULT_SEGM, self.progress)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_schema_and_validation_never_download_and_allow_missing_default(self):
        with mock.patch.object(bundle, 'installed_models', return_value=([], [])), \
             mock.patch.object(bundle, 'installed_sams', return_value=[]), \
             mock.patch.object(bundle, 'ensure_detection_model', side_effect=AssertionError('download')):
            schema = bundle.NAIDetectionCombineLoader.INPUT_TYPES()
            self.assertEqual(schema['required']['face_segm_model'][1]['default'], models.DEFAULT_SEGM)
            self.assertIs(bundle.NAIDetectionCombineLoader.VALIDATE_INPUTS(models.DEFAULT_SEGM), True)
            self.assertEqual(bundle.NAIDetectionCombineLoader().load('OFF')[0], bundle.DetectionBundle())

    def test_default_download_before_loading_and_ignored_selections_need_no_sam(self):
        yolo = mock.Mock(); yolo.return_value.doit.return_value = ('bbox', 'segm')
        with mock.patch.object(bundle, 'installed_models', return_value=([], [])), \
             mock.patch.object(bundle, 'installed_sams', side_effect=AssertionError('SAM metadata')), \
             mock.patch.object(bundle, 'provider', return_value=yolo) as provider, \
             mock.patch.object(bundle, 'ensure_detection_model') as download:
            yolo.return_value.doit.side_effect = lambda name: (download.assert_called_once(), 'segm')
            result = bundle.NAIDetectionCombineLoader().load(
                face_bbox_model='missing bbox.pt', sam_model='missing sam.pth')[0]
        self.assertEqual(result, bundle.DetectionBundle(segm_detector='segm'))
        provider.assert_called_once_with('UltralyticsDetectorProvider')

    def test_selected_bbox_download_uses_bbox_folder_and_only_selected_file(self):
        name = 'bbox/hand_yolov8n.pt'
        spec = {**models.CATALOG[name], 'size': len(self.data),
                'sha256': hashlib.sha256(self.data).hexdigest()}
        self.paths.get_folder_paths = mock.Mock(return_value=[str(self.root)])
        with mock.patch.dict(models.CATALOG, {name: spec}), \
             mock.patch.object(models, 'urlopen', return_value=io.BytesIO(self.data)) as fetch:
            target = models.ensure_detection_model(name, self.progress)
        self.assertEqual(target.name, 'hand_yolov8n.pt')
        self.paths.get_folder_paths.assert_called_once_with('ultralytics_bbox')
        fetch.assert_called_once_with(spec['url'], timeout=30)
        self.assertEqual(list(self.root.iterdir()), [target])

    def test_folder_models_merge_deduplicate_and_remain_selectable_without_catalog(self):
        values = ([], [])
        with mock.patch.object(bundle, 'installed_models', side_effect=lambda: values), \
             mock.patch.object(bundle, 'installed_sams', return_value=['custom/sam_vit_b.pth']), \
             mock.patch.object(models, 'urlopen', side_effect=AssertionError('network')):
            before = bundle.NAIDetectionCombineLoader.INPUT_TYPES()
            values = ([models.DEFAULT_SEGM, 'segm/custom/new.pt'], ['bbox/custom/new.pt'])
            after = bundle.NAIDetectionCombineLoader.INPUT_TYPES()
            self.assertNotIn('segm/custom/new.pt', before['required']['face_segm_model'][0])
            self.assertIn('segm/custom/new.pt', after['required']['face_segm_model'][0])
            self.assertIn('bbox/custom/new.pt', after['optional']['face_bbox_model'][0])
            self.assertIn('custom/sam_vit_b.pth', after['optional']['sam_model'][0])
            self.assertEqual(after['required']['face_segm_model'][0].count(models.DEFAULT_SEGM), 1)
            self.assertIs(bundle.NAIDetectionCombineLoader.VALIDATE_INPUTS('segm/custom/new.pt'), True)
            self.assertIsNone(models.ensure_detection_model('segm/custom/new.pt', self.progress))

    def test_catalog_entries_have_target_hash_and_specific_artifact_urls(self):
        self.assertGreaterEqual({spec['target'] for spec in models.CATALOG.values()},
                                {'face', 'eyes', 'clothes', 'hands', 'skin/body', 'person'})
        for name, spec in models.CATALOG.items():
            self.assertIn(name.split('/')[0], ('segm', 'bbox'))
            self.assertEqual(len(Path(name).parts), 2)
            self.assertEqual(len(bytes.fromhex(spec['sha256'])), 32)
            self.assertGreater(spec['size'], 0)
            self.assertTrue(spec['url'].startswith('https://'))
            self.assertNotIn('/resolve/main/', spec['url'])

    def test_notice_wrapper_preserves_node_id_for_download_progress(self):
        from ComfyUI_RS_NAI_API_Request.diagnostics import node_notices
        @node_notices
        class Loader(bundle.NAIDetectionCombineLoader):
            pass
        with mock.patch.object(bundle, 'TaggerProgress') as progress:
            result = Loader().load('OFF', unique_id='loader-2')
        progress.assert_called_once_with('loader-2')
        self.assertEqual(result['result'], (bundle.DetectionBundle(),))


if __name__ == '__main__': unittest.main()
