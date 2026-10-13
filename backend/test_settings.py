"""Disposable SQLite test databases: never connects to local/remote customer data."""
from .settings import *  # noqa: F403

DATABASES = {alias: {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}
             for alias in ('default', 'ecommerce', 'childcare', 'hsc', 'honours', 'job', 'ailt', 'extcheradip')}
MIGRATION_MODULES = {'cheradip': None, 'ecommerce': None, 'childcare': None}
SECURE_SSL_REDIRECT = False
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
