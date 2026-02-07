"""
Local development settings — always uses XAMPP MySQL from .env.

To run: python manage.py runserver
  or:   python manage.py runserver --settings=backend.settings_local

Both use the same MySQL DB (DATABASE_NAME, DATABASE_USER, etc. from .env).
Ensure .env has your XAMPP credentials, e.g.:
  DATABASE_NAME=cheradip_cheradip
  DATABASE_USER=root
  DATABASE_PASSWORD=
  DATABASE_HOST=localhost
  DATABASE_PORT=3306
"""

import os
from .settings import *

# Keep using XAMPP MySQL from .env (same as default settings.py)
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
    }
}

# Enable DEBUG for local development
DEBUG = True

# Allow all hosts for local development
ALLOWED_HOSTS = ['*']
print("[LOCAL] Using MySQL (XAMPP) from .env")

