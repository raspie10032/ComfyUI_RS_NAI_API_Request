"""Both installed source packages, no network or paid inference.

Set RS_MC_TEST_PATH=/path/to/comfyui-rs-multicharacter-sampler and
RS_MC_TEST_COMFYUI=/path/to/ComfyUI for cross-package/core checks.
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
from ComfyUI_RS_NAI_API_Request.generation_context import ContextCharacter, NAIContext, UnavailableNAIContext
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


@unittest.skipUnless(os.environ.get('RS_MC_TEST_PATH') and os.environ.get('RS_MC_TEST_COMFYUI'),
                     'Set RS_MC_TEST_PATH and RS_MC_TEST_COMFYUI for cross-package tests')
class BidirectionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        core = os.environ.get('RS_MC_TEST_COMFYUI')
        if core:
            sys.path.insert(0, core)
            cls.addClassCleanup(sys.path.remove, core)
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

    def test_camera_shared_node_is_identical_and_preserves_real_context_round_trip(self):
        from ComfyUI_RS_NAI_API_Request.camera_control import RSCameraControl
        node = RSCameraControl()
        native = self.package.NODE_CLASS_MAPPINGS['RSCameraControl']()
        for section in ('required','optional'):
            self.assertEqual(native.INPUT_TYPES()[section], node.INPUT_TYPES()[section])
        changed = node.apply(context=self.pipe, elevation=60)['result'][0]
        self.assertNotEqual(changed.characters[0].prompt, self.pipe.characters[0].prompt)
        self.assertEqual(replace(changed.characters[0],prompt=self.pipe.characters[0].prompt), self.pipe.characters[0])
        self.assertIn('(from above:',changed.characters[0].prompt)
        self.assertIn('(from above:', changed.prompt)
        incoming = bridge.NAICharacterPipe(tuple(bridge.nai_character_list(changed)), *bridge.nai_pipe_prompts('', '', changed))
        self.assertIn('::from above::', incoming.prompt)
        returned = self.p.local_pipe(incoming)
        self.assertEqual(returned.characters, changed.characters)
        self.assertEqual(returned.prompt, changed.prompt)
        # Native NAIContext is frozen too; all NAI request settings survive.
        context = NAIContext(prompt='cafe', negative_prompt='blur', model='NAI Diffusion V5 Full',
            characters=tuple(incoming.characters), sampler='k_euler_ancestral', steps=23,
            cfg_scale=6., scheduler='native', cfg_rescale=0., prefer_brownian=False, variety_boost=True,
            source_seed=7, source_action='generate', source_size=(64,48))
        updated = native.apply(context=context, azimuth=90)['result'][0]
        self.assertIsInstance(updated, NAIContext)
        self.assertIn('::viewed from the right side::',updated.prompt)
        self.assertEqual(updated.model,context.model)
        self.assertIn('::viewed from the right side::', updated.characters[0].prompt)
        self.assertEqual(replace(updated.characters[0],prompt=context.characters[0].prompt),context.characters[0])
        self.assertEqual(context.prompt,'cafe')

    def test_camera_framing_nai_snapshot_keeps_masks_parts_and_request_settings(self):
        from ComfyUI_RS_NAI_API_Request.camera_control import RSCameraControl
        region = sys.modules[self.package.__name__ + '.region_mask']
        shape=torch.zeros(1,80,120);shape[:,10:65,15:50]=1
        mask=region.prepare_mask(shape,margin=0)
        pipe=replace(self.pipe,characters=(replace(self.pipe.characters[0],region_mask=mask,
                     body_parts=(('head',mask),),body_part_strength=.2),))
        incoming=bridge.NAICharacterPipe(tuple(bridge.nai_character_list(pipe)),
                     *bridge.nai_pipe_prompts('', '', pipe),local_record_json=bridge.local_record(pipe))
        node=RSCameraControl()
        updated=node.apply(context=incoming,distance=.75,roll=20,layout_sync='distance_and_roll',canvas_aspect=1.5)['result'][0]
        restored=self.p.local_pipe(updated)
        expected=self.package.NODE_CLASS_MAPPINGS['RSCameraControl']().apply(context=pipe,distance=.75,roll=20,
                     layout_sync='distance_and_roll',canvas_aspect=1.5)['result'][0]
        self.assertEqual(restored.characters,expected.characters)
        self.assertNotEqual(restored.characters[0].region_mask,mask)
        self.assertEqual(pipe.characters[0].region_mask,mask)
        self.assertEqual(updated.characters[0].center,restored.characters[0].center)
        context=NAIContext(prompt=incoming.prompt,negative_prompt=incoming.negative_prompt,
            model='NAI Diffusion V5 Full',characters=incoming.characters,sampler='k_euler_ancestral',steps=23,
            cfg_scale=6.,scheduler='native',cfg_rescale=0.,prefer_brownian=False,variety_boost=True,
            source_seed=123,source_action='generate',source_size=(120,80),local_record_json=incoming.local_record_json)
        moved=node.apply(context=context,distance=.75,roll=20,layout_sync='distance_and_roll',canvas_aspect=1.5)['result'][0]
        self.assertEqual(moved.model,context.model)
        self.assertEqual(moved.source_seed,123)
        self.assertEqual(self.p.local_pipe(moved).characters,expected.characters)

    def test_camera_perspective_nai_snapshot_keeps_masks_parts_and_request_settings(self):
        from ComfyUI_RS_NAI_API_Request.camera_control import RSCameraControl
        region = sys.modules[self.package.__name__ + '.region_mask']
        shape=torch.zeros(1,80,120);shape[:,10:65,15:50]=1
        mask=region.prepare_mask(shape,margin=0)
        pipe=replace(self.pipe,characters=(replace(self.pipe.characters[0],region_mask=mask,
                     body_parts=(('head',mask),),body_part_strength=.2),))
        incoming=bridge.NAICharacterPipe(tuple(bridge.nai_character_list(pipe)),
                     *bridge.nai_pipe_prompts('', '', pipe),local_record_json=bridge.local_record(pipe))
        node=RSCameraControl()
        updated=node.apply(context=incoming,distance=.75,roll=20,azimuth=45,elevation=25,layout_sync='perspective',canvas_aspect=1.5)['result'][0]
        restored=self.p.local_pipe(updated)
        expected=self.package.NODE_CLASS_MAPPINGS['RSCameraControl']().apply(context=pipe,distance=.75,roll=20,
                     azimuth=45,elevation=25,layout_sync='perspective',canvas_aspect=1.5)['result'][0]
        self.assertEqual(restored.characters,expected.characters)
        self.assertNotEqual(restored.characters[0].region_mask,mask)
        self.assertEqual(pipe.characters[0].region_mask,mask)
        self.assertEqual(updated.characters[0].center,restored.characters[0].center)
        context=NAIContext(prompt=incoming.prompt,negative_prompt=incoming.negative_prompt,
            model='NAI Diffusion V5 Full',characters=incoming.characters,sampler='k_euler_ancestral',steps=23,
            cfg_scale=6.,scheduler='native',cfg_rescale=0.,prefer_brownian=False,variety_boost=True,
            source_seed=123,source_action='generate',source_size=(120,80),local_record_json=incoming.local_record_json)
        moved=node.apply(context=context,distance=.75,roll=20,azimuth=45,elevation=25,layout_sync='perspective',canvas_aspect=1.5)['result'][0]
        self.assertEqual(moved.model,context.model)
        self.assertEqual(moved.source_seed,123)
        self.assertEqual(self.p.local_pipe(moved).characters,expected.characters)

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

    def test_shared_pipe_detailer_saves_whole_scene_and_restores_local_extras(self):
        from ComfyUI_RS_NAI_API_Request import combined_detailer, detailer
        from test_detailer import PipelineTests
        ld = sys.modules[self.package.__name__ + '.detector_bundle']
        mask = np.zeros((48, 64), np.float32); mask[8:32, 8:32] = 1
        detector = NS(detect=lambda image, *a, **k: ((48, 64), [NS(
            bbox=(8, 8, 32, 32), crop_region=(0, 0, 64, 48), cropped_mask=mask)]))
        captured = NS(payloads=[])
        rich = self.rich_pipe()
        for slot in ('characterPrompts', 'nai_context'):
            for fmt in self.m.FORMATS:
                with self.subTest(slot=slot, fmt=fmt), \
                     patch.object(detailer, 'get_nai_token', return_value='offline-test'), \
                     patch.object(detailer, 'post_nai', side_effect=lambda *a, **k: PipelineTests.fake_post(captured, *a, **k)), \
                     patch.object(generators.NovelAIGenerator, '_get_output_directory', return_value=self.root):
                    combined_detailer.NAIMultiCharacterDetailer().detail(image=torch.zeros(1,48,64,3),
                        detectors=ld.DetectionBundle(detector), **{slot:rich},
                        prompt='ignored', negative_prompt='ignored', model='NAI Diffusion V5 Full',
                        matching_mode='shared', limit_opus_free=False, save_format=fmt)
                    path = max(self.root.rglob('NAI_face_*'), key=lambda p:p.stat().st_mtime_ns)
                    with Image.open(path) as image:
                        data = nai_meta.inspect_metadata(image)
                        restored = self.m.pipe_from_record(self.m.read_record(image))
                    self.assertNotIn('detailer_not_base', data['warnings'])
                    self.assertEqual(data['settings']['prompt'], 'scene, 1.3::cafe::')
                    self.assertEqual(data['record']['base_generation']['action'], 'unknown')
                    self.assertEqual(restored.characters, rich.characters)
                    self.assertEqual(restored.text_regions, rich.text_regions)
                    self.assertEqual(json.loads(restored.interaction_json)['preset'], 'delay6')
                    ctx, report = restore_context(data)
                    self.assertEqual(report['status'], 'ready', report)
                    self.assertEqual(self.p.local_pipe(ctx).characters, rich.characters)

    def test_shared_context_also_works_at_character_input_and_strict_remains_local(self):
        fixture = transport.MediumNodeTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        _, context, _ = generators.NovelAIGenerator().generate(**dict(fixture.options(),
            model='NAI Diffusion V5 Full', characterPrompts=self.rich_pipe()))
        _, updated, _ = generators.NovelAIGenerator().generate(**dict(fixture.options(),
            model='NAI Diffusion V5 Full', characterPrompts=context))
        self.assertEqual(updated.prompt, context.prompt)
        self.assertEqual(updated.characters, context.characters)
        self.assertEqual(self.p.local_pipe(updated).characters, self.rich_pipe().characters)
        fixture.post.reset_mock()
        for slot in ('nai_context', 'characterPrompts'):
            with self.subTest(slot=slot), patch.object(generators, 'get_nai_token', side_effect=AssertionError('auth')), \
                 patch.object(generators, 'pil_to_base64', side_effect=AssertionError('encoding')):
                with self.assertRaisesRegex(RuntimeError, 'image-to-image'):
                    generators.NAIImg2ImgNode().generate(**dict(fixture.options(),
                        image=torch.zeros(1,48,64,3), strength=.3, **{slot:self.rich_pipe()}, limit_opus_free=True))
        fixture.post.assert_not_called()

    def test_native_nai_syntax_in_local_text_regions_converts_once(self):
        rich = self.rich_pipe()
        rich = replace(rich, prompt='1.3::cafe::', syntax='NovelAI',
            characters=(replace(rich.characters[0], prompt='2::red hair::', uc='hat'),),
            text_regions=(replace(rich.text_regions[0], prompt='1.5::sign::', uc='-2::blur::'),))
        fixture = transport.MediumNodeTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        _, context, _ = generators.NovelAIGenerator().generate(**dict(fixture.options(),
            model='NAI Diffusion V5 Full', characterPrompts=rich))
        expected = self.p.local_pipe(context)
        self.assertEqual(expected.text_regions[0].prompt, '(sign:1.5)')
        for fmt in self.m.FORMATS:
            path = nai_meta.autosave(self.image, self.root/fmt, payload=fixture.post.call_args.kwargs['json'],
                extra=bridge.context_extra(context), save_format=fmt)
            with Image.open(path) as image:
                local = self.m.pipe_from_record(self.m.read_record(image))
            self.assertEqual(local.text_regions, expected.text_regions)

    def test_nai_pipe_enters_lora_position_and_finalize_without_prompt_reentry(self):
        builder = sys.modules[self.package.__name__ + '.character_builder']
        original = bridge.pipe_from_context(NAIContext('1.3::cafe::', 'blur',
            'NAI Diffusion V5 Full', 'k_euler', 23, 5., 'karras', 0., False, False,
            (ContextCharacter('2::red hair::', 'hat', .25,.5),
             ContextCharacter('blue hair', 'glasses', .75,.5)), 7, 'generate', (64,64)))
        # Every builder also accepts a finished pipe/context at its input.
        for node in (builder.RSMultiCharacterLoRA, builder.RSMultiCharacterPosition,
                     builder.RSMultiCharacterFinalize):
            self.assertIn('NAI_CONTEXT', node.INPUT_TYPES().get('optional', node.INPUT_TYPES()['required'])['building_pipe'][0])
        no_edit, = builder.RSMultiCharacterFinalize().build(original)
        self.assertEqual(no_edit.characters[0].prompt, '(red hair:2)')
        self.assertEqual(no_edit.characters[0].uc, 'hat')
        self.assertEqual(no_edit.prompt, '(cafe:1.3)')
        staged, = builder.RSMultiCharacterLoRA().apply(2, building_pipe=original,
            character1_lora='one.safetensors', character2_lora='two.safetensors')
        staged, = builder.RSMultiCharacterPosition().apply(2, building_pipe=staged,
            character1_x=.3, character1_y=.5, character2_x=.7, character2_y=.5)
        edited, = builder.RSMultiCharacterFinalize().build(staged)
        self.assertEqual([c.lora_name for c in edited.characters], ['one.safetensors', 'two.safetensors'])
        self.assertEqual([c.uc for c in edited.characters], ['hat', 'glasses'])
        self.assertEqual([c.x for c in edited.characters], [.3, .7])
        self.assertEqual(json.loads(edited.nai_settings_json)['settings']['steps'], 23)
        self.assertEqual(original[0].x, .25)
        resolved = self.p.local_pipe(bridge.NAICharacterPipe(edited.characters, edited.prompt, edited.negative_prompt,
            local_record_json=bridge.local_record(edited), syntax='ComfyUI'))
        self.assertEqual(resolved.characters, edited.characters)

    def test_rich_finished_pipe_can_reenter_finalize_without_losing_settings(self):
        builder = sys.modules[self.package.__name__ + '.character_builder']
        original = self.rich_pipe()
        rebuilt, = builder.RSMultiCharacterFinalize().build(original)
        self.assertEqual(rebuilt, original)
        self.assertEqual(rebuilt.characters[0].uc, original.characters[0].uc)
        self.assertEqual(rebuilt.text_regions, original.text_regions)

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

    def rich_pipe(self):
        masks = sys.modules[self.package.__name__ + '.region_mask']
        mask = masks.prepare_mask(torch.ones(1, 16, 16), margin=0)
        char = replace(self.pipe.characters[0], bbox=(0., .6, .4, 1.),
                       region_mask=mask, body_parts=(("head", mask),), body_part_strength=.12,
                       lora_name="example.safetensors", lora_strength=.7, lora_clip_strength=.8)
        text = self.c.TextRegion("sign", "", .7, .3, (.5, .1, .9, .5), "HELLO")
        return replace(self.pipe, characters=(char,), text_regions=(text,),
            interaction_json=json.dumps({"preset":"delay6", "delay_steps":0,"decrement":.1}),
            lora_application_mode="normal")

    def test_full_context_round_trip_keeps_masks_parts_lora_text_and_both_settings(self):
        from ComfyUI_RS_NAI_API_Request.generation_context import inherit_context, NAIContext
        fixture = transport.MediumNodeTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        rich = replace(self.rich_pipe(), generation_json=json.dumps(self.record()['rs_multicharacter']))
        args = dict(fixture.options(), model="NAI Diffusion V5 Full", nai_context=rich)
        _, context, output = generators.NovelAIGenerator().generate(**args)
        self.assertIsInstance(context, NAIContext)
        self.assertEqual(context.model, "NAI Diffusion V5 Full")
        for value in (context, output):
            local = self.p.local_pipe(value)
            self.assertEqual(local.characters, rich.characters)
            self.assertEqual(local.text_regions, rich.text_regions)
            self.assertEqual(json.loads(local.interaction_json)['preset'], 'delay6')
            self.assertEqual(local.lora_application_mode, "normal")
            self.assertEqual(json.loads(local.generation_json)['settings']['sampler_name'], 'euler')
            settings = inherit_context(local, True, manual={**fixture.options(), 'model':'NAI Diffusion V4.5 Full',
                'scheduler': 'karras', 'prefer_brownian':False, 'variety_boost':True})
            self.assertEqual(settings['model'], 'NAI Diffusion V5 Full')
            self.assertEqual(settings['prompt'], 'scene, 1.3::cafe::')
        request = fixture.post.call_args.kwargs['json']
        self.assertNotIn('rs_multicharacter', request['parameters'])
        self.assertNotIn('lora_name', request['parameters'])
        self.assertNotIn('rs_context', request)
        self.assertIsNone(rich.nai_settings_json)

    def test_cross_context_saved_files_restore_all_extras_and_effective_nai_settings(self):
        from ComfyUI_RS_NAI_API_Request.generation_context import NAIContext
        fixture = transport.MediumNodeTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        rich = self.rich_pipe()
        for fmt in self.m.FORMATS:
            args = dict(fixture.options(), model="NAI Diffusion V5 Full", characterPrompts=rich,
                        save_format=fmt)
            _, context, _ = generators.NovelAIGenerator().generate(**args)
            path = nai_meta.autosave(self.image, self.root/fmt, payload=fixture.post.call_args.kwargs['json'],
                extra=bridge.context_extra(context), save_format=fmt)
            with Image.open(path) as image:
                local = self.m.pipe_from_record(self.m.read_record(image))
                data = nai_meta.inspect_metadata(image)
            for restored in (local, self.p.local_pipe(bridge.pipe_from_metadata(data))):
                self.assertEqual(restored.characters, rich.characters)
                self.assertEqual(restored.text_regions, rich.text_regions)
                self.assertEqual(json.loads(restored.interaction_json)['preset'], 'delay6')
                self.assertEqual(json.loads(restored.nai_settings_json)['settings']['model'], 'NAI Diffusion V5 Full')
            restored_context, _ = restore_context(data)
            self.assertIsInstance(restored_context, NAIContext)
            self.assertEqual(self.p.local_pipe(restored_context).characters, rich.characters)
            # Generate/save locally after importing NAI; NAI reload must use its
            # own sampler/model snapshot while taking current scene captions.
            local = replace(local, prompt="new common prompt")
            local_path = self.m.save_image(self.image, self.root/(fmt+'-local'), self.record(local), fmt)
            with Image.open(local_path) as image:
                data = nai_meta.inspect_metadata(image)
            restored_context, report = restore_context(data)
            self.assertIsInstance(restored_context, NAIContext, report)
            self.assertEqual(restored_context.model, 'NAI Diffusion V5 Full')
            self.assertEqual(restored_context.prompt, 'new common prompt')

    def test_detector_and_tagger_loaders_have_shared_inputs_and_cross_bundle(self):
        from ComfyUI_RS_NAI_API_Request import detector_bundle as nd, wd_tagger as nt
        ld = sys.modules[self.package.__name__+'.detector_bundle']
        lt = sys.modules[self.package.__name__+'.wd_tagger']
        for left, right in ((ld.RSMultiCharacterDetectionLoader, nd.NAIDetectionCombineLoader),
                            (lt.RSMultiCharacterTaggerLoader, nt.WDTaggerLoader)):
            for group in ('required', 'optional'):
                self.assertEqual(left.INPUT_TYPES().get(group), right.INPUT_TYPES().get(group))
        detector = NS(detect=lambda *args, **kwargs: (None, []))
        for bundle in (ld.DetectionBundle(detector), nd.DetectionBundle(detector)):
            self.assertIs(nd.detection_bundle(bundle).segm_detector, detector)
            self.assertIs(ld.detection_bundle(bundle).segm_detector, detector)
        from comfy_execution.validation import validate_node_input
        for name, node in self.package.NODE_CLASS_MAPPINGS.items():
            if name == 'RSMultiCharacterLoadImage':
                continue  # Delegates to the core LoadImage, with no pipe input.
            for group in node.INPUT_TYPES().values():
                if isinstance(group, dict) and 'character_pipe' in group:
                    self.assertTrue(validate_node_input('NAI_CONTEXT', group['character_pipe'][0], strict=True))

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
            self.assertTrue(validate_node_input('NAI_CONTEXT', bridge.CHARACTER_INPUT, strict=True))
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

