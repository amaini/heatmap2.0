import os
from pathlib import Path
from urllib.parse import urlparse

# Optional WhiteNoise support (guarded for dev machines without the package)
try:
    import whitenoise  # noqa: F401
    HAS_WHITENOISE = True
except Exception:
    HAS_WHITENOISE = False


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-heatmap-local-dev-key'
)

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'market',
]
if HAS_WHITENOISE:
    INSTALLED_APPS.append('whitenoise.runserver_nostatic')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
if HAS_WHITENOISE:
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

ROOT_URLCONF = 'heatmap.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'heatmap.wsgi.application'


def db_from_env():
    url = os.environ.get('DATABASE_URL')
    if not url:
        return None
    parsed = urlparse(url)
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': parsed.path.lstrip('/'),
        'USER': parsed.username,
        'PASSWORD': parsed.password,
        'HOST': parsed.hostname,
        'PORT': parsed.port or '5432',
        'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '60')),
    }


pg = db_from_env()
sqlite_dir = os.environ.get('SQLITE_DIR')
sqlite_path = (Path(sqlite_dir) / 'db.sqlite3') if sqlite_dir else (BASE_DIR / 'db.sqlite3')

DATABASES = {
    'default': pg or {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': sqlite_path,
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
if HAS_WHITENOISE:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Finnhub configuration
FINNHUB_API_KEY = os.environ.get(
    'FINNHUB_API_KEY',
    # Provided key; you can override with env var
    'SignUp to Finnhub'
)
FINNHUB_BASE_URL = os.environ.get('FINNHUB_BASE_URL', 'https://finnhub.io/api/v1')
FINNHUB_TIMEOUT_SECONDS = int(os.environ.get('FINNHUB_TIMEOUT_SECONDS', '10'))
FINNHUB_MAX_RETRIES = int(os.environ.get('FINNHUB_MAX_RETRIES', '3'))
FINNHUB_BACKOFF_FACTOR = float(os.environ.get('FINNHUB_BACKOFF_FACTOR', '0.75'))
FINNHUB_METRICS_TTL_SECONDS = int(os.environ.get('FINNHUB_METRICS_TTL_SECONDS', '21600'))
FINNHUB_MAX_CONCURRENCY = int(os.environ.get('FINNHUB_MAX_CONCURRENCY', '4'))
FINNHUB_QUOTE_TTL_SECONDS = int(os.environ.get('FINNHUB_QUOTE_TTL_SECONDS', '10'))

# CSRF in local dev
def _parse_list_env(name: str) -> list[str]:
    raw = os.environ.get(name, '').strip()
    if not raw:
        return []
    # Support comma or semicolon separated
    parts = [p.strip() for p in raw.replace(';', ',').split(',') if p.strip()]
    return parts

# CSRF: allow configuring trusted origins for HTTPS reverse proxies (e.g., Nginx)
CSRF_TRUSTED_ORIGINS = _parse_list_env('CSRF_TRUSTED_ORIGINS') or [
    'http://localhost',
    'http://127.0.0.1',
]

# Respect X-Forwarded-Proto from reverse proxies to correctly detect HTTPS
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Authentication
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'
