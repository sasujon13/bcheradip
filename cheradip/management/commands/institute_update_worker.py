"""Run the durable public and monthly institute update queue."""

from django.core.management.base import BaseCommand

from cheradip.institute_refresh import run_worker_loop, worker_iteration


class Command(BaseCommand):
    help = 'Refresh queued institutes and automatically run the monthly Banbeis/EMIS pass.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Process one bounded iteration and exit.')
        parser.add_argument('--poll-seconds', type=int, default=5)

    def handle(self, *args, **options):
        if options['once']:
            worked = worker_iteration(prune=True)
            self.stdout.write('Institute update work processed.' if worked else 'No institute update is due.')
            return
        poll_seconds = max(2, int(options['poll_seconds']))
        self.stdout.write(f'Institute update worker started (polling every {poll_seconds}s when idle).')
        run_worker_loop(poll_seconds=poll_seconds)
