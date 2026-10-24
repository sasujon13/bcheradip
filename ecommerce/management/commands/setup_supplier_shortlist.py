from django.core.management.base import BaseCommand
from ecommerce.models import Supplier


class Command(BaseCommand):
    help = 'Add the nine selected supplier configuration placeholders, DISABLED; never imports products or purchases plans.'

    def handle(self, *args, **options):
        entries = [('ShopBase BD', 'https://shopbasebd.com/'), ('Business Koro', 'https://www.businesskoro.com/'),
            ('Uddoog / DropShop', 'https://dropshop.com.bd/'), ('SelfShop', 'https://selfshop.com.bd/'),
            ('DropBazarBD', 'https://dropbazarbd.com/'),
            ('DropifyBD', 'https://www.dropifybd.com/'), ('ResellKori', 'https://resellkori.com/'),
            ('Dropshipping.com.bd', 'https://www.dropshipping.com.bd/'), ('BDResellHUB', 'https://www.bdresellhub.com/')]
        created = 0
        for name, url in entries:
            _, added = Supplier.objects.using('ecommerce').get_or_create(name=name, defaults={'website': url})
            created += int(added)
        self.stdout.write(f'{created} disabled supplier placeholders added; existing settings preserved.')
