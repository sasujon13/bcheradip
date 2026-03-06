# Minimal migration: only create PendingSubjectRequest (pending subject requests for Degree signup).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0013_subject_question_type_level_audit'),
    ]

    operations = [
        migrations.CreateModel(
            name='PendingSubjectRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subject_name', models.CharField(max_length=255)),
                ('subject_translated', models.CharField(max_length=255)),
                ('country_id', models.CharField(blank=True, db_index=True, max_length=2, null=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], db_index=True, default='pending', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, null=True)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_pending_subject_requests', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Pending subject request',
                'verbose_name_plural': 'Pending subject requests',
                'db_table': 'cheradip_pending_subject_request',
                'ordering': ['-created_at'],
            },
        ),
    ]
