FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils libgomp1 libglib2.0-0 libsm6 libxrender1 libxext6 libgl1 wget \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && useradd -r -u 1001 -m vera

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts

RUN chown -R vera:vera /app

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

USER vera
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info", "--access-log"]
