#!/usr/bin/env sh
set -e

# Optional: wait for DB if using Postgres
if [ -n "${DATABASE_URL:-}" ]; then
  case "$DATABASE_URL" in
    postgres://*|postgresql://*)
      echo "Waiting for Postgres to be ready..."
      python - <<'PY'
import os, time
from urllib.parse import urlparse
import psycopg2

url = os.environ.get('DATABASE_URL')
timeout = int(os.environ.get('DB_WAIT_TIMEOUT', '60'))
parsed = urlparse(url)

start = time.time()
while True:
    try:
        conn = psycopg2.connect(
            dbname=parsed.path.lstrip('/'),
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port or 5432,
        )
        conn.close()
        print('Postgres is ready')
        break
    except Exception as e:
        if time.time() - start > timeout:
            print(f'DB not ready after {timeout}s: {e}')
            raise
        print('Waiting for DB...', e)
        time.sleep(2)
PY
      ;;
  esac
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput || true

exec gunicorn heatmap.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers ${GUNICORN_WORKERS:-3} \
  --timeout 60
