"""Check deployed database columns before publishing code.

The local-to-remote table sync intentionally does not copy rows or alter existing
tables. This command catches model/column drift that a basic health check misses.
Only a short, reviewed list of additive fields can be repaired automatically.
"""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, router


SAFE_ADDITIONS = {
    ('ecommerce', 'ecommerce', 'deliverysettings', 'cost_defaults'),
    ('ecommerce', 'ecommerce', 'deliverysettings', 'courier_profiles'),
    ('ecommerce', 'ecommerce', 'order', 'delivery_quote'),
    ('ecommerce', 'ecommerce', 'productvariant', 'pricing_inputs'),
    ('ecommerce', 'ecommerce', 'product', 'delivery_dhaka_charge'),
    ('ecommerce', 'ecommerce', 'product', 'delivery_outside_dhaka_charge'),
    ('ecommerce', 'ecommerce', 'product', 'cod_percent'),
    ('ecommerce', 'ecommerce', 'deliverysettings', 'cod_percent'),
    ('ecommerce', 'ecommerce', 'order', 'cod_total'),
    ('ecommerce', 'ecommerce', 'order', 'reservation_expires_at'),
    ('ecommerce', 'ecommerce', 'order', 'receipt_attempts'),
    ('ecommerce', 'ecommerce', 'order', 'receipt_sent_at'),
    ('ecommerce', 'ecommerce', 'order', 'receipt_pending'),
    ("default", "cheradip", "customer", "profile_image"),
    ("default", "cheradip", "customer", "referred_by"),
    ("default", "cheradip", "trxmanagement", "verified"),
    ("childcare", "childcare", "parentaccount", "email"),
    ("childcare", "childcare", "parentaccount", "email_verified"),
    ("childcare", "childcare", "parentaccount", "full_name"),
    ("childcare", "childcare", "parentaccount", "password_hash"),
    ("childcare", "childcare", "parentaccount", "registered_device_id"),
    ("childcare", "childcare", "parentaccount", "role"),
    ("childcare", "childcare", "parentaccount", "username"),
    ("childcare", "childcare", "devicesession", "expires_at"),
    ("childcare", "childcare", "devicesession", "token"),
    ("childcare", "childcare", "otpcode", "channel"),
    ("childcare", "childcare", "otpcode", "target"),
    ("childcare", "childcare", "otpcode", "used"),
}


class Command(BaseCommand):
    help = "Verify that deployed database tables contain the model's columns."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply-safe", action="store_true",
            help="Add only reviewed, missing columns; never change or copy records.",
        )

    def handle(self, *args, **options):
        missing = []
        tables_by_alias = {}
        for model in apps.get_models():
            meta = model._meta
            if not meta.managed or meta.proxy:
                continue
            alias = router.db_for_read(model) or "default"
            connection = connections[alias]
            if alias not in tables_by_alias:
                with connection.cursor() as cursor:
                    tables_by_alias[alias] = set(connection.introspection.table_names(cursor))
            table = meta.db_table
            if table not in tables_by_alias[alias]:
                missing.append((alias, model, None, f"missing table {table}"))
                continue
            with connection.cursor() as cursor:
                present = {
                    column.name for column in connection.introspection.get_table_description(cursor, table)
                }
            for field in meta.local_fields:
                if field.column not in present:
                    missing.append((alias, model, field, f"{table}.{field.column}"))

        if options["apply_safe"]:
            for alias, model, field, description in list(missing):
                if field is None:
                    continue
                key = (alias, model._meta.app_label, model._meta.model_name, field.name)
                if key not in SAFE_ADDITIONS:
                    continue
                self.stdout.write(f"Adding reviewed column {alias}:{description}")
                with connections[alias].schema_editor() as editor:
                    editor.add_field(model, field)
            if missing:
                # Recheck from the database, including the new columns and indexes.
                options["apply_safe"] = False
                return self.handle(*args, **options)

        if missing:
            for alias, _model, _field, description in missing:
                self.stderr.write(f"MISSING {alias}:{description}")
            raise CommandError(f"Database schema is missing {len(missing)} table(s)/column(s).")
        self.stdout.write(self.style.SUCCESS("Database model columns verified."))
