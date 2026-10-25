"""NAI-menu camera works without the local extension; transport is mocked."""
import copy
import inspect
from dataclasses import replace
import unittest
from unittest.mock import patch

import test_generation_context as contexts
from ComfyUI_RS_NAI_API_Request import NODE_CLASS_MAPPINGS, generators
from ComfyUI_RS_NAI_API_Request.camera_control import NAICameraControl, RSCameraControl, random_camera
from ComfyUI_RS_NAI_API_Request.camera_layout import framing, perspective_framing, project


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
            character1='brown hair', character2_enable=True, character2='pink hair',
            character1_x=.3, character2_x=.7)[0]
        with patch.dict('sys.modules', {'nodes': None}):
            edited = NAICameraControl().apply(context=source, base_prompt='two adult women, garden',
                distance=.7, roll=10, layout_sync='distance_and_roll')['result'][0]
            args = dict(self.transport.options(), model='NAI Diffusion V5 Full',
                        nai_context=edited, characterPrompts=None, seed=567, limit_opus_free=True)
            _, output, _ = generators.NovelAIGenerator().generate(**args)
        payload = self.transport.post.call_args.kwargs['json']
        self.assertEqual(payload['input'], edited.prompt)
        params = payload['parameters']
        self.assertTrue(params['v4_prompt']['use_coords'])
        for sent, expected in zip(params['v4_prompt']['caption']['char_captions'], edited.characters):
            self.assertEqual(sent['char_caption'], expected.prompt)
            self.assertEqual(sent['centers'][0], expected.center)
        self.assertEqual(output.source_seed, 567)
        self.assertEqual(output.characters[0].x, edited.characters[0].x)
        self.assertEqual(len(output.characters), 2)

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
