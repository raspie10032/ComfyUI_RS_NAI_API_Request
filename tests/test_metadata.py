"""Offline round trips and bounds; no API calls or paid requests."""
import gzip
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ComfyUI_RS_NAI_API_Request import metadata as meta, metadata_loader, generators, nai_api
import test_medium_nodes as medium_fixtures
import test_inset_assets as inset_fixtures
import test_detailer as detail_fixtures


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = Image.fromarray(np.random.default_rng(123).integers(0, 256, (128, 192, 3), dtype=np.uint8))
        characters = generators.CharacterPromptSelect().build_character_prompt(
            character1='青い鳥, 파랑', character1_uc='hat', character1_x=.3, character1_y=.5, character2_enable=True,
            character2='赤い鳥', character2_uc='ribbon', character2_x=.7)[0]
        parameters = nai_api.build_common_parameters(192, 128, 123, 'k_euler', 28, 6, 'bad', model_id='nai-diffusion-5-full')
        nai_api.apply_v4_parameters(parameters, 'nai-diffusion-5-full', '鳥と花, 새', 'bad', characters)
        self.payload = nai_api.build_nai_payload('鳥と花, 새', 'nai-diffusion-5-full', 'generate', parameters)
        self.comment = json.dumps({'prompt': self.payload['input'], **parameters}, ensure_ascii=False)
        self.image.info.update(Comment=self.comment, Description=self.payload['input'], Source='NovelAI Diffusion V5 HASH', Software='NovelAI', workflow='DO NOT SAVE', prompt='DO NOT SAVE')

    def test_png_and_webp_roundtrip_unicode_settings_characters_and_no_workflow(self):
        for format in meta.SAVE_FORMATS:
            with self.subTest(format=format):
                path = meta.autosave(self.image, self.root / format, payload=self.payload, save_format=format)
                with Image.open(path) as saved:
                    if format != 'WebP lossy':
                        np.testing.assert_array_equal(np.array(saved), np.array(self.image))
                    fields, warnings = meta.read_fields(saved)
                    self.assertEqual(fields['Comment'], self.comment)
                    self.assertEqual(fields['Description'], self.payload['input'])
                    self.assertEqual(warnings, [])
                    self.assertNotIn('workflow', fields)
                    self.assertNotIn('prompt', fields)
                    self.assertNotIn(b'DO NOT SAVE', path.read_bytes())
                    data = meta.inspect_metadata(saved)
                    self.assertEqual(data['status'], 'ok')
                    self.assertEqual(data['settings']['model'], 'NAI Diffusion V5 Full')
                    self.assertEqual(data['settings']['seed'], 123)
                    self.assertEqual(data['settings']['prompt'], '鳥と花, 새')
                    self.assertEqual(len(data['characters']), 2)
                    self.assertEqual(data['characters'][0]['centers'], [{'x': .3, 'y': .5}])
                    if format.startswith('WebP'):
                        exif_comment = saved.getexif().get_ifd(34665)[37510]
                        self.assertTrue(exif_comment.startswith(b'ASCII\0\0\0'))
                        self.assertEqual(json.loads(exif_comment[8:]), json.loads(self.comment))

    def test_png_does_not_carry_unrelated_exif_workflow(self):
        exif = Image.Exif()
        exif[37510] = 'COMFY_WORKFLOW_DO_NOT_KEEP'
        self.image.info['exif'] = exif.tobytes()
        path = meta.autosave(self.image, self.root / 'clean', payload=self.payload)
        with Image.open(path) as saved:
            self.assertFalse(saved.getexif())
            self.assertEqual(meta.inspect_metadata(saved)['settings']['seed'], 123)
        self.assertNotIn(b'COMFY_WORKFLOW_DO_NOT_KEEP', path.read_bytes())

    def test_original_png_and_official_webp_exif_without_custom_record(self):
        info = PngInfo()
        info.add_text('Comment', self.comment)
        info.add_text('Source', 'NovelAI Diffusion V5 HASH')
        self.image.save(self.root / 'official.png', pnginfo=info)
        exif = Image.Exif()
        exif[305] = 'NovelAI Diffusion V5 HASH'
        exif[34665] = {37510: b'ASCII\0\0\0' + json.dumps(json.loads(self.comment), ensure_ascii=True).encode('ascii')}
        self.image.save(self.root / 'official.webp', exif=exif, lossless=True)
        for filename in ('official.png', 'official.webp'):
            with Image.open(self.root / filename) as image:
                data = meta.inspect_metadata(image)
                self.assertEqual(data['settings']['prompt'], self.payload['input'])
                self.assertEqual(len(data['characters']), 2)
                self.assertIn('unknown_model', data['warnings'])
                self.assertNotIn('model', data['settings'])

    def hidden(self, fields):
        raw = gzip.compress(json.dumps(fields).encode())
        stream = b'stealth_pngcomp' + (len(raw)*8).to_bytes(4, 'big') + raw
        bits = np.unpackbits(np.frombuffer(stream, dtype=np.uint8))
        array = np.full((128, 192, 4), 255, dtype=np.uint8)
        alpha = array[:, :, 3].T.copy().reshape(-1)
        alpha[:len(bits)] = (alpha[:len(bits)] & 254) | bits
        array[:, :, 3] = alpha.reshape(192, 128).T
        return Image.fromarray(array)

    def test_hidden_metadata_bounded_and_preserved_before_rgb_conversion(self):
        from ComfyUI_RS_NAI_API_Request.image_utils import png_bytes_to_pil
        image = self.hidden({'Comment': self.comment})
        buf = io.BytesIO(); image.save(buf, format='PNG')
        decoded = png_bytes_to_pil(buf.getvalue())
        self.assertEqual(decoded.mode, 'RGB')
        self.assertEqual(meta.inspect_metadata(decoded)['settings']['seed'], 123)
        corrupt = self.hidden({'Comment': 'x'})
        a = np.array(corrupt)
        alpha = a[:, :, 3].T.copy().reshape(-1)
        alpha[120:152] = 255
        a[:, :, 3] = alpha.reshape(192,128).T
        bad = meta.inspect_metadata(Image.fromarray(a))
        self.assertIn('invalid_hidden_metadata', bad['warnings'])

    def test_missing_corrupt_comment_and_path_traversal(self):
        self.image.info.clear()
        self.assertEqual(meta.inspect_metadata(self.image)['status'], 'empty')
        self.image.info['Comment'] = 'broken json'
        self.assertIn('invalid_comment', meta.inspect_metadata(self.image)['warnings'])
        folder_paths = mock.Mock(get_input_directory=lambda: str(self.root), get_output_directory=lambda: str(self.root), get_temp_directory=lambda: str(self.root), get_annotated_filepath=lambda name: str(self.root / name))
        with mock.patch.dict(sys.modules, folder_paths=folder_paths):
            with self.assertRaises(ValueError): metadata_loader.image_path('../outside.png')
            self.image.save(self.root / 'valid.png')
            self.assertEqual(metadata_loader.inspect_file('valid.png')['status'], 'empty')

    def test_safe_request_omits_encoded_images_and_credentials(self):
        self.payload['parameters'].update(image='PRIVATE_IMAGE', mask='PRIVATE_MASK', reference_image_multiple=['PRIVATE_REF'])
        self.payload['token'] = 'PRIVATE_TOKEN'
        record = meta.request_record(self.payload)
        self.assertTrue(record['references_omitted'])
        self.assertNotIn('PRIVATE_', json.dumps(record))

    def test_detailer_never_applies_crop_as_base_and_inset_has_canvas_warning(self):
        self.image.info['rs_detailer_regions'] = '[{"index": 0}]'
        data = meta.inspect_metadata(self.image)
        self.assertEqual(data['operation'], 'detailer')
        self.assertEqual(data['settings'], {})
        self.image.info.pop('rs_detailer_regions')
        path = meta.autosave(self.image, self.root/'detail', operation='detailer', extra={'edits':[{'region':1, 'request':meta.request_record(self.payload)}]}, save_format='WebP lossless')
        with Image.open(path) as saved:
            data = meta.inspect_metadata(saved)
            self.assertEqual(data['settings'], {})
            self.assertEqual(len(data['record']['edits']), 1)
        self.image.info['rs_nai_inset'] = '{}'
        self.assertIn('inset_canvas_coordinates', meta.inspect_metadata(self.image)['warnings'])

    def test_save_preflight_no_api_and_old_widget_prefixes(self):
        with mock.patch.object(meta.features, 'check', return_value=False), mock.patch.object(generators, 'get_nai_token') as token:
            with self.assertRaisesRegex(RuntimeError, 'cannot save WebP'):
                generators.NovelAIGenerator().generate('a', '', 'NAI Diffusion V5 Full', 64,64,'k_euler',28,6,1,save_format='WebP lossless')
            token.assert_not_called()
        for value in (0, 101, True, 2.5):
            with self.assertRaises(ValueError): meta.validate_save_options('WebP lossy', value)
        for cls in (generators.NovelAIGenerator, generators.NAIImg2ImgNode, generators.NAIInpaintNode, generators.NAIFaceDetailerNode, generators.NAIFaceDetailerSegmNode):
            legacy_fields = [key for key in cls.INPUT_TYPES()['optional'] if key not in {'nai_context', 'use_context_settings'}]
            self.assertEqual(legacy_fields[-3:], ['save_format','webp_quality','request_delay_seconds'])


