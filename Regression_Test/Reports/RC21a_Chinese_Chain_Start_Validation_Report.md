# RC21a Chinese Chain-Start Parser Validation Report

Validation date: 2026-07-09

Application under validation: `Crochet_Translator_Beta_RC21a.py`

Dictionary under validation: `stitches_1_8e.csv`

Scope: validation only. No application code was modified during this validation task.

## Objective

Validate the RC21a parser-assisted Chinese pattern instruction rule for:

- `倒X針`
- `倒X鉤`
- `倒數第X針`
- `倒數第X鉤`
- `倒X回鉤`
- `倒數第X回鉤`
- similar real-world wording found in supplied crochet pattern images

Expected English output:

`Start in the Xth chain from hook`

## Validation Method

1. Ran syntax check on RC21a.
2. Ran targeted OCR crops against supplied Chinese real-world patterns.
3. Extracted OCR lines containing likely chain-start wording.
4. Passed each OCR line through:
   - `clean_single_ocr_line()`
   - `replace_chain_start_instructions()`
   - `translate_ocr_line()`
5. Ran regression-safety spot checks for English patterns, grouped expressions, and dictionary replacement.

## Validation Summary

- Successful parser matches: 11
- Parser failures / not triggered: 1
- New wording variants discovered: 5
- Critical regressions found: 0
- Recommendation: RC21a needs minor parser enhancement before promotion.

## Successful Matches

| Pattern | Original OCR text | Normalized parser input | Parser output | Final translated output | Result |
|---|---|---|---|---|---|
| V02 Sushi Series | `起10ch,倒三回钩8F` | `起10ch,倒三回钩8F` | `起10ch,Start in the 3rd chain from hook 8F` | `起10 ch, Start in the 3rd chain from hook 8 dc` | PASS |
| V03 Jellycat Potato | `R1:起6ch,倒2回钩4x,w,3x,V R1:起11ch,倒2回钩v,8x,w,9x` | same | `R1:起6ch,Start in the 2nd chain from hook 4x,w,3x,V R1:起11ch,Start in the 2nd chain from hook v,8x,w,9x` | `R1: 起6 ch, Start in the 2nd chain from hook 4 sc, 3 sc in same stitch, 3 sc, V R1:起11 ch, Start in the 2nd chain from hook v, 8 sc, 3 sc in same stitch, 9 sc` | PASS with adjacent-symbol limitation |
| V04 Lily Flowerpot | `12ch.倒二钩` | same | `12ch. Start in the 2nd chain from hook` | `12 ch, Start in the 2nd chain from hook` | PASS |
| V04 Lily Flowerpot | `1.玫红12ch倒二钩3X,T.3F.2T,X` | same | `1.玫红12ch Start in the 2nd chain from hook 3X,T.3F.2T,X` | `1, 玫红12 ch Start in the 2nd chain from hook 3 sc, hdc, 3 dc, 2 hdc, sc` | PASS |
| V04 Lily Flowerpot | `9ch倒二钩S. [(5ch.在5ch的倒二钩4S)` | same | `9ch Start in the 2nd chain from hook S. [(5ch.在5ch的 Start in the 2nd chain from hook 4S)` | `9 ch Start in the 2nd chain from hook S, [(5 ch.在5ch的 Start in the 2nd chain from hook 4S)` | PASS with unrelated `S` limitation |
| V05 Strawberry Cake | `R1:5ch倒二钩3xw,2x,v` | same | `R1:5ch Start in the 2nd chain from hook 3xw,2x,v` | `R1: 5 ch Start in the 2nd chain from hook 3xw, 2 sc, inc` | PASS with unrelated `3xw` limitation |
| V05 Strawberry Cake | `起10ch倒二钩` | same | `起10ch Start in the 2nd chain from hook` | `起10 ch Start in the 2nd chain from hook` | PASS |
| V10 Wings CN | `倒2钩10x` | same | `Start in the 2nd chain from hook 10x` | `Start in the 2nd chain from hook 10 sc` | PASS |
| V10 Wings CN | `倒2钩9x` | same | `Start in the 2nd chain from hook 9x` | `Start in the 2nd chain from hook 9 sc` | PASS |

