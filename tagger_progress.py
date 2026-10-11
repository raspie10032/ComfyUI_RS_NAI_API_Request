# SPDX-License-Identifier: GPL-3.0-only
"""Hugging Face byte progress on the executing ComfyUI loader node."""

import time

from .runtime_control import check_interrupted


class TaggerProgress:
    def __init__(self, node_id=None):
        self.node_id = node_id
        self._last_update = 0
        self._server = None
        self._bar = None
        if node_id is not None:
            from comfy.utils import ProgressBar
            from server import PromptServer

            self._bar = ProgressBar(1000, node_id=node_id)
            self._server = PromptServer.instance
            self._client_id = self._server.client_id

    def report(self, text, fraction=0, *, force=False, failed=False):
        if not failed:
            check_interrupted()
        now = time.monotonic()
        if not force and now - self._last_update < 0.2:
            return
        self._last_update = now
        if self._bar is not None and not failed:
            self._bar.update_absolute(round(max(0, min(1, fraction)) * 1000), 1000)
        if self._server is not None:
            self._server.send_sync(
                "rs_nai_tagger_progress", {"node": str(self.node_id), "text": text},
                self._client_id,
            )

    def download_bar(self, filename):
        # Use tqdm's public interface, not Hub globals: HTTP and Xet both call it.
        # Keep counters even when terminal progress is disabled (e.g. systemd).
        from tqdm.auto import tqdm

        reporter = self

        class DownloadBar(tqdm):
            def __init__(self, *args, **kwargs):
                kwargs.pop("name", None)
                kwargs["disable"] = True
                super().__init__(*args, **kwargs)
                self._transferred = self.n
                self._report(force=True)

            def _report(self, force=False):
                received = max(self.n, self._transferred)
                mib = received / 1024**2
                if self.total:
                    fraction = min(1, received / self.total)
                    text = f"Downloading {filename}: {fraction:.0%} ({mib:.1f} / {self.total / 1024**2:.1f} MiB)"
                else:
                    fraction = 0
                    text = f"Downloading {filename}: {mib:.1f} MiB"
                # A completed transfer still needs verification by hf_hub_download.
                reporter.report(text, min(fraction, 0.999), force=force)

            def update(self, n=1):
                self.n += n
                self._report()

            def update_transfer(self, n):
                # Recent Hub Xet versions report transfer and reconstruction apart.
                self._transferred += n
                self._report()

            def set_transfer_postfix_str(self, *args, **kwargs):
                pass

        return DownloadBar
