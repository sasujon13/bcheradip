"""
Custom MySQL/MariaDB database backend for Django 5.x with MariaDB 10.4

Fixes:
1. Bypasses mysqlclient version check (allows PyMySQL or mysqlclient 1.4.x)
2. Bypasses DB server version check (MariaDB 10.4)
3. Disables RETURNING clause (not supported in MariaDB 10.4)
4. PyMySQL: decode text fields with errors="replace" on UnicodeError so corrupt/truncated
   UTF-8 in legacy rows does not crash long reads (e.g. management commands scanning TEXT).
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


def _patch_pymysql_lenient_text_decode() -> None:
    """Monkey-patch PyMySQL row decode: strict UTF-8 fails on some legacy HSC TEXT cells."""
    try:
        import pymysql.connections as _pymysql_connections
    except ImportError:
        return
    cls = _pymysql_connections.MySQLResult
    if getattr(cls, "_cheradip_lenient_text_decode", False):
        return

    def _read_row_from_packet(self, packet):
        row = []
        for encoding, converter in self.converters:
            try:
                data = packet.read_length_coded_string()
            except IndexError:
                break
            if data is not None:
                if encoding is not None:
                    try:
                        data = data.decode(encoding)
                    except UnicodeError:
                        data = data.decode(encoding, errors="replace")
                if converter is not None:
                    data = converter(data)
            row.append(data)
        return tuple(row)

    cls._read_row_from_packet = _read_row_from_packet  # type: ignore[assignment]
    cls._cheradip_lenient_text_decode = True  # type: ignore[attr-defined]


_patch_pymysql_lenient_text_decode()

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
