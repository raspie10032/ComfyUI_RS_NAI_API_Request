"""Restore files into real consumers; HTTP transport is mocked, never paid."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest import mock

from PIL import Image

import test_metadata as fixtures
import test_generation_context as chains
from ComfyUI_RS_NAI_API_Request import metadata as meta, generators as g, metadata_loader
from ComfyUI_RS_NAI_API_Request.combined_detailer import NAIMultiCharacterDetailer
from ComfyUI_RS_NAI_API_Request.detector_bundle import DetectionBundle
from ComfyUI_RS_NAI_API_Request.generation_context import NAIContext, UnavailableNAIContext, context_from_payload, inherit_context
from ComfyUI_RS_NAI_API_Request.metadata_context import restore_context


class MetadataContextTests(unittest.TestCase):
    setUp = fixtures.MetadataTests.setUp

    def data(self):
        image = self.image.copy()
        image.info['rs_nai'] = json.dumps({'request': meta.request_record(self.payload)})
        return meta.inspect_metadata(image)

    def test_roundtrip_all_formats_preserves_exact_context_and_fractional_coordinates(self):
        self.payload['parameters']['v4_prompt']['caption']['char_captions'][0]['centers'][0]['x'] = .345678
        self.payload['parameters']['v4_negative_prompt']['caption']['char_captions'][0]['centers'][0]['x'] = .345678
        self.image.info['Comment'] = json.dumps(self.payload['parameters'])
        expected = context_from_payload(self.payload)
        for fmt in meta.SAVE_FORMATS:
            with self.subTest(fmt=fmt):
                path = meta.autosave(self.image, self.root / fmt, payload=self.payload, save_format=fmt)
                with Image.open(path) as image:
                    context, report = restore_context(meta.inspect_metadata(image))
                self.assertEqual(report['status'], 'ready')
                self.assertEqual(context, expected)
                self.assertNotIn('seed', context.settings())

    def test_model_hash_requires_explicit_selection_without_mutating_metadata(self):
        data = meta.inspect_metadata(self.image)
        before = copy.deepcopy(data)
        context, report = restore_context(data)
        self.assertIsInstance(context, UnavailableNAIContext)
        self.assertIn({'code': 'missing', 'field': 'model'}, report['issues'])
        restored, report = restore_context(data, 'NAI Diffusion V5 Full')
        self.assertEqual(restored, replace(context_from_payload(self.payload), source_action='unknown'))
        self.assertEqual(data, before)
        self.assertEqual(report['model_choice'], 'NAI Diffusion V5 Full')

    def test_each_inherited_field_is_required_and_values_are_not_coerced(self):
        data = self.data()
        for field in data['settings']:
            if field in ('strength', 'noise'):
                continue
            modified = copy.deepcopy(data)
            modified['settings'].pop(field)
            with self.subTest(missing=field):
                self.assertIsInstance(restore_context(modified)[0], UnavailableNAIContext)
        for field, value in [('steps', '28'), ('steps', True), ('steps', 51), ('seed', -1),
                ('width', 0), ('height', 2.5), ('cfg_scale', float('inf')), ('cfg_rescale', -.1),
                ('prefer_brownian', 'false'), ('variety_boost', 1), ('sampler', 'bogus'),
                ('scheduler', {}), ('model', []), ('negative_prompt', 1)]:
            modified = copy.deepcopy(data); modified['settings'][field] = value
            with self.subTest(field=field, value=value):
                self.assertIsInstance(restore_context(modified)[0], UnavailableNAIContext)

    def test_unsupported_coordinates_and_malformed_pairs_are_not_silently_dropped(self):
        for centers in ([], [{'x': .3, 'y': .5}, {'x': .7, 'y': .5}], [{'x': 2, 'y': .5}], [{'x': True, 'y': .5}]):
            data = self.data(); data['characters'][0]['centers'] = centers
            self.assertIsInstance(restore_context(data)[0], UnavailableNAIContext)
        for change in ('extra_negative', 'numeric_negative', 'mismatched_centers', 'automatic'):
            image = self.image.copy(); p = copy.deepcopy(self.payload['parameters'])
            neg = p['v4_negative_prompt']['caption']['char_captions']
            if change == 'extra_negative': neg.append(copy.deepcopy(neg[0]))
            if change == 'numeric_negative': neg[0]['char_caption'] = 10
            if change == 'mismatched_centers': neg[0]['centers'] = [{'x': .99, 'y': .99}]
            if change == 'automatic': p['v4_prompt']['use_coords'] = False
            image.info.update(Comment=json.dumps(p), Source='nai-diffusion-5-full')
            with self.subTest(change=change):
                self.assertIsInstance(restore_context(meta.inspect_metadata(image))[0], UnavailableNAIContext)

    def test_malformed_structured_prompt_and_variety_boost_are_not_coerced(self):
        for key, value in [('v4_prompt', []), ('v4_prompt', {'caption': None}),
                ('v4_negative_prompt', 'broken'), ('skip_cfg_above_sigma', 'false'),
                ('skip_cfg_above_sigma', True), ('skip_cfg_above_sigma', -1),
                ('skip_cfg_above_sigma', float('inf'))]:
            image = self.image.copy(); p = copy.deepcopy(self.payload['parameters'])
            p[key] = value
            image.info.update(Comment=json.dumps(p), Source='nai-diffusion-5-full')
            with self.subTest(key=key, value=value):
                self.assertIsInstance(restore_context(meta.inspect_metadata(image))[0], UnavailableNAIContext)

    def test_zero_empty_false_and_model_character_limits(self):
        data = self.data()
        data['settings'].update(prompt='', negative_prompt='', cfg_scale=0, cfg_rescale=0, prefer_brownian=False, variety_boost=False, seed=0)
        context, _ = restore_context(data)
        self.assertIsInstance(context, NAIContext)
        self.assertEqual((context.prompt, context.negative_prompt, context.cfg_scale, context.source_seed), ('', '', 0, 0))
        self.assertIsInstance(restore_context(data, 'NAI Diffusion V3')[0], UnavailableNAIContext)
        data['characters'] *= 4
        self.assertIsInstance(restore_context(data, 'NAI Diffusion V4.5 Full')[0], UnavailableNAIContext)
        self.assertIsInstance(restore_context(data, 'NAI Diffusion V5 Full')[0], NAIContext)

    def test_empty_reference_arrays_do_not_report_missing_references(self):
        for value in ([], None, False, 0, ''):
            p = copy.deepcopy(self.payload)
            p['parameters'].update(reference_image_multiple=value, director_reference_strength_values=value)
            self.assertFalse(meta.request_record(p)['references_omitted'])
            image = self.image.copy(); image.info['Comment'] = json.dumps(p['parameters'])
            self.assertNotIn('references_omitted', meta.inspect_metadata(image)['warnings'])
        p['parameters']['reference_image_multiple'] = ['encoded-reference']
        self.assertTrue(meta.request_record(p)['references_omitted'])
        self.assertNotIn('encoded-reference', json.dumps(meta.request_record(p)))

    def test_detailer_restores_connected_base_not_last_crop(self):
        source = context_from_payload(self.payload)
        for fmt in meta.SAVE_FORMATS:
            path = meta.autosave(self.image, self.root / ('detail-' + fmt), operation='detailer', save_format=fmt,
                extra={'base_generation_available': True, 'base_generation': meta.context_record(source),
                       'edits': [{'request': {'input': 'last face only'}}]})
            with Image.open(path) as image:
                actual, _ = restore_context(meta.inspect_metadata(image))
            self.assertEqual(actual, source)
        for warning in ('detailer_not_base', 'inset_canvas_coordinates', 'invalid_record'):
            data = self.data(); data['warnings'].append(warning)
            self.assertIsInstance(restore_context(data)[0], UnavailableNAIContext)

    def test_fingerprint_accepts_error_wrappers_hidden_node_id(self):
        import sys
        from types import SimpleNamespace
        core = SimpleNamespace(IS_CHANGED=lambda image: "file-content-hash")
        with mock.patch.dict(sys.modules, {"nodes": SimpleNamespace(LoadImage=core)}), \
                mock.patch.object(metadata_loader, 'image_path'):
            fingerprint = metadata_loader.NAILoadImage.IS_CHANGED
            original = fingerprint('image.png', unique_id='1')
            self.assertEqual(original, fingerprint('image.png', unique_id='42'))
            self.assertNotEqual(original, fingerprint('image.png', context_model='NAI Diffusion V5 Full', unique_id='1'))

    def test_image_and_mask_slots_remain_first(self):
        self.assertEqual(metadata_loader.NAILoadImage.RETURN_TYPES, ('IMAGE', 'MASK', 'NAI_CONTEXT'))


class RestoredContextConsumerTests(unittest.TestCase):
    setUp = chains.ContextTests.setUp
    source = chains.ContextTests.source
    i2i = chains.ContextTests.i2i

    def test_loader_to_t2i_selective_override_to_i2i_and_file(self):
        _, original = self.source()
        image = Image.new('RGB', original.source_size)
        path = meta.autosave(image, Path(self.transport.temp.name) / 'source',
                            payload=meta.context_record(original))
        with Image.open(path) as saved:
            loaded, _ = restore_context(meta.inspect_metadata(saved))
        opts = self.transport.options()
        opts.update(nai_context=loaded, seed=222, context_mode='override_selected',
                    override_cfg_scale=True, cfg_scale=4.5, override_negative_prompt=True, negative_prompt='')
        img, generated = g.NovelAIGenerator().generate(**opts)
        self.assertEqual(generated, replace(original, cfg_scale=4.5, negative_prompt='', source_seed=222))
        _, next_context = self.i2i(img, generated, context_mode='override_selected', override_steps=True, steps=19)
        self.assertEqual(next_context.prompt, original.prompt)
        self.assertEqual((next_context.steps, next_context.cfg_scale, next_context.source_seed), (19, 4.5, 456))
        self.assertEqual(next_context.characters, original.characters)

    def test_unavailable_context_blocks_all_enabled_consumers_before_auth(self):
        invalid = UnavailableNAIContext(('missing: model',))
        self.transport.post.reset_mock()
        with mock.patch.object(g, 'get_nai_token', side_effect=AssertionError('token access')):
            with self.assertRaisesRegex(ValueError, 'missing: model'):
                g.NovelAIGenerator().generate(**self.transport.options(), nai_context=invalid)
            with self.assertRaisesRegex(ValueError, 'missing: model'):
                self.i2i(chains.torch.zeros((1, 64, 64, 3)), invalid)
            with self.assertRaisesRegex(ValueError, 'missing: model'):
                NAIMultiCharacterDetailer().detail(chains.torch.zeros((1, 64, 64, 3)), DetectionBundle(None, object()),
                    'manual', '', 'NAI Diffusion V5 Full', nai_context=invalid)
        self.transport.post.assert_not_called()

    def test_disabling_context_explicitly_uses_manual_settings(self):
        invalid = UnavailableNAIContext(('missing: model',))
        _, context = g.NovelAIGenerator().generate(**self.transport.options(), nai_context=invalid, use_context_settings=False)
        self.assertEqual(context.prompt, 'bird on a branch')
        from ComfyUI_RS_NAI_API_Request import detailer
        with mock.patch.object(detailer, 'run_face_detail', return_value=(None, None, '[]')) as run:
            NAIMultiCharacterDetailer().detail(chains.torch.zeros((1, 64, 64, 3)), DetectionBundle(None, object()),
                'manual', '', 'NAI Diffusion V5 Full', nai_context=invalid, use_context_settings=False)
        self.assertIsNone(run.call_args.kwargs['nai_context'])
        self.assertIsNone(inherit_context(invalid, False))


if __name__ == '__main__':
    unittest.main()
