# Ensure subject_code is unique in cheradip_subject

from django.db import migrations, models


def remove_duplicate_subject_codes(apps, schema_editor):
    """Keep one row per subject_code (smallest id), delete the rest."""
    Subject = apps.get_model('cheradip', 'Subject')
    seen = set()
    to_delete = []
    for row in Subject.objects.order_by('id').values_list('id', 'subject_code'):
        sid, code = row[0], (row[1] or '').strip()
        if not code or code in seen:
            to_delete.append(sid)
        else:
            seen.add(code)
    if to_delete:
        Subject.objects.filter(id__in=to_delete).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0008_subject_class_level_after_groups'),
    ]

    operations = [
        migrations.RunPython(remove_duplicate_subject_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='subject',
            name='subject_code',
            field=models.CharField(db_index=True, max_length=12, unique=True),
        ),
    ]
