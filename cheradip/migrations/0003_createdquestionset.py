# Generated migration: CreatedQuestionSet model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0002_customer_settings'),
    ]

    operations = [
        migrations.CreateModel(
            name='CreatedQuestionSet',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(help_text='Display/save name; user can rename', max_length=200)),
                ('question_header', models.CharField(blank=True, max_length=255)),
                ('questions', models.JSONField(default=list, help_text='List of question objects {question, option_1, ...}')),
                ('counter', models.PositiveIntegerField(default=1, help_text='Per-customer sequence for unique filename (name_counter)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('customer', models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, related_name='created_question_sets', to='cheradip.customer')),
            ],
            options={
                'db_table': 'cheradip_created_question_sets',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='createdquestionset',
            index=models.Index(fields=['customer', 'counter'], name='cqs_customer_counter_idx'),
        ),
    ]