Note: V03 contains two `倒2回钩` matches in one merged OCR line. V04 contains two `倒二钩` matches in one OCR line.

## Failure / Edge Case

| Pattern | Original OCR text | Normalized parser input | Parser output | Final translated output | Failure Type |
|---|---|---|---|---|---|
| V01 Jellycat Ingot | `R1:立6ch.倒2.v.3x.(5x).3x.(W)` | same | unchanged | `R1: 立6 ch, 倒2, inc, 3 sc, (5 sc), 3 sc, (3 sc in same stitch)` | Parser not triggered |

Root cause:

The OCR/image text contains bare `倒2` followed by punctuation, without `針`, `针`, `鉤`, `钩`, or `回钩`.

Current RC21a intentionally supports `倒X針`, `倒X鉤`, `倒數第X針`, `倒數第X鉤`, and `倒X回鉤`, but does not support bare `倒X`.

This is a real-world variant in the supplied validation set.

## Newly Discovered Variants

| Variant | Observed In | Handled by RC21a? | Notes |
|---|---|---|---|
| `倒三回钩` | V02 | Yes | Correctly outputs `Start in the 3rd chain from hook`. |
| `倒2回钩` | V03 | Yes | Correctly extracts `2`. |
| `倒二钩` | V04, V05 | Yes | Correctly extracts Chinese numeral `二`. |
| `在5ch的倒二钩` | V04 | Yes | Parser triggers inside embedded phrase. Surrounding prose remains partially untranslated. |
| `倒2钩` | V10 | Yes | Correctly extracts `2`. |
| bare `倒2` | V01 | No | New real-world shorthand / OCR variant. Needs minor enhancement if product wants this covered. |

## Failure Case Review

- Parser not triggered: 1 case, bare `倒2`.
- Incorrect number extraction: 0 cases observed.
- OCR spelling variation not recognized: 1 case, bare `倒2`.
- Wrong English translation: 0 cases observed for triggered parser matches.
- Phrase partially translated: observed around adjacent stitch symbols such as `倒2回钩v`; parser output is correct, but existing prose/expression handling may leave adjacent `v` untranslated.
- Parser conflicts with CSV replacement: no direct conflicts observed. Generated phrase remained protected from the CSV loop.
- Parser incorrectly triggers on unrelated text: not observed.

## Regression Safety Checks

Spot checks showed no new regression from the Chinese parser rule:

| Area | Check | Result |
|---|---|---|
| English patterns | `start in 2nd ch from hook` | Chinese parser did not trigger. Existing dictionary replacement behavior unchanged. |
| English loop wording | `Row 3: Start in 2nd loop: 6 SC` | Chinese parser did not trigger. |
| Grouped expression | `(X,V)` | `(sc, inc)` unchanged. |
| Grouped expression with repeat | `3(X,V)` | `(sc, inc) x3` unchanged. |
| Stitch dictionary replacement | `BLO 24X` | `24 blo sc` unchanged. |
| Japanese output smoke | `R1: 6 sc` | `R1: 細編み6目` unchanged. |

## Recommendation

RC21a needs minor parser enhancement before promotion.

Reason:

The parser successfully handles the requested forms and most newly supplied real-world variants, but the validation set revealed a common shorthand / OCR variant:

`倒2`

This appears in a real pattern line:

`R1:立6ch.倒2.v.3x.(5x).3x.(W)`

The current parser does not trigger because there is no following `針`, `针`, `鉤`, `钩`, or `回钩`.

Recommended next enhancement:

Add a conservative bare `倒X` rule only when the expression is clearly in crochet chain-start context, for example when nearby text contains `ch` / `CH` or when `倒X` is followed by a separator and stitch symbols. Avoid a broad global `倒X` replacement.

Suggested status:

RC21a is not yet complete for promotion. It is close, but should receive a small RC21b parser enhancement for bare `倒X` in crochet-chain context.
