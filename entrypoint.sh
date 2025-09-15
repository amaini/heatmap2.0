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

# Optionally create a superuser on first run
if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  echo "Ensuring Django superuser ${DJANGO_SUPERUSER_USERNAME} exists..."
  python - <<'PY'
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL') or f"{username}@example.com"
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

u, created = User.objects.get_or_create(username=username, defaults={
    'email': email,
    'is_staff': True,
    'is_superuser': True,
})
if not created:
    # Make sure it retains admin privileges
    u.is_staff = True
    u.is_superuser = True
u.email = email
u.set_password(password)
u.save()
print(f"Superuser '{username}' {'created' if created else 'updated'}.")
PY
fi

exec gunicorn heatmap.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers ${GUNICORN_WORKERS:-3} \
  --timeout 60
