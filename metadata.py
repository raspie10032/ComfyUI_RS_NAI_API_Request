# SPDX-License-Identifier: GPL-3.0-only
"""NovelAI image metadata. No workflow, credentials or encoded references."""
import copy
import gzip
import io
import json
import math
import zlib

import numpy as np
from PIL import Image, features
from PIL.PngImagePlugin import PngInfo

from .errors import user_error
from .nai_api import MODEL_ID_MAP

MAX_METADATA = 4 * 1024 * 1024
NAI_FIELDS = ('Title', 'Description', 'Software', 'Source', 'Generation time', 'Generation_time', 'Comment', 'Artist', 'Copyright', 'rs_nai', 'rs_nai_inset', 'rs_detailer_regions')
PARAMETERS = ('width', 'height', 'seed', 'sampler', 'steps', 'scale', 'negative_prompt', 'cfg_rescale', 'prefer_brownian', 'noise_schedule', 'skip_cfg_above_sigma', 'strength', 'noise', 'inpaintImg2ImgStrength', 'v4_prompt', 'v4_negative_prompt')
SAVE_FORMATS = ['PNG', 'WebP lossless', 'WebP lossy']


def save_inputs():
    return {
        'save_format': (SAVE_FORMATS, {'default': 'PNG', 'tooltip': 'Autosave format. Preserves NovelAI generation information. No ComfyUI workflow is embedded.'}),
        'webp_quality': ('INT', {'default': 90, 'min': 1, 'max': 100, 'tooltip': 'Used only for lossy WebP. Lossless WebP preserves pixels.'}),
    }


def validate_save_options(save_format, webp_quality):
    if save_format not in SAVE_FORMATS or isinstance(webp_quality, bool) or not isinstance(webp_quality, int) or not 1 <= webp_quality <= 100:
        raise user_error('AUTOSAVE', ValueError, 'Choose PNG, WebP lossless or WebP lossy and quality 1–100. No request was sent.')
    if save_format != 'PNG' and not features.check('webp'):
        raise user_error('AUTOSAVE', RuntimeError, 'This Pillow installation cannot save WebP. Choose PNG or install Pillow with WebP support. No request was sent.')


def json_object(value):
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or len(value) > MAX_METADATA:
        raise ValueError('Metadata must be a JSON object under 4 MiB.')
    result = json.loads(value)
    if not isinstance(result, dict):
        raise ValueError('Metadata is not a JSON object.')
    return result


def _comment_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        if value.startswith(b'ASCII\0\0\0'):
            return value[8:].rstrip(b'\0').decode('ascii')
        if value.startswith(b'UNICODE\0'):
            return value[8:].decode('utf-16').rstrip('\0')
    return None


def _alpha_metadata(image):
    if 'A' not in image.getbands():
        return {}
    alpha = np.asarray(image.getchannel('A')).T.reshape(-1)
    # NAI stealth_pngcomp: column-major alpha LSBs, big-endian bit length.
    header = np.packbits(alpha[:152] & 1).tobytes()
    if header[:15] != b'stealth_pngcomp':
        return {}
    bits = int.from_bytes(header[15:19], 'big')
    if bits % 8 or bits > MAX_METADATA * 8 or bits > len(alpha) - 152:
        raise ValueError('Invalid hidden metadata length.')
    compressed = np.packbits(alpha[152:152 + bits] & 1).tobytes()
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        raw = stream.read(MAX_METADATA + 1)
    if len(raw) > MAX_METADATA:
        raise ValueError('Hidden metadata exceeds 4 MiB.')
    return json_object(raw.decode('utf-8'))


