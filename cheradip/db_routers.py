"""
Database routers: route models to cheradip_job, cheradip_hsc, cheradip_honours.
Django model._meta.model_name is lowercase (e.g. 'institutes' not 'Institutes').
"""

APP_LABEL = 'cheradip'

# Models whose tables live in cheradip_job (used by NTRCA, institute list, tokens)
JOB_MODEL_NAMES = {
    'institutes', 'token', 'banbeis', 'merit', 'merit5', 'merit6',
    'vacancy', 'vacancy5', 'vacancy6', 'recommend', 'recommend5', 'recommend6',
}

# Models that would live in cheradip_hsc - left empty so they use default DB only.
# (Tables Subject, Chapter, Topic, Mcq_ict are not in cheradip_hsc; routing here caused ProgrammingError.)
HSC_MODEL_NAMES = set()


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
        return True


class HSCRouter:
    """Route Subject, Chapter, Topic, Mcq_ict to the 'hsc' database (cheradip_hsc)."""

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