from django.db import transaction
from .models import (
    Book, Brand, Category, CommerceNotification, Product, ProductImage, ProductVariant,
)


def sync_book_catalog(book: Book, notify: bool = True) -> Product:
    """Mirror book metadata into the existing storefront product/variant tables."""
    with transaction.atomic(using='ecommerce'):
        parent, _ = Category.objects.using('ecommerce').get_or_create(
            slug='books-ebooks',
            defaults={'name': 'Books & eBooks', 'description': 'Digital and printed books for Cheradip readers.'},
        )
        category_slug = f"books-{book.book_type.replace('_', '-')}"
        category, _ = Category.objects.using('ecommerce').get_or_create(
            slug=category_slug,
            defaults={
                'name': book.get_book_type_display(), 'parent': parent,
                'description': f'{book.get_book_type_display()} books for Bangladesh.',
            },
        )
        brand, _ = Brand.objects.using('ecommerce').get_or_create(
            slug='cheradip-books', defaults={'name': 'Cheradip Books'},
        )
        product_defaults = {
            'name': book.title,
            'description': book.description,
            'short_description': book.subtitle or book.preview_text[:500],
            'category': category,
            'brand': brand,
            'product_type': 'physical' if book.hard_copy_available else 'digital',
            'status': 'active' if book.status == 'published' else ('archived' if book.status == 'archived' else 'draft'),
            'featured': book.featured,
            'tags': book.tags,
            'attributes': {
                'book_id': book.pk, 'book_type': book.book_type, 'audience': book.audience,
                'language': book.language, 'author': book.author, 'publisher': book.publisher,
                'isbn': book.isbn, 'edition': book.edition, 'publication_year': book.publication_year,
                'page_count': book.page_count, 'source_type': book.source_type,
            },
        }
        if book.product_id:
            product = Product.objects.using('ecommerce').filter(pk=book.product_id).first()
            if product:
                for key, value in product_defaults.items():
                    setattr(product, key, value)
                product.slug = book.slug
                product.save(using='ecommerce')
            else:
                book.product_id = None
        if not book.product_id:
            product, _ = Product.objects.using('ecommerce').update_or_create(
                slug=book.slug,
                defaults=product_defaults,
            )
            Book.objects.using('ecommerce').filter(pk=book.pk).update(product_id=product.pk)
            book.product_id = product.pk

        ProductVariant.objects.using('ecommerce').update_or_create(
            sku=f'BOOK-{book.pk:06d}-DIGITAL',
            defaults={
                'product': product, 'title': 'Digital eBook', 'price': book.digital_price,
                'compare_at_price': book.compare_at_price, 'stock': 999999,
                'low_stock_threshold': 0, 'weight_grams': 0, 'requires_shipping': False,
                'allow_backorder': True, 'is_active': book.status == 'published',
                'option1_name': 'Format', 'option1_value': 'Digital',
            },
        )
        ProductVariant.objects.using('ecommerce').update_or_create(
            sku=f'BOOK-{book.pk:06d}-HARDCOPY',
            defaults={
                'product': product, 'title': 'Printed hard copy',
                'price': book.hard_copy_price if book.hard_copy_price is not None else book.digital_price,
                'compare_at_price': book.compare_at_price, 'stock': book.hard_copy_quantity,
                'low_stock_threshold': 5, 'weight_grams': book.weight_grams, 'requires_shipping': True,
                'allow_backorder': False,
                'is_active': book.status == 'published' and book.hard_copy_available,
                'option1_name': 'Format', 'option1_value': 'Hard copy',
            },
        )
        if book.cover_image:
            ProductImage.objects.using('ecommerce').update_or_create(
                product=product, position=0,
                defaults={'url': book.cover_image.url, 'alt_text': f'{book.title} cover'},
            )
        if notify:
            CommerceNotification.objects.using('ecommerce').create(
                kind='system', title=f'Book catalog updated: {book.title}',
                message=f'{book.get_book_type_display()} · {book.get_status_display()}',
                link=f'/admin/ecommerce/book/{book.pk}/change/', admin_only=True,
            )
        return product


def book_variant_ids(book: Book) -> dict:
    variants = ProductVariant.objects.using('ecommerce').filter(product_id=book.product_id)
    return {
        'digital_variant_id': variants.filter(sku__endswith='-DIGITAL', is_active=True).values_list('id', flat=True).first(),
        'hard_copy_variant_id': variants.filter(sku__endswith='-HARDCOPY', is_active=True).values_list('id', flat=True).first(),
    }
