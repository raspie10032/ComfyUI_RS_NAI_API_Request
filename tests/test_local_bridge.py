"""Offline prompt/pipe boundary checks; no API or model calls."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from test_behavior import CharacterPromptSelect
from ComfyUI_RS_NAI_API_Request import local_bridge as bridge
from ComfyUI_RS_NAI_API_Request.generation_context import ContextCharacter


class LocalBridgeTests(unittest.TestCase):
    def test_scopes_tail_and_negative_magnitude(self):
        self.assertEqual(bridge.local_prompts('2::red hair:: blue eyes, -1.5::hat::', 'bad anatomy', '(blur:1.2)'),
                         ('(red hair:2) blue eyes', 'bad anatomy, hat, (blur:1.2)'))
        for magnitude in ('-0.1', '-1.5', '-99'):
            self.assertEqual(bridge.local_prompts(f'{magnitude}::{{hat}}::'), ('', 'hat'))

    def test_legacy_emphasis_literal_parentheses_zero_and_multiple_scopes(self):
        positive, negative = bridge.local_prompts('{eyes}, [hair], 0::discard::, 2::girl:: 0.8::dress::, name (series), -2::blue, {hat}::')
        self.assertEqual(positive, '(eyes:1.05), (hair:0.952381), (girl:2) (dress:0.8), name \\(series\\)')
        self.assertEqual(negative, 'blue, hat')
        self.assertNotIn('discard', positive + negative)

    def test_existing_negative_stays_negative(self):
        self.assertEqual(bridge.local_prompts('scene', '-2::hat::, 1.3::blur::'), ('scene', '(blur:1.3), hat'))

    def test_receiving_node_clips_without_changing_original(self):
        source = bridge.NAICharacterPipe(tuple(ContextCharacter(f'person {i}, -2::hat::', 'blur', .2, .8) for i in range(22)),
                                         '2::scene::, -1.5::text::', 'bad')
        def character(prompt, uc, x, y):
            return SimpleNamespace(prompt=prompt, uc=uc, x=x, y=y)
        def pipe(characters, **kwargs):
            return SimpleNamespace(characters=characters, **kwargs)
        with patch.object(bridge, '_pipe_classes', return_value=(character, pipe)):
            result = source.as_local_character_pipe()
        self.assertEqual(len(result.characters), 10)
        self.assertEqual(len(source), 22)
        self.assertEqual(result.characters[-1].prompt, 'person 9')
        self.assertEqual(result.characters[-1].uc, 'blur, hat')
        self.assertEqual((result.characters[-1].x, result.characters[-1].y), (.2, .8))
        self.assertEqual((result.prompt, result.negative_prompt, result.syntax), ('(scene:2)', 'bad, text', 'ComfyUI'))
        self.assertIn('-2::hat::', source[0].prompt)

    def test_nai_receiver_limits_preserve_shared_pipe(self):
        source, = CharacterPromptSelect().build_character_prompt(character_count=22,
            **{f'character{i}': f'person {i}' for i in range(1, 23)},
            **{f'character{i}_enable': True for i in range(2, 23)})
        self.assertEqual(len(bridge.prepare_characters('nai-diffusion-4-5-full', source)), 6)
        self.assertEqual(len(bridge.prepare_characters('nai-diffusion-5-full', source)), 22)
        self.assertEqual(len(source), 22)
