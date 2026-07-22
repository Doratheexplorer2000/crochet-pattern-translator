"""Fail-safe anonymous usage analytics for Crochet Intelligence apps."""

from __future__ import annotations

import ipaddress
import threading
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Dict, Iterable, Mapping, Optional


SPREADSHEET_NAME = "Crochet Intelligence Usage Analytics"
WORKSHEET_PATTERN_TRANSLATION = "pattern_translation"

ANALYTICS_COLUMNS = [
    "timestamp_utc",
    "session_id",
    "event_type",
    "app_version",
    "interface_language",
    "country",
    "workflow_mode",
    "success",
    "translate_from",
    "translate_to",
    "ocr_box_count",
    "ocr_time_sec",
    "translation_time_sec",
    "session_translation_no",
]

_HEADER_LOCK = threading.Lock()
_HEADER_CHECKED = set()


def _console_log(message: str) -> None:
    try:
        print(f"[analytics] {message}")
    except Exception:
        pass


def _normalize_success(value: object) -> str:
    if value is True:
        return "TRUE"
    if value is False:
        return "FALSE"
    if value in {"TRUE", "FALSE"}:
        return str(value)
    return ""


def _mapping_to_plain_dict(value: object) -> Dict[str, object]:
    try:
        return dict(value)  # Streamlit Secrets/AttrDict objects support this.
    except Exception:
        return {}


def _get_credentials(secrets: object) -> Optional[Dict[str, object]]:
    possible_keys = [
        "gcp_service_account",
        "google_service_account",
        "service_account",
        "analytics_service_account",
    ]
    for key in possible_keys:
        try:
            candidate = secrets.get(key)  # type: ignore[attr-defined]
        except Exception:
            candidate = None
        if candidate:
            credentials = _mapping_to_plain_dict(candidate)
            if credentials:
                return credentials

    root = _mapping_to_plain_dict(secrets)
    required = {"type", "project_id", "private_key", "client_email"}
    if required.issubset(set(root.keys())):
        return root
    return None


def _extract_public_ip(headers: Optional[Mapping[str, object]]) -> Optional[str]:
    if not headers:
        return None
    normalized = {str(k).lower(): str(v) for k, v in dict(headers).items()}
    candidates: Iterable[str] = (
        normalized.get("cf-connecting-ip", ""),
        normalized.get("x-real-ip", ""),
        normalized.get("x-forwarded-for", ""),
        normalized.get("x-appengine-user-ip", ""),
    )
    for candidate in candidates:
        for raw_ip in str(candidate).split(","):
            ip = raw_ip.strip()
            if not ip:
                continue
            try:
                parsed = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if not (
                parsed.is_private
                or parsed.is_loopback
                or parsed.is_link_local
                or parsed.is_reserved
                or parsed.is_multicast
            ):
                return ip
    return None


def resolve_country(headers: Optional[Mapping[str, object]] = None) -> str:
    """Return a country name without storing or returning the user's IP address."""
    ip = _extract_public_ip(headers)
    if not ip:
        return "Unknown"
    try:
        url = f"https://ipapi.co/{ip}/country_name/"
        request = urllib.request.Request(url, headers={"User-Agent": "CrochetIntelligenceAnalytics/1.0"})
        with urllib.request.urlopen(request, timeout=1.0) as response:
            country = response.read(128).decode("utf-8", errors="ignore").strip()
        return country or "Unknown"
    except Exception:
        _console_log("country lookup failed")
        return "Unknown"


def ensure_analytics_session(session_state: object, headers: Optional[Mapping[str, object]] = None) -> None:
    try:
        session_state.setdefault("analytics_session_id", uuid.uuid4().hex)
        session_state.setdefault("analytics_session_translation_no", 1)
        if "analytics_country" not in session_state:
            session_state["analytics_country"] = resolve_country(headers)
        session_state.setdefault("analytics_app_open_logged", False)
    except Exception as exc:
        _console_log(f"session initialization failed: {exc}")


def get_session_translation_no(session_state: object) -> int:
    try:
        return int(session_state.get("analytics_session_translation_no", 1))
    except Exception:
        return 1


def increment_session_translation_no(session_state: object) -> None:
    try:
        session_state["analytics_session_translation_no"] = get_session_translation_no(session_state) + 1
    except Exception as exc:
        _console_log(f"translation counter increment failed: {exc}")


def _ensure_header(worksheet: object, worksheet_name: str) -> None:
    key = f"{SPREADSHEET_NAME}:{worksheet_name}"
    if key in _HEADER_CHECKED:
        return
    with _HEADER_LOCK:
        if key in _HEADER_CHECKED:
            return
        try:
            first_row = worksheet.row_values(1)
            if first_row != ANALYTICS_COLUMNS:
                worksheet.update("A1:N1", [ANALYTICS_COLUMNS])
            _HEADER_CHECKED.add(key)
        except Exception as exc:
            _console_log(f"header check failed: {exc}")


def _append_row(credentials: Dict[str, object], worksheet_name: str, row: Dict[str, str]) -> None:
    try:
        import gspread  # Imported lazily so missing analytics dependencies never break app startup.

        client = gspread.service_account_from_dict(credentials)
        sheet = client.open(SPREADSHEET_NAME)
        worksheet = sheet.worksheet(worksheet_name)
        _ensure_header(worksheet, worksheet_name)
        worksheet.append_row([row.get(column, "") for column in ANALYTICS_COLUMNS], value_input_option="RAW")
    except Exception as exc:
        _console_log(f"Google Sheets append failed: {exc}")


def track_event(
    *,
    session_state: object,
    secrets: object,
    worksheet_name: str,
    event_type: str,
    app_version: str,
    interface_language: str = "",
    country: str = "",
    workflow_mode: str = "",
    success: object = "",
    translate_from: str = "",
    translate_to: str = "",
    ocr_box_count: object = "",
    ocr_time_sec: object = "",
    translation_time_sec: object = "",
    session_translation_no: object = "",
) -> None:
    """Queue one analytics row; all failures are logged to console and ignored."""
    try:
        credentials = _get_credentials(secrets)
        if not credentials:
            _console_log("Google service account credentials not available; event skipped")
            return
        row = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "session_id": str(session_state.get("analytics_session_id", "")),
            "event_type": str(event_type or ""),
            "app_version": str(app_version or ""),
            "interface_language": str(interface_language or ""),
            "country": str(country or session_state.get("analytics_country", "Unknown") or "Unknown"),
            "workflow_mode": str(workflow_mode or ""),
            "success": _normalize_success(success),
            "translate_from": str(translate_from or ""),
            "translate_to": str(translate_to or ""),
            "ocr_box_count": str(ocr_box_count) if ocr_box_count != "" else "",
            "ocr_time_sec": str(ocr_time_sec) if ocr_time_sec != "" else "",
            "translation_time_sec": str(translation_time_sec) if translation_time_sec != "" else "",
            "session_translation_no": str(session_translation_no) if session_translation_no != "" else "",
        }
        thread = threading.Thread(
            target=_append_row,
            args=(credentials, worksheet_name, row),
            daemon=True,
        )
        thread.start()
    except Exception as exc:
        _console_log(f"event queue failed: {exc}")
