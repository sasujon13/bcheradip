from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _ensure_subject_question_tables(sender, **kwargs):
    """After migrate: create any missing subject question tables from cheradip_subject (new environment)."""
    if sender.name != 'cheradip':
        return
    try:
        from cheradip.subject_question_tables import ensure_subject_question_tables
        created, total = ensure_subject_question_tables(verbose=False)
        if created > 0:
            import logging
            logging.getLogger(__name__).info('Subject question tables: created %s of %s from cheradip_subject.', created, total)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning('Could not ensure subject question tables: %s', e)


class CheradipConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cheradip'

    def ready(self):
        post_migrate.connect(_ensure_subject_question_tables, sender=self)
