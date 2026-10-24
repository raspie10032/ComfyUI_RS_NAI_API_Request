"""User-visible settings must match final requests; all HTTP is mocked."""
import unittest
from unittest import mock

import torch

import test_medium_nodes as generation
from ComfyUI_RS_NAI_API_Request import diagnostics, generators as g, nai_api


class RequestSummaryTests(unittest.TestCase):
    setUp = generation.MediumNodeTests.setUp
    options = generation.MediumNodeTests.options

    def assert_matches_payload(self, result):
        report, = result['ui']['rs_nai_parameters']
        payload = self.post.call_args.kwargs['json']
        self.assertEqual(report['model'], payload['model'])
        self.assertEqual(report['action'], payload['action'])
        for key in ('width', 'height', 'seed', 'steps', 'sampler', 'scale', 'cfg_rescale'):
            self.assertEqual(report[key], payload['parameters'][key])
        self.assertEqual(report['request_count'], 1)
        for key in ('image', 'mask', 'prompt', 'negative_prompt', 'token', 'loras', 'regions'):
            self.assertNotIn(key, report)
        self.assertIsNone(diagnostics._requests.get())
        return report

    def test_medium_fixed_values_and_opus_limits_appear_in_ui(self):
        args = {**self.options(), 'width': 2048, 'height': 2048, 'unique_id': 'test'}
        result = g.NovelAIGenerator().generate(**args)
        report = self.assert_matches_payload(result)
        self.assertEqual((report['width'], report['height'], report['steps']), (1024, 1024, 14))
        self.assertEqual(report['negative_mode'], 'fixed_heavy')
        self.assertEqual(report['sampler'], 'k_euler_ancestral')
        self.assertEqual(report['cfg_rescale'], 0)

    def test_inpainting_reports_fallback_model_and_used_character_count(self):
        args = {**self.options(), 'model': 'NAI Diffusion V5 Curated',
                'characterPrompts': [g.CharacterPrompt(str(i), '', .5, .5) for i in range(22)]}
        result = g.NAIInpaintNode().generate(**args, image=torch.zeros(1, 64, 64, 3),
            mask=torch.ones(1, 64, 64), strength=.4, limit_opus_free=False, unique_id='test')
        report = self.assert_matches_payload(result)
        self.assertEqual(report['model'], 'nai-diffusion-4-5-curated-inpainting')
        self.assertEqual(report['characters'], 6)
        self.assertEqual(report['inpaintImg2ImgStrength'], .4)
        self.assertNotIn('strength', report)

    def test_img2img_reports_only_its_actual_optional_parameters(self):
        result = g.NAIImg2ImgNode().generate(**self.options(), image=torch.zeros(1, 64, 64, 3),
            strength=.3, noise=.1, limit_opus_free=False, unique_id='test')
        report = self.assert_matches_payload(result)
        self.assertEqual((report['strength'], report['noise']), (.3, .1))
        self.assertNotIn('inpaintImg2ImgStrength', report)

    def test_multiple_requests_keep_last_settings_and_count_without_vibe_encoding(self):
        @diagnostics.node_notices
        class Many:
            INPUT_TYPES = classmethod(lambda cls: {})
            FUNCTION = 'run'
            def run(self):
                for seed in (7, 8):
                    parameters = nai_api.build_common_parameters(64, 64, seed, 'k_euler', 20, 5, '')
                    nai_api.post_nai('test-only', nai_api.build_nai_payload('bird', 'nai-diffusion-3', 'generate', parameters))
                nai_api.post_nai('test-only', {}, url='https://example.invalid/encode')
                return ('ok',)
        result = Many().run(unique_id='test')
        report, = result['ui']['rs_nai_parameters']
        self.assertEqual((report['request_count'], report['seed']), (2, 8))
        self.assertEqual(report['characters'], 0)
        self.assertEqual(Many().run(), ('ok',))
        self.assertIsNone(diagnostics._requests.get())

    def test_failed_request_clears_execution_state(self):
        with mock.patch.object(nai_api._session, 'post', side_effect=RuntimeError('offline failure')):
            with self.assertRaisesRegex(RuntimeError, 'offline failure'):
                g.NovelAIGenerator().generate(**self.options(), unique_id='test')
        self.assertIsNone(diagnostics._requests.get())
        self.assert_matches_payload(g.NovelAIGenerator().generate(**self.options(), unique_id='next'))
