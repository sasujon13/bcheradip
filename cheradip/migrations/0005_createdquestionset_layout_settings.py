# Generated manually: layout_settings for CreatedQuestionSet

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0004_pending_question'),
    ]

    operations = [
        migrations.AddField(
            model_name='createdquestionset',
            name='layout_settings',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Optional layout from creator: pageSize, margins, columns, gap, divider, padding, etc.',
            ),
        ),
    ]
