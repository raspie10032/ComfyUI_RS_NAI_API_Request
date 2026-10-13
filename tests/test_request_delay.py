"""Node inputs through the real pacing boundary, without NovelAI traffic."""
from contextlib import contextmanager
from types import SimpleNamespace
import sys
import unittest
from unittest import mock

import torch

import test_medium_nodes as medium_fixtures
from test_medium_nodes import response
import test_inset_assets as inset_fixtures
import test_detailer as detail_fixtures
from ComfyUI_RS_NAI_API_Request import NODE_CLASS_MAPPINGS, detailer, generators, nai_api, request_delay
from ComfyUI_RS_NAI_API_Request.inset import NAIReferenceInsetGenerate


@contextmanager
def clock():
    now = [100.0]
    def sleep(seconds):
        now[0] += seconds
    with mock.patch.object(request_delay.time, "monotonic", side_effect=lambda: now[0]), \
         mock.patch.object(request_delay.time, "sleep", side_effect=sleep):
        yield now


class RequestDelayTests(unittest.TestCase):
    def setUp(self):
        self.fixture = medium_fixtures.MediumNodeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_all_image_generators_delay_each_request_without_payload_pollution(self):
        image = torch.zeros((1, 64, 64, 3))
        for cls, extra in ((generators.NovelAIGenerator, {}),
                           (generators.NAIImg2ImgNode, {"image": image, "strength": .5}),
                           (generators.NAIInpaintNode, {"image": image, "mask": torch.ones(1,64,64), "strength": .5})):
            with self.subTest(node=cls.__name__), clock() as now:
                starts = []
                def send(*args, **kwargs):
                    starts.append(now[0])
                    self.assertNotIn("request_delay_seconds", kwargs["json"]["parameters"])
                    now[0] += 1
                    return self.fixture.post.return_value
                self.fixture.post.side_effect = send
                nai_api._next_request_at = 102  # Overlaps the 5s delay; does not add 2s.
                for _ in range(2):
                    cls().generate(**self.fixture.options(), **extra, limit_opus_free=False,
                                   request_delay_seconds=5)
                self.assertEqual(starts, [105, 111])
                self.assertIsNone(request_delay.current_timer.get())

    def test_invalid_input_and_strict_protection_fail_before_wait_or_http(self):
        with mock.patch.object(request_delay.RequestTimer, "wait") as wait:
            for value in (-1, float("nan"), float("inf"), True, "5"):
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "REQUEST_DELAY"):
                    generators.NovelAIGenerator().generate(**self.fixture.options(), request_delay_seconds=value)
            with self.assertRaises(RuntimeError):
                generators.NAIImg2ImgNode().generate(**self.fixture.options(), image=torch.zeros(1,64,64,3),
                                                     strength=.5, request_delay_seconds=30, limit_opus_free=True)
            wait.assert_not_called()
            self.fixture.get.assert_not_called()
            self.fixture.post.assert_not_called()
        self.assertIsNone(request_delay.current_timer.get())

    def test_cancellation_clears_countdown_and_releases_lock_without_sending(self):
        server = mock.Mock(client_id="test-browser")
        with clock(), mock.patch.dict(sys.modules, {"server": SimpleNamespace(PromptServer=SimpleNamespace(instance=server))}), \
             mock.patch.object(request_delay, "check_interrupted", side_effect=[None, None, RuntimeError("cancelled")]):
            with self.assertRaisesRegex(RuntimeError, "cancelled"):
                generators.NovelAIGenerator().generate(**self.fixture.options(), request_delay_seconds=30, unique_id="42")
        self.fixture.post.assert_not_called()
        self.fixture.get.assert_not_called()
        self.assertFalse(nai_api._request_lock.locked())
        self.assertIsNone(request_delay.current_timer.get())
        self.assertEqual(server.send_sync.call_args_list[0].args, ("rs_nai_request_wait", {"node":"42", "remaining":30, "retry":False}, "test-browser"))
        self.assertEqual(server.send_sync.call_args.args[1]["remaining"], 0)

    def test_retry_waits_for_the_longer_of_server_deadline_and_user_delay(self):
        for retry_after, expected in ((7, 112), (1, 110)):
            with self.subTest(retry_after=retry_after), clock() as now:
                nai_api._next_request_at = 0
                starts = []
                def send(*args, **kwargs):
                    starts.append(now[0])
                    if len(starts) == 1:
                        res = response(b"limited", 429)
                        res.headers["Retry-After"] = str(retry_after)
                        return res
                    return self.fixture.post.return_value
                self.fixture.post.side_effect = send
                generators.NovelAIGenerator().generate(**self.fixture.options(), limit_opus_free=False, request_delay_seconds=5)
            self.assertEqual(starts, [105, expected])

    def test_old_workflow_omitting_delay_keeps_existing_wait(self):
        with mock.patch.object(request_delay.RequestTimer, "wait") as wait:
            generators.NovelAIGenerator().generate(**self.fixture.options())
        wait.assert_not_called()
        self.fixture.post.assert_called_once()

    def test_uncached_vibe_encoding_uses_same_node_timer(self):
        from ComfyUI_RS_NAI_API_Request.references import NAIVibeTransfer
        vibes = NAIVibeTransfer().build(torch.zeros(1,64,64,3))[0]
        options = self.fixture.options()
        options["model"] = "NAI Diffusion V4.5 Full"
        import tempfile
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(sys.modules, {"folder_paths": SimpleNamespace(models_dir=folder)}), clock() as now:
            calls = []
            def send(url, **kwargs):
                calls.append((url, now[0]))
                return response(b"encoded") if "encode-vibe" in url else self.fixture.post.return_value
            self.fixture.post.side_effect = send
            generators.NovelAIGenerator().generate(**options, vibes=vibes, limit_opus_free=False, request_delay_seconds=5)
        self.assertEqual([t for _, t in calls], [105, 110])
        self.assertIn("encode-vibe", calls[0][0])


