FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

# Dépendances minimales; Playwright installe ensuite les libs Chromium exactes.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements/crawler.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash pwuser
COPY apps/crawler /app/apps/crawler
COPY apps/api /app/apps/api
COPY libs /app/libs
COPY scrapy.cfg /app/scrapy.cfg

USER pwuser
CMD ["python", "-m", "apps.crawler.worker"]
