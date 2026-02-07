# Drop table cheradip_subject_translated and remove SubjectTranslated from state

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0030_replace_science_music_in_subject_name_tr'),
    ]

    operations = [
        migrations.DeleteModel(name='SubjectTranslated'),
    ]
