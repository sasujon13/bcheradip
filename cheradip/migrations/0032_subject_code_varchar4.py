# Subject.subject_code: varchar(3) -> varchar(4)
# MySQL blocks ALTER on a column referenced by FKs; drop FKs, alter, then re-add.

from django.db import migrations, models


def alter_subject_code_varchar4(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor != 'mysql':
        return

    subject_table = 'cheradip_subject'
    with conn.cursor() as cur:
        cur.execute("""
            SELECT kcu.CONSTRAINT_NAME, kcu.TABLE_NAME, kcu.COLUMN_NAME,
                   kcu.REFERENCED_COLUMN_NAME,
                   rc.DELETE_RULE, rc.UPDATE_RULE
            FROM information_schema.KEY_COLUMN_USAGE kcu
            JOIN information_schema.REFERENTIAL_CONSTRAINTS rc
              ON rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
             AND rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
             AND rc.TABLE_NAME = kcu.TABLE_NAME
            WHERE kcu.REFERENCED_TABLE_SCHEMA = DATABASE()
              AND kcu.REFERENCED_TABLE_NAME = %s
        """, [subject_table])
        fks = cur.fetchall()

    for constraint_name, table_name, column_name, ref_col, delete_rule, update_rule in fks:
        with conn.cursor() as cur:
            cur.execute(f"ALTER TABLE `{table_name}` DROP FOREIGN KEY `{constraint_name}`")

    with conn.cursor() as cur:
        cur.execute(
            f"ALTER TABLE `{subject_table}` MODIFY COLUMN subject_code VARCHAR(4) NOT NULL"
        )

    for constraint_name, table_name, column_name, ref_col, delete_rule, update_rule in fks:
        delete_rule = delete_rule or 'RESTRICT'
        update_rule = update_rule or 'RESTRICT'
        with conn.cursor() as cur:
            cur.execute(
                f"ALTER TABLE `{table_name}` ADD CONSTRAINT `{constraint_name}` "
                f"FOREIGN KEY (`{column_name}`) REFERENCES `{subject_table}`(`{ref_col}`) "
                f"ON DELETE {delete_rule} ON UPDATE {update_rule}"
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0031_drop_cheradip_subject_translated'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='subject',
                    name='subject_code',
                    field=models.CharField(db_index=True, max_length=4),
                ),
            ],
            database_operations=[
                migrations.RunPython(alter_subject_code_varchar4, noop),
            ],
        ),
    ]
