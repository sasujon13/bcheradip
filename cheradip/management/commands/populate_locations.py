"""
Management command to populate Location (cheradip_location) from location.py.
Creates one Location per (division, district, thana) for Bangladesh.
Run: python manage.py populate_locations
"""
from django.core.management.base import BaseCommand
from cheradip.models import Location, Country
from cheradip.location import Bangladesh


class Command(BaseCommand):
    help = 'Populate Location (cheradip_location) from Bangladesh division/district/thana data'

    def handle(self, *args, **options):
        self.stdout.write('Starting to populate location data...')
        bd = Country.objects.filter(country_code='BD').first()
        if not bd:
            self.stdout.write(self.style.WARNING('Country BD (Bangladesh) not found. Run insert_all_countries or add BD first.'))
            return
        total = 0
        for division_name, districts_dict in Bangladesh.items():
            for district_name, thanas_list in districts_dict.items():
                for thana_name in thanas_list:
                    loc, created = Location.objects.get_or_create(
                        country=bd,
                        division=division_name,
                        district=district_name,
                        thana=thana_name,
                        defaults={'local_address': ''}
                    )
                    if created:
                        total += 1
            self.stdout.write(f'  Processed {len(districts_dict)} districts in {division_name}')
        self.stdout.write(self.style.SUCCESS(f'\nCompleted! Created {total} location records.'))
