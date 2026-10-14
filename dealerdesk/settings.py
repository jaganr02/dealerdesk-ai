"""
Django settings for dealerdesk project.

DealerDesk: B2B dealer ordering backend for Bengaluru automotive parts distributor.
"""

import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env if present
load_dotenv(BASE_DIR / ".env")

# Security settings
SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-dealerdesk-dev-key-change-in-production-only-600sku"
)

DEBUG = os.environ.get("DEBUG", "True").lower() in ("true", "1", "t", "yes")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
    if host.strip()
]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party apps
    "rest_framework",
    "drf_spectacular",
    # Local apps
    "accounts.apps.AccountsConfig",
    "inventory.apps.InventoryConfig",
    "assistant",
    "ml.apps.MlConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "dealerdesk.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "dealerdesk.wsgi.application"
ASGI_APPLICATION = "dealerdesk.asgi.application"


import dj_database_url
from django.core.exceptions import ImproperlyConfigured

# Database
# PostgreSQL is the mandatory database backend for DealerDesk.
# SQLite is strictly prohibited to ensure PostgreSQL transaction and concurrency testing.
# Connection is read from DATABASE_URL as required by API_CONTRACT.md.

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    # Support development fallback from individual DB_* environment variables
    db_name = os.environ.get("DB_NAME")
    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASSWORD", "")
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "5432")
    if db_name and db_user:
        from urllib.parse import quote_plus
        encoded_password = quote_plus(db_password) if db_password else ""
        auth_part = f"{db_user}:{encoded_password}@" if db_password else f"{db_user}@"
        DATABASE_URL = f"postgresql://{auth_part}{db_host}:{db_port}/{db_name}"

if not DATABASE_URL:
    raise ImproperlyConfigured(
        "DATABASE_URL or DB_NAME/DB_USER environment variables must be provided. "
        "PostgreSQL is mandatory for DealerDesk; SQLite is strictly prohibited."
    )

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        engine="django.db.backends.postgresql",
        conn_max_age=600,
    )
}

# Strict enforcement: fail immediately if configured engine is not PostgreSQL
if "postgresql" not in DATABASES["default"].get("ENGINE", ""):
    raise ImproperlyConfigured(
        f"Invalid database engine '{DATABASES['default'].get('ENGINE')}'. "
        "DealerDesk strictly requires PostgreSQL."
    )


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]


# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom User Model
AUTH_USER_MODEL = "accounts.User"


# Django REST Framework configuration
# Per API_CONTRACT.md: Auth is not required for any API endpoint.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.AllowAny",
    ),
    "DEFAULT_PAGINATION_CLASS": "dealerdesk.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "dealerdesk.exceptions.contract_exception_handler",
}


# Simple JWT Configuration
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}


# OpenAPI Documentation (drf-spectacular) Configuration
SPECTACULAR_SETTINGS = {
    "TITLE": "DealerDesk API",
    "DESCRIPTION": (
        "DealerDesk B2B Dealer Ordering Platform API. "
        "Distributor platform supplying automotive parts to 25 dealers across South India."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}