def read_fields(image):
    fields = {k: image.info[k] for k in NAI_FIELDS if k in image.info}
    warnings = []
    try:
        exif = image.getexif()
        for tag, key in ((269, 'Title'), (270, 'Description'), (305, 'Source'), (315, 'Artist'), (33432, 'Copyright')):
            if tag in exif:
                fields.setdefault(key, exif[tag])
        comment = _comment_text(exif.get_ifd(34665).get(37510)) if 34665 in exif else _comment_text(exif.get(37510))
        if comment:
            fields.setdefault('Comment', comment)
        if 37395 in exif:
            extra = json_object(exif[37395])
            fields.update({k: v for k, v in extra.items() if k in NAI_FIELDS})
    except (ValueError, TypeError, OSError, UnicodeError, KeyError, RecursionError):
        warnings.append('invalid_exif')
    try:
        hidden = _alpha_metadata(image)
        for key in NAI_FIELDS:
            if key in hidden:
                fields.setdefault(key, hidden[key])
    except (ValueError, TypeError, OSError, EOFError, UnicodeError, RecursionError, zlib.error):
        warnings.append('invalid_hidden_metadata')
    return fields, warnings


def request_record(payload):
    parameters = payload.get('parameters', {})
    return copy.deepcopy({
        'input': payload.get('input', ''), 'model': payload.get('model'), 'action': payload.get('action'),
        'parameters': {k: parameters[k] for k in PARAMETERS if k in parameters},
        'references_omitted': any(k.startswith(('reference_', 'director_reference_')) for k in parameters),
    })


def autosave(image, path, *, source_image=None, payload=None, operation=None, extra=None, save_format='PNG', webp_quality=90):
    validate_save_options(save_format, webp_quality)
    fields, _ = read_fields(source_image if source_image is not None else image)
    record = {'version': 1, 'operation': operation or (payload or {}).get('action', 'generate'), 'output_size': list(image.size)}
    if payload is not None:
        record['request'] = request_record(payload)
    if extra:
        record.update(extra)
    fields['rs_nai'] = json.dumps(record, ensure_ascii=True)
    fields = {k: json.dumps(v, ensure_ascii=True) if isinstance(v, dict) else str(v) for k, v in fields.items() if k in NAI_FIELDS}
    path = path.with_suffix('.png' if save_format == 'PNG' else '.webp')
    try:
        if save_format == 'PNG':
            info = PngInfo()
            for key, value in fields.items():
                info.add_text(key, value)
            image.save(path, format='PNG', pnginfo=info, exif=b'')
        else:
            exif = Image.Exif()
            for tag, key in ((269, 'Title'), (270, 'Description'), (305, 'Source'), (315, 'Artist'), (33432, 'Copyright')):
                if key in fields:
                    exif[tag] = fields[key]
            if 'Comment' in fields:
                # Official NAI WebP uses ASCII JSON in UserComment, in the Exif IFD.
                comment = json.dumps(json_object(fields['Comment']), ensure_ascii=True)
                exif[34665] = {37510: b'ASCII\0\0\0' + comment.encode('ascii')}
            exif[37395] = json.dumps(fields, ensure_ascii=True)
            image.save(path, format='WEBP', lossless=save_format == 'WebP lossless', quality=webp_quality, method=4, exif=exif)
    except (OSError, ValueError) as error:
        raise user_error('AUTOSAVE', type(error), f'Generation finished but autosave failed: {error}. Check output storage and permissions before retrying; generation may spend Anlas again.') from error
    return path


def _structured(data, key):
    value = data.get(key)
    if not isinstance(value, dict) or not isinstance(value.get('caption'), dict):
        return {}
    return value['caption']


