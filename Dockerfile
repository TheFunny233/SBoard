FROM node:24-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y nginx supervisor \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/pyproject.toml backend/README.md ./
COPY backend/sboard ./sboard
RUN python -m pip install --no-cache-dir . \
    && addgroup --system sboard \
    && adduser --system --ingroup sboard sboard \
    && mkdir -p /app/data \
    && chown -R sboard:sboard /app

COPY --from=frontend-build /frontend/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/sites-available/default
COPY docker/supervisord.conf /etc/supervisor/conf.d/sboard.conf

RUN rm -f /etc/nginx/sites-enabled/default \
    && ln -s /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default

VOLUME ["/app/data"]
EXPOSE 80

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
