# RC24b Translation Function Profiling Evidence

## RC23a English HDC Android Whole Pattern
- Source diagnostic: `/Users/doralam/Downloads/PatternOCR_DiagnosticReport_RC23a_20260717_122144.txt`
- Translation wall time in profiling harness: `84.091s`
- OCR lines profiled: `29`

| Function | Calls | Inclusive sec | Self sec | Avg ms | Max ms | % wall inclusive |
|---|---:|---:|---:|---:|---:|---:|
| `translate_expression` | 142 | 126.659 | 0.107 | 891.963 | 3172.926 | 150.6% |
| `build_ocr_line_translations` | 1 | 84.074 | 0.025 | 84074.174 | 84074.174 | 100.0% |
| `translate_ocr_line` | 29 | 84.012 | 0.016 | 2896.971 | 3935.067 | 99.9% |
| `replace_csv_terms_in_line` | 111 | 83.622 | 12.322 | 753.350 | 920.579 | 99.4% |
| `lookup_term` | 55163 | 66.088 | 0.779 | 1.198 | 16.543 | 78.6% |
| `lookup_row` | 55269 | 65.436 | 65.002 | 1.184 | 16.494 | 77.8% |
| `translate_piece` | 110 | 57.815 | 0.185 | 525.589 | 846.862 | 68.8% |
| `get_all_csv_terms` | 111 | 3.195 | 3.037 | 28.785 | 186.178 | 3.8% |
| `norm_text` | 314520 | 2.421 | 2.421 | 0.008 | 0.415 | 2.9% |
| `generate_all_csv_terms_uncached` | 1 | 0.158 | 0.145 | 158.463 | 158.463 | 0.2% |

Repeated work summary:
- `norm_text`: total `314520`, unique `717`, top5 `[('前半针', 1332), ('后半针', 1332), ('slip marker', 893), ('開始', 891), ('花樣', 891)]`
- `lookup_term`: total `55163`, unique `497`, top5 `[('slst', 112), ('start from ... chain from hook|start in the ... chain from hook|work in the ... chain from hook', 111), ('in flo|front loop only|front loops only|work in front loop only|work in front loops only', 111), ('join with slst|join with a slip stitch|join with a sl st|join with a slst|join with a ss', 111), ('in blo|back loop only|back loops only|work in back loop only|work in back loops only', 111)]`
- `lookup_row`: total `55269`, unique `497`, top5 `[('hdc', 217), ('slst', 112), ('start from ... chain from hook|start in the ... chain from hook|work in the ... chain from hook', 111), ('in flo|front loop only|front loops only|work in front loop only|work in front loops only', 111), ('join with slst|join with a slip stitch|join with a sl st|join with a slst|join with a ss', 111)]`
- `replace_csv_terms_in_line`: total `111`, unique `76`, top5 `[('hdc dec', 26), ('hdc inc', 4), ('Etsy:', 2), ('Body (hook 6mm)', 2), ('Barunka', 2)]`

## RC16f Fisherman Hat Whole Pattern
- Source diagnostic: `/Users/doralam/Downloads/PatternOCR_DiagnosticReport_RC16f_20260703_115510.txt`
- Translation wall time in profiling harness: `22.272s`
- OCR lines profiled: `33`

| Function | Calls | Inclusive sec | Self sec | Avg ms | Max ms | % wall inclusive |
|---|---:|---:|---:|---:|---:|---:|
| `build_ocr_line_translations` | 1 | 22.266 | 0.023 | 22266.395 | 22266.395 | 100.0% |
| `translate_ocr_line` | 33 | 22.240 | 0.002 | 673.944 | 1527.113 | 99.9% |
| `replace_csv_terms_in_line` | 34 | 22.176 | 0.412 | 652.221 | 861.679 | 99.6% |
| `lookup_term` | 16903 | 20.134 | 0.211 | 1.191 | 2.560 | 90.4% |
| `lookup_row` | 16927 | 19.951 | 19.824 | 1.179 | 2.288 | 89.6% |
| `get_all_csv_terms` | 34 | 1.087 | 0.928 | 31.975 | 186.662 | 4.9% |
| `translate_expression` | 61 | 0.774 | 0.003 | 12.684 | 664.817 | 3.5% |
| `translate_piece` | 48 | 0.722 | 0.004 | 15.041 | 663.481 | 3.2% |
| `norm_text` | 97643 | 0.711 | 0.711 | 0.007 | 0.356 | 3.2% |
| `generate_all_csv_terms_uncached` | 1 | 0.159 | 0.145 | 159.088 | 159.088 | 0.7% |

Repeated work summary:
- `norm_text`: total `97643`, unique `596`, top5 `[('3 sc in same stitch', 445), ('hdc inc', 411), ('hdc dec', 411), ('sl st', 379), ('bl', 379)]`
- `lookup_term`: total `16903`, unique `498`, top5 `[('start from ... chain from hook|start in the ... chain from hook|work in the ... chain from hook', 34), ('in flo|front loop only|front loops only|work in front loop only|work in front loops only', 34), ('join with slst|join with a slip stitch|join with a sl st|join with a slst|join with a ss', 34), ('in blo|back loop only|back loops only|work in back loop only|work in back loops only', 34), ('leave long end to weave in|leave for sewing|leave for assembly|leave for now', 34)]`
- `lookup_row`: total `16927`, unique `500`, top5 `[('start from ... chain from hook|start in the ... chain from hook|work in the ... chain from hook', 34), ('in flo|front loop only|front loops only|work in front loop only|work in front loops only', 34), ('join with slst|join with a slip stitch|join with a sl st|join with a slst|join with a ss', 34), ('in blo|back loop only|back loops only|work in back loop only|work in back loops only', 34), ('leave long end to weave in|leave for sewing|leave for assembly|leave for now', 34)]`
- `replace_csv_terms_in_line`: total `34`, unique `33`, top5 `[('拉菲草渔夫帽', 2), ('R1:环起8x', 1), ('R2:8v', 1), ('R3:8(×.v)', 1), ('R4:8(2×.v)', 1)]`
