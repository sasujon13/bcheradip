"""Recoverably relocate pre-existing manuscripts out of public media."""
import hashlib
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from ecommerce.models import BookAsset
from ecommerce.private_storage import ebook_storage


class Command(BaseCommand):
    help = 'Inspect old public book files. --apply copies and verifies them in private storage, then archives public originals outside MEDIA_ROOT.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        media = Path(settings.MEDIA_ROOT).resolve()
        storage = ebook_storage()
        private = Path(storage.location).resolve()
        if private == media or media in private.parents:
            raise CommandError('PRIVATE_EBOOK_ROOT must be outside public MEDIA_ROOT.')
        for asset in BookAsset.objects.using('ecommerce').exclude(file='').iterator():
            name = asset.file.name
            source, target = (media / name).resolve(), (private / name).resolve()
            if media not in source.parents or private not in target.parents:
                raise CommandError(f'Unsafe asset path for asset {asset.pk}.')
            if not source.is_file():
                continue
            self.stdout.write(f'Asset {asset.pk}: public file needs private relocation.')
            if not options['apply']:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(source, target)
            def digest(path):
                with path.open('rb') as stream:
                    return hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest(source) != digest(target):
                raise CommandError(f'Asset {asset.pk}: conflicting private file; public source retained.')
            archive = private / 'public-originals' / name
            archive.parent.mkdir(parents=True, exist_ok=True)
            if archive.exists():
                raise CommandError(f'Asset {asset.pk}: archive already exists; investigate before retrying.')
            shutil.move(str(source), str(archive))
            self.stdout.write(f'Asset {asset.pk}: protected; original archived outside public media.')