def inspect_metadata(image):
    fields, warnings = read_fields(image)
    record, data = {}, {}
    for key, name in (('rs_nai', 'record'), ('Comment', 'comment')):
        if key not in fields:
            continue
        try:
            parsed = json_object(fields[key])
            if key == 'Comment' and 'Comment' in parsed:
                parsed = json_object(parsed['Comment'])
            if name == 'record':
                record = parsed
            else:
                data = parsed
        except (ValueError, TypeError, RecursionError):
            warnings.append('invalid_' + name)
    request = record.get('request') if isinstance(record.get('request'), dict) else {}
    parameters = request.get('parameters') if isinstance(request.get('parameters'), dict) else {}
    data = {**parameters, **data}
    operation = record.get('operation', request.get('action', 'unknown'))
    # Legacy composites hold the LAST crop's Comment, never the source image's prompt.
    legacy_detail = 'rs_detailer_regions' in fields and not record
    if operation == 'detailer' or legacy_detail:
        return {'status': 'partial', 'operation': 'detailer', 'settings': {}, 'characters': [],
                'warnings': warnings + ['detailer_not_base'], 'size': list(image.size), 'record': record,
                'detailer_regions': fields.get('rs_detailer_regions'), 'missing': []}
    positive = _structured(data, 'v4_prompt')
    negative = _structured(data, 'v4_negative_prompt')
    settings = {}
    prompt = positive.get('base_caption', data.get('prompt', request.get('input', fields.get('Description'))))
    uc = negative.get('base_caption', data.get('uc', data.get('negative_prompt')))
    if isinstance(prompt, str):
        settings['prompt'] = prompt
    if isinstance(uc, str):
        settings['negative_prompt'] = uc
    aliases = {'width': 'width', 'height': 'height', 'seed': 'seed', 'steps': 'steps', 'scale': 'cfg_scale', 'sampler': 'sampler', 'noise_schedule': 'scheduler', 'cfg_rescale': 'cfg_rescale', 'prefer_brownian': 'prefer_brownian', 'strength': 'strength', 'noise': 'noise', 'inpaintImg2ImgStrength': 'strength'}
    for source, target in aliases.items():
        v = data.get(source)
        if isinstance(v, (str, bool, int, float)) and (not isinstance(v, float) or math.isfinite(v)):
            settings[target] = v
    if "skip_cfg_above_sigma" in data or parameters:
        settings['variety_boost'] = bool(data.get('skip_cfg_above_sigma'))
    model = request.get('model') or data.get('model') or fields.get('Source', '')
    reverse = {v: k for k, v in MODEL_ID_MAP.items()}
    if isinstance(model, str) and model.removesuffix('-inpainting') in reverse:
        settings['model'] = reverse[model.removesuffix('-inpainting')]
    elif data:
        warnings.append('unknown_model')
    characters = []
    pos_chars = positive.get('char_captions', [])
    neg_chars = negative.get('char_captions', [])
    if not isinstance(pos_chars, list) or not isinstance(neg_chars, list):
        warnings.append('invalid_characters')
        pos_chars, neg_chars = [], []
    for i, char in enumerate(pos_chars):
        if not isinstance(char, dict) or not isinstance(char.get('char_caption'), str):
            warnings.append('invalid_characters')
            continue
        neg = neg_chars[i] if i < len(neg_chars) and isinstance(neg_chars[i], dict) else {}
        centers = char.get('centers')
        characters.append({'prompt': char['char_caption'], 'negative_prompt': neg.get('char_caption', ''), 'centers': centers if isinstance(centers, list) else []})
    structured = data.get('v4_prompt', {})
    if isinstance(structured, dict) and structured.get('use_coords') is False and characters:
        warnings.append('automatic_coordinates')
    if operation == 'inset' or 'rs_nai_inset' in fields:
        warnings.append('inset_canvas_coordinates')
        # Inspect the canvas prompts but do not apply canvas coordinates to a crop.
    if request.get('references_omitted') or any(k.startswith(('reference_', 'director_reference_')) for k in data):
        warnings.append('references_omitted')
    if request.get('action') in ('infill', 'img2img'):
        warnings.append('source_image_required')
    missing = [k for k in ('prompt', 'negative_prompt', 'model', 'seed', 'steps', 'cfg_scale', 'sampler') if k not in settings]
    return {'status': 'ok' if settings else 'empty', 'operation': operation, 'size': list(image.size), 'settings': settings, 'characters': characters, 'characters_present': 'char_captions' in positive, 'warnings': list(dict.fromkeys(warnings)), 'missing': missing, 'record': record}
