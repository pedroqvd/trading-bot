FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/trading-bot

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app
COPY backtest ./backtest
COPY scripts ./scripts
COPY alembic.ini ./alembic.ini

RUN useradd -r -u 1001 trader && chown -R trader:trader /srv/trading-bot
USER trader

EXPOSE 9108

CMD ["python", "-m", "app.main"]
