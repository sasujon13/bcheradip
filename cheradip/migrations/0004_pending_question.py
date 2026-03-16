# Generated migration: PendingQuestion model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0003_createdquestionset'),
    ]

    operations = [
        migrations.CreateModel(
            name='PendingQuestion',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('level_tr', models.CharField(blank=True, max_length=100)),
                ('class_level', models.CharField(blank=True, max_length=50)),
                ('subject_tr', models.CharField(max_length=255)),
                ('chapter_no', models.CharField(blank=True, max_length=50)),
                ('chapter', models.CharField(max_length=255)),
                ('topic_no', models.CharField(blank=True, max_length=50)),
                ('topic', models.CharField(max_length=255)),
                ('question', models.TextField()),
                ('option_1', models.CharField(blank=True, max_length=500)),
                ('option_2', models.CharField(blank=True, max_length=500)),
                ('option_3', models.CharField(blank=True, max_length=500)),
                ('option_4', models.CharField(blank=True, max_length=500)),
                ('answer', models.CharField(blank=True, max_length=500)),
                ('explanation', models.TextField(blank=True)),
                ('explanation2', models.TextField(blank=True)),
                ('explanation3', models.TextField(blank=True)),
                ('type', models.CharField(blank=True, max_length=100)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], db_index=True, default='pending', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('approved_qid', models.CharField(blank=True, help_text='qid assigned when approved', max_length=64)),
            ],
            options={
                'db_table': 'cheradip_pending_questions',
                'ordering': ['-created_at'],
            },
        ),
    ]
