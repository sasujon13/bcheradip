"""Build/refresh the AI Tutor topic index (cheradip_tutor_topic_index).

Usage:
    python manage.py build_tutor_index            # incremental (upsert)
    python manage.py build_tutor_index --rebuild  # wipe + rebuild
    python manage.py build_tutor_index --verbose
"""
from django.core.management.base import BaseCommand

from cheradip import tutor_search


class Command(BaseCommand):
    help = 'Build the AI Tutor topic index from the subject question tables.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--rebuild', action='store_true',
            help='Delete existing index rows before rebuilding.',
        )
        parser.add_argument(
            '--verbose', action='store_true',
            help='Print a line per scanned table.',
        )

    def handle(self, *args, **options):
        rebuild = options['rebuild']
        verbose = options['verbose']
        self.stdout.write('Building AI Tutor topic index (rebuild=%s)...' % rebuild)
        rows = tutor_search.build_index(rebuild=rebuild, verbose=verbose)
        self.stdout.write(self.style.SUCCESS('Done: %d topic rows indexed.' % rows))
