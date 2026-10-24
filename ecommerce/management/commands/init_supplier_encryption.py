"""Explicit one-time setup, not automatic key rotation or a credential export."""
import getpass
import os
from pathlib import Path
import subprocess
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from ecommerce.models import Supplier


class Command(BaseCommand):
    help = 'Create an owner-protected local supplier encryption key, without printing it or replacing an existing key.'

    def handle(self, *args, **options):
        from ecommerce.supplier_crypto import cipher
        if getattr(settings, 'COMMERCE_SUPPLIER_KEY', ''):
            try:
                cipher()
            except ValueError as exc:
                raise CommandError(str(exc))
            self.stdout.write('Existing environment key retained.')
            return
        target = getattr(settings, 'COMMERCE_SUPPLIER_KEY_FILE', '')
        if not target:
            raise CommandError('Set a protected COMMERCE_SUPPLIER_KEY_FILE path first.')
        path = Path(target).resolve()
        if path.exists():
            try:
                cipher()
            except ValueError as exc:
                raise CommandError(str(exc))
            self.stdout.write('Existing encryption file retained; no key was printed or rotated.')
            return
        if Supplier.objects.using('ecommerce').exclude(credentials_ciphertext='').exists():
            raise CommandError('Encrypted credentials already exist. Restore the original key; do not generate a replacement.')
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        def protect(target, directory=False):
            if os.name == 'nt':
                identity = os.environ.get('USERDOMAIN', '') + '\\' + getpass.getuser()
                grant = identity.lstrip('\\') + (':(OI)(CI)F' if directory else ':F')
                result = subprocess.run(['icacls', str(target), '/inheritance:r', '/grant:r', grant], capture_output=True)
                if result.returncode:
                    raise CommandError('Could not restrict encryption-path permissions. No key was printed.')
            else:
                os.chmod(target, 0o700 if directory else 0o600)
        protect(path.parent, directory=True)
        try:
            with path.open('xb') as stream:
                stream.write(Fernet.generate_key())
            protect(path)
        except OSError:
            raise CommandError('Could not create the protected key file. No existing key was overwritten.') from None
        self.stdout.write('Protected supplier encryption initialized. Back up this file securely; it is not copied by deployment.')
