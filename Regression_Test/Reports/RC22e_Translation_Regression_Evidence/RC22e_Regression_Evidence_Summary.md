# RC22e Translation Pipeline Regression Evidence

Scope: translation pipeline consistency for counted shorthand tokens.

Overlay unchanged for all tested patterns; overlay PNGs were not regenerated because RC22e does not modify overlay rendering or placement.

## Summary Table

| Pattern | Changed | Result |
|---|---:|---|
| Pattern_008 - French Rose Notes | Yes | PASS - 2SL correctly translated after chain-start parser |
| Pattern_008_SelectArea - French Rose Notes Select Area | Yes | PASS - 2SL correctly translated after chain-start parser |
| Pattern_001 - Alien | Yes | FAIL - unintended mm measurement formatting regression |
| Pattern_005 - Flowerpot Soil Block | No | PASS - no translation difference |
| Targeted_Count_Tokens - Counted Token Corpus | Yes | PASS - affected counted token corrected |
| Targeted_English_US_to_UK - English Source Counted Token Corpus | No | PASS - no translation difference |

## Affected Lines

### Pattern_008 - French Rose Notes
- Line 24: `R5：立9CH，倒2回钩2SL，X.2T2FE.空2针引`
  - Before RC22c: `R5: 立9 ch, Start in the 2nd chain from hook 2SL, sc, 2T2FE, 空2 sts引`
  - After RC22e: `R5: 立9 ch, Start in the 2nd chain from hook 2 sl st, sc, 2T2FE, 空2 sts引`

### Pattern_008_SelectArea - French Rose Notes Select Area
- Line 8: `R5:立9CH,倒2回钩2SL，X,2T，2FE，空2针引`
  - Before RC22c: `R5: 立9 ch, Start in the 2nd chain from hook 2SL, sc, 2 hdc, 2 FPtr, 空2 sts引`
  - After RC22e: `R5: 立9 ch, Start in the 2nd chain from hook 2 sl st, sc, 2 hdc, 2 FPtr, 空2 sts引`

### Pattern_001 - Alien
- Line 1: `材料：2.5mm 钩针.黑色不织布.4mm 眼睛.填充棉`
  - Before RC22c: `材料:2.5mm hook, 黑色不织布, 4mm 眼睛, 填充棉`
  - After RC22e: `材料:2.5 MM hook, 黑色不织布, 4 MM 眼睛, 填充棉`
  - Finding: unintended regression. The counted-token regex is too broad and matches the trailing `mm` unit in hook-size measurements.

### Targeted_Count_Tokens - Counted Token Corpus
- Line 8: `倒2回鈎2SL`
  - Before RC22c: `Start in the 2nd chain from hook 2SL`
  - After RC22e: `Start in the 2nd chain from hook 2 sl st`

## Future Engineering Standard

- Translation-related RC: provide before/after translation TXT or Markdown evidence.
- Overlay-related RC: provide before/after overlay PNG evidence.
- OCR-related RC: provide before/after OCR TXT evidence.
- Performance RC: provide timing comparison.
- Parser RC: include at least one real pattern translation result, not only unit tests.
