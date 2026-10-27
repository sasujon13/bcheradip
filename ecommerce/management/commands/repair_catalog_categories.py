"""Correct reviewed clock-category mistakes without touching staff assignments."""
from collections import Counter
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ecommerce.catalog_structure import classify, ensure_category, category_slug
from ecommerce.models import Product

REVIEWED_TITLES = (
    'Elegant Stylish Baby Hoodie Set', 'Premium Kids Sherpa Padding Jacket',
    'Cotton T-shirt and Trouser Set', 'Mash T-Shirt and Short Pant Set',
    'Premium Stylish Skirt Set',
    "Gent's Sweetshirt",
    'Kemei Kemei KM-026', 'Chest Strap Mount', 'MiLi MiTag Android Device',
    'Mobile Phone Waterproof Box', 'FRB N27', '140W স্মার্ট ফুল চার্জ সেপারেটর',
    'Portable Smart Electric Grape Peeler', 'Memo CX07 Magnetic Phone Cooler',
    'MEMO CX12 Magnetic Phone Cooler', 'Mini Body Massage Gun SL-720',
    'Hoco GA6 Glacier AI Semiconductor Mobile Cooler',
)


class Command(BaseCommand):
    help = 'Preview/apply narrowly reviewed category corrections.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--through-id', type=int, help='Limit corrections to the completed review checkpoint.')

    def handle(self, *args, **options):
        reviewed = Counter()
        changed = Counter()
        examples = []
        scope = Q(category__slug__in=['home-living-clocks', 'shoes-bags-footwear'])
        for title in REVIEWED_TITLES:
            scope |= Q(name__istartswith=title)
        products = Product.objects.using('ecommerce').select_related('category').filter(
            scope, status='active',
        ).order_by('pk')
        if options['through_id']:
            products = products.filter(pk__lte=options['through_id'])
        for product in products:
            reviewed['products'] += 1
            metadata = (product.attributes or {}).get('_catalog', {})
            if metadata.get('manual_category'):
                reviewed['staff_assignments_preserved'] += 1
                continue
            plan = classify(product.name)
            if product.category.slug == 'shoes-bags-footwear' and plan['path'] != ['Shoes & Bags', 'Shoe Care']:
                reviewed['kept_or_needs_review'] += 1
                continue
            if not plan['path'] and product.description:
                plan = classify(product.name, description=product.description)
            if plan['reason'] != 'title' or not plan['path'] or product.category.slug == category_slug(plan['path']):
                reviewed['kept_or_needs_review'] += 1
                continue
            # A clear product-type phrase in the title is required. Do not
            # let generic supplier labels or incidental description words move
            # a listing. The full-catalogue audit handles ambiguous cases.
            path = tuple(plan['path'])
            changed[' / '.join(path)] += 1
            if len(examples) < 30:
                examples.append((product.pk, product.name[:85], ' / '.join(path)))
            if not options['apply']:
                continue
            with transaction.atomic(using='ecommerce'):
                row = Product.objects.using('ecommerce').select_for_update().get(pk=product.pk)
                attrs = row.attributes or {}
                if attrs.get('_catalog', {}).get('manual_category') or row.category_id != product.category_id:
                    continue
                destination = ensure_category(path)
                aliases = list(dict.fromkeys([*attrs.get('_catalog_legacy_categories', []), row.category.slug]))
                updated_attrs = {**attrs, '_catalog': {**metadata, **plan, 'reviewed_at': timezone.now().isoformat()},
                                 '_catalog_legacy_categories': aliases}
                # Classification changes do not alter publication, stock or
                # price. Avoid rerunning the unrelated full-catalogue release
                # check in Product.save() for every corrected row.
                Product.objects.using('ecommerce').filter(pk=row.pk, category_id=row.category_id).update(
                    category=destination, attributes=updated_attrs, updated_at=timezone.now())
        self.stdout.write(str({'apply': options['apply'], 'reviewed': dict(reviewed),
                               'reassignments': dict(changed), 'examples': examples}))
