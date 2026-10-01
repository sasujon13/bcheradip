import json
from decimal import Decimal
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from ecommerce.models import Brand, Category, Product, ProductImage, ProductVariant


CATEGORIES = [
    ('Beauty & Personal Care', 'beauty'), ('Fragrances', 'fragrances'),
    ('Health & Wellness', 'skin-care'), ("Women's Clothing", 'womens-dresses'),
    ("Men's Clothing", 'mens-shirts'), ('Kids & Baby', 'tops'),
    ('Shoes', 'womens-shoes'), ('Bags & Luggage', 'womens-bags'),
    ('Jewelry & Watches', 'womens-jewellery'), ('Smartphones', 'smartphones'),
    ('Tablets & E-readers', 'tablets'), ('Mobile Accessories', 'mobile-accessories'),
    ('Laptops', 'laptops'), ('Desktop Computers', 'laptops'),
    ('Computer Accessories', 'mobile-accessories'), ('Computer Components', 'laptops'),
    ('Networking', 'mobile-accessories'), ('Cameras & Photography', 'mobile-accessories'),
    ('TV & Home Entertainment', 'mobile-accessories'), ('Audio & Headphones', 'mobile-accessories'),
    ('Smart Home', 'home-decoration'), ('Gadgets & Wearables', 'mobile-accessories'),
    ('Video Games', 'mobile-accessories'), ('Home & Furniture', 'furniture'),
    ('Home Decor', 'home-decoration'), ('Kitchen & Dining', 'kitchen-accessories'),
    ('Appliances', 'kitchen-accessories'), ('Groceries', 'groceries'),
    ('Books & Stationery', 'home-decoration'), ('Office Supplies', 'home-decoration'),
    ('Toys & Games', 'sports-accessories'), ('Sports & Outdoors', 'sports-accessories'),
    ('Automotive', 'vehicle'), ('Motorcycle', 'motorcycle'),
    ('Tools & Home Improvement', 'home-decoration'), ('Garden & Outdoor', 'home-decoration'),
    ('Pet Supplies', 'groceries'), ('Industrial & Scientific', 'home-decoration'),
    ('Arts & Crafts', 'home-decoration'), ('Musical Instruments', 'mobile-accessories'),
    ('Travel & Experiences', 'vehicle'),
]

# DummyJSON has excellent public sample data but does not cover every broad
# marketplace department. These department-specific names prevent unrelated
# source items (for example groceries in Pet Supplies) from being presented as
# if they belonged to that department.
CATEGORY_PRODUCT_BASES = {
    'Desktop Computers': ('Desktop PC', 'Business Workstation', 'Gaming Tower', 'All-in-One Computer'),
    'Computer Accessories': ('Wireless Mouse', 'Mechanical Keyboard', 'USB Hub', 'Laptop Stand', 'Webcam'),
    'Computer Components': ('Graphics Card', 'Memory Kit', 'Solid State Drive', 'Power Supply', 'CPU Cooler'),
    'Networking': ('Wi-Fi Router', 'Network Switch', 'Range Extender', 'Ethernet Adapter', 'Mesh Wi-Fi Node'),
    'Cameras & Photography': ('Mirrorless Camera', 'Camera Lens', 'Tripod', 'Camera Bag', 'LED Photo Light'),
    'TV & Home Entertainment': ('Smart Television', 'Streaming Box', 'Projector', 'Soundbar', 'TV Wall Mount'),
    'Audio & Headphones': ('Wireless Headphones', 'Bluetooth Speaker', 'Studio Microphone', 'Earbuds', 'Audio Interface'),
    'Smart Home': ('Smart Bulb', 'Security Camera', 'Smart Plug', 'Video Doorbell', 'Home Sensor'),
    'Gadgets & Wearables': ('Smart Watch', 'Fitness Band', 'Portable Tracker', 'Smart Ring', 'Action Camera'),
    'Video Games': ('Game Controller', 'Gaming Headset', 'Console Dock', 'Arcade Stick', 'Gaming Chair'),
    'Books & Stationery': ('Notebook Set', 'Fountain Pen', 'Study Planner', 'Reference Book', 'Art Marker Set'),
    'Office Supplies': ('Desk Organizer', 'Printer Paper', 'Stapler Set', 'Document Folder', 'Label Maker'),
    'Toys & Games': ('Building Block Set', 'Board Game', 'Remote Control Car', 'Learning Puzzle', 'Doll House'),
    'Tools & Home Improvement': ('Cordless Drill', 'Hand Tool Set', 'Measuring Tape', 'Safety Kit', 'Paint Roller Set'),
    'Garden & Outdoor': ('Garden Tool Set', 'Outdoor Planter', 'Watering Hose', 'Patio Light', 'Camping Chair'),
    'Pet Supplies': ('Dry Pet Food', 'Pet Bed', 'Training Leash', 'Pet Carrier', 'Grooming Brush'),
    'Industrial & Scientific': ('Digital Caliper', 'Safety Goggles', 'Lab Scale', 'Soldering Station', 'Storage Bin'),
    'Arts & Crafts': ('Acrylic Paint Set', 'Canvas Pack', 'Craft Paper Kit', 'Sewing Kit', 'Sculpting Clay'),
    'Musical Instruments': ('Acoustic Guitar', 'Digital Keyboard', 'Drum Pad', 'Ukulele', 'Studio Stand'),
    'Travel & Experiences': ('Weekend Resort Package', 'City Tour Pass', 'Adventure Day Trip', 'Travel Gift Card', 'Museum Pass'),
}
SAMPLE_MODIFIERS = ('Essential', 'Classic', 'Plus', 'Pro', 'Max', 'Mini', 'Smart', 'Premium', 'Eco', 'Studio')


