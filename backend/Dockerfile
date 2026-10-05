FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY sboard ./sboard

RUN python -m pip install --no-cache-dir . \
    && addgroup --system sboard \
    && adduser --system --ingroup sboard sboard \
    && mkdir -p /app/data \
    && chown -R sboard:sboard /app

USER sboard

EXPOSE 8000
VOLUME ["/app/data"]

CMD ["python", "-m", "sboard"]
