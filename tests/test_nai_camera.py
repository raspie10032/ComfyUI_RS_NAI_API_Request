"""NAI-menu camera works without the local extension; transport is mocked."""
import copy
import inspect
import math
from dataclasses import replace
import unittest
from unittest.mock import patch

import test_generation_context as contexts
from ComfyUI_RS_NAI_API_Request import NODE_CLASS_MAPPINGS, generators
from ComfyUI_RS_NAI_API_Request.camera_control import NAICameraControl, RSCameraControl, random_camera
from ComfyUI_RS_NAI_API_Request.camera_layout import framing, perspective_framing, project
from ComfyUI_RS_NAI_API_Request.camera_prompt import _VIEWS, nearest_view, view_direction
from ComfyUI_RS_NAI_API_Request.camera_tags import iter_prompt_tags


class NAICameraTests(unittest.TestCase):
    setUp = contexts.ContextTests.setUp
    source = contexts.ContextTests.source
    i2i = contexts.ContextTests.i2i

    def test_registered_entry_preserves_shared_engine_and_defaults(self):
        self.assertIs(NODE_CLASS_MAPPINGS['NAICameraControl'], NAICameraControl)
        self.assertIs(inspect.unwrap(NAICameraControl.apply), inspect.unwrap(RSCameraControl.apply))
        fields = NAICameraControl.INPUT_TYPES()
        self.assertEqual(fields['required']['prompt_syntax'][0][0], 'NovelAI')
        self.assertEqual(RSCameraControl.INPUT_TYPES()['required']['prompt_syntax'][0][0], 'ComfyUI')
        self.assertEqual(NAICameraControl.RETURN_TYPES, RSCameraControl.RETURN_TYPES)
        self.assertEqual(NAICameraControl.CATEGORY, 'RS_NovelAI_API/Camera')

    def test_native_nai_context_perspective_without_local_extension(self):
        _, source, _ = self.source()
        before = copy.deepcopy(source)
        with patch.dict('sys.modules', {'nodes': None}):
            result = NAICameraControl().apply(context=source, azimuth=45, elevation=25,
                distance=.65, roll=12, canvas_aspect=1216/832, layout_sync='perspective')
        changed = result['result'][0]
        transform = perspective_framing(.65, 12, 1216/832, 45, 25)
        self.assertIs(type(changed), type(source))
        self.assertIn('::from above::', changed.prompt)
        self.assertEqual(len(result['ui']['camera_regions'][0]), len(source.characters))
        for original, current in zip(source.characters, changed.characters):
            x, y = project(original.x, original.y, transform)
            self.assertAlmostEqual(current.x, x)
            self.assertAlmostEqual(current.y, y)
            self.assertEqual(current.uc, original.uc)
        self.assertEqual(source, before)
        self.assertEqual(replace(changed, prompt=source.prompt, characters=source.characters), source)

    def test_before_first_generation_sends_nai_weights_and_coordinates(self):
        source = generators.CharacterPromptSelect().build_character_prompt(character_count=2,
            character1='brown hair, 1.4::front view, red coat::, {smile}, -1::blue eyes::',
            character2_enable=True, character2='pink hair, headshot, front view',
            character1_x=.3, character1_y=.5, character2_x=.7, character2_y=.5)[0]
        with patch.dict('sys.modules', {'nodes': None}):
            edited = NAICameraControl().apply(context=source,
                base_prompt='two adult women, garden, medium shot, 1.2::coat:: with buttons, front view',
                azimuth=180, roll=10, layout_sync='distance_and_roll')['result'][0]
            args = dict(self.transport.options(), model='NAI Diffusion V5 Full',
                        nai_context=edited, characterPrompts=None, seed=567, limit_opus_free=True)
            _, output, _ = generators.NovelAIGenerator().generate(**args)
        payload = self.transport.post.call_args.kwargs['json']
        self.assertEqual(payload['input'], edited.prompt)
        params = payload['parameters']
        self.assertEqual(params['v4_prompt']['caption']['base_caption'], edited.prompt)
        self.assertIn('1.2::coat:: with buttons', payload['input'])
        self.assertIn('upper back', payload['input'])
        self.assertNotIn('front view', payload['input'])
        self.assertTrue(params['v4_prompt']['use_coords'])
        for sent, expected in zip(params['v4_prompt']['caption']['char_captions'], edited.characters):
            self.assertEqual(sent['char_caption'], expected.prompt)
            self.assertEqual(sent['centers'][0], expected.center)
        first, second = params['v4_prompt']['caption']['char_captions']
        tags = dict(iter_prompt_tags(first['char_caption'], 'NovelAI'))
        self.assertEqual(tags['red coat'], 1.4)
        self.assertEqual(tags['blue eyes'], -1)
        self.assertNotIn('front view', tags)
        self.assertNotIn('smile', tags)
        self.assertIn('back of head', second['char_caption'])
        self.assertNotIn('medium shot', second['char_caption'])
        self.assertEqual(output.source_seed, 567)
        self.assertEqual(output.characters[0].x, edited.characters[0].x)
        self.assertEqual(len(output.characters), 2)

    def test_42_view_geometry_and_framing_in_prompt_only_mode(self):
        node = NAICameraControl()
        base = 'front view, from behind, from left, from right, from above, from below, black coat'
        for view in _VIEWS:
            x, y, z = view[0]
            azimuth = math.degrees(math.atan2(x, z))
            elevation = math.degrees(math.asin(y))
            yaw, side, pitch = view_direction(view)
            self.assertEqual(nearest_view(azimuth, elevation), view)
            for frame, cue in (
                ('headshot', 'back of head' if yaw in ('rear', 'rear quarter') else
                 'top of head' if pitch == 'overhead' else None),
                ('medium shot', 'upper back' if yaw in ('rear', 'rear quarter') else
                 'foreshortened body outline' if pitch == 'underneath' else None),
                ('feet focus', None),
            ):
                with self.subTest(azimuth=azimuth, elevation=elevation, frame=frame):
                    options = dict(base_prompt=f'{base}, {frame}', prompt_syntax='NovelAI',
                                   azimuth=azimuth, elevation=elevation)
                    _, prompt, caption = node.apply(**options)['result']
                    self.assertIn('black coat', prompt)
                    if side != 'left':
                        self.assertNotIn(', from left', prompt)
                    if side != 'right':
                        self.assertNotIn(', from right', prompt)
                    if yaw != 'front':
                        self.assertNotIn(', front view', prompt)
                    if cue:
                        self.assertIn(cue, caption)
                    if frame == 'feet focus':
                        self.assertNotIn('medium shot', caption)
                    _, off, _ = node.apply(**options, visible_details=False)['result']
                    self.assertIn(frame, off)
                    if cue:
                        self.assertNotIn(cue, off)

    def test_scope_and_unclosed_or_legacy_weights(self):
        _, source, _ = self.source()
        base = '“front view, smile”, [front view, silk], {{front view::, wool, +1.3::front view, black coat'
        edited, prompt, _ = NAICameraControl().apply(context=source, base_prompt=base,
            azimuth=180, scope='scene_only', weighting='plain')['result']
        self.assertIs(edited.characters, source.characters)
        self.assertIn('“front view, smile”', prompt)
        self.assertEqual(prompt.count('front view'), 1)
        tags = dict(iter_prompt_tags(prompt, 'NovelAI'))
        self.assertEqual(tags['upper back'], 1)
        self.assertAlmostEqual(tags['silk'], 1/1.05)
        self.assertEqual(tags['wool'], 1)
        self.assertEqual(tags['black coat'], 1.3)

    def test_random_manual_equivalence_and_i2i_forwarding(self):
        image, source, _ = self.source()
        node = NAICameraControl()
        sampled = random_camera('balanced', 5678)
        with patch.dict('sys.modules', {'nodes': None}):
            randomized = node.apply(context=source, random_mode='balanced', random_seed=5678,
                                    layout_sync='distance_and_roll')
            manual = node.apply(context=source, layout_sync='distance_and_roll', **sampled)
            self.assertEqual(randomized, manual)
            edited = randomized['result'][0]
            _, output, _ = self.i2i(image, edited)
        self.assertEqual(output.characters, edited.characters)
        self.assertEqual(output.prompt, edited.prompt)
        self.assertEqual(output.source_seed, 456)
        self.assertEqual(output.source_action, 'img2img')

    def test_disabled_preserves_context_and_camera_makes_no_request(self):
        _, source, _ = self.source()
        self.transport.post.reset_mock()
        for settings in ({'enabled': False}, {'strength': 0}):
            output = NAICameraControl().apply(context=source, layout_sync='perspective', **settings)
            self.assertIs(output['result'][0], source)
        self.transport.post.assert_not_called()

    def test_downstream_strict_guard_still_blocks_paid_i2i(self):
        image, source, _ = self.source()
        edited = NAICameraControl().apply(context=source, elevation=25)['result'][0]
        self.transport.post.reset_mock()
        with self.assertRaisesRegex(RuntimeError, '(?i)free|anlas'):
            self.i2i(image, edited, limit_opus_free=True)
        self.transport.post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
