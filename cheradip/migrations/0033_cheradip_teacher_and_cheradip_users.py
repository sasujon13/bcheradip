# Rename cheradip_users -> cheradip_teacher (Teacher signups); create new cheradip_users (Student/Job Seeker).

from django.db import migrations, models


def rename_users_table_to_teacher(apps, schema_editor):
    conn = schema_editor.connection
    with conn.cursor() as cur:
        if conn.vendor == 'mysql':
            cur.execute(
                "SELECT 1 FROM information_schema.TABLES WHERE table_schema = DATABASE() AND table_name = 'cheradip_teacher'"
            )
            if cur.fetchone():
                return  # already renamed
            cur.execute("RENAME TABLE cheradip_users TO cheradip_teacher")
        elif conn.vendor == 'sqlite':
            cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cheradip_teacher'")
            if cur.fetchone():
                return
            cur.execute("ALTER TABLE cheradip_users RENAME TO cheradip_teacher")
        else:
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'cheradip_teacher'"
            )
            if cur.fetchone():
                return
            cur.execute('ALTER TABLE cheradip_users RENAME TO cheradip_teacher')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0032_subject_code_varchar4'),
    ]

    operations = [
        # Do table rename only in DB (RunPython); state updated by RenameModel + AlterModelTable
        # so AlterModelTable does not run RENAME again (would fail: cheradip_teacher already exists)
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameModel(old_name='CheradipUser', new_name='CheradipTeacher'),
                migrations.AlterModelTable(
                    name='cheradipteacher',
                    table='cheradip_teacher',
                ),
            ],
            database_operations=[
                migrations.RunPython(rename_users_table_to_teacher, noop),
            ],
        ),
        migrations.RemoveField(
            model_name='cheradipteacher',
            name='acctype',
        ),
        migrations.RemoveField(
            model_name='cheradipteacher',
            name='class_name',
        ),
        migrations.RemoveField(
            model_name='cheradipteacher',
            name='group',
        ),
        migrations.RemoveField(
            model_name='cheradipteacher',
            name='department',
        ),
        migrations.CreateModel(
            name='CheradipUser',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('acctype', models.CharField(choices=[('Student', 'Student'), ('JobSeeker', 'Job Seeker')], db_index=True, default='Student', max_length=10)),
                ('fullName', models.CharField(max_length=31)),
                ('username', models.CharField(db_index=True, max_length=15, unique=True)),
                ('password', models.CharField(max_length=128)),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('class_name', models.CharField(blank=True, max_length=20, null=True)),
                ('group', models.CharField(blank=True, max_length=30, null=True)),
                ('department', models.CharField(blank=True, max_length=50, null=True)),
                ('gender', models.CharField(blank=True, default='Male', max_length=10)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('country_code', models.CharField(db_index=True, max_length=2)),
                ('date_joined', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'cheradip_users',
                'ordering': ['-date_joined'],
                'verbose_name': 'Cheradip User',
                'verbose_name_plural': 'Cheradip Users',
                'indexes': [
                    models.Index(fields=['username'], name='cheradip_us_username_idx'),
                    models.Index(fields=['email'], name='cheradip_us_email_idx'),
                    models.Index(fields=['acctype'], name='cheradip_us_acctype_idx'),
                    models.Index(fields=['country_code'], name='cheradip_us_country_idx'),
                ],
            },
        ),
    ]
