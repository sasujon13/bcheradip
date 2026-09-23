import os
from decouple import AutoConfig, Csv

# PyMySQL as MySQLdb (matches requirements.txt; avoids needing mysqlclient build deps on Linux).
import pymysql

pymysql.install_as_MySQLdb()

# BASE_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Merge project .env into os.environ with override=True so values win over inherited env (systemd,
# profile, or DATABASE_USER=root). python-decouple alone prefers OS env over .env — that caused root.
from dotenv import load_dotenv

load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)
# Same Brevo SMTP credentials as AI Language Tutor when not set in project .env
load_dotenv(os.path.join(BASE_DIR, "ailt_api", ".env"), override=False)

# Admin-editable JSON settings (/admin/settings/). Values saved there override
# .env / process environment without a server restart, so every config(...)
# read below (and the direct os.environ reads in module code) sees them.
from backend import site_settings as _site_settings

_site_settings.apply_to_os_environ()

# Always resolve keys relative to project root (manage.py directory), not cwd.
config = AutoConfig(search_path=BASE_DIR)

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

MEDIA_URL = '/media/'

# Environment Variables Configuration
SECRET_KEY = config('SECRET_KEY', default='django-insecure-d37cp#^cs90*bzhh+pvvv$6+h$tm@crx6$=_*^=d&g)k@+c%rj', cast=str)

DEBUG = config('DEBUG', default=True, cast=bool)  # Default True for local development

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='localhost,127.0.0.1,cheradip.com,www.cheradip.com',
    cast=Csv(),
)

# Host URL Configuration
HOST_URL = config('HOST_URL', default='http://127.0.0.1:8000', cast=str)

CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='https://cheradip.com,https://www.cheradip.com,http://localhost:4200,http://127.0.0.1:4200',
    cast=Csv()
)

# Required for cross-origin POST from Angular (Origin: http://localhost:4200).
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='http://localhost:4200,http://127.0.0.1:4200,https://cheradip.com,https://www.cheradip.com',
    cast=Csv(),
)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'cheradip',
    'childcare',
    'django.contrib.staticfiles',
    'rest_framework.authtoken',
    'rest_framework',
    'corsheaders'
]
ADMIN_SITE_HEADER = "Cheradip Administration"
ADMIN_SITE_TITLE = "admin"
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'backend.translation_middleware.TranslateResponseMiddleware',
]

# CORS Configuration - More secure (default True for local development)
CORS_ORIGIN_ALLOW_ALL = config('CORS_ORIGIN_ALLOW_ALL', default=True, cast=bool)  # True for local dev, False for production
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
CORS_ALLOWED_HEADERS = ['Content-Type', 'Authorization', 'X-CSRFToken', 'X-Language']

ROOT_URLCONF = 'backend.urls'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,  # Adjust this number based on your needs
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],
}

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages'
            ]
        }
    }
]

WSGI_APPLICATION = 'backend.wsgi.application'

# Database Configuration from Environment Variables
# Regular `python manage.py migrate` (no --database) applies to 'default' only (cheradip_cheradip).
# Use `migrate --database=hsc` or `--database=honours` to migrate those DBs.
DATABASES = {
    'default': {
        'ENGINE': 'backend.db_backend',
        'NAME': config('DATABASE_NAME', default='cheradip_cheradip', cast=str),
        'USER': config('DATABASE_USER', default='root', cast=str),
        'PASSWORD': config('DATABASE_PASSWORD', default='', cast=str),
        'HOST': config('DATABASE_HOST', default='127.0.0.1', cast=str),
        'PORT': config('DATABASE_PORT', default='3306', cast=str),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    },
    'honours': {
        'ENGINE': 'backend.db_backend',
        'NAME': config('DATABASE_HONOURS_NAME', default='cheradip_honours', cast=str),
        'USER': config('DATABASE_USER', default='root', cast=str),
        'PASSWORD': config('DATABASE_PASSWORD', default='', cast=str),
        'HOST': config('DATABASE_HOST', default='127.0.0.1', cast=str),
        'PORT': config('DATABASE_PORT', default='3306', cast=str),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    },
    'hsc': {
        'ENGINE': 'backend.db_backend',
        'NAME': config('DATABASE_HSC_NAME', default='cheradip_hsc', cast=str),
        'USER': config('DATABASE_USER', default='root', cast=str),
        'PASSWORD': config('DATABASE_PASSWORD', default='', cast=str),
        'HOST': config('DATABASE_HOST', default='127.0.0.1', cast=str),
        'PORT': config('DATABASE_PORT', default='3306', cast=str),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    },
    'job': {
        'ENGINE': 'backend.db_backend',
        'NAME': config('DATABASE_JOB_NAME', default='cheradip_job', cast=str),
        'USER': config('DATABASE_USER', default='root', cast=str),
        'PASSWORD': config('DATABASE_PASSWORD', default='', cast=str),
        'HOST': config('DATABASE_HOST', default='127.0.0.1', cast=str),
        'PORT': config('DATABASE_PORT', default='3306', cast=str),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    },
    'ailt': {
        'ENGINE': 'backend.db_backend',
        'NAME': config('DATABASE_AILT_NAME', default='ailanguagetutor', cast=str),
        'USER': config('DATABASE_USER', default='root', cast=str),
        'PASSWORD': config('DATABASE_PASSWORD', default='', cast=str),
        'HOST': config('DATABASE_HOST', default='127.0.0.1', cast=str),
        'PORT': config('DATABASE_PORT', default='3306', cast=str),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    },
    'childcare': {
        'ENGINE': 'backend.db_backend',
        'NAME': config('DATABASE_CHILDCARE_NAME', default='childcare', cast=str),
        'USER': config('DATABASE_USER', default='root', cast=str),
        'PASSWORD': config('DATABASE_PASSWORD', default='', cast=str),
        'HOST': config('DATABASE_HOST', default='127.0.0.1', cast=str),
        'PORT': config('DATABASE_PORT', default='3306', cast=str),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    },
    # Cheradip VS Code extension accounts (``extcheradip.ext_users``) — mirrored
    # from cheradip_customers by cheradip/ext_account_sync.py on signup/login.
    # Tables are created by the AILT FastAPI app (SQLAlchemy), never by Django.
    'extcheradip': {
        'ENGINE': 'backend.db_backend',
        'NAME': config('DATABASE_EXT_NAME', default='extcheradip', cast=str),
        'USER': config('DATABASE_USER', default='root', cast=str),
        'PASSWORD': config('DATABASE_PASSWORD', default='', cast=str),
        'HOST': config('DATABASE_HOST', default='127.0.0.1', cast=str),
        'PORT': config('DATABASE_PORT', default='3306', cast=str),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    },
}

