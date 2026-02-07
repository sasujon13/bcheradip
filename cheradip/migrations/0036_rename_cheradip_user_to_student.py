# Rename cheradip_users table to cheradip_student and model CheradipUser to CheradipStudent

from django.db import migrations


def rename_table_forwards(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor == 'mysql':
        schema_editor.execute('RENAME TABLE cheradip_users TO cheradip_student')
    else:
        schema_editor.execute('ALTER TABLE cheradip_users RENAME TO cheradip_student')


def rename_table_backwards(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor == 'mysql':
        schema_editor.execute('RENAME TABLE cheradip_student TO cheradip_users')
    else:
        schema_editor.execute('ALTER TABLE cheradip_student RENAME TO cheradip_users')


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0035_cheradip_jobseeker'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterModelOptions(
                    name='cheradipuser',
                    options={'db_table': 'cheradip_student', 'ordering': ['-date_joined'], 'verbose_name': 'Cheradip Student', 'verbose_name_plural': 'Cheradip Students'},
                ),
                migrations.RenameModel('CheradipUser', 'CheradipStudent'),
            ],
            database_operations=[
                migrations.RunPython(rename_table_forwards, rename_table_backwards),
            ],
        ),
    ]
