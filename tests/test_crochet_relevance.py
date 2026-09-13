import unittest

import pandas as pd

from pattern_translator.engine.crochet_relevance import evaluate_crochet_relevance


class CrochetRelevanceGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.glossary = pd.read_csv(
            "knowledge_base/data/master_stitches.csv"
        ).fillna("")

    def assertAllowed(self, text: str) -> None:
        result = evaluate_crochet_relevance(text, self.glossary)
        self.assertTrue(result.evaluated)
        self.assertTrue(result.allowed, result)

    def test_actual_mineral_water_ocr_is_rejected(self):
        text = """
        Warning Carbonated Inatural mineral water
        covering cap Pressurised container Open with care
        STORAGE sunlight strong Store in godours acool dry place away from direct
        For Best before see neck keep refrigerated and consume within 3 days
        COMPOSITION Typical values Per litre as sold Calcium Magnesium Potassium
        Sodium Bicarbonate Sulphate Nitrate Chloride Dry Residue pH at source
        Recycling Recycle Bottled at source Tesco Stores Ltd Tesco Ireland Ltd
        """
        result = evaluate_crochet_relevance(text, self.glossary)
        self.assertTrue(result.evaluated)
        self.assertFalse(result.allowed)
        self.assertEqual("readable_text_without_crochet_evidence", result.reason)
        self.assertEqual(0, result.glossary_hit_count)
        self.assertEqual(0, result.structure_signal_count)

    def test_normal_english_pattern_is_allowed(self):
        self.assertAllowed("Round 1: 6 sc in magic ring. Round 2: inc in each stitch (12).")

    def test_traditional_chinese_pattern_is_allowed(self):
        self.assertAllowed("第1圈：環狀起針，6短針。第2圈：每針加針，共12針。")

    def test_simplified_chinese_pattern_is_allowed(self):
        self.assertAllowed("第1圈：环状起针，6短针。第2圈：每针加针，共12针。")

    def test_japanese_pattern_is_allowed(self):
        self.assertAllowed("1段目：輪の作り目に細編み6目。2段目：各目に細編み2目。")

    def test_crochet_notes_prose_is_allowed_without_row_formulas(self):
        self.assertAllowed(
            "注意事項。本花樣採用美式鈎針術語編寫。本花樣以連續圈鈎織。"
            "安全眼不適合三歲以下兒童。YouTube 教學。"
        )

    def test_compact_symbolic_pattern_is_allowed_by_combined_structure(self):
        self.assertAllowed("花苞 R1: 6X R2: 6V R3: (X,V)*6 R4: (2X,V)*6")

    def test_ordinary_non_crochet_prose_is_rejected(self):
        result = evaluate_crochet_relevance(
            "Quarterly planning notes. The committee reviewed the budget, "
            "approved the schedule, and assigned follow-up actions.",
            self.glossary,
        )
        self.assertFalse(result.allowed)

    def test_sparse_zero_signal_text_is_rejected(self):
        for text in ("LIBRARY", "EXIT", "SCHOOL", "PARKING", "HELLO"):
            with self.subTest(text=text):
                result = evaluate_crochet_relevance(text, self.glossary)
                self.assertTrue(result.evaluated)
                self.assertFalse(result.allowed)
                self.assertEqual(
                    "readable_text_without_crochet_evidence", result.reason
                )
                self.assertEqual(0, result.glossary_hit_count)
                self.assertEqual(0, result.structure_signal_count)
                self.assertEqual(0, result.explicit_domain_signal_count)

    def test_sparse_text_with_existing_crochet_evidence_is_allowed(self):
        for text in ("R1: 6 sc", "Magic ring", "短針", "第1圈", "鈎針"):
            with self.subTest(text=text):
                result = evaluate_crochet_relevance(text, self.glossary)
                self.assertTrue(result.allowed, result)
                self.assertGreater(
                    result.glossary_hit_count
                    + result.structure_signal_count
                    + result.explicit_domain_signal_count,
                    0,
                )

    def test_count_plus_active_glossary_abbreviation_is_a_structure_signal(self):
        for text in ("8F", "6X", "12FV", "4FA", "8f", "6x", "12fv", "4fa"):
            with self.subTest(text=text):
                result = evaluate_crochet_relevance(text, self.glossary)
                self.assertTrue(result.allowed, result)
                self.assertEqual(1, result.structure_signal_count)

    def test_counted_abbreviation_signal_is_data_driven(self):
        custom = self.glossary.copy()
        custom.loc[custom.index[0], "Chinese_abb"] = "ZZ"
        self.assertFalse(evaluate_crochet_relevance("3ZZ", self.glossary).allowed)
        result = evaluate_crochet_relevance("3ZZ", custom)
        self.assertTrue(result.allowed)
        self.assertEqual(1, result.structure_signal_count)

    def test_no_text_defers_to_existing_path(self):
        result = evaluate_crochet_relevance("", self.glossary)
        self.assertFalse(result.evaluated)
        self.assertTrue(result.allowed)
        self.assertEqual("no_usable_text_existing_path", result.reason)

    def test_sparse_and_weak_cases_are_allowed(self):
        self.assertAllowed("R1")
        self.assertAllowed("Round 1 of voting is complete for the annual awards.")


if __name__ == "__main__":
    unittest.main()
