"""
Create any missing subject question tables from current cheradip_subject.
Safe to run after loading subject data on a new environment. Uses CREATE TABLE IF NOT EXISTS.
Also runs automatically after each migrate (post_migrate signal).
"""
from django.core.management.base import BaseCommand
from cheradip.subject_question_tables import ensure_subject_question_tables


class Command(BaseCommand):
    help = 'Create missing subject question tables from cheradip_subject (safe, idempotent). Runs automatically after migrate.'

    def handle(self, *args, **options):
        created, total = ensure_subject_question_tables(verbose=True)
        self.stdout.write(self.style.SUCCESS(f'Subject question tables: {created} created, {total} total expected from cheradip_subject.'))
