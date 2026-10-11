# SPDX-License-Identifier: GPL-3.0-only
"""Actionable execution errors; keep exception types and the original traceback."""

import errno
import json
import os
from pathlib import Path
import re
import zipfile

from PIL import UnidentifiedImageError
import requests
import torch

MESSAGES = json.loads((Path(__file__).parent / "web" / "error_messages.json").read_text(encoding="utf-8"))
DETAIL_MARKER = "\n\nTechnical details:\n"


def user_error(code, exception_type, detail):
    error = exception_type(detail)
    error.rs_nai_code = code
    return error


def redact(text, secrets=()):
    text = str(text)
    for secret in (*secrets, os.getenv("NAI_ACCESS_TOKEN"), os.getenv("NAI_API_TOKEN"), os.getenv("HF_TOKEN")):
        if secret:
            text = text.replace(secret, "[redacted]")
    text = re.sub(r"(?i)(Bearer\s+)[^\s\"',;]+", r"\1[redacted]", text)
    text = re.sub(r"(?i)((?:access_token|api_token|token|authorization|api_key)[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,}]+", r"\1[redacted]", text)
    text = re.sub(r"[A-Za-z0-9_+=-]{160,}", "[long data omitted]", text)
    return text[:3000]


def mark_api_error(error, *, phase, token):
    """Called only at the NovelAI boundary, never for model downloads."""
    status = error.response.status_code if isinstance(error, requests.HTTPError) and error.response is not None else None
    codes = {401: "NAI_AUTH", 402: "NAI_PAYMENT", 403: "NAI_FORBIDDEN", 429: "NAI_RATE_LIMIT", 400: "NAI_REQUEST", 422: "NAI_REQUEST"}
    if phase == "subscription":
        code = "NAI_AUTH" if status == 401 else "SUBSCRIPTION_CHECK"
    elif status is not None:
        code = codes.get(status, "NAI_SERVER" if status >= 500 else "NAI_HTTP")
    elif isinstance(error, requests.exceptions.SSLError):
        code = "NAI_TLS"
    elif isinstance(error, requests.Timeout):
        code = "NAI_TIMEOUT"
    elif isinstance(error, requests.ConnectionError):
        code = "NAI_CONNECTION"
    else:
        code = "NAI_HTTP"
    details = f"Stage: {phase}" + (f"; HTTP {status}" if status is not None else "")
    if isinstance(error, requests.HTTPError) and error.response is not None:
        # Do not dump headers, request bodies, HTML, or encoded reference images.
        try:
            body = error.response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            for key in ("message", "error"):
                if isinstance(body.get(key), str):
                    details += f"\nServer {key}: {redact(body[key], (token,))}"
    error.rs_nai_code = code
    error.rs_nai_details = redact(details, (token,))
    error.args = (redact(str(error), (token,)),)
    return error


def error_code(error):
    # Concrete resource failures take precedence over a broad download context.
    if isinstance(error, (torch.OutOfMemoryError, MemoryError)):
        return "MEMORY"
    if isinstance(error, PermissionError):
        return "FILE_PERMISSION"
    if isinstance(error, OSError) and error.errno == errno.ENOSPC:
        return "DISK_FULL"
    if hasattr(error, "rs_nai_code"):
        return error.rs_nai_code
    if isinstance(error, (zipfile.BadZipFile, UnidentifiedImageError)):
        return "IMAGE_RESPONSE"
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        return "DEPENDENCY"
    if isinstance(error, FileNotFoundError):
        return "FILE_MISSING"
    return "UNKNOWN"


def explain_exception(error):
    """Add the English fallback once. The browser localizes the stable code."""
    if getattr(error, "rs_nai_explained", False):
        return
    code = error_code(error)
    title, action = MESSAGES["en"][code]
    details = []
    current, seen = error, set()
    while current is not None and id(current) not in seen and len(seen) < 5:
        seen.add(id(current))
        original = redact(str(current))
        details.append(f"{type(current).__name__}: {original}")
        if hasattr(current, "rs_nai_details"):
            details.append(current.rs_nai_details)
        # Scrub chained error messages as well as the message shown on the node.
        current.args = (original,)
        if isinstance(current, OSError) and current.strerror is not None:
            current.strerror = redact(current.strerror)
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    text = f"[RS NAI:{code}] {title}\n{action}{DETAIL_MARKER}" + "\n".join(details)
    error.args = (text,)
    if isinstance(error, OSError) and error.strerror is not None:
        error.strerror = text
    error.rs_nai_explained = True
