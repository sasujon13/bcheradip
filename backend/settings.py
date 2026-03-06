from pathlib import Path
import os
import pymysql
from decouple import config, Csv

pymysql.install_as_MySQLdb()

# BASE_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

MEDIA_URL = '/media/'

# Environment Variables Configuration
SECRET_KEY = config('SECRET_KEY', default='django-insecure-d37cp#^cs90*bzhh+pvvv$6+h$tm@crx6$=_*^=d&g)k@+c%rj', cast=str)

DEBUG = config('DEBUG', default=True, cast=bool)  # Default True for local development

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# Host URL Configuration
HOST_URL = config('HOST_URL', default='http://127.0.0.1:8000', cast=str)

CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='https://cheradip.com,http://localhost:4200,http://127.0.0.1:4200',
    cast=Csv()
)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'cheradip',
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
DATABASES = {
    'default': {
        'ENGINE': 'backend.db_backend',
        'NAME': config('DATABASE_NAME', default='cheradip_cheradip', cast=str),
        'USER': config('DATABASE_USER', default='root', cast=str),
        'PASSWORD': config('DATABASE_PASSWORD', default='', cast=str),
        'HOST': config('DATABASE_HOST', default='localhost', cast=str),
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
        'HOST': config('DATABASE_HOST', default='localhost', cast=str),
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
        'HOST': config('DATABASE_HOST', default='localhost', cast=str),
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
        'HOST': config('DATABASE_HOST', default='localhost', cast=str),
        'PORT': config('DATABASE_PORT', default='3306', cast=str),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    },
}

# Route models to cheradip_job and cheradip_hsc (order: first non-None wins)
DATABASE_ROUTERS = [
    'cheradip.db_routers.JobRouter',
    'cheradip.db_routers.HSCRouter',
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


