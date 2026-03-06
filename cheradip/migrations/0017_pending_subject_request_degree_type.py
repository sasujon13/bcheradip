# Add degree_type to PendingSubjectRequest (Degree Type for Groups column on approve)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0016_degree_subjects_seed'),
    ]

    operations = [
        migrations.AddField(
            model_name='pendingsubjectrequest',
            name='degree_type',
            field=models.CharField(blank=True, help_text='Degree Type: Degree, Honours (Pass), Honours, B.Sc, BSS, BBA, MBA, MSS, MSC, Others; stored in Subject.groups on approve.', max_length=50, null=True),
        ),
    ]
