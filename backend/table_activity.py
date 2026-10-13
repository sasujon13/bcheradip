"""Acknowledged table activity, distinct from unresolved work awaiting admin action."""
import logging
import io
import threading
from django.core.cache import cache
from django.core.management import call_command
from django.db import close_old_connections
from django.db import transaction
from django.db.models import Max
from django.db.models.signals import post_save, post_delete


def record_table_event(database, table, action, row_key=''):
    def record():
        try:
            from cheradip.models import AdminTableEvent
            AdminTableEvent.objects.using('default').create(database_alias=database, table_name=table,
                                                           action=action, row_key=str(row_key)[:160])
        except Exception:
            logging.getLogger(__name__).warning('Could not record table activity for %s.%s', database, table, exc_info=True)
    transaction.on_commit(record, using=database)


def _saved(sender, instance, using, created=False, raw=False, **kwargs):
    if raw or sender._meta.app_label not in {'cheradip', 'ecommerce', 'childcare'}:
        return
    if sender._meta.model_name in {'admintableevent', 'admintablereview', 'admintablefingerprint'}:
        return
    row_key = '' if sender._meta.model_name == 'customertoken' else instance.pk
    record_table_event(using, sender._meta.db_table, 'created' if created else 'updated', row_key)


def _deleted(sender, instance, using, **kwargs):
    if sender._meta.app_label in {'cheradip', 'ecommerce', 'childcare'} and sender._meta.model_name not in {'admintableevent', 'admintablereview', 'admintablefingerprint'}:
        record_table_event(using, sender._meta.db_table, 'deleted', '' if sender._meta.model_name == 'customertoken' else instance.pk)


def connect_activity_signals():
    post_save.connect(_saved, dispatch_uid='cheradip-table-activity-save', weak=False)
    post_delete.connect(_deleted, dispatch_uid='cheradip-table-activity-delete', weak=False)


def refresh_external_markers(database):
    """Refresh independent-service markers without blocking the admin page."""
    if database not in {'ailt', 'extcheradip'}:
        return
    if not cache.add(f'admin-external-scan:{database}', True, timeout=300):
        return

    def scan():
        close_old_connections()
        try:
            call_command('scan_admin_table_changes', database=[database], stdout=io.StringIO(), stderr=io.StringIO())
        except Exception:
            logging.getLogger(__name__).warning('External activity scan unavailable for %s', database)
        finally:
            close_old_connections()
    threading.Thread(target=scan, name=f'admin-activity-{database}', daemon=True).start()


def unread_count(request, database, table):
    if not request:
        return 0
    from cheradip.models import AdminTableEvent, AdminTableReview
    review = AdminTableReview.objects.filter(customer_id=request.user.pk, database_alias=database, table_name=table).first()
    return AdminTableEvent.objects.filter(database_alias=database, table_name=table,
                                         id__gt=review.last_event_id if review else 0).count()


def acknowledge(request, database, table):
    from cheradip.models import AdminTableEvent, AdminTableReview
    latest = AdminTableEvent.objects.filter(database_alias=database, table_name=table).aggregate(last=Max('id'))['last'] or 0
    # Monotonic checkpoint: older tabs may never make newer activity unread again.
    with transaction.atomic():
        review, _ = AdminTableReview.objects.select_for_update().get_or_create(
            customer_id=request.user.pk, database_alias=database, table_name=table)
        if latest > review.last_event_id:
            review.last_event_id = latest
            review.save(update_fields=['last_event_id'])


class AdminActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.method == 'GET' and response.status_code == 200 and getattr(request.user, 'is_staff', False):
            match = getattr(request, 'resolver_match', None)
            name = getattr(match, 'url_name', '') or ''
            if name.endswith('_changelist'):
                from django.contrib import admin
                from django.db import router
                model = next((m for m in admin.site._registry if name == f'{m._meta.app_label}_{m._meta.model_name}_changelist'), None)
                if model:
                    acknowledge(request, router.db_for_read(model) or 'default', model._meta.db_table)
        return response
