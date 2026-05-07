# Converter Playtest

## Policy

- Commas are always tag separators, even inside weighted scopes.
- Old NAI opening braces/brackets apply forward until closed.
- Old NAI closing braces/brackets with no active opener apply backward to previous tags.
- Unclosed NovelAI V4 numeric scopes apply to all following comma-separated tags.

## comfy_to_v4: single weighted tag
- input: `tag, (focus:1.2), plain`
- legacy: `tag, 1.2::focus ::, plain`
- parser: `tag, 1.2::focus ::, plain`
- same: `True`

## comfy_to_v4: multiple weighted tags
- input: `(tag1:1.05), (tag2:0.9), (tag3:-1.5), tail`
- legacy: `1.05::tag1 ::, 0.9::tag2 ::, -1.5::tag3 ::, tail`
- parser: `1.05::tag1 ::, 0.9::tag2 ::, -1.5::tag3 ::, tail`
- same: `True`

## comfy_to_v4: comma inside weighted tag
- input: `(misty, golden hour:1.1), background`
- legacy: `1.1::misty, golden hour ::, background`
- parser: `1.1::misty, golden hour ::, background`
- same: `True`

## comfy_to_v4: escaped parentheses
- input: `artist:abc, e\(f: g h\), (negative example:-1.5)`
- legacy: `artist:abc, e(f: g h), -1.5::negative example ::`
- parser: `artist:abc, e(f: g h), -1.5::negative example ::`
- same: `True`

## comfy_to_v4: nested comfy parentheses
- input: `((nested tag:1.2):1.1), plain`
- legacy: `1.1::(nested tag:1.2) ::, plain`
- parser: `1.1::(nested tag:1.2) ::, plain`
- same: `True`

## comfy_to_v4: unweighted parentheses
- input: `(implicit emphasis), plain`
- legacy: `1.1::implicit emphasis ::, plain`
- parser: `1.1::implicit emphasis ::, plain`
- same: `True`

## v4_to_comfy: single weighted tag
- input: `tag, 1.2::focus ::, plain`
- legacy: `tag, (focus :1.2), plain`
- parser: `tag, (focus:1.2), plain`
- same: `False`

## v4_to_comfy: multiple weighted tags
- input: `1.05::tag1 ::, 0.9::tag2 ::, -1.5::tag3 ::, tail`
- legacy: `(tag1 :1.05), (tag2 :0.9), (tag3 :-1.5), tail`
- parser: `(tag1:1.05), (tag2:0.9), (tag3:-1.5), tail`
- same: `False`

## v4_to_comfy: comma inside weighted tag
- input: `1.1::misty, golden hour ::, background`
- legacy: `(misty, golden hour :1.1), background`
- parser: `(misty:1.1), (golden hour:1.1), background`
- same: `False`

## v4_to_comfy: artist and literal parens
- input: `artist:abc, e(f: g h), -1.5::negative example ::`
- legacy: `artist:abc, e\(f: g h\), (negative example :-1.5)`
- parser: `artist:abc, e\(f: g h\), (negative example:-1.5)`
- same: `False`

## v4_to_comfy: colon inside weighted tag
- input: `1.2::artist:abc ::, 0.8::expression: smile ::`
- legacy: `(artist:abc :1.2), 0.8::expression: smile ::`
- parser: `(artist:abc:1.2), (expression: smile:0.8)`
- same: `False`

## v4_to_old: single weighted tag
- input: `1.2::focus ::, plain`
- legacy: `{{{{focus}}}}, plain`
- parser: `{{{{focus}}}}, plain`
- same: `True`

## v4_to_old: multiple weighted tags
- input: `1.05::tag1 ::, 0.9::tag2 ::, 1.2::tag3 ::`
- legacy: `{tag1}, [[tag2]], {{{{tag3}}}}`
- parser: `{tag1}, [[tag2]], {{{{tag3}}}}`
- same: `True`

Warning: Old NAI format cannot represent negative or zero weights. Applying the default decrease weight of 0.95 > '[negative tag]' instead.
Warning: Old NAI format cannot represent negative or zero weights. Applying the default decrease weight of 0.95 > '[zero weight tag]' instead.
## v4_to_old: negative and zero weights
- input: `-1.5::negative tag ::, 0::zero weight tag ::`
- legacy: `[negative tag], [zero weight tag]`
- parser: `[negative tag], [zero weight tag]`
- same: `True`

## v4_to_old: comma inside weighted tag
- input: `1.1::misty, golden hour ::, background`
- legacy: `{{misty, golden hour}}, background`
- parser: `{{misty, golden hour}}, background`
- same: `True`

## v4_to_old: unclosed numeric scope
- input: `1.3::tag1, tag2, tag3`
- legacy: `1.3::tag1, tag2, tag3`
- parser: `{{{{{tag1, tag2, tag3}}}}}`
- same: `False`

## v4_to_old: numeric scope closes later
- input: `1.3::tag1, tag2::, tag3`
- legacy: `{{{{{tag1, tag2}}}}}, tag3`
- parser: `{{{{{tag1, tag2}}}}}, tag3`
- same: `True`

## old_to_v4: single curly and square
- input: `{tag1}, [tag2], tag3`
- legacy: `1.05::tag1 ::, 0.95::tag2 ::, tag3`
- parser: `1.05::tag1 ::, 0.95::tag2 ::, tag3`
- same: `True`

## old_to_v4: multiple curly and square
- input: `{{tag1}}, [[tag2]], {{{tag3}}}, [[[tag4]]]`
- legacy: `1.1::tag1 ::, 0.9::tag2 ::, 1.16::tag3 ::, 0.86::tag4 ::`
- parser: `1.1::tag1 ::, 0.9::tag2 ::, 1.16::tag3 ::, 0.86::tag4 ::`
- same: `True`

## old_to_v4: comma inside braces
- input: `{{misty, golden hour}}, background`
- legacy: `1.1::misty, golden hour ::, background`
- parser: `1.1::misty, golden hour ::, background`
- same: `True`

## old_to_v4: opening scope applies forward
- input: `{tag1, tag2, tag3`
- legacy: `tag2, tag3, {tag1`
- parser: `1.05::tag1, tag2, tag3 ::`
- same: `False`

## old_to_v4: closing scope applies backward
- input: `tag1, tag2, tag3}`
- legacy: `tag1, tag2, tag3}`
- parser: `1.05::tag1, tag2, tag3 ::`
- same: `False`

## old_to_v4: scope opens and closes around several tags
- input: `{tag1, tag2}, tag3`
- legacy: `1.05::tag1, tag2 ::, tag3`
- parser: `1.05::tag1, tag2 ::, tag3`
- same: `True`

## old_to_v4: mixed bracket types
- input: `{[mixed]}, [{mixed2}], {tag], [tag}`
- legacy: `mixed, mixed2, {tag], [tag}`
- parser: `0.95::mixed, mixed2 ::, tag, tag`
- same: `False`

## old_to_v4: unbalanced brackets
- input: `{{broken}, [[broken2], plain`
- legacy: `{{broken}, [[broken2], plain`
- parser: `1.1::broken ::, 0.95::broken2 ::, plain`
- same: `False`

# Summary

- cases: `25`
- mismatches: `10`
