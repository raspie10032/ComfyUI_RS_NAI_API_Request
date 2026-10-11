"""Error UX through node, request, and cancellation boundaries. No network."""

import errno
import json
from pathlib import Path
import sys
import traceback
import types
import unittest
from unittest import mock

import requests
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ComfyUI_RS_NAI_API_Request import diagnostics, errors, generators, nai_api, wd_tagger


class ErrorTests(unittest.TestCase):
    def options(self):
        return dict(prompt="bird", negative_prompt="", model="NAI Diffusion V4.5 Full",
                    width=64, height=64, sampler="k_euler", steps=20, cfg_scale=5, seed=1,
                    limit_opus_free=False)

    def test_http_failure_reports_status_message_and_phase_without_changing_type(self):
        cases = {400: "NAI_REQUEST", 401: "NAI_AUTH", 402: "NAI_PAYMENT", 403: "NAI_FORBIDDEN",
                 429: "NAI_RATE_LIMIT", 422: "NAI_REQUEST", 500: "NAI_SERVER", 404: "NAI_HTTP"}
        for status, code in cases.items():
            with self.subTest(status=status):
                response = requests.Response()
                response.status_code = status
                response._content_consumed = True
                response._content = json.dumps({"message": "Server explanation with Bearer dummy-secret", "request": {"token": "dummy-secret"}}).encode()
                with mock.patch.object(generators, "get_nai_token", return_value="dummy-secret"), \
                     mock.patch.object(nai_api._session, "post", return_value=response) as post, \
                     mock.patch.object(nai_api, "wait_until"), mock.patch.object(nai_api, "_next_request_at", 0):
                    with self.assertRaises(requests.HTTPError) as caught:
                        generators.NovelAIGenerator().generate(**self.options())
                text = str(caught.exception)
                self.assertIn(f"[RS NAI:{code}]", text)
                self.assertIn(f"HTTP {status}", text)
                self.assertIn("Stage: generation", text)
                self.assertIn("Server explanation", text)
                self.assertNotIn("dummy-secret", text)
                self.assertNotIn('"request"', text)
                self.assertEqual(post.call_count, 2 if status == 429 else 1)
                self.assertIs(caught.exception.response, response)

    def test_transport_failure_has_no_automatic_duplicate_submission(self):
        cases = [(requests.Timeout, "NAI_TIMEOUT"), (requests.ConnectionError, "NAI_CONNECTION"),
                 (requests.exceptions.SSLError, "NAI_TLS")]
        for kind, code in cases:
            with self.subTest(code=code), mock.patch.object(generators, "get_nai_token", return_value="dummy"), \
                 mock.patch.object(nai_api._session, "post", side_effect=kind("network detail")) as post, \
                 mock.patch.object(nai_api, "wait_until"), mock.patch.object(nai_api, "_next_request_at", 0):
                with self.assertRaises(kind) as caught:
                    generators.NovelAIGenerator().generate(**self.options())
                self.assertIn(f"[RS NAI:{code}]", str(caught.exception))
                post.assert_called_once()

    def test_subscription_failure_retains_check_context_and_blocks_generation(self):
        with mock.patch.object(nai_api._session, "get", side_effect=requests.Timeout("subscription timeout")), \
             mock.patch.object(nai_api._session, "post") as post:
            with self.assertRaises(RuntimeError) as caught:
                nai_api._verify_opus_subscription("dummy", "nai-diffusion-5-full")
            errors.explain_exception(caught.exception)
            text = str(caught.exception)
            self.assertIn("[RS NAI:SUBSCRIPTION_CHECK]", text)
            self.assertIn("subscription timeout", text)
            self.assertIn("Stage: subscription", text)
            post.assert_not_called()

    def test_strict_input_failure_is_friendly_before_token_or_encoding(self):
        with mock.patch.object(generators, "get_nai_token") as token, \
             mock.patch.object(generators, "tensor_to_pil") as encode, \
             mock.patch.object(nai_api._session, "post") as post:
            options = {**self.options(), "limit_opus_free": True}
            with self.assertRaisesRegex(RuntimeError, r"\[RS NAI:PAID_BLOCKED\]"):
                generators.NAIImg2ImgNode().generate(**options, image=None, strength=0.5)
            token.assert_not_called()
            encode.assert_not_called()
            post.assert_not_called()

    def test_resource_failures_keep_type_errno_and_actual_details(self):
        cases = [(torch.OutOfMemoryError("CUDA allocation failed"), "MEMORY"),
                 (MemoryError("RAM allocation failed"), "MEMORY"),
                 (PermissionError(errno.EACCES, "Permission denied", "/models/cache"), "FILE_PERMISSION"),
                 (OSError(errno.ENOSPC, "No space left", "/output/image.png"), "DISK_FULL")]
        for error, code in cases:
            with self.subTest(code=code):
                kind, number, original = type(error), getattr(error, "errno", None), str(error)
                error.rs_nai_code = "TAGGER_DOWNLOAD"
                errors.explain_exception(error)
                self.assertIs(type(error), kind)
                self.assertEqual(getattr(error, "errno", None), number)
                self.assertIn(f"[RS NAI:{code}]", str(error))
                self.assertIn(original, str(error))

    def test_cancellation_is_not_converted_to_failure(self):
        class Cancelled(Exception):
            pass
        @diagnostics.node_notices
        class Node:
            INPUT_TYPES = classmethod(lambda cls: {})
            FUNCTION = "run"
            def run(self):
                raise Cancelled("cancel")
        comfy = types.ModuleType("comfy")
        manager = types.ModuleType("comfy.model_management")
        manager.InterruptProcessingException = Cancelled
        with mock.patch.dict(sys.modules, {"comfy": comfy, "comfy.model_management": manager}):
            with self.assertRaises(Cancelled) as caught:
                Node().run()
        self.assertEqual(str(caught.exception), "cancel")
        self.assertIsNone(diagnostics._messages.get())

    def test_unknown_failure_keeps_traceback_and_scrubs_chained_tokens(self):
        def fail():
            try:
                raise ValueError("Authorization: Bearer dummy-token")
            except ValueError as cause:
                raise LookupError("Unexpected result; token=dummy-token") from cause
        try:
            fail()
        except LookupError as error:
            errors.explain_exception(error)
            first = str(error)
            errors.explain_exception(error)
            self.assertEqual(first, str(error))
            self.assertIn("[RS NAI:UNKNOWN]", first)
            stack = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            # Source lines contain the dummy literal; exception messages do not.
            self.assertNotIn("dummy-token", str(error))
            self.assertNotIn("dummy-token", str(error.__cause__))
            self.assertIn('in fail', stack)
            self.assertIn("LookupError", first)

    def test_redaction_preserves_install_paths_and_hides_bodies(self):
        path = "/very-long-folder" * 15 + "/requirements-tagger.txt"
        self.assertEqual(errors.redact(path), path)
        self.assertNotIn("credential", errors.redact("Bearer credential"))
        self.assertNotIn("credential", errors.redact('token="credential"'))
        self.assertNotIn("A" * 200, errors.redact("A" * 200))

    def test_all_locales_cover_the_same_error_codes(self):
        self.assertEqual(set(errors.MESSAGES), {"en", "ko", "ja"})
        for locale, values in errors.MESSAGES.items():
            self.assertEqual(set(values), set(errors.MESSAGES["en"]), locale)
            for pair in values.values():
                self.assertEqual(len(pair), 2)
                self.assertTrue(all(isinstance(s, str) and s.strip() for s in pair))

    def test_model_download_context_is_distinct_from_novelai(self):
        class Progress:
            def report(self, *args, **kwargs): pass
            def download_bar(self, name): return None
        download = mock.Mock(side_effect=requests.ConnectionError("hub unavailable"))
        with mock.patch.object(wd_tagger, "check_dependencies", return_value=(None, download, None, None, None)):
            tagger = wd_tagger.WDTagger("/unused")
            with self.assertRaises(requests.ConnectionError) as caught:
                tagger._load(Progress())
        errors.explain_exception(caught.exception)
        self.assertIn("[RS NAI:TAGGER_DOWNLOAD]", str(caught.exception))
        self.assertIn("file:", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
