"""Read-only visibility funnel for supplier catalog investigations."""
import json
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone
from ecommerce.models import Product, Supplier, SupplierOffer, SupplierJob, SupplierPolicy, SupplierSourceProduct, Category
from ecommerce.manual_catalogue import purchasable_offers


class Command(BaseCommand):
    help = 'Report storefront visibility exclusions without changing catalog records.'

    def handle(self, *args, **options):
        now = timezone.now()
        eligible = purchasable_offers()
        report = {'checked_at': now.isoformat(), 'suppliers': []}
        for supplier in Supplier.objects.using('ecommerce').order_by('pk'):
            offers = SupplierOffer.objects.using('ecommerce').filter(supplier=supplier)
            linked = offers.filter(imported_product__isnull=False)
            active = linked.filter(imported_product__status='active')
            report['suppliers'].append({
                'id': supplier.pk, 'name': supplier.name,
                'offers': offers.count(), 'linked': linked.count(),
                'product_status': list(linked.values('imported_product__status').annotate(n=Count('id'))),
                'active': active.count(),
                'active_in_stock': active.filter(availability='in_stock').count(),
                'active_stale_in_stock': active.filter(availability='in_stock',observed_at__lt=now-timedelta(hours=24)).count(),
                'active_category_review': active.filter(imported_product__attributes___catalog__status='needs_review').count(),
                'orderable': eligible.filter(supplier=supplier).count(),
                'public': eligible.filter(supplier=supplier,imported_product__status='active').count(),
                'last_offer_check': str(offers.order_by('-observed_at').values_list('observed_at',flat=True).first()),
                'source_checks_last_hour': SupplierSourceProduct.objects.using('ecommerce').filter(
                    supplier=supplier, updated_at__gte=now-timedelta(hours=1)).count(),
            })
        report['products'] = list(Product.objects.using('ecommerce').values('status').annotate(n=Count('id')))
        report['categories'] = Category.objects.using('ecommerce').count()
        report['active_categories'] = Category.objects.using('ecommerce').filter(is_active=True).count()
        report['last_nightly_date'] = str(SupplierPolicy.objects.using('ecommerce').filter(pk=1).values_list('last_nightly_date', flat=True).first())
        report['jobs'] = list(SupplierJob.objects.using('ecommerce').order_by('-created_at').values(
            'supplier__name', 'action', 'status', 'processed', 'total', 'activity', 'created_at', 'finished_at'
        )[:12])
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, default=str))
