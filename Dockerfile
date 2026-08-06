FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt setup.py ./
COPY crochet_intelligence ./crochet_intelligence
COPY knowledge_base ./knowledge_base
COPY pattern_translator ./pattern_translator

RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY railway_start.sh ./railway_start.sh
RUN chmod +x ./railway_start.sh

EXPOSE 8501

CMD ["./railway_start.sh"]
