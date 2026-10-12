# SPDX-License-Identifier: GPL-3.0-only
"""Load Image with immediate, local NovelAI metadata inspection."""
import asyncio
from pathlib import Path

from PIL import Image

from .errors import user_error
from .metadata import inspect_metadata


def image_path(filename):
    import folder_paths
    if not isinstance(filename, str) or not filename:
        raise ValueError('Select an image first.')
    path = Path(folder_paths.get_annotated_filepath(filename)).resolve()
    roots = [Path(getter()).resolve() for getter in (folder_paths.get_input_directory, folder_paths.get_output_directory, folder_paths.get_temp_directory)]
    if not any(path.is_relative_to(root) for root in roots) or not path.is_file():
        raise ValueError('Select an image inside the ComfyUI input, output or temp folder.')
    return path


def inspect_file(filename):
    with Image.open(image_path(filename)) as image:
        return inspect_metadata(image)


class NAILoadImage:
    DESCRIPTION = 'Load an image and inspect NovelAI prompts, characters and settings immediately in this node. Apply recovered values to a chosen generation node without extra metadata wires. Missing reference images and unsupported settings are reported. Local operation; no Anlas.'
    RETURN_TYPES = ('IMAGE', 'MASK')
    RETURN_NAMES = ('image', 'mask')
    FUNCTION = 'load_image'
    CATEGORY = 'RS_NovelAI_API/Image'

    @classmethod
    def INPUT_TYPES(cls):
        from nodes import LoadImage
        return LoadImage.INPUT_TYPES()

    def load_image(self, image):
        from nodes import LoadImage
        try:
            metadata = inspect_file(image)
            result = LoadImage().load_image(image)
        except (ValueError, OSError) as error:
            raise user_error('METADATA_IMAGE', type(error), str(error)) from error
        return {'ui': {'rs_nai_metadata': [metadata]}, 'result': result}

    @classmethod
    def IS_CHANGED(cls, image):
        from nodes import LoadImage
        image_path(image)
        return LoadImage.IS_CHANGED(image)

    @classmethod
    def VALIDATE_INPUTS(cls, image):
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
            data = await asyncio.to_thread(inspect_file, request.query.get('image', ''))
            return web.json_response(data)
        except (ValueError, OSError):
            return web.json_response({'error': 'METADATA_IMAGE'}, status=400)


register_routes()
NODE_CLASS_MAPPINGS = {'NAILoadImage': NAILoadImage}
NODE_DISPLAY_NAME_MAPPINGS = {'NAILoadImage': 'NAI Load Image'}
