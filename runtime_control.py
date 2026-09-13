# SPDX-License-Identifier: GPL-3.0-only
"""Cooperative cancellation without requiring ComfyUI for standalone tests."""

import time


def check_interrupted():
    try:
        from comfy.model_management import throw_exception_if_processing_interrupted
    except ImportError:
        return
    throw_exception_if_processing_interrupted()


def wait_until(deadline):
    while True:
        check_interrupted()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.1))
