"""
Identify Django models whose table does not exist in the database they are routed to.
Used to unregister them from admin and skip their API registration (all databases).
"""
from django.apps import apps
from django.db import connections, router

_CACHE = None


def get_models_with_missing_tables():
    """
    Return set of (app_label, model_name) for models whose db_table
    does not exist in the database the router assigns for that model.
    Result is cached. On any error (e.g. DB unavailable), returns empty set.
    """
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    out = set()
    try:
        for model in apps.get_models(app_label='cheradip'):
            db_alias = router.db_for_read(model) or 'default'
            if db_alias not in connections:
                out.add((model._meta.app_label, model._meta.model_name))
                continue
            table_name = model._meta.db_table
            try:
                conn = connections[db_alias]
                with conn.cursor() as cursor:
                    existing = set(conn.introspection.table_names(cursor))
                if table_name not in existing:
                    out.add((model._meta.app_label, model._meta.model_name))
            except Exception:
                out.add((model._meta.app_label, model._meta.model_name))
    except Exception:
        pass
    _CACHE = out
    return out


def model_has_table(model):
    """Return True if the model's table exists in its routed database."""
    return (getattr(model, '_meta', None) and
            (model._meta.app_label, model._meta.model_name) not in get_models_with_missing_tables())
