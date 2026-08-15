from django.core.management.base import BaseCommand

from childcare.views import DASHBOARD_MODULES
from childcare import models


class Command(BaseCommand):
    help = "Seed the 15 Child Care dashboard modules into the childcare database"

    def handle(self, *args, **options):
        created = 0
        for key, en, bn, icon, order in DASHBOARD_MODULES:
            _, was_created = models.Module.objects.using("childcare").update_or_create(
                key=key,
                defaults={
                    "title_en": en,
                    "title_bn": bn,
                    "icon_name": icon,
                    "sort_order": order,
                    "is_enabled": True,
                },
            )
            if was_created:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded modules. newly_created={created} total={len(DASHBOARD_MODULES)}"))
