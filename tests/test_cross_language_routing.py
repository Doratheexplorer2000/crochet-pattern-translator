import os
import unittest
from unittest import mock

import pandas as pd

from pattern_translator.engine import broad_translation
from pattern_translator.engine import line_translation
from pattern_translator.engine import ocr_lines


ROUTES = {
    ("English — US", "English — UK"),
    ("English — US", "Traditional Chinese"),
    ("English — US", "Simplified Chinese"),
    ("English — US", "Japanese"),
    ("English — UK", "English — US"),
    ("English — UK", "Traditional Chinese"),
    ("English — UK", "Simplified Chinese"),
    ("English — UK", "Japanese"),
    ("Simplified Chinese", "English — US"),
    ("Simplified Chinese", "English — UK"),
    ("Simplified Chinese", "Traditional Chinese"),
    ("Simplified Chinese", "Japanese"),
    ("Traditional Chinese", "English — US"),
    ("Traditional Chinese", "English — UK"),
    ("Traditional Chinese", "Simplified Chinese"),
    ("Traditional Chinese", "Japanese"),
    ("Japanese", "English — US"),
    ("Japanese", "English — UK"),
    ("Japanese", "Traditional Chinese"),
    ("Japanese", "Simplified Chinese"),
}

LANGUAGES = {
    "English — US",
    "English — UK",
    "Traditional Chinese",
    "Simplified Chinese",
    "Japanese",
}


def _ocr_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "text": "R1: 6 sc",
                "confidence": 0.98,
                "x": 10.0,
                "y": 0.0,
                "min_x": 10.0,
                "max_x": 410.0,
                "min_y": 0.0,
                "max_y": 24.0,
            }
        ]
    )


def _broad_result() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Original": "R1: 6 sc",
                "Translation": "translated",
                "Confidence": 0.98,
                "Changed": "✓",
                "Validation Status": "validated",
                "Validation Failure Reason": "",
                "min_x": 10.0,
                "max_x": 410.0,
                "min_y": 0.0,
                "max_y": 24.0,
            }
        ]
    )


class CrossLanguageBroadRoutingTests(unittest.TestCase):
    def test_broad_matrix_is_exactly_twenty_unique_routes(self):
        self.assertEqual(ROUTES, set(broad_translation._ROUTE_CONFIGS))
        self.assertEqual(20, len(ROUTES))
        self.assertEqual(20, len(broad_translation._ROUTE_CONFIGS))

    def test_every_cross_language_pair_and_no_same_language_pair_is_broad(self):
        all_directed = {
            (source, target)
            for source in LANGUAGES
            for target in LANGUAGES
            if source != target
        }
        self.assertEqual(all_directed, ROUTES)
        for route in all_directed:
            with self.subTest(route=route):
                self.assertTrue(
                    broad_translation.is_broad_translation_route(*route)
                )
        for language in LANGUAGES:
            with self.subTest(language=language):
                self.assertFalse(
                    broad_translation.is_broad_translation_route(
                        language,
                        language,
                    )
                )

    @mock.patch.dict(
        os.environ,
        {
            "PATTERN_BROAD_TRANSLATION_ENABLED": "1",
            "OPENAI_API_KEY": "test-key",
        },
        clear=False,
    )
    def test_all_twenty_routes_enter_the_same_broad_provider_architecture(self):
        for source_mode, output_mode in sorted(ROUTES):
            with self.subTest(route=(source_mode, output_mode)), mock.patch.object(
                broad_translation,
                "translate_merged_ocr_lines_broad",
                return_value=_broad_result(),
            ) as broad_provider, mock.patch.object(
                line_translation,
                "translate_ocr_line",
                side_effect=AssertionError("legacy deterministic path"),
            ) as legacy:
                result = ocr_lines.build_ocr_line_translations(
                    _ocr_rows(),
                    {},
                    pd.DataFrame(),
                    output_mode,
                    source_mode,
                )
                broad_provider.assert_called_once()
                self.assertEqual(
                    source_mode,
                    broad_provider.call_args.kwargs["source_mode"],
                )
                self.assertEqual(
                    output_mode,
                    broad_provider.call_args.kwargs["output_mode"],
                )
                legacy.assert_not_called()
                self.assertEqual("translated", result.loc[0, "Translation"])

    @mock.patch.dict(
        os.environ,
        {"PATTERN_BROAD_TRANSLATION_ENABLED": "0"},
        clear=False,
    )
    def test_feature_flag_off_preserves_legacy_routing_for_supported_route(self):
        with mock.patch.object(
            broad_translation,
            "translate_merged_ocr_lines_broad",
            side_effect=AssertionError("Broad must be off"),
        ) as broad_provider, mock.patch.object(
            line_translation,
            "translate_ocr_line",
            return_value="legacy",
        ) as legacy:
            result = ocr_lines.build_ocr_line_translations(
                _ocr_rows(),
                {},
                pd.DataFrame(),
                "Japanese",
                "English — US",
            )
        broad_provider.assert_not_called()
        legacy.assert_called()
        self.assertEqual("legacy", result.loc[0, "Translation"])

    @mock.patch.dict(
        os.environ,
        {"PATTERN_BROAD_TRANSLATION_ENABLED": "1"},
        clear=False,
    )
    def test_same_language_route_remains_legacy_when_flag_is_on(self):
        with mock.patch.object(
            broad_translation,
            "translate_merged_ocr_lines_broad",
            side_effect=AssertionError("unsupported route entered Broad"),
        ) as broad_provider, mock.patch.object(
            line_translation,
            "translate_ocr_line",
            return_value="legacy",
        ) as legacy:
            result = ocr_lines.build_ocr_line_translations(
                _ocr_rows(),
                {},
                pd.DataFrame(),
                "Japanese",
                "Japanese",
            )
        broad_provider.assert_not_called()
        legacy.assert_called()
        self.assertEqual("legacy", result.loc[0, "Translation"])


if __name__ == "__main__":
    unittest.main()
