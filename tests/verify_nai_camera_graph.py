"""Execute NAI-only camera graphs in ComfyUI with all real HTTP blocked."""
import argparse
import asyncio
from contextlib import ExitStack
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
    options = parser.parse_args()
    sys.argv[:] = [sys.argv[0], '--cpu']
    sys.path[:0] = [str(options.comfy.resolve()), str(Path(__file__).resolve().parents[2])]
    from comfy.cli_args import args
    args.cpu = True
    import nodes
    import execution
    import ComfyUI_RS_NAI_API_Request as nai
    from ComfyUI_RS_NAI_API_Request import generators
    from ComfyUI_RS_NAI_API_Request.camera_layout import perspective_framing, project
    from PIL import Image

    # Only this NAI package is registered: no local sampler extension imported.
    nodes.NODE_CLASS_MAPPINGS.update(nai.NODE_CLASS_MAPPINGS)
    assert 'RSMultiCharacterScene' not in nodes.NODE_CLASS_MAPPINGS
    results = []

    class Sink:
        OUTPUT_NODE = True
        RETURN_TYPES = ()
        FUNCTION = 'check'
        @classmethod
        def INPUT_TYPES(cls):
            return {'required': {'image': ('IMAGE',), 'context': ('NAI_CONTEXT',)}}
        def check(self, image, context):
            assert tuple(image.shape) == (1, 64, 64, 3)
            assert len(context.characters) == 2
            assert context.source_action == 'img2img'
            assert context.source_seed == 888
            transform = perspective_framing(.65, 12, 1.5, 45, 25)
            for c, x in zip(context.characters, (.3, .7)):
                expected = project(x, .5, transform)
                assert abs(c.x-expected[0]) < 1e-12 and abs(c.y-expected[1]) < 1e-12
                assert '::from above::' in c.prompt
            results.append({'characters': 2, 'centers': [c.center for c in context.characters],
                            'action': context.source_action, 'model': context.model})
            return ()
    nodes.NODE_CLASS_MAPPINGS['_RSOfflineNAICameraSink'] = Sink

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
        '1': node('CharacterPromptSelect', character_count=2, character1='brown hair',
                  character1_x=.3, character1_y=.5, character2_enable=True, character2='pink hair',
                  character2_x=.7, character2_y=.5),
        '2': node('NAICameraControl', building_pipe=['1',0], base_prompt='two adult women, garden',
                  layout_sync='perspective', azimuth=45., elevation=25., distance=.65, roll=12., canvas_aspect=1.5),
        '3': node('NovelAIGenerator', nai_context=['2',0], model='NAI Diffusion V5 Full',
                  use_context_settings=True, width=64, height=64, steps=2, seed=777, limit_opus_free=False),
        '4': node('NAICameraControl', context=['3',1], enabled=False),
        '5': node('NAIImg2ImgNode', image=['3',0], nai_context=['4',0], strength=.3,
                  seed=888, width=64, height=64, limit_opus_free=False),
        '6': node('_RSOfflineNAICameraSink', image=['5',0], context=['5',1]),
    }
    png = io.BytesIO()
    Image.new('RGB', (64,64), 'cyan').save(png, format='PNG')
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('image_0.png', png.getvalue())
    server = SimpleNamespace(client_id=None, last_node_id=None, send_sync=lambda *a: None)
    with tempfile.TemporaryDirectory() as root, ExitStack() as stack:
        stack.enter_context(patch('requests.sessions.Session.request', side_effect=AssertionError('HTTP disabled')))
        stack.enter_context(patch.object(generators, 'get_nai_token', return_value='offline-test'))
        remote = stack.enter_context(patch.object(generators, 'post_nai', return_value=archive.getvalue()))
        stack.enter_context(patch.object(generators.NovelAIGenerator, '_get_output_directory', return_value=root))
        valid = asyncio.run(execution.validate_prompt('rs-nai-camera-offline', graph, None))
        if not valid[0]:
            raise AssertionError(json.dumps(valid, ensure_ascii=False))
        executor = execution.PromptExecutor(server, cache_args={'ram': 0, 'ram_inactive': 0})
        executor.execute(graph, 'rs-nai-camera-offline', execute_outputs=valid[2])
        if not executor.success or not results:
            raise AssertionError(str(executor.status_messages))
        assert remote.call_count == 2
        assert len(list(Path(root).rglob('*.png'))) == 2
        print(json.dumps({'status': 'passed', 'nodes': len(graph), 'local_extension_loaded': False,
                          'mock_requests': remote.call_count, 'real_http_requests': 0, 'results': results}))


if __name__ == '__main__':
    main()