# Route models to cheradip_job, cheradip_hsc, cheradip_honours, childcare
DATABASE_ROUTERS = [
    'childcare.db_routers.ChildcareRouter',
    'cheradip.db_routers.JobRouter',
    'cheradip.db_routers.HSCRouter',
    'cheradip.db_routers.HonoursRouter',
]

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'
    }
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

# Google Cloud Translation API key for translating website data to country language.
# Set in .env as GOOGLE_TRANSLATE_API_KEY. Get from: https://console.cloud.google.com/apis/credentials
GOOGLE_TRANSLATE_API_KEY = config('GOOGLE_TRANSLATE_API_KEY', default='', cast=str)

# Exam-question AI generation (admin Settings: Create Exam / Add Exam)
# Cloud AI = the same service the AI Language Tutor Android app uses (bcheradip/ailt_api).
# If every Cloud AI response errors, the backend falls back to Home AI (server/v2).
CLOUD_AI_QUESTIONS_URL = config(
    'CLOUD_AI_QUESTIONS_URL',
    default='https://cheradip.com/ailt/api/ai/generate-questions',
    cast=str,
)
HOME_AI_QUESTIONS_URL = config(
    'HOME_AI_QUESTIONS_URL',
    default='https://ai.cheradip.com/ide/chat/sync',
    cast=str,
)
# Explicit Ollama model used for question generation/update via Home AI's /ide/chat/sync.
# Sending a concrete model skips Auto mode (parallel multi-LLM + CPU synthesis), which
# was running >100s per request and hitting the Cloudflare tunnel timeout. If left empty,
# the request falls back to model:null (Auto mode — slow). Use one available on the site,
# e.g. qwen2.5:7b-instruct-q4_K_M.
HOME_AI_QUESTIONS_MODEL = config(
    'HOME_AI_QUESTIONS_MODEL',
    default='qwen2.5:7b-instruct-q4_K_M',
    cast=str,
)
EXAM_AI_FILL_ENABLED = config('EXAM_AI_FILL_ENABLED', default=True, cast=bool)
AI_QUESTIONS_TIMEOUT_SECONDS = config('AI_QUESTIONS_TIMEOUT_SECONDS', default=60, cast=int)

# OTP email — same Brevo SMTP_* vars as ailt_api (AI Language Tutor)
SMTP_ENABLED = config('SMTP_ENABLED', default=True, cast=bool)
SMTP_HOST = config('SMTP_HOST', default='', cast=str)
SMTP_PORT = config('SMTP_PORT', default=587, cast=int)
SMTP_USER = config('SMTP_USER', default='', cast=str)
SMTP_PASSWORD = config('SMTP_PASSWORD', default='', cast=str)
SMTP_FROM = config('SMTP_FROM', default='Cheradip <noreply@cheradip.com>', cast=str)
SMTP_USE_TLS = config('SMTP_USE_TLS', default=True, cast=bool)
SMTP_USE_SSL = config('SMTP_USE_SSL', default=False, cast=bool)
OTP_TTL_MINUTES = config('OTP_TTL_MINUTES', default=15, cast=int)
CHILDCARE_SESSION_TTL_DAYS = config('CHILDCARE_SESSION_TTL_DAYS', default=30, cast=int)

STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static_src')]



DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'debug_file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'debug.log'),  # Adjust the path accordingly
        },
    },
    'loggers': {
        'django': {
            'handlers': ['debug_file'],
            'level': 'DEBUG',
            'propagate': False,  # Prevent other loggers from handling the message
        },
    }
}

# Custom User Model Configuration
AUTH_USER_MODEL = 'cheradip.Customer'

AUTHENTICATION_BACKENDS = [
    'cheradip.backends.CustomBackend',
    'django.contrib.auth.backends.ModelBackend'
]


