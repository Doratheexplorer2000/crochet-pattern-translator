FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY stitch_translator/requirements.txt ./stitch_translator/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r stitch_translator/requirements.txt

COPY knowledge_base ./knowledge_base
COPY crochet_intelligence ./crochet_intelligence
COPY stitch_translator ./stitch_translator

RUN chmod +x ./stitch_translator/railway_start.sh

EXPOSE 8501

CMD ["./stitch_translator/railway_start.sh"]
