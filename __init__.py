# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2025 raspie10032

from .generators import NODE_CLASS_MAPPINGS as GENERATOR_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as GENERATOR_DISPLAY_MAPPINGS
from .converters import CONVERTER_NODE_CLASS_MAPPINGS, CONVERTER_NODE_DISPLAY_NAME_MAPPINGS
from .diagnostics import node_notices
from .request_delay import node_request_delay
from .inset import NODE_CLASS_MAPPINGS as INSET_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as INSET_DISPLAY_MAPPINGS
from .assets import NODE_CLASS_MAPPINGS as ASSET_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as ASSET_DISPLAY_MAPPINGS

from .metadata_loader import NODE_CLASS_MAPPINGS as IMAGE_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as IMAGE_DISPLAY_MAPPINGS
from .camera_control import RSCameraControl
from .detector_bundle import NAIDetectionCombineLoader
from .combined_detailer import NAIMultiCharacterDetailer

NODE_CLASS_MAPPINGS = {
    "RSCameraControl": RSCameraControl,
    **GENERATOR_MAPPINGS,
    **CONVERTER_NODE_CLASS_MAPPINGS,
    **INSET_MAPPINGS,
    **ASSET_MAPPINGS,
    **IMAGE_MAPPINGS,
    "NAIDetectionCombineLoader": NAIDetectionCombineLoader,
    "NAIMultiCharacterDetailer": NAIMultiCharacterDetailer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RSCameraControl": "RS Camera Control",
    **GENERATOR_DISPLAY_MAPPINGS,
    **CONVERTER_NODE_DISPLAY_NAME_MAPPINGS,
    **INSET_DISPLAY_MAPPINGS,
    **ASSET_DISPLAY_MAPPINGS,
    **IMAGE_DISPLAY_MAPPINGS,
    "NAIDetectionCombineLoader": "NAI Detection Combine Loader",
    "NAIMultiCharacterDetailer": "NAI Multi-Character Detailer",
}

for node_class in NODE_CLASS_MAPPINGS.values():
    node_notices(node_class)

for name in ("NovelAIGenerator", "NAIImg2ImgNode", "NAIInpaintNode",
             "NAIFaceDetailerNode", "NAIFaceDetailerSegmNode", "NAIReferenceInsetGenerate", "NAIMultiCharacterDetailer"):
    node_request_delay(NODE_CLASS_MAPPINGS[name])

# Hidden aliases keep saved API prompts and old frontend workflows loadable.
class NAICombinedFaceDetailerTest(NAIMultiCharacterDetailer):
    DEPRECATED = True


class NAIDetectorCombineLoaderTest(NAIDetectionCombineLoader):
    DEPRECATED = True


NODE_CLASS_MAPPINGS.update({
    "NAICombinedFaceDetailerTest": NAICombinedFaceDetailerTest,
    "NAIDetectorCombineLoaderTest": NAIDetectorCombineLoaderTest,
})
NODE_DISPLAY_NAME_MAPPINGS.update({
    "NAICombinedFaceDetailerTest": "NAI Multi-Character Detailer",
    "NAIDetectorCombineLoaderTest": "NAI Detection Combine Loader",
})

WEB_DIRECTORY = "./web"

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']