class NodeSaveTests(unittest.TestCase):
    def test_regular_img2img_inpaint_real_node_code_mock_http_webp(self):
        case = medium_fixtures.MediumNodeTests()
        case.setUp()
        try:
            import torch
            for cls, extra, strict in ((generators.NovelAIGenerator, {},True), (generators.NAIImg2ImgNode, {'image':torch.zeros(1,64,64,3),'strength':.5},False), (generators.NAIInpaintNode, {'image':torch.zeros(1,64,64,3),'mask':torch.ones(1,64,64),'strength':.5},False)):
                cls().generate(**case.options(),**extra,limit_opus_free=strict,save_format='WebP lossless')
            paths=list(Path(case.temp.name).rglob('*.webp'))
            self.assertEqual(len(paths),3)
            for path in paths:
                with Image.open(path) as image:
                    data=meta.inspect_metadata(image)
                    self.assertEqual(data['settings']['model'], 'NAI Diffusion V5 Full — Medium Effort')
                    self.assertEqual(image.getpixel((0,0)), (0,255,255))
        finally: case.doCleanups()

    def test_inset_saves_both_outputs_to_webp(self):
        case=inset_fixtures.InsetTests();case.setUp()
        try:
            from ComfyUI_RS_NAI_API_Request import inset
            prepared=case.prepare()['result'][0];case.response()
            inset.NAIReferenceInsetGenerate().generate(**case.options(prepared),save_format='WebP lossy')
            paths=list((case.root/'output').rglob('*.webp'))
            self.assertEqual(len(paths),2)
            for path in paths:
                with Image.open(path) as image:
                    data=meta.inspect_metadata(image)
                    self.assertEqual(data['operation'],'inset')
                    self.assertIn('inset_canvas_coordinates',data['warnings'])
        finally: case.doCleanups()

    def test_detailer_saves_edit_history_not_last_crop_comment(self):
        case=detail_fixtures.PipelineTests();case.setUp()
        try:
            case.run_detail(save_format='WebP lossless')
            paths=list(Path(case.temp.name).rglob('*.webp'))
            self.assertEqual(len(paths),1)
            with Image.open(paths[0]) as image:
                data=meta.inspect_metadata(image)
                self.assertEqual(data['operation'],'detailer')
                self.assertEqual(data['settings'],{})
                self.assertEqual(len(data['record']['edits']),2)
                self.assertNotIn('Comment',meta.read_fields(image)[0])
                prompts=[edit['request']['input'] for edit in data['record']['edits']]
                self.assertTrue(any('alice' in p for p in prompts))
                self.assertTrue(any('bob' in p for p in prompts))
        finally: case.doCleanups()
