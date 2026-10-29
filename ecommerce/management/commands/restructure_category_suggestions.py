"""Apply reviewed taxonomy suggestions 1-4 and 6-7 (skip sunglasses)."""
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from ecommerce.category_suggestion_rules import (
    beauty_destination, clothing_destination, electronics_destination,
    kids_destination, product_text,
)
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
    help = 'Merge kids/mobile departments, flatten redundant types, classify untyped dumps. Skips sunglasses.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        apply = options['apply']
        self.created = []
        self.deactivated = []
        summary = []
        with transaction.atomic(using='ecommerce'):
            summary.append(self.merge_mobile())
            summary.append(self.flatten_type('Digital Services', 'Software & Services'))
            summary.append(self.flatten_type('Food & Groceries', 'Food & Drinks'))
            summary.append(self.merge_toys_into_kids())
            summary.append(self.rehome_kids())
            summary.append(self.classify_untyped('Electronics', electronics_destination))
            summary.append(self.classify_untyped('Clothing & Fashion', clothing_destination))
            summary.append(self.classify_untyped('Beauty & Personal Care', beauty_destination))
            summary.append(self.deactivate_empty_kids_departments())
            if not apply:
                transaction.set_rollback(True, using='ecommerce')
        for line in summary:
            if line:
                self.stdout.write(line)
        if self.created:
            self.stdout.write('Types created: ' + ', '.join(dict.fromkeys(self.created)))
        if self.deactivated:
            self.stdout.write('Deactivated: ' + ', '.join(dict.fromkeys(self.deactivated)))
        self.stdout.write('Applied.' if apply else 'Preview only. Re-run with --apply to save.')

    def department(self, name, required=True):
        qs = Category.objects.using('ecommerce').filter(name=name, parent=None, is_active=True)
        if qs.count() == 1:
            return qs.get()
        if not required:
            return None
        raise CommandError(f'Expected one active department named {name}, found {qs.count()}')

    def child(self, parent, name):
        qs = parent.children.filter(name=name, is_active=True)
        if qs.exists():
            return qs.first()
        return parent.children.filter(name=name).first()

    def ensure_child(self, parent, name):
        existing = self.child(parent, name)
        if existing:
            if not existing.is_active:
                Category.objects.using('ecommerce').filter(pk=existing.pk).update(
                    is_active=True, updated_at=timezone.now())
                existing.is_active = True
            return existing
        slug = slugify(f'{parent.name} {name}')[:180]
        if Category.objects.using('ecommerce').filter(slug=slug).exists():
            slug = (slug[:160] + '-' + str(parent.pk))[:180]
        category = Category.objects.using('ecommerce').create(
            name=name, slug=slug, parent=parent, is_active=True)
        self.created.append(f'{parent.name}/{name}')
        return category

    def resolve(self, path):
        department = self.department(path[0])
        if len(path) == 1:
            return department
        return self.ensure_child(department, path[1])

    def deactivate(self, category):
        if not category or not category.is_active:
            return
        self.deactivated.append(category.name)
        Category.objects.using('ecommerce').filter(pk=category.pk).update(
            is_active=False, updated_at=timezone.now())
        category.is_active = False

    def move_product(self, product, destination, *legacy):
        if not destination or product.category_id == destination.pk:
            return False
        sources = [product.category, *legacy]
        Product.objects.using('ecommerce').filter(pk=product.pk).update(
            category=destination, attributes=remember_legacy(product, *sources),
            updated_at=timezone.now())
        secondary = set(product.secondary_categories.values_list('pk', flat=True))
        if destination.pk in secondary:
            product.secondary_categories.remove(destination)
        for category in sources:
            if category and category.pk in secondary:
                product.secondary_categories.remove(category)
        return True

    def merge_into(self, source, destination):
        count = 0
        for product in Product.objects.using('ecommerce').filter(category=source):
            self.move_product(product, destination, source)
            count += 1
        for product in Product.objects.using('ecommerce').filter(secondary_categories=source):
            product.secondary_categories.remove(source)
            product.secondary_categories.add(destination)
        self.deactivate(source)
        return count

    def reparent_or_merge(self, child, destination_parent, merge_name=None):
        target_name = merge_name or child.name
        existing = destination_parent.children.filter(
            name=target_name, is_active=True).exclude(pk=child.pk).first()
        count = Product.objects.using('ecommerce').filter(category=child).count()
        if existing:
            self.merge_into(child, existing)
            return f'{child.name} merged into {destination_parent.name}/{existing.name} ({count})'
        child.parent = destination_parent
        child.save(update_fields=['parent'])
        if merge_name and child.name != merge_name:
            Category.objects.using('ecommerce').filter(pk=child.pk).update(
                name=merge_name, updated_at=timezone.now())
        return f'{child.name} -> {destination_parent.name}/{target_name} ({count})'

    def merge_mobile(self):
        source = self.department('Mobile & Accessories', required=False)
        if not source:
            return 'Mobile & Accessories already removed'
        electronics = self.department('Electronics')
        moved = []
        for child in list(source.children.filter(is_active=True)):
            merge_name = 'Phone Cases & Accessories' if child.name == 'Phone Cases' else None
            moved.append(self.reparent_or_merge(child, electronics, merge_name=merge_name))
        leftover_n = 0
        for product in Product.objects.using('ecommerce').filter(category=source):
            self.move_product(product, electronics, source)
            leftover_n += 1
        self.deactivate(source)
        extra = f'; {leftover_n} department listings moved to Electronics' if leftover_n else ''
        return 'Removed Mobile & Accessories: ' + '; '.join(moved) + extra

    def flatten_type(self, department_name, type_name):
        department = self.department(department_name, required=False)
        if not department:
            return f'{department_name} already removed'
        child = department.children.filter(name=type_name, is_active=True).first()
        if not child:
            return f'{department_name}/{type_name} already flattened'
        count = 0
        for product in Product.objects.using('ecommerce').filter(category=child):
            self.move_product(product, department, child)
            count += 1
        for product in Product.objects.using('ecommerce').filter(secondary_categories=child):
            product.secondary_categories.remove(child)
        self.deactivate(child)
        return f'Flattened {department_name}/{type_name}: {count} products now sit on {department_name}'

    def merge_toys_into_kids(self):
        source = self.department('Toys & Games', required=False)
        if not source:
            return 'Toys & Games already removed'
        kids = self.department('Kids & Baby')
        moved = []
        for child in list(source.children.filter(is_active=True)):
            moved.append(self.reparent_or_merge(child, kids))
        leftover_n = 0
        if Product.objects.using('ecommerce').filter(category=source).exists():
            toys = self.ensure_child(kids, 'Toys')
            for product in Product.objects.using('ecommerce').filter(category=source):
                self.move_product(product, toys, source)
                leftover_n += 1
        self.deactivate(source)
        extra = f'; {leftover_n} department listings moved to Kids & Baby/Toys' if leftover_n else ''
        return 'Removed Toys & Games: ' + '; '.join(moved) + extra

    def rehome_kids(self):
        kids = self.department('Kids & Baby')
        counts = defaultdict(int)
        sources = []
        toys_dept = self.department('Kids & Toys', required=False)
        if toys_dept:
            sources.append((toys_dept, True))
            sources.extend((child, True) for child in toys_dept.children.filter(is_active=True))
        for name in ('Kids Zone', 'Baby Collection', 'Baby & Kids', 'Baby Item', 'Baby Winter', 'Baby &amp; Kids'):
            sources.extend((category, True) for category in Category.objects.using('ecommerce').filter(name=name, parent=None))
        clothing = self.department('Clothing & Fashion', required=False)
        if clothing:
            sources.append((clothing, False))
            sources.extend((child, False) for child in clothing.children.filter(is_active=True))
        home = self.department('Home & Living', required=False)
        blankets = self.child(home, 'Blankets') if home else None
        if blankets:
            sources.append((blankets, False))
        seen = set()
        for source, assume in sources:
            for product in Product.objects.using('ecommerce').filter(category=source).select_related('category', 'category__parent'):
                if product.pk in seen:
                    continue
                if product.category.parent_id and product.category.parent.name == 'Kids & Baby':
                    continue
                dest = kids_destination(product_text(product), assume_kids=assume)
                if dest is None:
                    continue
                if dest == ('Kids & Baby',):
                    if source == blankets:
                        dest = ('Kids & Baby', 'Baby Bedding')
                    elif not assume:
                        dest = ('Kids & Baby', "Children's Clothing")
                destination = self.resolve(dest)
                seen.add(product.pk)
                if self.move_product(product, destination, source):
                    counts[' / '.join(dest)] += 1
        if toys_dept:
            for product in Product.objects.using('ecommerce').filter(category=toys_dept):
                if product.pk in seen:
                    continue
                if self.move_product(product, kids, toys_dept):
                    counts['Kids & Baby'] += 1
            self.deactivate(toys_dept)
        detail = ', '.join(f'{name} {n}' for name, n in sorted(counts.items(), key=lambda item: -item[1]))
        return f'Kids listings moved into Kids & Baby ({sum(counts.values())}): {detail or "none"}'

    def classify_untyped(self, department_name, classifier):
        department = self.department(department_name, required=False)
        if not department:
            return f'{department_name} missing'
        counts = defaultdict(int)
        stayed = 0
        for product in list(Product.objects.using('ecommerce').filter(category=department)):
            dest = classifier(product_text(product))
            if not dest:
                stayed += 1
                continue
            destination = self.resolve(dest)
            if self.move_product(product, destination, department):
                counts[' / '.join(dest)] += 1
            else:
                stayed += 1
        detail = ', '.join(f'{name} {n}' for name, n in sorted(counts.items(), key=lambda item: -item[1]))
        return (
            f'{department_name} untyped: classified {sum(counts.values())}, '
            f'left {stayed} on department' + (f'. {detail}' if detail else '')
        )

    def deactivate_empty_kids_departments(self):
        names = (
            'Kids & Toys', 'Toys & Games', 'Kids Zone', 'Baby Collection', 'Baby & Kids',
            'Baby Item', 'Baby Winter', 'Baby &amp; Kids', 'Toys',
        )
        removed = []
        for name in names:
            for category in Category.objects.using('ecommerce').filter(name=name, parent=None, is_active=True):
                has_products = Product.objects.using('ecommerce').filter(category=category).exists()
                has_secondary = Product.objects.using('ecommerce').filter(secondary_categories=category).exists()
                has_children = category.children.filter(is_active=True).exists()
                if has_products or has_secondary or has_children:
                    continue
                self.deactivate(category)
                removed.append(name)
        return 'Empty kids departments deactivated: ' + (', '.join(removed) or 'none')
