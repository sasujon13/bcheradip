# Seed limited Degree / Honours / Masters subjects for BD (class_level 13-16).
# Safe to run: only inserts if no 13-16 subjects exist for BD.

from django.db import migrations


# subject_code must be <= 12 chars (Subject.subject_code max_length)
DEGREE_SUBJECTS_BD = [
    ('DEG_BANGLA', 'বাংলা', 'Bengali'),
    ('DEG_ENGLISH', 'ইংরেজি', 'English'),
    ('DEG_HISTORY', 'ইতিহাস', 'History'),
    ('DEG_PHILOS', 'দর্শন', 'Philosophy'),
    ('DEG_ISLAMIC', 'ইসলামের ইতিহাস', 'Islamic History'),
    ('DEG_POLSCI', 'রাষ্ট্রবিজ্ঞান', 'Political Science'),
    ('DEG_ECON', 'অর্থনীতি', 'Economics'),
    ('DEG_MATH', 'গণিত', 'Mathematics'),
    ('DEG_PHYSICS', 'পদার্থবিজ্ঞান', 'Physics'),
    ('DEG_CHEM', 'রসায়ন', 'Chemistry'),
    ('DEG_ZOOLOGY', 'প্রাণিবিজ্ঞান', 'Zoology'),
    ('DEG_BOTANY', 'উদ্ভিদবিজ্ঞান', 'Botany'),
    ('DEG_GEO', 'ভূগোল', 'Geography'),
    ('DEG_ICT', 'তথ্য ও যোগাযোগ প্রযুক্তি', 'Information and Communication Technology'),
]


def seed_degree_subjects(apps, schema_editor):
    Subject = apps.get_model('cheradip', 'Subject')
    # Only seed if no 13-16 subjects exist for BD
    if Subject.objects.filter(class_level='13-16', country_id='BD').exists():
        return
    for subject_code, subject_name, subject_translated in DEGREE_SUBJECTS_BD:
        Subject.objects.get_or_create(
            subject_code=subject_code,
            defaults={
                'level': 'Degree / Honours / Masters',
                'level_tr': 'Degree / Honours / Masters',
                'class_level': '13-16',
                'subject_name': subject_name,
                'subject_translated': subject_translated,
                'country_id': 'BD',
                'groups': None,
            }
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0015_add_pending_subject_reviewed_by'),
    ]

    operations = [
        migrations.RunPython(seed_degree_subjects, noop_reverse),
    ]
