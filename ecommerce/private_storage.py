"""Book manuscripts must never be served by the public media alias."""
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateEbookStorage(FileSystemStorage):
    @property
    def location(self):
        location = Path(getattr(settings, 'PRIVATE_EBOOK_ROOT', str(Path(settings.BASE_DIR) / 'private_ebooks'))).resolve()
        media = Path(settings.MEDIA_ROOT).resolve()
        if location == media or media in location.parents:
            from django.core.exceptions import ImproperlyConfigured
            raise ImproperlyConfigured('PRIVATE_EBOOK_ROOT must be outside public MEDIA_ROOT.')
        return str(location)

    @property
    def base_location(self):
        return self.location


def ebook_storage():
    return PrivateEbookStorage(base_url='/api/ecommerce/private-files/')
