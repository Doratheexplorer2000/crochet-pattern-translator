"""Primary translation-result delivery helpers."""

from collections.abc import Callable, MutableMapping
from typing import Any, Dict, Tuple


RESULT_STATE_KEY = "rc3_ocr_result"


def store_primary_result(
    session_state: MutableMapping[str, Any],
    result: Dict[str, Any],
) -> None:
    """Commit the primary translation result before optional artifacts."""
    session_state[RESULT_STATE_KEY] = result


def generate_optional_diagnostic_report(
    result: Dict[str, Any],
    builder: Callable[[], str],
) -> Tuple[bool, str]:
    """Attach a diagnostic report without invalidating an existing result."""
    try:
        report = builder()
    except Exception:
        return False, "generation_error"
    result["debug_report_txt"] = report
    return True, "success"
