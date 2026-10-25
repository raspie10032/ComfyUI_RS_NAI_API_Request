# SPDX-License-Identifier: GPL-3.0-only
"""The camera node is importable without ComfyUI or a GPU."""
from dataclasses import dataclass, field
import importlib.util
import math
import sys
import types
from pathlib import Path
import unittest

parent = types.ModuleType("_rs_camera_unit")
parent.__path__ = [str(Path(__file__).resolve().parents[1])]
sys.modules[parent.__name__] = parent
spec = importlib.util.spec_from_file_location("_rs_camera_unit.camera_control", Path(__file__).resolve().parents[1]/"camera_control.py")
camera = importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera)


@dataclass(frozen=True)
class Caption:
    prompt: str
    uc: str = "unchanged UC"
    x: float = .28
    y: float = .5
    lora_name: str = "test.safetensors"


@dataclass(frozen=True)
class SharedContext:
    prompt: str | None = "cafe, two adult women"
    syntax: str = "ComfyUI"
    characters: tuple = (Caption("brown hair"), Caption("pink hair", x=.72))
    character_syntax: str | None = None
    text_regions: tuple = (Caption("a sign"),)
    negative_prompt: str = "blur"
    generation_json: str = '{"steps":30,"scheduler":"sgm_uniform"}'
    local_record_json: str = '{"character_masks":[1,2]}'
    model: str = "V5 Full"
    source_seed: int = 999
    settings: dict = field(default_factory=lambda: {"lora":"RSCV5"})


