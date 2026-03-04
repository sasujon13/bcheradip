# Move class_level column to after groups (match CSV order: level, level_tr, groups, class, ...)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0007_subject_class_level_char'),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE cheradip_subject MODIFY COLUMN class_level VARCHAR(10) NULL AFTER groups;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
