"""
Database routers: route models to cheradip_job, cheradip_hsc, cheradip_honours.
Django model._meta.model_name is lowercase (e.g. 'institutes' not 'Institutes').
"""

APP_LABEL = 'cheradip'

# Models whose tables live in cheradip_job (used by NTRCA, institute list, tokens)
JOB_MODEL_NAMES = {
    'institutes', 'token', 'banbeis',
    'merit5', 'merit6', 'merit7',
    'vacancy5', 'vacancy6', 'vacancy7',
    'recommend5', 'recommend6', 'recommend7',
}

# Only these models live in cheradip_hsc: Subject, PendingSubjectRequestHsc, and dynamic subject question tables (created by app, not migrations). All other models stay in default (cheradip_cheradip).
HSC_MODEL_NAMES = {'subject', 'pendingsubjectrequesthsc'}

# Models whose tables live in cheradip_honours
HONOURS_MODEL_NAMES = {'pendingsubjectrequesthonours'}


def _is_job_model(model):
    return (
        model._meta.app_label == APP_LABEL
        and model._meta.model_name in JOB_MODEL_NAMES
    )


def _is_hsc_model(model):
    return (
        model._meta.app_label == APP_LABEL
        and model._meta.model_name in HSC_MODEL_NAMES
    )


def _is_honours_model(model):
    return (
        model._meta.app_label == APP_LABEL
        and model._meta.model_name in HONOURS_MODEL_NAMES
    )


class JobRouter:
    """Route job/NTRCA models to the 'job' database (cheradip_job)."""

    def db_for_read(self, model, **hints):
        if _is_job_model(model):
            return 'job'
        return None

    def db_for_write(self, model, **hints):
        if _is_job_model(model):
            return 'job'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Allow relations only when both are on the same DB
        if _is_job_model(obj1) and _is_job_model(obj2):
            return True
        if not _is_job_model(obj1) and not _is_job_model(obj2):
            return True
        return False

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # Job models: migrate only on the job database
        if app_label == APP_LABEL and model_name and model_name.lower() in JOB_MODEL_NAMES:
            return db == 'job'
        # On the job DB, only allow job models (no other app/model)
        if db == 'job':
            return False
        # Defer to HSCRouter / HonoursRouter for hsc and honours
        if db in ('hsc', 'honours'):
            return None
        return True


class HSCRouter:
    """Route only Subject and PendingSubjectRequestHsc to the 'hsc' database (cheradip_hsc). All other models use default."""

    def db_for_read(self, model, **hints):
        if _is_hsc_model(model):
            return 'hsc'
        return None

    def db_for_write(self, model, **hints):
        if _is_hsc_model(model):
            return 'hsc'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        if _is_hsc_model(obj1) and _is_hsc_model(obj2):
            return True
        if not _is_hsc_model(obj1) and not _is_hsc_model(obj2):
            return True
        return False

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == APP_LABEL and model_name and model_name.lower() in HSC_MODEL_NAMES:
            return db == 'hsc'
        if db == 'hsc':
            return False
        return True


class HonoursRouter:
    """Route PendingSubjectRequestHonours to the 'honours' database (cheradip_honours)."""

    def db_for_read(self, model, **hints):
        if _is_honours_model(model):
            return 'honours'
        return None

    def db_for_write(self, model, **hints):
        if _is_honours_model(model):
            return 'honours'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        if _is_honours_model(obj1) and _is_honours_model(obj2):
            return True
        if not _is_honours_model(obj1) and not _is_honours_model(obj2):
            return True
        return False

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == APP_LABEL and model_name and model_name.lower() in HONOURS_MODEL_NAMES:
            return db == 'honours'
        if db == 'honours':
            return False
        # Defer to HSCRouter for hsc (so only cheradip subject/pendingsubjectrequesthsc migrate there)
        if db == 'hsc':
            return None
        return True