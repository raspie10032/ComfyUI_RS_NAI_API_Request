"""Byte progress, disabled terminals, resume, Xet and loader failure. No downloads."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ComfyUI_RS_NAI_API_Request import tagger_progress, wd_tagger


class ProgressTests(unittest.TestCase):
    def test_http_resumed_bytes_update_even_with_console_disabled(self):
        progress = tagger_progress.TaggerProgress()
        with mock.patch.object(progress, "report") as report:
            bar = progress.download_bar("model.safetensors")(total=100, initial=20, disable=True)
            bar.update(25)
            self.assertEqual(bar.n, 45)
            self.assertIn("45%", report.call_args.args[0])
            self.assertEqual(report.call_args.args[1], 0.45)
            count = report.call_count
            bar.close()  # Closing a failed transfer must not imply success.
            self.assertEqual(report.call_count, count)

    def test_xet_transfer_and_reconstruction_are_not_double_counted(self):
        progress = tagger_progress.TaggerProgress()
        with mock.patch.object(progress, "report") as report:
            bar = progress.download_bar("model.safetensors")(total=100)
            bar.update_transfer(30)
            bar.update(30)
            self.assertEqual(report.call_args.args[1], 0.3)
            bar.update_transfer(70)
            self.assertLess(report.call_args.args[1], 1)  # Download return verifies the file.
            bar.close()

    def test_node_id_routing_and_throttling(self):
        server = mock.Mock(client_id="browser-A")
        bar = mock.Mock()
        modules = {"comfy.utils": mock.Mock(ProgressBar=mock.Mock(return_value=bar)),
                   "server": mock.Mock(PromptServer=mock.Mock(instance=server))}
        with mock.patch.dict(sys.modules, modules), mock.patch.object(tagger_progress, "check_interrupted"):
            progress = tagger_progress.TaggerProgress("42")
            with mock.patch.object(tagger_progress.time, "monotonic", side_effect=[10, 10.05, 10.3]):
                progress.report("Downloading 10%", 0.1)
                progress.report("Downloading 11%", 0.11)
                progress.report("Downloading 25%", 0.25)
            self.assertEqual(server.send_sync.call_count, 2)
            server.send_sync.assert_called_with("rs_nai_tagger_progress", {"node": "42", "text": "Downloading 25%"}, "browser-A")
            bar.update_absolute.assert_called_with(250, 1000)

    def test_old_hub_fails_early_with_install_command(self):
        def old_download(repo_id, filename):
            pass
        with mock.patch("huggingface_hub.hf_hub_download", old_download):
            with self.assertRaisesRegex(RuntimeError, "huggingface-hub>=1.1") as error:
                wd_tagger.check_dependencies()
            self.assertIn("requirements-tagger.txt", str(error.exception))

    def test_failure_is_not_ready_and_preserves_original_error(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(sys.modules, {"folder_paths": mock.Mock(models_dir=folder)}):
            with mock.patch.object(wd_tagger, "check_dependencies"), mock.patch.object(wd_tagger, "TaggerProgress") as reporter:
                with mock.patch.object(wd_tagger.WDTagger, "_load", side_effect=OSError("download interrupted")):
                    with self.assertRaisesRegex(OSError, "download interrupted"):
                        wd_tagger.WDTaggerLoader().load()
                calls = reporter.return_value.report.call_args_list
                self.assertTrue(calls[-1].kwargs["failed"])
                self.assertFalse(any("Ready" in c.args[0] for c in calls))


if __name__ == "__main__":
    unittest.main()
