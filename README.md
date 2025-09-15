Stocks Heatmap (Django)

Quickstart

- Create a virtualenv and install Django 4.x
- Run migrations and start the server

Commands

1. python -m venv .venv
2. .venv/Scripts/Activate.ps1  # on Windows PowerShell
3. pip install django
4. python manage.py migrate
5. python manage.py seed_demo   # add demo sectors/tickers/lots and cached quotes
6. python manage.py runserver

Open http://127.0.0.1:8000/

Features

- CRUD: Sectors, Tickers, Purchased Lots (modals)
- Live data via Finnhub (quote, search, profile fallback)
- Debounced search with autocomplete (symbol + company)
- Heatmap grouped by sector; tile color by % change, progress bar between day low/high
- Manual refresh + auto-refresh (Off/1/5/15/30 min) with countdown and last refresh time
- Loading spinners, skeletons, error handling, retries, and timeouts
- Connection status indicator; persists last-good data in localStorage + DB cache
- Responsive, keyboard-friendly, with tooltips

Configuration

- Set an environment variable `FINNHUB_API_KEY` to override the default key baked in settings.
- Optional env vars: `FINNHUB_TIMEOUT_SECONDS`, `FINNHUB_MAX_RETRIES`, `FINNHUB_BACKOFF_FACTOR`.

Notes

- Pre-/post-market price display is supported in the UI but Finnhub’s `/quote` API does not explicitly return extended-hours fields. The UI will show placeholders when unavailable.
- The server caches latest quotes in the DB (`CachedQuote`) for offline fallback; the frontend also caches in localStorage.
- Admin panel is available at `/admin/` for direct DB management.

Authentication

- No default users are created. Create one locally with:
  - `python manage.py createsuperuser`

- For Docker/Compose deployments, you can auto-create an admin by setting env vars before first start (or any time):
  - `DJANGO_SUPERUSER_USERNAME`
  - `DJANGO_SUPERUSER_PASSWORD`
  - `DJANGO_SUPERUSER_EMAIL` (optional)

  The container entrypoint will create or update this superuser after migrations.

  Example (docker compose):

  ```yaml
  services:
    web:
      environment:
        - DJANGO_SETTINGS_MODULE=heatmap.settings
        - FINNHUB_API_KEY=${FINNHUB_API_KEY}
        - ALLOWED_HOSTS=*
        - GUNICORN_WORKERS=3
        - SQLITE_DIR=/app/db
        - CSRF_TRUSTED_ORIGINS=${CSRF_TRUSTED_ORIGINS}
        - DJANGO_SUPERUSER_USERNAME=admin
        - DJANGO_SUPERUSER_PASSWORD=change-me
        - DJANGO_SUPERUSER_EMAIL=admin@example.com
  ```

Login URLs

- App login: `/accounts/login/`
- Admin site: `/admin/`
# heatmap1.0
