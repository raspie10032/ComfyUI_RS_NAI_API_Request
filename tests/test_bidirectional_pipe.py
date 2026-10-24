"""Both installed source packages, no network or paid inference.

RS_MC_TEST_PATH=/path/to/comfyui-rs-multicharacter-sampler enables cross-package tests.
"""
import copy
from contextlib import contextmanager
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ComfyUI_RS_NAI_API_Request import local_bridge as bridge, metadata as nai_meta, generators
from ComfyUI_RS_NAI_API_Request.generation_context import UnavailableNAIContext
from ComfyUI_RS_NAI_API_Request.metadata_context import restore_context
import test_medium_nodes as transport


@contextmanager
def temporary_modules(values):
    # Restore only injected names; torch's lazy imports have native side effects
    # and must not be removed from sys.modules after a test.
    missing = object()
    previous = {key: sys.modules.get(key, missing) for key in values}
    sys.modules.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is missing: sys.modules.pop(key, None)
            else: sys.modules[key] = value


class InlineWeightTests(unittest.TestCase):
    def test_inline_nested_escaped_literal_and_square_brackets(self):
        self.assertEqual(bridge.comfy_to_nai('scene, (red hair:2) blue eyes'), 'scene, 2::red hair:: blue eyes')
        self.assertEqual(bridge.comfy_to_nai('(girl (red hair:2))'), '1.1::girl ::2::red hair::')
        self.assertEqual(bridge.comfy_to_nai(r'girl \(series\), [literal]'), r'girl (series), \[literal\]')
        self.assertEqual(bridge.local_prompts(r'girl \[literal\], -3::hat::', 'bad'), ('girl [literal]', 'bad, hat'))
        with self.assertRaises(ValueError):
            bridge.comfy_to_nai('(hair:nan)')

    def test_native_pipe_honors_declared_syntax(self):
        pipe = bridge.NAICharacterPipe((NS(prompt='girl, (red hair:2)', uc='hat', center={'x': .2, 'y': .8}),),
                                       'scene, (cafe:1.3)', '(blur:1.2)', 'ComfyUI')
        self.assertEqual(bridge.nai_character_list(pipe)[0].prompt, 'girl, 2::red hair::')
        self.assertEqual(bridge.nai_pipe_prompts('', '', pipe), ('scene, 1.3::cafe::', '1.2::blur::'))


