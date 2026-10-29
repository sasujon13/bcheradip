"""Retire the misnamed Pet Supplies bucket without classifying fish food as watches."""
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from ecommerce.models import Category, Product
from .restructure_requested_categories import remember_legacy


class Command(BaseCommand):
    help = 'Preview or move the remaining Pet Supplies products into accurate two-level types.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        using = 'ecommerce'
        parent = Category.objects.using(using).filter(name='Pet Supplies', parent=None, is_active=True).first()
        if not parent:
            self.stdout.write('Pet Supplies already retired.')
            return
        home = Category.objects.using(using).get(name='Home & Living', parent=None, is_active=True)
        sports = Category.objects.using(using).get(name='Sports & Outdoors', parent=None, is_active=True)
        watches = Category.objects.using(using).get(name='Watches & Jewelry', parent=None, is_active=True)
        electronics = Category.objects.using(using).get(name='Electronics', parent=None, is_active=True)
        targets = {
            'aquarium': self._child(home, 'Aquarium Supplies', options['apply']),
            'lighting': self._child(home, 'Lighting', options['apply']),
            'cleaning': self._child(home, 'Cleaning & Laundry', options['apply']),
            'outdoors': self._child(sports, 'Outdoor Gear', options['apply']),
            'wristwatch': self._child(watches, 'Wrist Watches', options['apply']),
            'smartwatch': self._child(electronics, 'Smartwatches', options['apply']),
        }
        counts = {key: 0 for key in targets}
        destinations = {}
        with transaction.atomic(using=using):
            categories = [parent, *Category.objects.using(using).filter(parent=parent)]
            for product in Product.objects.using(using).filter(category__in=categories).select_related('category__parent'):
                text = f'{product.name} {product.short_description or ""}'.casefold()
                if re.search(r'\bsmart\s*watch\b|স্মার্ট\s*ঘড়ি', text):
                    key = 'smartwatch'
                elif re.search(r'\bwatch\b|wristwatch|ঘড়ি', text):
                    key = 'wristwatch'
                elif re.search(r'\bfishing\b', text):
                    key = 'outdoors'
                elif re.search(r'\bpet hair remover\b', text):
                    key = 'cleaning'
                elif re.search(r'\bclip lamp\b', text):
                    key = 'lighting'
                else:
                    key = 'aquarium'
                counts[key] += 1
                destinations[product.pk] = targets[key]
                if options['apply']:
                    Product.objects.using(using).filter(pk=product.pk).update(
                        category=targets[key],
                        attributes=remember_legacy(product, product.category, parent),
                        updated_at=timezone.now(),
                    )
            if options['apply']:
                for category in categories:
                    for product in Product.objects.using(using).filter(secondary_categories=category):
                        product.secondary_categories.remove(category)
                        destination = destinations.get(product.pk)
                        if destination and product.category_id != destination.pk:
                            product.secondary_categories.add(destination)
                Category.objects.using(using).filter(pk__in=[item.pk for item in categories]).update(
                    is_active=False, updated_at=timezone.now())
            else:
                transaction.set_rollback(True, using=using)
        self.stdout.write(', '.join(f'{key}={count}' for key, count in counts.items()))
        self.stdout.write('Applied.' if options['apply'] else 'Preview only.')

    def _child(self, parent, name, apply):
        child = Category.objects.using('ecommerce').filter(parent=parent, name=name).first()
        if child:
            return child
        if name != 'Aquarium Supplies':
            raise CommandError(f'Missing category {parent.name} / {name}')
        from django.utils.text import slugify
        fields = dict(parent=parent, name=name,
                      slug=slugify(f'{parent.name} {name}')[:180], is_active=True)
        if not apply:
            return Category(**fields)
        return Category.objects.using('ecommerce').create(**fields)
