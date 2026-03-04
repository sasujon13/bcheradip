# Unify class into single class_level CharField: '0'..'8', '9-10', '11-12', '13-16'

from django.db import migrations, models


def copy_class_to_char(apps, schema_editor):
    Subject = apps.get_model('cheradip', 'Subject')
    for row in Subject.objects.all():
        if row.class_level is not None:
            row.class_level_str = str(row.class_level)
        elif row.class_range:
            row.class_level_str = row.class_range.strip()
        else:
            row.class_level_str = None
        row.save(update_fields=['class_level_str'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0006_subject_class_range'),
    ]

    operations = [
        migrations.AddField(
            model_name='subject',
            name='class_level_str',
            field=models.CharField(blank=True, db_index=True, max_length=10, null=True),
        ),
        migrations.RunPython(copy_class_to_char, noop),
        migrations.RemoveField(
            model_name='subject',
            name='class_level',
        ),
        migrations.RemoveField(
            model_name='subject',
            name='class_range',
        ),
        migrations.RenameField(
            model_name='subject',
            old_name='class_level_str',
            new_name='class_level',
        ),
    ]