@unittest.skipUnless(os.environ.get('RS_MC_TEST_PATH'), 'Set RS_MC_TEST_PATH for cross-package tests')
class BidirectionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ['RS_MC_TEST_PATH']).resolve()
        spec = importlib.util.spec_from_file_location('_rs_mc_cross_test', root / '__init__.py', submodule_search_locations=[str(root)])
        cls.package = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.package
        spec.loader.exec_module(cls.package)
        cls.c = sys.modules[spec.name + '.characters']
        cls.m = sys.modules[spec.name + '.metadata']
        cls.n = sys.modules[spec.name + '.nodes']
        cls.p = sys.modules[spec.name + '.pipe_compat']
        cls.d = sys.modules[spec.name + '.detailer']

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.host = NS(NODE_CLASS_MAPPINGS=self.package.NODE_CLASS_MAPPINGS)
        modules = temporary_modules({'nodes': self.host})
        modules.__enter__()
        self.addCleanup(modules.__exit__, None, None, None)
        network = patch('requests.sessions.Session.request', side_effect=AssertionError('OFFLINE: HTTP blocked'))
        network.start()
        self.addCleanup(network.stop)
        self.pipe = self.c.CharacterPipe((self.c.Character('girl, (red hair:2) blue eyes', '(hat:1.2)', .2, .8),),
                                        'scene, (cafe:1.3)', 'bad anatomy', 'ComfyUI')
        self.image = Image.new('RGB', (64, 48), 'cyan')

    def record(self, pipe=None):
        return self.m.build_record(pipe or self.pipe, dict(width=64, height=48, seed=7, steps=2, cfg=5,
            sampler_name='euler', scheduler='normal'), {}, [], {'spatial_slots': 1}, engine='sdxl-spatial-alpha-1')

    def test_direct_round_trip_preserves_native_text_positions_and_source(self):
        before = self.pipe
        chars = bridge.nai_character_list(self.pipe)
        common = bridge.nai_pipe_prompts('', '', self.pipe)
        incoming = bridge.NAICharacterPipe(tuple(chars), *common)
        local = self.p.local_pipe(incoming)
        self.assertEqual(local.characters, before.characters)
        self.assertEqual((local.prompt, local.negative_prompt), (before.prompt, before.negative_prompt))
        self.assertEqual(self.pipe, before)
        for _ in range(3):
            incoming = bridge.NAICharacterPipe(tuple(bridge.nai_character_list(local)), *bridge.nai_pipe_prompts('', '', local))
            local = self.p.local_pipe(incoming)
        self.assertEqual(local.characters, before.characters)
        self.assertEqual(local.prompt, before.prompt)

    def test_local_saved_image_to_nai_to_local_all_formats(self):
        for fmt in self.m.FORMATS:
            with self.subTest(fmt=fmt):
                path = self.m.save_image(self.image, self.root / fmt, self.record(), fmt)
                with Image.open(path) as image:
                    data = nai_meta.inspect_metadata(image)
                self.assertIn('local_generation_settings', data['warnings'])
                self.assertIsInstance(restore_context(data)[0], UnavailableNAIContext)
                incoming = bridge.pipe_from_metadata(data)
                self.assertEqual(incoming.characters[0].prompt, 'girl, 2::red hair:: blue eyes')
                local = self.p.local_pipe(incoming)
                self.assertEqual(local.characters, self.pipe.characters)
                self.assertEqual((local.prompt, local.negative_prompt), (self.pipe.prompt, self.pipe.negative_prompt))

    def test_real_nai_generators_accept_local_pipe_and_trim_only_receiver(self):
        fixture = transport.MediumNodeTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        pipe = replace(self.pipe, characters=tuple(replace(self.pipe.characters[0], prompt=f'person {i}, (hair:2)', x=i/10) for i in range(10)))
        for node, extra in ((generators.NovelAIGenerator(), {}), (generators.NAIImg2ImgNode(), {'image': torch.zeros(1,48,64,3), 'strength': .3}),
                            (generators.NAIInpaintNode(), {'image': torch.zeros(1,48,64,3), 'mask': torch.ones(1,48,64), 'strength': .3})):
            for model, count in (('NAI Diffusion V4.5 Full', 6), ('NAI Diffusion V5 Full', 10)):
                with self.subTest(node=type(node).__name__, model=model):
                    args = dict(fixture.options(), model=model, characterPrompts=pipe, limit_opus_free=False)
                    args.update(extra)
                    output = node.generate(**args)
                    request = fixture.post.call_args.kwargs['json']
                    self.assertEqual(request['input'], 'scene, 1.3::cafe::')
                    self.assertEqual(len(request['parameters']['v4_prompt']['caption']['char_captions']), count)
                    self.assertEqual(request['parameters']['v4_prompt']['caption']['char_captions'][0]['char_caption'], 'person 0, 2::hair::')
                    if len(output) > 2:
                        restored = self.p.local_pipe(output[2])
                    else:
                        saved_path = sorted(Path(fixture.temp.name).rglob('NAI_inpaint_*.png'))[-1]
                        with Image.open(saved_path) as saved:
                            restored = self.p.local_pipe(bridge.pipe_from_metadata(nai_meta.inspect_metadata(saved)))
                    self.assertEqual(len(restored.characters), count)
        self.assertEqual(len(pipe.characters), 10)

    def test_nai_saved_request_to_local_detailer_and_back(self):
        fixture = transport.MediumNodeTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        image, context, nai_pipe = generators.NovelAIGenerator().generate(**dict(fixture.options(),
            model='NAI Diffusion V5 Full', characterPrompts=bridge.NAICharacterPipe(
                (NS(prompt='girl, 2::red hair::, -2.5::hat::', uc='blur', center={'x': .2, 'y': .8}),),
                '2::cafe::, -3::text::', 'bad anatomy')))
        payload = fixture.post.call_args.kwargs['json']
        for fmt in nai_meta.SAVE_FORMATS:
            path = nai_meta.autosave(self.image, self.root / fmt, payload=payload, save_format=fmt)
            with Image.open(path) as saved:
                record = self.m.read_record(saved)
            local = self.m.pipe_from_record(record)
            self.assertEqual((local.prompt, local.negative_prompt), ('(cafe:2)', 'bad anatomy, text'))
            self.assertEqual((local.characters[0].prompt, local.characters[0].uc), ('girl, (red hair:2)', 'blur, hat'))
        captured = []
        mask = np.zeros((48,64), np.float32); mask[8:32,8:32] = 1
        detector = NS(detect=lambda image, *args, **kw: ((48,64), [NS(bbox=(8,8,32,32), crop_region=(0,0,64,48), cropped_mask=mask)]))
        def sample(crop, mask, **kw):
            captured.append(kw)
            return crop, (64,48)
        with temporary_modules({'comfy.samplers': NS(KSampler=NS(SAMPLERS=['euler_ancestral'], SCHEDULERS=['sgm_uniform']))}), patch.object(self.d, '_sample_crop', side_effect=sample):
            result = self.d.RSMultiCharacterDetailer().detail(image=torch.zeros(1,48,64,3), model=object(), clip=object(), vae=object(),
                character_pipe=nai_pipe, detectors=sys.modules[self.package.__name__+'.detector_bundle'].DetectionBundle(detector), autosave=False)
        self.assertEqual(captured[0]['positive'], '(cafe:2), girl, (red hair:2)')
        self.assertEqual(captured[0]['negative'], 'bad anatomy, text, blur, hat')
        # The returned pipe remains valid input for either backend.
        self.assertEqual(bridge.nai_character_list(result['result'][2])[0].center, {'x': .2, 'y': .8})

    def test_local_pipe_to_nai_detailer_and_reference_inset(self):
        from ComfyUI_RS_NAI_API_Request import combined_detailer, detailer, inset
        from ComfyUI_RS_NAI_API_Request.detector_bundle import DetectionBundle
        from test_detailer import PipelineTests
        from test_inset_assets import InsetTests
        # Execute the actual face pipeline with deterministic mask/HTTP response.
        mask = np.zeros((48,64), np.float32); mask[8:32,8:32] = 1
        detector = NS(detect=lambda image, *a, **k: ((48,64), [NS(bbox=(8,8,32,32), crop_region=(0,0,64,48), cropped_mask=mask)]))
        captured = NS(payloads=[])
        def post(*args, **kwargs): return PipelineTests.fake_post(captured, *args, **kwargs)
        with patch.object(detailer, 'get_nai_token', return_value='offline-test'), patch.object(detailer, 'post_nai', side_effect=post), patch.object(generators.NovelAIGenerator, '_get_output_directory', return_value=self.root):
            combined_detailer.NAIMultiCharacterDetailer().detail(image=torch.zeros(1,48,64,3), detectors=DetectionBundle(detector),
                characterPrompts=self.pipe, prompt='ignored', negative_prompt='ignored', model='NAI Diffusion V5 Full',
                matching_mode='shared', limit_opus_free=False)
        self.assertEqual(len(captured.payloads), 1)
        self.assertEqual(captured.payloads[0]['input'], 'scene, 1.3::cafe::, girl, 2::red hair:: blue eyes')
        self.assertEqual(captured.payloads[0]['parameters']['negative_prompt'], 'bad anatomy, 1.2::hat::')

        fixture = InsetTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        prepared = fixture.prepare()['result'][0]
        fixture.response()
        source = replace(self.pipe, characters=self.pipe.characters * 10)
        inset.NAIReferenceInsetGenerate().generate(**dict(fixture.options(prepared),
            characterPrompts=source, model='NAI Diffusion V5 Curated'))
        request = fixture.post.call_args.kwargs['json']
        self.assertEqual(request['model'], 'nai-diffusion-4-5-curated-inpainting')
        self.assertEqual(request['input'], 'reference inset, scene, 1.3::cafe::')
        chars = request['parameters']['v4_prompt']['caption']['char_captions']
        self.assertEqual(len(chars), 6)
        self.assertEqual(chars[0]['centers'], [{'x':.6, 'y':.8}])
        self.assertEqual(len(source.characters), 10)

    def test_receiver_limits_and_prequeue_notice_do_not_modify_source(self):
        source = bridge.NAICharacterPipe(tuple(NS(prompt=f'person {i}', uc='hat', center={'x': .5, 'y': .5}) for i in range(22)), 'scene', 'bad')
        self.assertEqual(len(self.p.local_pipe(source).characters), 10)
        self.assertEqual(len(bridge.prepare_characters('nai-diffusion-4-5-full', source)), 6)
        self.assertEqual(len(bridge.prepare_characters('nai-diffusion-5-full', source)), 22)
        self.assertEqual(len(source.characters), 22)
        payload = {'input': 'scene', 'model': 'nai-diffusion-5-full', 'action': 'generate',
                   'parameters': {'v4_prompt': {'caption': {'base_caption': 'scene', 'char_captions': [
                       {'char_caption': c.prompt, 'centers': [c.center]} for c in source.characters]}, 'use_coords': True}}}
        path = nai_meta.autosave(self.image, self.root/'22', payload=payload)
        folders = NS(get_annotated_filepath=lambda _: str(path), get_input_directory=lambda: str(self.root),
                     get_output_directory=lambda: str(self.root), get_temp_directory=lambda: str(self.root))
        notice = sys.modules[self.package.__name__+'.metadata_notice']
        with temporary_modules({'folder_paths': folders}):
            self.assertEqual(notice.inspect_file('22.png'), {'character_count':22, 'local_count':10, 'truncated':True})

    def test_prompt_only_nai_pipe_and_nai_receiver_do_not_double_convert(self):
        source = bridge.NAICharacterPipe((NS(prompt='girl, 2::hair::, -2::hat::', uc='blur', center={'x':.3,'y':.5}),))
        incoming = self.p.local_pipe(source)
        self.assertIsNone(incoming.prompt)
        result = self.p.sampling_pipe(incoming, '2::scene::', 'bad', 'NovelAI')
        self.assertEqual(result.prompt, '(scene:2)')
        self.assertEqual((result.characters[0].prompt, result.characters[0].uc), ('girl, (hair:2)', 'blur, hat'))

    def test_local_sampling_negative_merges_once_and_keeps_per_character_uc(self):
        incoming = bridge.NAICharacterPipe((NS(prompt='girl, -2.5::hat::', uc='blur', center={'x': .5, 'y': .5}),),
                                           '2::cafe::, -3::text::', 'bad anatomy')
        pipe = self.p.local_pipe(incoming)
        normalized = self.p.sampling_pipe(pipe, 'unused', 'local defect', 'ComfyUI')
        negative = self.p.merge_negative(normalized.negative_prompt, *(c.uc for c in normalized.characters))
        self.assertEqual(negative, 'bad anatomy, text, local defect, blur, hat')
        again = self.p.sampling_pipe(normalized, 'unused', 'local defect', 'ComfyUI')
        self.assertEqual(again, normalized)
        self.assertEqual(normalized.characters[0].uc, 'blur, hat')

    def test_nai_detail_base_restores_whole_scene_and_inset_is_rejected(self):
        record = {'input': 'base scene', 'model': 'nai-diffusion-5-full', 'parameters': self.record()}
        path = nai_meta.autosave(self.image, self.root/'base', operation='detailer', extra={'base_generation_available': True, 'base_generation':record})
        with Image.open(path) as saved:
            restored = self.m.read_record(saved)
        self.assertEqual(restored['prompt'], 'base scene')
        for operation in ('detailer', 'inset'):
            path = nai_meta.autosave(self.image, self.root/operation, operation=operation)
            with Image.open(path) as saved, self.assertRaises(ValueError):
                self.m.read_record(saved)

    def test_official_alpha_metadata_and_malformed_coordinate_rejection(self):
        from test_metadata import MetadataTests
        record = self.record()
        record.pop('rs_multicharacter')
        record['prompt'] = '2::cafe::, -2::text::'
        record['v4_prompt']['caption']['base_caption'] = record['prompt']
        record['v4_prompt']['caption']['char_captions'][0]['char_caption'] = 'girl, -3::hat::'
        hidden = MetadataTests().hidden({'Comment': json.dumps(record)})
        restored = self.m.pipe_from_record(self.m.read_record(hidden))
        self.assertEqual((restored.prompt, restored.negative_prompt), ('(cafe:2)', 'bad anatomy, text'))
        self.assertEqual(restored.characters[0].uc, '\\(hat:1.2\\), hat')
        for mutate in ('automatic', 'multiple', 'mismatched', 'nan'):
            bad = copy.deepcopy(record)
            p = bad['v4_prompt']['caption']['char_captions'][0]
            n = bad['v4_negative_prompt']['caption']['char_captions'][0]
            if mutate == 'automatic': bad['v4_prompt']['use_coords'] = False
            elif mutate == 'multiple': p['centers'].append({'x':.7, 'y':.5})
            elif mutate == 'mismatched': n['centers'][0]['x'] = .9
            else: p['centers'][0]['x'] = n['centers'][0]['x'] = float('nan')
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.m.pipe_from_record(bad)

    def test_real_comfy_tokenizer_matches_reverse_inline_weights(self):
        path = os.environ.get('RS_MC_TEST_COMFYUI')
        if not path: self.skipTest('Set RS_MC_TEST_COMFYUI for real tokenizer parity')
        sys.path.insert(0, path)
        try:
            from comfy.sd1_clip import token_weights, escape_important, unescape_important
            from comfy_execution.validation import validate_node_input
            self.assertTrue(validate_node_input(bridge.PIPE_TYPE, bridge.CHARACTER_INPUT, strict=True))
            self.assertTrue(validate_node_input('LIST', bridge.CHARACTER_INPUT, strict=True))
            self.assertTrue(validate_node_input(bridge.PIPE_TYPE, bridge.PIPE_TYPE, strict=True))
            self.assertFalse(validate_node_input('NAI_CONTEXT', bridge.CHARACTER_INPUT, strict=True))
            for source in ('scene, (hair:2) tail', '(girl (red hair:2))', r'girl \(series\)', '(hair:0)', '(hair:-1.5)', '[literal]'):
                spans = token_weights(escape_important(source), 1.)
                expected_positive = ''.join(unescape_important(text) for text, weight in spans if weight > 0).strip(' ,')
                expected_negative = ''.join(unescape_important(text) for text, weight in spans if weight < 0).strip(' ,')
                positive, negative = bridge.local_prompts(bridge.comfy_to_nai(source))
                parsed = token_weights(escape_important(positive), 1.)
                self.assertEqual(''.join(unescape_important(text) for text, weight in parsed).strip(' ,'), expected_positive)
                self.assertEqual(negative, expected_negative)
                self.assertEqual([weight for text, weight in parsed if text.strip(' ,')],
                                 [weight for text, weight in spans if text.strip(' ,') and weight > 0])
        finally:
            sys.path.remove(path)