class CameraTests(unittest.TestCase):
    def test_random_reproducible_and_respects_ranges(self):
        for mode, bounds in camera.RANDOM_RANGES.items():
            for seed in range(1000):
                view = camera.random_camera(mode, seed)
                self.assertEqual(view, camera.random_camera(mode, seed))
                for value, (low, high) in zip(view.values(), bounds):
                    self.assertTrue(low <= value < high)
                self.assertTrue(camera.camera_weights(**view))
            self.assertNotEqual(camera.random_camera(mode, 100), camera.random_camera(mode, 101))
        for seed in (-1, 2**32, 1.5, True, '4', float('nan')):
            with self.assertRaisesRegex(ValueError, '시드'):
                camera.random_camera('balanced', seed)

    def test_random_matches_manual_and_preserves_image_seed(self):
        node = camera.RSCameraControl()
        for syntax in ('ComfyUI', 'NovelAI'):
            source = SharedContext(syntax=syntax)
            for mode in ('balanced', 'full'):
                for seed in (0, 12345, 0xffffffff):
                    view = camera.random_camera(mode, seed)
                    manual = node.apply(context=source, **view)
                    randomized = node.apply(context=source, random_mode=mode, random_seed=seed)
                    self.assertEqual(manual, randomized)
                    self.assertEqual(randomized['result'][0].source_seed, source.source_seed)
                    self.assertEqual(randomized['ui']['camera_values'][0], view)
        for mode in ('balanced', 'full'):
            self.assertIs(node.apply(context=source, enabled=False, random_mode=mode)['result'][0], source)
            self.assertIs(node.apply(context=source, strength=0, random_mode=mode)['result'][0], source)
        self.assertEqual(node.apply(), node.apply(random_mode='off', random_seed=1234))
        with self.assertRaisesRegex(ValueError, '랜덤'):
            node.apply(random_mode='invalid')

    def test_continuous_weights_and_no_hidden_gain_at_knots(self):
        for field, knots in (("azimuth",[-180,-90,0,90,180]), ("elevation",[-90,-60,0,60,90]), ("distance",[0,.25,.5,.75,1])):
            low, high = {"azimuth":(-180,180), "elevation":(-90,90), "distance":(0,1)}[field]
            for point in knots:
                left=camera.camera_weights(**{field:max(low,point-1e-5)})
                right=camera.camera_weights(**{field:min(high,point+1e-5)})
                self.assertLess(max(abs(left.get(k,0)-right.get(k,0)) for k in left.keys()|right.keys()), .0001)
        self.assertEqual(camera.camera_weights(azimuth=-180), camera.camera_weights(azimuth=180))
        self.assertEqual(camera.camera_weights(elevation=90),camera.camera_weights(azimuth=90,elevation=90))

    def test_linear_strength_and_distance_conservation(self):
        for distance in [i/1000 for i in range(1001)]:
            weights=camera.camera_weights(distance=distance)
            self.assertAlmostEqual(sum(weights.get(t,0) for t in camera.DISTANCE_TAGS),1.2)
            self.assertTrue(all(math.isfinite(v) and v>=0 for v in weights.values()))
        low=camera.camera_weights(30,20,.4,10,.8)
        high=camera.camera_weights(30,20,.4,10,1.6)
        for tag in low: self.assertAlmostEqual(high[tag],low[tag]*2)

    def test_native_and_nai_context_are_immutable_and_keep_extras(self):
        for syntax in ("ComfyUI","NovelAI"):
            source=SharedContext(syntax=syntax)
            result=camera.RSCameraControl().apply(context=source,elevation=60)
            updated,prompt,caption=result['result']
            self.assertNotEqual(source.prompt,updated.prompt)
            self.assertTrue(prompt.startswith(source.prompt))
            for name in ('text_regions','negative_prompt','generation_json','local_record_json','model','source_seed','settings'):
                self.assertEqual(getattr(source,name),getattr(updated,name))
            for original, changed in zip(source.characters,updated.characters):
                self.assertTrue(changed.prompt.startswith(original.prompt+", "))
                for name in ('uc','x','y','lora_name'):
                    self.assertEqual(getattr(original,name),getattr(changed,name))
            self.assertIn('::from above::' if syntax=='NovelAI' else '(from above:',caption)
            self.assertNotIn('::' if syntax=='ComfyUI' else '(from',caption)

    def test_common_only_and_mixed_character_syntax(self):
        source=SharedContext(character_syntax="NovelAI")
        common=camera.RSCameraControl().apply(context=source,scope="scene_only")['result'][0]
        self.assertEqual(common.characters,source.characters)
        both=camera.RSCameraControl().apply(context=source)['result'][0]
        self.assertIn('(from front:',both.prompt)
        self.assertIn('::from front::',both.characters[0].prompt)
        self.assertEqual(source.characters[0].prompt,'brown hair')

    def test_no_scene_does_not_silently_replace_sampler_caption(self):
        pipe=SharedContext(prompt=None)
        with self.assertRaisesRegex(ValueError,'base_prompt'):
            camera.RSCameraControl().apply(context=pipe)
        output,prompt,_=camera.RSCameraControl().apply(context=pipe,base_prompt='new scene')['result']
        self.assertTrue(prompt.startswith('new scene'))
        self.assertIsNone(pipe.prompt)
        self.assertIs(camera.RSCameraControl().apply(context=pipe,enabled=False)['result'][0],pipe)
        self.assertIs(camera.RSCameraControl().apply(context=pipe,strength=0)['result'][0],pipe)

    def test_off_zero_and_string_only_paths(self):
        pipe=SharedContext()
        for settings in ({'enabled':False},{'strength':0}):
            out,caption,tags=camera.RSCameraControl().apply(context=pipe,**settings)['result']
            self.assertIs(out,pipe);self.assertEqual(caption,pipe.prompt);self.assertEqual(tags,'')
        out,prompt,tags=camera.RSCameraControl().apply(base_prompt='hello',weighting='plain')['result']
        self.assertIsNone(out);self.assertTrue(prompt.startswith('hello'));self.assertNotIn(':',tags)
        self.assertIn('::',camera.RSCameraControl().apply(prompt_syntax='NovelAI')['result'][2])

    def test_plain_axes_are_independent_across_eight_views_and_elevations(self):
        for distance in (0., .1, .25, .4, .5, .65, .75, .9, 1.):
            expected = None
            for angle in (-180, -135, -90, -45, 0, 45, 90, 135, 180):
                for elevation in (-90, -60, -25, 0, 25, 60, 90):
                    for roll in (0, 2, 45):
                        for syntax in ('ComfyUI', 'NovelAI'):
                            caption = camera.camera_caption(camera.camera_weights(angle, elevation, distance, roll), syntax, 'plain')
                            distance_tags = set(caption.split(', ')) & set(camera.DISTANCE_TAGS)
                            if expected is None:
                                expected = distance_tags
                            self.assertEqual(distance_tags, expected)
            self.assertTrue(expected)
        for angle, direction in ((0, 'from front'), (90, 'viewed from the right side'), (180, 'from behind')):
            caption = camera.camera_caption(camera.camera_weights(angle, 0, .65), weighting='plain')
            self.assertIn(direction, caption)
            self.assertIn('medium shot', caption)
            self.assertIn('full body', caption)
        self.assertEqual(camera.camera_caption(camera.camera_weights(strength=0), weighting='plain'), '')

    def test_plain_direction_is_independent_of_distance_and_roll(self):
        for angle in (-180, -135, -90, -45, 0, 45, 90, 135, 180):
            expected = None
            for distance in (0., .1, .25, .4, .65, .9, 1.):
                for roll in (0, 2, 45):
                    caption = camera.camera_caption(camera.camera_weights(angle, 0, distance, roll), weighting='plain')
                    tags = set(caption.split(', ')) - set(camera.DISTANCE_TAGS) - {'dutch angle'}
                    if expected is None:
                        expected = tags
                    self.assertEqual(tags, expected)
            self.assertTrue(expected)

    def test_bad_inputs_show_readable_errors(self):
        for field in ('azimuth','elevation','distance','roll','strength'):
            for value in (float('nan'),float('inf'),True,'oops'):
                with self.assertRaisesRegex(ValueError,'카메라'):
                    camera.camera_weights(**{field:value})
        with self.assertRaisesRegex(ValueError,'최종'):
            camera.RSCameraControl().apply(context=object())
        with self.assertRaisesRegex(ValueError,'문자열'):
            camera.RSCameraControl().apply(base_prompt=12)


if __name__=='__main__': unittest.main()