class Command(BaseCommand):
    help = 'Seed the ecommerce database with marketplace categories and replaceable sample products.'

    def add_arguments(self, parser):
        parser.add_argument('--per-category', type=int, default=10)
        parser.add_argument('--replace-samples', action='store_true')

    def handle(self, *args, **options):
        per_category = max(10, options['per_category'])
        if options['replace_samples']:
            Product.objects.using('ecommerce').filter(is_sample=True).delete()

        products_by_category = self._source_products()
        brand, _ = Brand.objects.using('ecommerce').get_or_create(
            slug='cheradip-sample', defaults={'name': 'Cheradip Sample Catalog'}
        )
        created = 0
        with transaction.atomic(using='ecommerce'):
            for sort_order, (category_name, source_category) in enumerate(CATEGORIES, start=1):
                category, _ = Category.objects.using('ecommerce').update_or_create(
                    slug=slugify(category_name),
                    defaults={
                        'name': category_name,
                        'sort_order': sort_order,
                        'is_active': True,
                        'description': f'Sample {category_name.lower()} catalog. Replace these items from the admin or CSV import.',
                    },
                )
                source_items = products_by_category.get(source_category) or []
                custom_bases = CATEGORY_PRODUCT_BASES.get(category_name)
                for index in range(per_category):
                    source = source_items[index % len(source_items)] if source_items and not custom_bases else {}
                    if custom_bases:
                        name = f'{custom_bases[index % len(custom_bases)]} {SAMPLE_MODIFIERS[index % len(SAMPLE_MODIFIERS)]}'
                    else:
                        source_title = source.get('title') or category_name.rstrip('s')
                        suffix = '' if index < len(source_items) else f' Sample {index + 1}'
                        name = f'{source_title}{suffix}'
                    slug = slugify(f'{category_name}-{name}-{index + 1}')[:255]
                    sample_description = f'Replaceable sample {name.lower()} for the {category_name} department.'
                    product, product_created = Product.objects.using('ecommerce').update_or_create(
                        slug=slug,
                        defaults={
                            'name': name,
                            'description': source.get('description') or sample_description,
                            'short_description': (source.get('description') or sample_description)[:500],
                            'category': category,
                            'brand': brand,
                            'status': 'active',
                            'featured': index < 2,
                            'tags': f'{slugify(category_name)},{source_category},sample',
                            'source_url': f'https://dummyjson.com/products/{source.get("id")}' if source.get('id') else 'https://dummyjson.com/docs/products',
                            'is_sample': True,
                        },
                    )
                    price_usd = Decimal(str(source.get('price') or (12 + index * 3)))
                    price_bdt = (price_usd * Decimal('120')).quantize(Decimal('1.00'))
                    ProductVariant.objects.using('ecommerce').update_or_create(
                        sku=f'SAMPLE-{sort_order:02d}-{index + 1:03d}',
                        defaults={
                            'product': product, 'title': 'Default', 'price': price_bdt,
                            'compare_at_price': (price_bdt * Decimal('1.15')).quantize(Decimal('1.00')),
                            'currency': 'BDT', 'stock': 20 + index * 3, 'low_stock_threshold': 5,
                            'weight_grams': 250 + index * 25, 'requires_shipping': True, 'is_active': True,
                        },
                    )
                    image_url = source.get('thumbnail') or f'https://dummyjson.com/image/600x400/008080/ffffff?text={slugify(name)}'
                    ProductImage.objects.using('ecommerce').update_or_create(
                        product=product, position=0,
                        defaults={'url': image_url, 'alt_text': name},
                    )
                    created += int(product_created)

        self.stdout.write(self.style.SUCCESS(
            f'{len(CATEGORIES)} categories ready; {per_category} samples per category; {created} products created.'
        ))

    def _source_products(self):
        try:
            request = Request('https://dummyjson.com/products?limit=0', headers={'User-Agent': 'Cheradip sample catalog importer'})
            with urlopen(request, timeout=25) as response:
                payload = json.loads(response.read().decode('utf-8'))
            grouped = {}
            for item in payload.get('products', []):
                grouped.setdefault(item.get('category', ''), []).append(item)
            self.stdout.write(f'Loaded {len(payload.get("products", []))} public sample products from DummyJSON.')
            return grouped
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f'DummyJSON unavailable; using generated placeholders: {exc}'))
            return {}

