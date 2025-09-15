FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps (build tools optional but handy for some wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better caching
COPY requirements.txt ./
RUN pip install -r requirements.txt && \
    pip install gunicorn whitenoise

# Copy app
COPY . .

# Collect static (safe if no static pipeline)
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

# Environment (override in runtime)
ENV DJANGO_SETTINGS_MODULE=heatmap.settings \
    ALLOWED_HOSTS=* \
    GUNICORN_WORKERS=3

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]

