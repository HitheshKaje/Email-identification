FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    WEB_CONCURRENCY=1

WORKDIR /app

# Run as non-root application user
RUN addgroup --system jobmail && adduser --system --ingroup jobmail jobmail

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/backend/requirements.txt

COPY backend/app /app/backend/app
COPY backend/scripts /app/backend/scripts
COPY ml /app/ml

# Pre-train classifier artifact during image build so runtime startup is fast and read-only compatible
RUN python /app/ml/training/train_model.py && chown -R jobmail:jobmail /app
USER jobmail

WORKDIR /app/backend
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD python -c "import os, httpx; port = os.environ.get('PORT', '8000'); r = httpx.get(f'http://127.0.0.1:{port}/health', timeout=3.0); raise SystemExit(0 if r.status_code == 200 else 1)"

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --workers \"${WEB_CONCURRENCY:-1}\" --proxy-headers"]
