# Tagger regression image

`wd-tagger-two-characters.png` is the fixed input for `tests/smoke_wd_tagger.py`.
The test supplies two face boxes and checks automatic character selection,
including a tighter-crop retry with WD ViT v3.

The pixels and metadata are preserved from the former `workflow_example/example.png`
so the regression remains reproducible. Its embedded legacy workflow is historical
test data, not a supported usage example. Use the
[current four-character guide](../../examples/four-character-v5-wd/README.md)
for runnable workflow PNGs and setup instructions.
