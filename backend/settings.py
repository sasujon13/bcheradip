from pathlib import Path
import os

HOST_URL = 'https://cheradip.com'
# BASE_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

MEDIA_URL = '/media/'

SECRET_KEY = 'django-insecure-d37cp#^cs90*bzhh+pvvv$6+h$tm@crx6$=_*^=d&g)k@+c%rj'

DEBUG = True

ALLOWED_HOSTS = ['*']


CORS_ALLOWED_ORIGINS = [
    "https://cheradip.com",
    "https://manage.cheradip.com",
    "http://localhost:4200" 
]

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
ADMIN_SITE_TITLE = "Cheradip Admin"
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware'
]

CORS_ORIGIN_ALLOW_ALL = True

ROOT_URLCONF = 'backend.urls'

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

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'cheradip_cheradip',
        'USER': 'cheradip_cheradip',
        'PASSWORD': 'Sa@2271029867',
        'HOST': 'localhost',
        'PORT': '3306'
    }
}

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

STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.AppDirectoriesFinder'
]

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
STATIC_DIRS = [os.path.join(BASE_DIR, 'static')]



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

AUTHENTICATION_BACKENDS = [
    'cheradip.backends.CustomBackend',
    'django.contrib.auth.backends.ModelBackend'
]


