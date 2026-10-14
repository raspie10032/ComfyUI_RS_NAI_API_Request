# SPDX-License-Identifier: GPL-3.0-only
"""Per-node request delay shared by generation, references and detail crops."""

from contextvars import ContextVar
from functools import wraps
import math
import time

from .errors import explain_exception, user_error
from .runtime_control import check_interrupted

current_timer = ContextVar("rs_nai_request_timer", default=None)


class RequestTimer:
    def __init__(self, seconds, node_id=None):
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
            error = user_error("REQUEST_DELAY", ValueError, "request_delay_seconds must be a finite, nonnegative number.")
            explain_exception(error)
            raise error
        self.seconds = seconds
        self.node_id = node_id

    def wait(self, deadline, *, retry=False):
        server = None
        if self.node_id is not None:
            try:
                from server import PromptServer
                server = PromptServer.instance
                client_id = server.client_id
            except (ImportError, AttributeError):
                server = None  # Direct Python use does not require ComfyUI's UI.

        def report(remaining):
            if server is not None:
                server.send_sync("rs_nai_request_wait", {
                    "node": str(self.node_id), "remaining": remaining, "retry": retry,
                }, client_id)

        last_second = None
        try:
            while True:
                check_interrupted()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                second = math.ceil(remaining)
                if second != last_second:
                    report(second)
                    last_second = second
                time.sleep(min(remaining, 0.1))
        finally:
            report(0)


def node_request_delay(cls):
    """Scope pacing to this execution, including reference encoding requests."""
    input_types = cls.INPUT_TYPES
    function = getattr(cls, cls.FUNCTION)

    @classmethod
    def inputs(subclass):
        schema = input_types()
        # Keep the entire context suffix after the legacy timer. Moving only
        # use_context_settings would shift it when new override widgets appear.
        optional = schema.get("optional", {})
        keys = list(optional)
        tail = keys[keys.index("use_context_settings"):] if "use_context_settings" in optional else []
        context_tail = {name: optional.pop(name) for name in tail}
        schema["optional"] = {**schema.get("optional", {}), "request_delay_seconds": (
            "FLOAT", {"default": 0.0, "min": 0.0, "max": 3600.0, "step": 0.5,
                      "tooltip": "Wait before each NovelAI request, including each detail region and uncached Vibe encoding. 0 adds no delay. The built-in 2-second gap overlaps this timer; a longer server retry wait still applies. Preview-only runs do not wait. Stop cancels the countdown."}
        )}
        # New context controls follow all legacy widgets, including this timer.
        schema["optional"].update(context_tail)
        return schema

    @wraps(function)
    def run(self, *args, request_delay_seconds=0.0, unique_id=None, **kwargs):
        timer = RequestTimer(request_delay_seconds, unique_id)
        marker = current_timer.set(timer)
        try:
            return function(self, *args, unique_id=unique_id, **kwargs)
        finally:
            current_timer.reset(marker)

    cls.INPUT_TYPES = inputs
    setattr(cls, cls.FUNCTION, run)
    return cls
