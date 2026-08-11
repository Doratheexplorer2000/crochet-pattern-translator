import unittest
from pathlib import Path


class PortalRoutingTests(unittest.TestCase):
    def test_production_tool_destinations_remain_configured(self):
        dockerfile = Path("portal/Dockerfile").read_text(encoding="utf-8")

        self.assertIn(
            "ARG PUBLIC_STITCH_TRANSLATOR_URL="
            "https://stitch-translator-production.up.railway.app/",
            dockerfile,
        )
        self.assertIn("ARG PUBLIC_PATTERN_TRANSLATOR_URL=", dockerfile)


if __name__ == "__main__":
    unittest.main()
