"""
Custom MySQL/MariaDB database backend for Django 5.x with MariaDB 10.4

Fixes:
1. Bypasses mysqlclient version check (allows PyMySQL or mysqlclient 1.4.x)
2. Bypasses DB server version check (MariaDB 10.4)
3. Disables RETURNING clause (not supported in MariaDB 10.4)
"""
# Satisfy Django's mysqlclient 2.2.1+ check when using PyMySQL or older mysqlclient.
# Must run before importing django.db.backends.mysql.
try:
    import MySQLdb as _Database
    if getattr(_Database, "version_info", (0,)) < (2, 2, 1):
        _Database.version_info = (2, 2, 1)
        if hasattr(_Database, "__version__"):
            _Database.__version__ = "2.2.1"
except ImportError:
    pass

from django.db.backends.mysql import base, features


class DatabaseFeatures(features.DatabaseFeatures):
    """Override features to disable RETURNING for MariaDB 10.4"""
    
    # Disable RETURNING clause - not supported in MariaDB 10.4
    can_return_columns_from_insert = False
    can_return_rows_from_bulk_insert = False


class DatabaseWrapper(base.DatabaseWrapper):
    """Custom database wrapper for MariaDB 10.4 compatibility"""
    
    # Use our custom features class
    features_class = DatabaseFeatures
    
    def check_database_version_supported(self):
        """Skip the database version check for MariaDB 10.4"""
        pass
