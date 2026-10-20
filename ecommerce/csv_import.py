import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils.text import slugify

from .models import Brand, Category, CommerceNotification, ImportJob, InventoryMovement, Product, ProductImage, ProductVariant
from .pricing import calculate_price, normalize_costs
from .delivery_rates import listing_defaults
from .models import DeliverySettings


CSV_COLUMNS = [
    'Handle', 'Title', 'Description', 'Vendor', 'Product Category', 'Type', 'Tags',
    'Published', 'Status', 'SKU', 'Barcode', 'Option1 Name', 'Option1 Value',
    'Option2 Name', 'Option2 Value', 'Option3 Name', 'Option3 Value', 'Price',
    'Compare At Price', 'Cost Per Item', 'Inventory Quantity', 'Low Stock Threshold',
    'Weight Grams', 'Requires Shipping', 'Image URL', 'Image Alt Text', 'Featured',
    'SEO Title', 'SEO Description', 'Source URL', 'Sample Product', 'Expected Inventory Quantity',
    'Dhaka Delivery Charge', 'Outside Dhaka Delivery Charge', 'COD Percent',
    'Supplier Max Delivery', 'Customer Delivery Budget', 'Ads Cost', 'Packaging Cost',
    'Return Allowance', 'Other Costs', 'Apply Calculated Price', 'Use Default Costs',
]


def _bool(value, default=False):
    if value is None or str(value).strip() == '':
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on', 'active'}


def _decimal(value, default='0'):
    try:
        parsed = Decimal(str(value).strip() or default)
    except (InvalidOperation, ValueError):
        raise ValueError(f'Invalid number: {value!r}')
    if not parsed.is_finite() or parsed < 0 or parsed > Decimal('999999999999'):
        raise ValueError(f'Price must be finite and non-negative: {value!r}')
    return parsed


def _int(value, default=0):
    try:
        return int(str(value).strip() or default)
    except (TypeError, ValueError):
        raise ValueError(f'Invalid integer: {value!r}')


def sample_csv_text():
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    rows = [
        {
            'Handle': 'sample-cotton-tshirt', 'Title': 'Sample Cotton T-Shirt',
            'Description': 'Replace this sample with your product description.', 'Vendor': 'Cheradip Sample',
            'Product Category': "Men's Clothing", 'Type': 'physical', 'Tags': 'shirt,cotton,sample',
            'Published': 'TRUE', 'Status': 'active', 'SKU': 'SAMPLE-TSHIRT-BLK-M',
            'Option1 Name': 'Color', 'Option1 Value': 'Black', 'Option2 Name': 'Size', 'Option2 Value': 'M',
            'Price': '799.00', 'Compare At Price': '999.00', 'Cost Per Item': '450.00',
            'Inventory Quantity': '25', 'Low Stock Threshold': '5', 'Weight Grams': '250',
            'Requires Shipping': 'TRUE', 'Image URL': 'https://cdn.dummyjson.com/product-images/mens-shirts/blue-&-black-check-shirt/thumbnail.webp',
            'Image Alt Text': 'Sample cotton T-shirt', 'Featured': 'TRUE',
            'SEO Title': 'Sample Cotton T-Shirt', 'SEO Description': 'CSV import example product.',
            'Source URL': 'https://dummyjson.com/docs/products', 'Sample Product': 'TRUE',
            'Dhaka Delivery Charge': 'DEFAULT', 'Outside Dhaka Delivery Charge': 'DEFAULT', 'COD Percent': 'DEFAULT',
            'Apply Calculated Price': 'FALSE', 'Use Default Costs': 'TRUE',
        },
        {
            'Handle': 'sample-cotton-tshirt', 'Title': '', 'Vendor': '', 'Product Category': '',
            'Published': 'TRUE', 'Status': 'active', 'SKU': 'SAMPLE-TSHIRT-BLU-L',
            'Option1 Name': 'Color', 'Option1 Value': 'Blue', 'Option2 Name': 'Size', 'Option2 Value': 'L',
            'Price': '849.00', 'Inventory Quantity': '15', 'Weight Grams': '260', 'Requires Shipping': 'TRUE',
            'Image URL': 'https://cdn.dummyjson.com/product-images/mens-shirts/blue-&-black-check-shirt/1.webp',
            'Image Alt Text': 'Blue sample T-shirt variant', 'Sample Product': 'TRUE',
        },
        {
            'Handle': 'sample-wireless-earbuds', 'Title': 'Sample Wireless Earbuds',
            'Description': 'Bluetooth earbuds sample listing.', 'Vendor': 'Cheradip Sample',
            'Product Category': 'Mobile Accessories', 'Type': 'physical', 'Tags': 'audio,bluetooth,sample',
            'Published': 'TRUE', 'Status': 'active', 'SKU': 'SAMPLE-EARBUD-001', 'Price': '1499.00',
            'Compare At Price': '1899.00', 'Inventory Quantity': '40', 'Low Stock Threshold': '8',
            'Weight Grams': '120', 'Requires Shipping': 'TRUE',
            'Image URL': 'https://cdn.dummyjson.com/product-images/mobile-accessories/apple-airpods/thumbnail.webp',
            'Image Alt Text': 'Sample wireless earbuds', 'Featured': 'TRUE',
            'Source URL': 'https://dummyjson.com/docs/products', 'Sample Product': 'TRUE',
        },
    ]
    for row in rows:
        writer.writerow({column: row.get(column, '') for column in CSV_COLUMNS})
    return output.getvalue()


