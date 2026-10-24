"""Fail closed except for owner-approved, individually verified manual pilots."""
MESSAGE = 'Supplier imports require a current individual staff pilot release. Automatic supplier purchasing is OFF; unverified products cannot be published or purchased.'


def is_supplier_staging(product_id):
    from .models import SupplierOffer, Product
    from .supplier_pilot import current_release
    if not product_id or not SupplierOffer.objects.using('ecommerce').filter(imported_product_id=product_id).exists():
        return False
    from .manual_catalogue import public_ids
    if Product.objects.using('ecommerce').filter(pk=product_id, pk__in=public_ids()).exists():
        return False
    try:
        current_release(Product.objects.using('ecommerce').get(pk=product_id))
        return False
    except (ValueError,SupplierOffer.DoesNotExist):
        return True


def check_publication(product, status=None):
    from .models import SupplierOffer
    if (status or product.status) == 'active' and product.pk and SupplierOffer.objects.using('ecommerce').filter(imported_product_id=product.pk).exists():
        from .manual_catalogue import public_ids
        if product.pk in public_ids():
            return
        from .supplier_pilot import current_release
        current_release(product)
