# SPDX-License-Identifier: GPL-3.0-only
"""Per-execution notices, without adding saved widgets or output sockets."""

import logging
from contextvars import ContextVar
from functools import wraps

_messages = ContextVar("rs_nai_messages", default=None)


def notice(message):
    messages = _messages.get()
    if messages is None:
        logging.warning("[RS NAI] %s", message)
    elif message not in messages:
        messages.append(message)
        logging.warning("[RS NAI] %s", message)


def node_notices(cls):
    """Keep direct Python tuple returns; expose notices in ComfyUI's UI result."""
    input_types = cls.INPUT_TYPES
    function = getattr(cls, cls.FUNCTION)

    @classmethod
    def inputs(subclass):
        schema = input_types()
        schema["hidden"] = {**schema.get("hidden", {}), "unique_id": "UNIQUE_ID"}
        return schema

    @wraps(function)
    def run(self, *args, unique_id=None, **kwargs):
        messages = []
        marker = _messages.set(messages)
        try:
            result = function(self, *args, **kwargs)
        finally:
            _messages.reset(marker)
        if unique_id is None:
            return result
        return {"ui": {"rs_nai_notice": messages}, "result": result}

    cls.INPUT_TYPES = inputs
    setattr(cls, cls.FUNCTION, run)
    return cls
