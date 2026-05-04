FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEBREFURB_STATE_ROOT=/app/state \
    WEBREFURB_SEARCH_PROVIDER=webserper

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY pipeline ./pipeline
COPY dashboard ./dashboard
COPY assets ./assets
COPY docs ./docs
COPY email_discovery.yaml ./email_discovery.yaml
COPY menu.html ./menu.html

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

RUN mkdir -p /app/state /app/dashboard/static

EXPOSE 8000

CMD ["uvicorn", "dashboard.app:app", "--host", "0.0.0.0", "--port", "8000"]