def import_products(file_obj, user_id=None):
    raw = file_obj.read()
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(raw))
    missing = [name for name in ('Handle', 'Title', 'Product Category', 'SKU', 'Price') if name not in (reader.fieldnames or [])]
    if missing:
        raise ValueError('Missing required CSV columns: ' + ', '.join(missing))

    job = ImportJob.objects.using('ecommerce').create(filename=getattr(file_obj, 'name', 'products.csv'), created_by=user_id)
    errors = []
    created_count = updated_count = 0

    for line_number, row in enumerate(reader, start=2):
        if not any(str(value or '').strip() for value in row.values()):
            continue
        job.total_rows += 1
        try:
            with transaction.atomic(using='ecommerce'):
                handle = slugify(row.get('Handle', '').strip())
                title = row.get('Title', '').strip()
                if not handle:
                    handle = slugify(title)
                if not handle:
                    raise ValueError('Handle or Title is required.')
                sku = (row.get('SKU') or '').strip()
                if not sku:
                    raise ValueError('SKU is required.')
                product = Product.objects.using('ecommerce').filter(slug=handle).first()
                created = product is None
                if created:
                    if not title:
                        raise ValueError('Title is required for the first row of a product.')
                    category_name = row.get('Product Category', '').strip() or 'Uncategorized'
                    category, _ = Category.objects.using('ecommerce').get_or_create(
                        slug=slugify(category_name), defaults={'name': category_name}
                    )
                    vendor = row.get('Vendor', '').strip()
                    brand = None
                    if vendor:
                        brand, _ = Brand.objects.using('ecommerce').get_or_create(
                            slug=slugify(vendor), defaults={'name': vendor}
                        )
                    product = Product.objects.using('ecommerce').create(
                        name=title, slug=handle, description=row.get('Description', '').strip(),
                        short_description=row.get('Description', '').strip()[:500], category=category,
                        brand=brand, product_type=(row.get('Type', '').strip() or 'physical').lower(),
                        status=(row.get('Status', '').strip() or ('active' if _bool(row.get('Published'), True) else 'draft')).lower(),
                        tags=row.get('Tags', '').strip(), featured=_bool(row.get('Featured')),
                        seo_title=row.get('SEO Title', '').strip(), seo_description=row.get('SEO Description', '').strip(),
                        source_url=row.get('Source URL', '').strip(), is_sample=_bool(row.get('Sample Product')),
                    )
                else:
                    if title:
                        product.name = title
                        product.description = row.get('Description', '').strip() or product.description
                        product.tags = row.get('Tags', '').strip() or product.tags
                        product.status = (row.get('Status', '').strip() or product.status).lower()
                        product.featured = _bool(row.get('Featured'), product.featured)
                        product.save(using='ecommerce')

                # Blank columns preserve overrides; DEFAULT restores inheritance.
                charge_fields = {'Dhaka Delivery Charge': 'delivery_dhaka_charge',
                                 'Outside Dhaka Delivery Charge': 'delivery_outside_dhaka_charge', 'COD Percent': 'cod_percent'}
                updated_charges = []
                for column, field in charge_fields.items():
                    raw_charge = (row.get(column) or '').strip()
                    if not raw_charge:
                        continue
                    amount = None if raw_charge.lower() == 'default' else _decimal(raw_charge)
                    if amount is not None and (amount > (Decimal('100') if field == 'cod_percent' else Decimal('99999999.99')) or amount.as_tuple().exponent < -2):
                        raise ValueError(f'{column} must be non-negative with at most two decimal places (COD maximum 100%).')
                    setattr(product, field, amount)
                    updated_charges.append(field)
                if updated_charges:
                    product.save(using='ecommerce', update_fields=updated_charges + ['updated_at'])

                previous_variant = ProductVariant.objects.using('ecommerce').select_for_update().filter(sku=sku).first()
                if previous_variant and previous_variant.product_id != product.pk:
                    raise ValueError('This SKU belongs to a different product. Use its existing Handle or a new SKU.')
                price_text = (row.get('Price') or '').strip()
                stock_text = (row.get('Inventory Quantity') or '').strip()
                source_cost = _decimal(row.get('Cost Per Item')) if row.get('Cost Per Item', '').strip() else (previous_variant.cost_price if previous_variant else None)
                pricing_inputs = dict(previous_variant.pricing_inputs) if previous_variant else {}
                weight = _int(row.get('Weight Grams')) if row.get('Weight Grams','').strip() else previous_variant.weight_grams if previous_variant else 0
                if weight < 0: raise ValueError('Weight Grams cannot be negative.')
                pricing_columns = {'Supplier Max Delivery': 'supplier_delivery_max', 'Customer Delivery Budget': 'customer_delivery_charge',
                    'Ads Cost': 'ads_cost', 'Packaging Cost': 'packaging_cost', 'Return Allowance': 'returns_allowance', 'Other Costs': 'other_costs'}
                for column, key in pricing_columns.items():
                    raw_cost = (row.get(column) or '').strip()
                    if raw_cost:
                        pricing_inputs[key] = raw_cost
                inherit = _bool(row.get('Use Default Costs')) or not pricing_inputs
                if _bool(row.get('Use Default Costs')) and any((row.get(column) or '').strip() for column in pricing_columns):
                    raise ValueError('Use Default Costs cannot be combined with manual cost columns. Leave them empty or disable defaults.')
                if inherit: pricing_inputs = {}
                if pricing_inputs:
                    pricing_inputs = normalize_costs(pricing_inputs)
                suggested = calculate_price(source_cost, listing_defaults(DeliverySettings.current(),weight)[0] if inherit else pricing_inputs) if _bool(row.get('Apply Calculated Price')) else None
                if not previous_variant and not price_text and not suggested:
                    raise ValueError('Price is required for a new SKU.')
                if not previous_variant and not stock_text:
                    raise ValueError('Inventory Quantity is required for a new SKU.')
                stock = _int(stock_text) if stock_text else previous_variant.stock
                if previous_variant and stock_text and stock != previous_variant.stock:
                    expected = (row.get('Expected Inventory Quantity') or '').strip()
                    if not expected or _int(expected) != previous_variant.stock:
                        raise ValueError('Stock changed or was not confirmed. Set Expected Inventory Quantity to the current stock, or leave Inventory Quantity empty to preserve stock.')
                if stock < 0:
                    raise ValueError('Inventory Quantity cannot be negative.')
                defaults = {
                    'product': product,
                    'title': ' / '.join(filter(None, [row.get('Option1 Value', '').strip(), row.get('Option2 Value', '').strip(), row.get('Option3 Value', '').strip()])) or 'Default',
                    'barcode': row.get('Barcode', '').strip(), 'option1_name': row.get('Option1 Name', '').strip(),
                    'option1_value': row.get('Option1 Value', '').strip(), 'option2_name': row.get('Option2 Name', '').strip(),
                    'option2_value': row.get('Option2 Value', '').strip(), 'option3_name': row.get('Option3 Name', '').strip(),
                    'option3_value': row.get('Option3 Value', '').strip(), 'price': Decimal(suggested['suggested_price']) if suggested else _decimal(price_text) if price_text else previous_variant.price,
                    'compare_at_price': _decimal(row.get('Compare At Price')) if row.get('Compare At Price', '').strip() else (previous_variant.compare_at_price if previous_variant else None),
                    'cost_price': source_cost, 'pricing_inputs': pricing_inputs,
                    'stock': stock, 'low_stock_threshold': max(0, _int(row.get('Low Stock Threshold'), 5)),
                    'weight_grams': weight,
                    'requires_shipping': _bool(row.get('Requires Shipping'), True), 'is_active': True,
                }
                previous_stock = previous_variant.stock if previous_variant else 0
                variant, variant_created = ProductVariant.objects.using('ecommerce').update_or_create(sku=sku, defaults=defaults)
                stock_delta = stock - previous_stock
                if variant_created or stock_delta:
                    InventoryMovement.objects.using('ecommerce').create(
                        variant=variant, quantity=stock_delta, reason='import', reference=job.filename, actor_id=user_id,
                    )
                image_url = row.get('Image URL', '').strip()
                if image_url:
                    ProductImage.objects.using('ecommerce').get_or_create(
                        product=product, variant=variant, url=image_url,
                        defaults={'alt_text': row.get('Image Alt Text', '').strip() or product.name},
                    )
            if created:
                created_count += 1
            else:
                updated_count += 1
        except Exception as exc:
            errors.append({'line': line_number, 'error': str(exc)[:500]})

    job.created_count = created_count
    job.updated_count = updated_count
    job.failed_count = len(errors)
    job.errors = errors[:200]
    job.status = 'completed' if not errors else ('failed' if created_count == 0 and updated_count == 0 else 'completed')
    job.save(using='ecommerce')
    CommerceNotification.objects.using('ecommerce').create(
        kind='import', title='Product CSV import completed',
        message=f'{created_count} created, {updated_count} updated, {len(errors)} failed.',
        link=f'/admin/ecommerce/importjob/{job.pk}/change/', admin_only=True,
    )
    return job

