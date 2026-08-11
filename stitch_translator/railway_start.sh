#!/usr/bin/env bash
set -euo pipefail

APP_PORT="${PORT:-8501}"

exec python -m streamlit run stitch_translator/app.py \
    --server.address=0.0.0.0 \
    --server.port="${APP_PORT}" \
    --client.toolbarMode=minimal \
    --theme.primaryColor="#0F766E"
