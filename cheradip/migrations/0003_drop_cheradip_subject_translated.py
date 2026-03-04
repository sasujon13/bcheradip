# Drop legacy table cheradip_subject_translated; all data now in cheradip_subject.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0002_subject_to_cheradip_subject'),
    ]

    operations = [
        migrations.RunSQL(
            "DROP TABLE IF EXISTS cheradip_subject_translated",
            migrations.RunSQL.noop,
        ),
    ]
