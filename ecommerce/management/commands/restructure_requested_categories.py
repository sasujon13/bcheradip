"""Apply the reviewed two-level storefront category moves."""
import re
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from ecommerce.models import Category, Product


def remember_legacy(product, *categories):
    attrs = dict(product.attributes or {})
    aliases = list(attrs.get('_catalog_legacy_categories', []))
    for category in categories:
        if not category:
            continue
        aliases.append(category.slug)
        if category.parent_id:
            aliases.append(category.parent.slug)
    attrs['_catalog_legacy_categories'] = list(dict.fromkeys(aliases))
    return attrs


class Command(BaseCommand):
    help = 'Move/rename the requested departments without creating a third category level.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        apply = options['apply']
        summary = []
        with transaction.atomic(using='ecommerce'):
            electronics = self.department('Electronics')
            tools = self.department('Tools & Home Improvement')
            watches = self.department('Watches & Accessories')
            womens = self.department("Women's Fashion")
            smartwatches = self.child(electronics, 'Smartwatches')

            summary.append(self.reparent_children('Computer & Accessories', electronics, apply))
            summary.append(self.reparent_children('Office & Stationery', electronics, apply))
            summary.append(self.reparent_children('Automotive', tools, apply))
            summary.append(self.rename_category(watches, 'Watches & Jewelry', 'watches-jewelry', apply))
            wrist = self.child(watches, 'Wristwatches')
            summary.append(self.rename_category(wrist, 'Wrist Watches', 'wrist-watches', apply))
            summary.append(self.move_pet_watches(smartwatches, wrist, apply))
            summary.append(self.rehome_dresses(womens, apply))
            if not apply:
                transaction.set_rollback(True, using='ecommerce')
        for line in summary:
            self.stdout.write(line)
        self.stdout.write('Applied.' if apply else 'Preview only. Re-run with --apply to save.')

    def department(self, name):
        qs = Category.objects.using('ecommerce').filter(name=name, parent=None, is_active=True)
        if qs.count() != 1:
            raise CommandError(f'Expected one active department named {name}, found {qs.count()}')
        return qs.get()

    def child(self, parent, name):
        qs = parent.children.filter(name=name)
        if not qs.exists():
            raise CommandError(f'Missing {parent.name} / {name}')
        return qs.first()

    def deactivate(self, category, apply):
        if apply:
            Category.objects.using('ecommerce').filter(pk=category.pk).update(is_active=False, updated_at=timezone.now())

    def reparent_children(self, source_name, destination, apply):
        source = self.department(source_name)
        moved = []
        for child in list(source.children.filter(is_active=True)):
            existing = destination.children.filter(name=child.name, is_active=True).exclude(pk=child.pk).first()
            if existing:
                count = Product.objects.using('ecommerce').filter(category=child).count()
                if apply:
                    self.merge_into(child, existing)
                moved.append(f'{child.name} merged into {destination.name}/{existing.name} ({count} products)')
            else:
                if apply:
                    child.parent = destination
                    child.save(update_fields=['parent'])
                moved.append(f'{child.name} -> {destination.name}/{child.name}')
        leftover = Product.objects.using('ecommerce').filter(category=source)
        leftover_n = leftover.count()
        if leftover_n and apply:
            for product in leftover:
                Product.objects.using('ecommerce').filter(pk=product.pk).update(
                    category=destination, attributes=remember_legacy(product, source), updated_at=timezone.now())
        self.deactivate(source, apply)
        extra = f'; {leftover_n} department listings moved to {destination.name}' if leftover_n else ''
        return f'Removed {source_name}: ' + ('; '.join(moved) or 'no children') + extra

    def merge_into(self, source, destination):
        for product in Product.objects.using('ecommerce').filter(category=source):
            Product.objects.using('ecommerce').filter(pk=product.pk).update(
                category=destination, attributes=remember_legacy(product, source), updated_at=timezone.now())
        for product in Product.objects.using('ecommerce').filter(secondary_categories=source):
            product.secondary_categories.remove(source)
            product.secondary_categories.add(destination)
        self.deactivate(source, True)

    def rename_category(self, category, name, slug, apply):
        old = category.name
        if apply:
            taken = Category.objects.using('ecommerce').filter(slug=slug).exclude(pk=category.pk).exists()
            Category.objects.using('ecommerce').filter(pk=category.pk).update(
                name=name, slug=category.slug if taken else slug, updated_at=timezone.now())
        return f'Renamed {old} -> {name}'

    def move_pet_watches(self, smartwatches, wrist, apply):
        try:
            pets = self.department('Pet Supplies')
        except CommandError:
            return 'Pet Supplies already removed'
        care = pets.children.filter(is_active=True)
        watch_n = other_n = 0
        for child in care:
            for product in Product.objects.using('ecommerce').filter(category=child):
                text = f'{product.name} {product.short_description or ""}'.casefold()
                destination = smartwatches if re.search(r'kospet|smart\s*watch|\bwatch\b|ঘড়ি', text) else None
                if destination is None:
                    other_n += 1
                    continue
                watch_n += 1
                if apply:
                    Product.objects.using('ecommerce').filter(pk=product.pk).update(
                        category=destination, attributes=remember_legacy(product, child, pets),
                        updated_at=timezone.now())
        return (
            f'Pet Supplies: moved {watch_n} watch listings to {smartwatches.name}; '
            f'left {other_n} aquarium/pet listings in place (not Wrist Watches)'
        )

    def rehome_dresses(self, womens, apply):
        dresses = Category.objects.using('ecommerce').filter(name='Dresses', parent__name='Clothing & Fashion', is_active=True)
        if not dresses.exists():
            return 'Dresses already removed'
        dresses = dresses.get()
        destinations = {name: self.child(womens, name) for name in (
            'Party Dresses', 'Gowns', 'Kurtis', 'Lehengas', 'Maxi Dresses', 'Three-Piece Sets',
            'Co-ord Sets', 'Skirt Sets', 'Matching Sets', 'Sarees', 'Nightdresses', 'Jeans', 'Casual Shirts',
        )}
        counts = {}
        for product in Product.objects.using('ecommerce').filter(category=dresses):
            target = self.dress_destination(product, destinations, womens)
            counts[target.name] = counts.get(target.name, 0) + 1
            if apply:
                Product.objects.using('ecommerce').filter(pk=product.pk).update(
                    category=target, attributes=remember_legacy(product, dresses), updated_at=timezone.now())
        self.deactivate(dresses, apply)
        inactive = Category.objects.using('ecommerce').filter(name='Dresses').exclude(pk=dresses.pk)
        if apply:
            inactive.update(is_active=False, updated_at=timezone.now())
        detail = ', '.join(f'{name} {n}' for name, n in sorted(counts.items(), key=lambda item: -item[1]))
        return f'Removed Dresses ({sum(counts.values())} products): {detail}'

    def dress_destination(self, product, destinations, womens):
        text = f'{product.name} {product.short_description or ""} {product.description or ""}'.casefold()
        rules = (
            (r'saree|শাড়ি|শাড়ি', 'Sarees'),
            (r'lehenga|ঘাঘরা', 'Lehengas'),
            (r'three[ -]?piece|3\s*pis|থ্রি ?পি[চস]|ফোর পিস|four piece', 'Three-Piece Sets'),
            (r'co-?ord|two[ -]?piece|2\s*piece|টু ?পি[চস]|two piece kurti', 'Co-ord Sets'),
            (r'skirt\s+(?:set|lehenga)|স্কার্ট', 'Skirt Sets'),
            (r'night\s*dress|নৈশ', 'Nightdresses'),
            (r'maxi', 'Maxi Dresses'),
            (r'party|পার্টি', 'Party Dresses'),
            (r'gown|গ্রাউন|anarkali', 'Gowns'),
            (r'kurti|কুর্তি', 'Kurtis'),
            (r'\bdenim\b|\bjeans\b', 'Jeans'),
            (r'\btops?\b|শার্ট', 'Casual Shirts'),
            (r'matching set', 'Matching Sets'),
        )
        for pattern, name in rules:
            if re.search(pattern, text):
                return destinations[name]
        return womens