class DetailDelayTests(unittest.TestCase):
    def test_both_detailers_delay_each_sent_region_but_preview_and_empty_do_not_wait(self):
        fixture = detail_fixtures.PipelineTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        masks = torch.zeros(2,64,128)
        masks[0,10:30,10:30] = 1
        masks[1,10:30,80:100] = 1
        for name in ("NAIFaceDetailerNode", "NAIFaceDetailerSegmNode"):
            cls = NODE_CLASS_MAPPINGS[name]
            schema = cls.INPUT_TYPES()
            options = {k:v[1]["default"] for group in ("required","optional") for k,v in schema[group].items()
                       if len(v)>1 and "default" in v[1]}
            options.update(image=fixture.image, sam_model=None, segm_detector=None, bbox_detector=None,
                           detail_mask=masks, mask_source="external_mask", matching_mode="shared",
                           detail_mode="all", limit_opus_free=False, request_delay_seconds=3)
            with self.subTest(node=name), clock() as now, mock.patch.object(nai_api, "_next_request_at", 0), \
                 mock.patch.object(detailer, "post_nai", nai_api.post_nai), mock.patch.object(nai_api._session, "post") as post:
                starts=[]
                def send(url, **kwargs):
                    starts.append(now[0])
                    return response(fixture.fake_post("test", kwargs["json"]))
                post.side_effect=send
                getattr(cls(), cls.FUNCTION)(**options)
                self.assertEqual(starts,[103,106])
                starts.clear()
                options["preview_only"]=True
                getattr(cls(), cls.FUNCTION)(**options)
                options.update(preview_only=False,detail_mask=torch.zeros_like(masks))
                getattr(cls(), cls.FUNCTION)(**options)
                self.assertEqual(starts,[])
                self.assertEqual(now[0],106)


class InsetDelayTests(unittest.TestCase):
    def test_inset_request_waits_and_preparation_does_not(self):
        fixture=inset_fixtures.InsetTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with clock() as now:
            prepared=fixture.prepare()["result"][0]
            self.assertEqual(now[0],100)
            fixture.response()
            NAIReferenceInsetGenerate().generate(**fixture.options(prepared),request_delay_seconds=5)
            self.assertEqual(now[0],105)
            fixture.post.assert_called_once()
