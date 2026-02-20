# Drop legacy table cheradip_customer (singular) and repoint any FKs to cheradip_customers.
# Handles DBs created from old dumps where the table was named cheradip_customer.

from django.db import migrations


def drop_cheradip_customer_and_repoint_fks(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor != 'mysql':
        return
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.TABLES
            WHERE table_schema = DATABASE() AND table_name = 'cheradip_customer'
        """)
        if not cur.fetchone():
            return

        # Find all FK constraints that reference cheradip_customer
        cur.execute("""
            SELECT kcu.TABLE_NAME, kcu.CONSTRAINT_NAME, kcu.COLUMN_NAME
            FROM information_schema.REFERENTIAL_CONSTRAINTS rc
            JOIN information_schema.KEY_COLUMN_USAGE kcu
              ON rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                 AND rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
            WHERE rc.REFERENCED_TABLE_NAME = 'cheradip_customer'
              AND rc.CONSTRAINT_SCHEMA = DATABASE()
        """)
        fks = cur.fetchall()

        for table_name, constraint_name, column_name in fks:
            try:
                cur.execute(
                    "ALTER TABLE `%s` DROP FOREIGN KEY `%s`" % (table_name, constraint_name)
                )
                # Add new FK to cheradip_customers (MySQL constraint name max 64 chars)
                new_fk_name = ("fk_%s_%s_ref_customers" % (table_name, column_name))[:64]
                cur.execute("""
                    ALTER TABLE `%s`
                    ADD CONSTRAINT `%s` FOREIGN KEY (`%s`) REFERENCES cheradip_customers (`id`)
                """ % (table_name, new_fk_name, column_name))
            except Exception:
                pass

        cur.execute("DROP TABLE IF EXISTS `cheradip_customer`")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0037_consolidate_customer'),
    ]

    operations = [
        migrations.RunPython(drop_cheradip_customer_and_repoint_fks, noop),
    ]
