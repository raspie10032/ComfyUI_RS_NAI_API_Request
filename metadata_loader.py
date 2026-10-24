# SPDX-License-Identifier: GPL-3.0-only
"""Load Image with immediate, local NovelAI metadata inspection."""
from .local_bridge import PIPE_TYPE, pipe_from_metadata
import asyncio
from pathlib import Path

from PIL import Image

from .errors import user_error
from .metadata import inspect_metadata
from .metadata_context import AUTO_MODEL, restore_context
from .nai_api import MODEL_DISPLAY_LIST


def image_path(filename):
    import folder_paths
    if not isinstance(filename, str) or not filename:
        raise ValueError('Select an image first.')
    path = Path(folder_paths.get_annotated_filepath(filename)).resolve()
    roots = [Path(getter()).resolve() for getter in (folder_paths.get_input_directory, folder_paths.get_output_directory, folder_paths.get_temp_directory)]
    if not any(path.is_relative_to(root) for root in roots) or not path.is_file():
        raise ValueError('Select an image inside the ComfyUI input, output or temp folder.')
    return path


def inspect_file(filename, context_model=AUTO_MODEL):
    with Image.open(image_path(filename)) as image:
        metadata = inspect_metadata(image)
    _, metadata['context'] = restore_context(metadata, context_model)
    if len(metadata.get('characters', [])) > 10:
        metadata.setdefault('warnings', []).append('Local multi-character uses characters 1–10. / 로컬 멀티캐릭터에는 1~10번만 전달됩니다. 큐 실행 시 앞 10명만 사용합니다.')
    return metadata


class NAILoadImage:
    DESCRIPTION = 'Load an image, inspect NovelAI metadata and output NAI context to T2I, img2img or the multi-character detailer. Choose the source model if metadata cannot identify it. Missing or unsupported context is explained in this node and stops enabled consumers before requests; IMAGE/MASK remain usable. Seed, size, references and Anlas protection stay local to the next node. Local operation; no Anlas.'
    RETURN_TYPES = ('IMAGE', 'MASK', 'NAI_CONTEXT', PIPE_TYPE)
    RETURN_NAMES = ('image', 'mask', 'nai_context', 'character_pipe')
    FUNCTION = 'load_image'
    CATEGORY = 'RS_NovelAI_API/Image'

    @classmethod
    def INPUT_TYPES(cls):
        from nodes import LoadImage
        inputs = LoadImage.INPUT_TYPES()
        return {**inputs, 'optional': {**inputs.get('optional', {}),
            'context_model': ([AUTO_MODEL, *MODEL_DISPLAY_LIST], {'default': AUTO_MODEL,
                'tooltip': 'Use the recorded model, or explicitly choose the original model when only an unknown hash was saved. Other missing/unsupported settings are reported, never guessed.'})}}

    def load_image(self, image, context_model=AUTO_MODEL):
        from nodes import LoadImage
        try:
            metadata = inspect_file(image, context_model)
            context, _ = restore_context(metadata, context_model)
            try:
                character_pipe = pipe_from_metadata(metadata)
            except ValueError as error:
                from .diagnostics import notice
                notice(str(error))
                from .local_bridge import NAICharacterPipe
                character_pipe = NAICharacterPipe(())
            result = LoadImage().load_image(image)
        except (ValueError, OSError) as error:
            raise user_error('METADATA_IMAGE', type(error), str(error)) from error
        return {'ui': {'rs_nai_metadata': [metadata]}, 'result': (*result, context, character_pipe)}

    @classmethod
    def IS_CHANGED(cls, image, context_model=AUTO_MODEL, unique_id=None):
        from nodes import LoadImage
        image_path(image)
        return (LoadImage.IS_CHANGED(image), context_model)

    @classmethod
    def VALIDATE_INPUTS(cls, image, context_model=AUTO_MODEL):
        try:
            image_path(image)
            return True
        except ValueError as error:
            return str(error)


def register_routes():
    try:
        from aiohttp import web
        from server import PromptServer
    except ImportError:
        return
    if not getattr(PromptServer, 'instance', None):
        return

    @PromptServer.instance.routes.get('/rs_nai/metadata')
    async def metadata(request):
        try:
            data = await asyncio.to_thread(inspect_file, request.query.get('image', ''), request.query.get('context_model', AUTO_MODEL))
            return web.json_response(data)
        except (ValueError, OSError):
            return web.json_response({'error': 'METADATA_IMAGE'}, status=400)


register_routes()
NODE_CLASS_MAPPINGS = {'NAILoadImage': NAILoadImage}
NODE_DISPLAY_NAME_MAPPINGS = {'NAILoadImage': 'NAI Load Image'}
