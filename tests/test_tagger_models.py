"""Model selection, download isolation and matching-score contracts. Offline."""

import builtins
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ComfyUI_RS_NAI_API_Request import wd_tagger as wd


class SelectionTests(unittest.TestCase):
    def test_old_positional_workflow_and_switching_models(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(sys.modules, {"folder_paths": mock.Mock(models_dir=folder)}):
            with mock.patch.object(wd, "check_dependencies"), mock.patch.object(wd.WDTagger, "_load") as load:
                node = wd.WDTaggerLoader()
                old, = node.load("cpu", 2)
                self.assertEqual(old.model_name, wd.DEFAULT_MODEL)
                again, = node.load("cpu", 2, wd.DEFAULT_MODEL)
                self.assertIs(old, again)
                pixai, = node.load("cpu", 2, wd.PIXAI_MODEL)
                self.assertIsNot(old, pixai)
                self.assertEqual(pixai.model_name, wd.PIXAI_MODEL)
                self.assertEqual(pixai.cache_dir, old.cache_dir)
                self.assertEqual(load.call_count, 3)  # Preparation now executes in the loader.
        inputs = wd.WDTaggerLoader.INPUT_TYPES()
        self.assertEqual(list(inputs["required"]), ["device", "batch_size"])
        self.assertEqual(inputs["optional"]["model_name"][1]["default"], wd.DEFAULT_MODEL)
        self.assertEqual(wd.WDTaggerLoader.RETURN_TYPES, ("RS_WD_TAGGER",))

    def test_invalid_model_is_rejected_before_dependencies_or_download(self):
        with mock.patch.object(wd, "check_dependencies") as check:
            with self.assertRaisesRegex(ValueError, "Unknown tagger"):
                wd.WDTaggerLoader().load(model_name="../../untrusted")
            check.assert_not_called()

    def test_wd_does_not_require_transformers_but_pixai_explains_install(self):
        original = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name == "transformers":
                raise ModuleNotFoundError("missing transformers")
            return original(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=blocked):
            wd.check_dependencies(wd.DEFAULT_MODEL)
            with self.assertRaisesRegex(RuntimeError, "requirements-tagger-pixai.txt") as error:
                wd.check_dependencies(wd.PIXAI_MODEL)
            self.assertIn(sys.executable, str(error.exception))

    def test_downloads_only_selected_revision_and_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "config.json").write_text(json.dumps({"architecture": "fake", "num_classes": 1, "pretrained_cfg": {}}))
            (path / "selected_tags.csv").write_text("name,category\nred_hair,0\n")
            for name, (repo, revision) in wd.MODELS.items():
                download = mock.Mock(side_effect=lambda repo, filename, **kw: str(path / filename))
                dependencies = (mock.Mock(), download, mock.Mock(), mock.Mock(), mock.Mock(return_value={}))
                with self.subTest(model=name), mock.patch.object(wd, "check_dependencies", return_value=dependencies):
                    tagger = wd.WDTagger(folder, model_name=name)
                    with mock.patch.object(tagger, "_load_pixai"):
                        tagger._load()
                filenames = {call.args[1] for call in download.call_args_list}
                expected = {"config.json", "model.safetensors"}
                expected |= {"preprocessor_config.json", "tagger_pipeline.py"} if name == wd.PIXAI_MODEL else {"selected_tags.csv"}
                self.assertEqual(filenames, expected)
                for call in download.call_args_list:
                    self.assertEqual(call.args[0], repo)
                    self.assertEqual(call.kwargs["revision"], revision)


class PixAIContractTests(unittest.TestCase):
    def test_pinned_code_and_category_mapping(self):
        config = {"num_classes": 6, "tags": ["red_hair", "alice", "series", "style", "meta", "rating"],
                  "tags_split": [[x, 1] for x in ["general", "character", "copyright", "style", "meta", "rating"]]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            code = path / "tagger_pipeline.py"
            code.write_bytes(b"# reviewed test fixture")
            paths = {"tagger_pipeline.py": str(code), "config.json": str(path / "config.json")}
            backend = mock.Mock()
            with mock.patch.dict(sys.modules, {"transformers": backend}):
                tagger = wd.WDTagger(folder, model_name=wd.PIXAI_MODEL)
                with self.assertRaisesRegex(ValueError, "checksum"):
                    tagger._load_pixai(paths, config)
                backend.AutoModel.from_pretrained.assert_not_called()
                with mock.patch.object(wd, "PIXAI_CODE_SHA256", hashlib.sha256(code.read_bytes()).hexdigest()):
                    tagger._load_pixai(paths, config)
                self.assertEqual([r["category"] for r in tagger._labels], ["0", "4", "ignored", "ignored", "ignored", "ignored"])
                self.assertTrue(backend.AutoModel.from_pretrained.call_args.kwargs["local_files_only"])

    def test_rgb_batching_dense_scores_and_offload_on_failure(self):
        class Model(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.moves = []

            def to(self, device):
                self.moves.append(str(device))
                return self

            def forward(self, batch):
                self.seen = batch.clone()
                return torch.tensor([[-4.0, 2.0, 3.0]]).repeat(batch.shape[0], 1)

        tagger = wd.WDTagger("unused", "cpu", 2, wd.PIXAI_MODEL)
        tagger._model = Model()
        tagger._labels = [{"name": "red_hair", "category": "0"}, {"name": "alice", "category": "4"}, {"name": "style", "category": "ignored"}]
        def processor(crops, **kwargs):
            return {"pixel_values": torch.tensor([1.0, 0.0, 0.0]).view(1, 3, 1, 1).repeat(len(crops), 1, 2, 2)}
        tagger._processor = mock.Mock(side_effect=processor)
        images = [Image.new("RGB", (8, 3), "red") for _ in range(3)]
        scores = tagger.score(images)
        self.assertEqual(len(scores), 3)
        self.assertEqual(tagger._processor.call_count, 2)
        self.assertEqual(set(scores[0]), {"red_hair", "alice"})
        self.assertLess(scores[0]["red_hair"], 0.1)  # No upstream thresholding before matching.
        self.assertEqual(tagger._model.seen[0, 0].min(), 1)
        self.assertEqual(tagger._model.seen[0, 2].max(), 0)
        self.assertEqual(tagger._model.moves[-1], "cpu")
        tagger._labels.pop()
        with self.assertRaisesRegex(ValueError, "vocabulary"):
            tagger.score(images)
        self.assertEqual(tagger._model.moves[-1], "cpu")
        tagger._processor.side_effect = RuntimeError("processor failed")
        with self.assertRaisesRegex(RuntimeError, "processor failed"):
            tagger.score(images)
        self.assertEqual(tagger._model.moves[-1], "cpu")


if __name__ == "__main__":
    unittest.main()
