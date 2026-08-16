#!/usr/bin/env bash
set -euo pipefail

APP_PORT="${PORT:-8501}"
export STREAMLIT_SERVER_DISCONNECTED_SESSION_TTL="${STREAMLIT_SERVER_DISCONNECTED_SESSION_TTL:-900}"

if [[ -n "${GCP_SERVICE_ACCOUNT_JSON_B64:-}" ]]; then
  mkdir -p .streamlit
  python - <<'PY'
import base64
import json
import os
from pathlib import Path

encoded = os.environ.get("GCP_SERVICE_ACCOUNT_JSON_B64", "").strip()
credentials = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))

required_keys = [
    "type",
    "project_id",
    "private_key_id",
    "private_key",
    "client_email",
    "client_id",
    "auth_uri",
    "token_uri",
    "auth_provider_x509_cert_url",
    "client_x509_cert_url",
]

missing = [key for key in required_keys if key not in credentials]
if missing:
    raise RuntimeError("Google service account JSON is missing required keys")

def toml_string(value: object) -> str:
    return json.dumps(str(value))

lines = ["[gcp_service_account]"]
for key in required_keys:
    if key == "private_key":
        lines.append(f'{key} = """{credentials[key]}"""')
    else:
        lines.append(f"{key} = {toml_string(credentials[key])}")

Path(".streamlit/secrets.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
fi

if command -v streamlit >/dev/null 2>&1; then
  exec streamlit run pattern_translator/app.py --server.address=0.0.0.0 --server.port="${APP_PORT}"
fi

if command -v python >/dev/null 2>&1; then
  exec python -m streamlit run pattern_translator/app.py --server.address=0.0.0.0 --server.port="${APP_PORT}"
fi

exec python3 -m streamlit run pattern_translator/app.py --server.address=0.0.0.0 --server.port="${APP_PORT}"
