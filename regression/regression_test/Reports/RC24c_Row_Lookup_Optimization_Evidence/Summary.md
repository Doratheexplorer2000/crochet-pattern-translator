# RC24c Row Lookup Optimization Evidence

## RC23a English HDC Android Whole Pattern
- Source diagnostic: `/Users/doralam/Downloads/PatternOCR_DiagnosticReport_RC23a_20260717_122144.txt`
- Translation wall time in profiling harness: `24.215s`
- OCR lines profiled: `29`

| Function | Calls | Inclusive sec | Self sec | Avg ms | Max ms | % wall inclusive |
|---|---:|---:|---:|---:|---:|---:|
| `translate_expression` | 142 | 36.019 | 0.110 | 253.653 | 915.502 | 148.7% |
| `build_ocr_line_translations` | 1 | 24.176 | 0.023 | 24175.777 | 24175.777 | 99.8% |
| `translate_ocr_line` | 29 | 24.117 | 0.021 | 831.613 | 1133.913 | 99.6% |
| `replace_csv_terms_in_line` | 111 | 23.799 | 11.693 | 214.407 | 453.412 | 98.3% |
| `translate_piece` | 110 | 16.745 | 0.181 | 152.230 | 251.711 | 69.2% |
| `get_all_csv_terms` | 111 | 9.048 | 8.890 | 81.512 | 185.586 | 37.4% |
| `norm_text` | 314520 | 2.313 | 2.313 | 0.007 | 1.814 | 9.6% |
| `lookup_term` | 55163 | 1.180 | 0.297 | 0.021 | 129.636 | 4.9% |
| `lookup_row` | 55269 | 0.883 | 0.468 | 0.016 | 129.619 | 3.6% |
| `generate_all_csv_terms_uncached` | 1 | 0.158 | 0.144 | 158.202 | 158.202 | 0.7% |

Repeated work summary:
- `norm_text`: total `314520`, unique `717`, top5 `[('前半针', 1332), ('后半针', 1332), ('slip marker', 893), ('開始', 891), ('花樣', 891)]`
- `lookup_term`: total `55163`, unique `497`, top5 `[('slst', 112), ('start from ... chain from hook|start in the ... chain from hook|work in the ... chain from hook', 111), ('in flo|front loop only|front loops only|work in front loop only|work in front loops only', 111), ('join with slst|join with a slip stitch|join with a sl st|join with a slst|join with a ss', 111), ('in blo|back loop only|back loops only|work in back loop only|work in back loops only', 111)]`
- `lookup_row`: total `55269`, unique `497`, top5 `[('hdc', 217), ('slst', 112), ('start from ... chain from hook|start in the ... chain from hook|work in the ... chain from hook', 111), ('in flo|front loop only|front loops only|work in front loop only|work in front loops only', 111), ('join with slst|join with a slip stitch|join with a sl st|join with a slst|join with a ss', 111)]`
- `replace_csv_terms_in_line`: total `111`, unique `76`, top5 `[('hdc dec', 26), ('hdc inc', 4), ('Etsy:', 2), ('Body (hook 6mm)', 2), ('Barunka', 2)]`

## RC16f Fisherman Hat Whole Pattern
- Source diagnostic: `/Users/doralam/Downloads/PatternOCR_DiagnosticReport_RC16f_20260703_115510.txt`
- Translation wall time in profiling harness: `4.208s`
- OCR lines profiled: `33`

| Function | Calls | Inclusive sec | Self sec | Avg ms | Max ms | % wall inclusive |
|---|---:|---:|---:|---:|---:|---:|
| `build_ocr_line_translations` | 1 | 4.200 | 0.023 | 4199.607 | 4199.607 | 99.8% |
| `translate_ocr_line` | 33 | 4.174 | 0.002 | 126.472 | 528.689 | 99.2% |
| `replace_csv_terms_in_line` | 34 | 4.163 | 0.367 | 122.433 | 397.219 | 98.9% |
| `get_all_csv_terms` | 34 | 2.851 | 2.693 | 83.856 | 185.510 | 67.8% |
| `norm_text` | 97643 | 0.673 | 0.673 | 0.007 | 0.350 | 16.0% |
| `lookup_term` | 16903 | 0.407 | 0.071 | 0.024 | 125.163 | 9.7% |
| `lookup_row` | 16927 | 0.336 | 0.217 | 0.020 | 125.151 | 8.0% |
| `generate_all_csv_terms_uncached` | 1 | 0.158 | 0.144 | 158.498 | 158.498 | 3.8% |
| `translate_expression` | 61 | 0.138 | 0.003 | 2.254 | 130.882 | 3.3% |
| `translate_piece` | 48 | 0.132 | 0.004 | 2.751 | 129.571 | 3.1% |

Repeated work summary:
- `norm_text`: total `97643`, unique `596`, top5 `[('3 sc in same stitch', 445), ('hdc inc', 411), ('hdc dec', 411), ('sl st', 379), ('bl', 379)]`
- `lookup_term`: total `16903`, unique `498`, top5 `[('start from ... chain from hook|start in the ... chain from hook|work in the ... chain from hook', 34), ('in flo|front loop only|front loops only|work in front loop only|work in front loops only', 34), ('join with slst|join with a slip stitch|join with a sl st|join with a slst|join with a ss', 34), ('in blo|back loop only|back loops only|work in back loop only|work in back loops only', 34), ('leave long end to weave in|leave for sewing|leave for assembly|leave for now', 34)]`
- `lookup_row`: total `16927`, unique `500`, top5 `[('start from ... chain from hook|start in the ... chain from hook|work in the ... chain from hook', 34), ('in flo|front loop only|front loops only|work in front loop only|work in front loops only', 34), ('join with slst|join with a slip stitch|join with a sl st|join with a slst|join with a ss', 34), ('in blo|back loop only|back loops only|work in back loop only|work in back loops only', 34), ('leave long end to weave in|leave for sewing|leave for assembly|leave for now', 34)]`
- `replace_csv_terms_in_line`: total `34`, unique `33`, top5 `[('拉菲草渔夫帽', 2), ('R1:环起8x', 1), ('R2:8v', 1), ('R3:8(×.v)', 1), ('R4:8(2×.v)', 1)]`
