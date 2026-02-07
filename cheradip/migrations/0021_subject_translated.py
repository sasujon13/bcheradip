# Create cheradip_subject_translated (copy of Subject per language).

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0020_subject_rename_group_to_groups'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubjectTranslated',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('language_code', models.CharField(db_index=True, max_length=10)),
                ('level', models.CharField(blank=True, db_index=True, max_length=20, null=True)),
                ('subject_name', models.CharField(blank=True, max_length=50)),
                ('subject_name_bn', models.CharField(blank=True, max_length=50, null=True)),
                ('groups', models.JSONField(blank=True, db_column='groups', default=list, help_text='List of group codes, e.g. ["S","A","B"]')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('country', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='subject_translations',
                    to='cheradip.country',
                    db_index=True,
                )),
                ('subject', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='translations',
                    to='cheradip.subject',
                    db_index=True,
                )),
            ],
            options={
                'db_table': 'cheradip_subject_translated',
                'ordering': ['subject', 'language_code'],
            },
        ),
        migrations.AddConstraint(
            model_name='subjecttranslated',
            constraint=models.UniqueConstraint(fields=('subject', 'language_code'), name='uq_subject_translated_subject_lang'),
        ),
        migrations.AddIndex(
            model_name='subjecttranslated',
            index=models.Index(fields=['subject', 'language_code'], name='cheradip_su_subject_6c1e8d_idx'),
        ),
        migrations.AddIndex(
            model_name='subjecttranslated',
            index=models.Index(fields=['language_code'], name='cheradip_su_languag_2b8f0a_idx'),
        ),
    ]
