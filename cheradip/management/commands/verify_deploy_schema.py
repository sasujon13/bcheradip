"""Check deployed database columns before publishing code.

The local-to-remote table sync intentionally does not copy rows or alter existing
tables. This command catches model/column drift that a basic health check misses.
Only a short, reviewed list of additive fields can be repaired automatically.
"""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, router
from django.db.models import UniqueConstraint


SAFE_ADDITIONS = {
    ('ecommerce', 'ecommerce', 'cartitem', 'requested_size'),
    ('ecommerce', 'ecommerce', 'cartitem', 'requested_color'),
    ('ecommerce', 'ecommerce', 'productimage', 'source_media'),
    ('ecommerce', 'ecommerce', 'supplieroffer', 'source_product'),
    ('ecommerce', 'ecommerce', 'product', 'supplier_delivery_rates'),
    ('ecommerce', 'ecommerce', 'deliverysettings', 'delivery_subsidy_enabled'),
    ('ecommerce', 'ecommerce', 'order', 'cost_snapshot'),
    ('ecommerce', 'ecommerce', 'deliverysettings', 'cost_defaults'),
    ('ecommerce', 'ecommerce', 'deliverysettings', 'pricing_rules'),
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

# Deployment normally creates absent tables through l2r. These new staging
# tables are also safe to create directly, in dependency order, without copying
# business rows or pretending that older migrations have been applied.
SAFE_SOURCE_TABLES = ('supplierrecollectionrun', 'suppliersourceproduct', 'suppliersourcemedia', 'supplierrecollectionitem')


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
        if options['apply_safe']:
            connection = connections['ecommerce']
            with connection.cursor() as cursor:
                existing = set(connection.introspection.table_names(cursor))
            membership = apps.get_model('ecommerce', 'Product').secondary_categories.through
            if membership._meta.db_table not in existing:
                self.stdout.write('Creating additive product secondary-category membership table')
                with connection.schema_editor() as editor:
                    editor.create_model(membership)
                existing.add(membership._meta.db_table)
            for name in SAFE_SOURCE_TABLES:
                model = apps.get_model('ecommerce', name)
                if model._meta.db_table not in existing:
                    self.stdout.write(f'Creating reviewed source-staging table ecommerce:{model._meta.db_table}')
                    with connection.schema_editor() as editor:
                        editor.create_model(model)
                    existing.add(model._meta.db_table)
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
            # Reviewed cart-key expansion: preserve existing rows (empty size),
            # while allowing two requested sizes of the same supplier variant.
            # Remote installs predate migration history, so inspect actual keys
            # rather than faking unrelated migrations or touching order records.
            cart_item = apps.get_model('ecommerce', 'CartItem')
            conn = connections['ecommerce']
            if cart_item._meta.db_table in tables_by_alias.get('ecommerce', set()):
                with conn.cursor() as cursor:
                    keys = conn.introspection.get_constraints(cursor, cart_item._meta.db_table)
                wanted = next(c for c in cart_item._meta.constraints if c.name == 'ecommerce_cart_variant_choices_unique')
                if not any(k.get('unique') and k.get('columns') == ['cart_id','variant_id','requested_size','requested_color'] for k in keys.values()):
                    with conn.schema_editor() as editor: editor.add_constraint(cart_item, wanted)
                for name, key in keys.items():
                    if key.get('unique') and key.get('columns') in (['cart_id','variant_id'], ['cart_id','variant_id','requested_size']):
                        fields = ['cart','variant'] if len(key['columns']) == 2 else ['cart','variant','requested_size']
                        with conn.schema_editor() as editor:
                            editor.remove_constraint(cart_item, UniqueConstraint(fields=fields, name=name))
            if missing:
                # Recheck from the database, including the new columns and indexes.
                options["apply_safe"] = False
                return self.handle(*args, **options)

        if missing:
            for alias, _model, _field, description in missing:
                self.stderr.write(f"MISSING {alias}:{description}")
            raise CommandError(f"Database schema is missing {len(missing)} table(s)/column(s).")
        self.stdout.write(self.style.SUCCESS("Database model columns verified."))
