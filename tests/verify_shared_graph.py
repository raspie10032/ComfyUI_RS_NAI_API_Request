"""Execute a mixed graph with the real ComfyUI executor; HTTP is disabled.

Usage: python tests/verify_shared_graph.py --comfy /path/ComfyUI --mc /path/extension
This tests registration, socket validation, execution and metadata, not NAI service quality.
"""
import argparse
import asyncio
from contextlib import ExitStack
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comfy', type=Path, required=True)
    parser.add_argument('--mc', type=Path, required=True)
    options = parser.parse_args()
    sys.argv[:] = [sys.argv[0], '--cpu']
    sys.path[:0] = [str(options.comfy.resolve()), str(Path(__file__).resolve().parents[2])]
    from comfy.cli_args import args
    args.cpu = True
    import nodes
    import execution
    import ComfyUI_RS_NAI_API_Request as nai
    from ComfyUI_RS_NAI_API_Request import generators
    from PIL import Image

    spec = importlib.util.spec_from_file_location('_rs_shared_graph_mc', options.mc.resolve()/'__init__.py',
                                                  submodule_search_locations=[str(options.mc.resolve())])
    mc = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mc
    spec.loader.exec_module(mc)
    nodes.NODE_CLASS_MAPPINGS.update(nai.NODE_CLASS_MAPPINGS)
    nodes.NODE_CLASS_MAPPINGS.update(mc.NODE_CLASS_MAPPINGS)
    results = []

    class Sink:
        OUTPUT_NODE = True
        RETURN_TYPES = ()
        FUNCTION = 'check'
        @classmethod
        def INPUT_TYPES(cls):
            return {'required': {'image': ('IMAGE',), 'character_pipe': ('RS_MC_CHARACTER_PIPE',),
                                 'context': ('NAI_CONTEXT',)}}
        def check(self, image, character_pipe, context):
            assert tuple(image.shape) == (1, 64, 64, 3)
            assert len(character_pipe.characters) == 2
            assert [c.x for c in character_pipe.characters] == [.3, .7]
            assert [c.uc for c in character_pipe.characters] == ['hat', 'glasses']
            assert character_pipe.characters[0].prompt == '(red hair:2)'
            assert context.model == 'NAI Diffusion V5 Full'
            assert context.source_action == 'img2img'
            assert context.source_seed == 888
            results.append({'characters': 2, 'coordinates': [.3, .7], 'action': context.source_action,
                            'model': context.model, 'prompt': character_pipe.prompt})
            return ()
    nodes.NODE_CLASS_MAPPINGS['_RSOfflineContextSink'] = Sink

    def node(kind, **overrides):
        fields = {}
        for name, spec in nodes.NODE_CLASS_MAPPINGS[kind].INPUT_TYPES().get('required', {}).items():
            config = spec[1] if len(spec) > 1 else {}
            if 'default' in config:
                fields[name] = config['default']
            elif isinstance(spec[0], list) and spec[0]:
                fields[name] = spec[0][0]
        return {'class_type': kind, 'inputs': fields | overrides}

    graph = {
        '1': node('CharacterPromptSelect', character_count=2, character1='2::red hair::', character1_uc='hat',
                  character2_enable=True, character2='blue hair', character2_uc='glasses'),
        '2': node('RSMultiCharacterPosition', building_pipe=['1',0], character_count=2,
                  character1_x=.3, character2_x=.7),
        '3': node('RSMultiCharacterFinalize', building_pipe=['2',0]),
        '4': node('NovelAIGenerator', characterPrompts=['3',0], prompt='two people, cafe',
                  negative_prompt='blur', model='NAI Diffusion V5 Full', width=64, height=64,
                  steps=2, seed=777, limit_opus_free=False),
        '5': node('RSMultiCharacterLoRA', building_pipe=['4',1], character_count=2),
        '6': node('RSMultiCharacterFinalize', building_pipe=['5',0]),
        '7': node('NAIImg2ImgNode', image=['4',0], nai_context=['6',0], strength=.3,
                  seed=888, width=64, height=64, limit_opus_free=False),
        '8': node('RSMultiCharacterFinalize', building_pipe=['7',2]),
        '9': node('_RSOfflineContextSink', image=['7',0], character_pipe=['8',0], context=['7',1]),
    }
    png = io.BytesIO(); Image.new('RGB', (64,64), 'cyan').save(png, format='PNG')
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('image_0.png', png.getvalue())
    server = SimpleNamespace(client_id=None, last_node_id=None, send_sync=lambda *a: None)
    with tempfile.TemporaryDirectory() as root, ExitStack() as stack:
        stack.enter_context(patch('requests.sessions.Session.request', side_effect=AssertionError('HTTP disabled')))
        stack.enter_context(patch.object(generators, 'get_nai_token', return_value='offline-test'))
        remote = stack.enter_context(patch.object(generators, 'post_nai', return_value=archive.getvalue()))
        stack.enter_context(patch.object(generators.NovelAIGenerator, '_get_output_directory', return_value=root))
        valid = asyncio.run(execution.validate_prompt('rs-shared-context-offline', graph, None))
        if not valid[0]:
            raise AssertionError(json.dumps(valid, ensure_ascii=False))
        executor = execution.PromptExecutor(server, cache_args={'ram': 0, 'ram_inactive': 0})
        executor.execute(graph, 'rs-shared-context-offline', execute_outputs=valid[2])
        if not executor.success or not results:
            raise AssertionError(str(executor.status_messages))
        assert remote.call_count == 2
        assert len(list(Path(root).rglob('*.png'))) == 2
        print(json.dumps({'status':'passed', 'nodes':len(graph), 'mock_requests':remote.call_count,
                          'real_http_requests':0, 'result':results}, ensure_ascii=False))


if __name__ == '__main__':
    main()
