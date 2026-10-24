"""Visible reseller-card observations, not bulk MOQ rates, retail prices or profit.

This enriches source references only. It never asserts cross-supplier equivalence,
reserves inventory, imports shop products or places an order.
"""
from collections import Counter
from decimal import Decimal
import hashlib
from urllib.parse import urlsplit

from django.db import transaction
from django.utils import timezone

from .models import SupplierOffer
from .supplier_connectors import RESTRICTED
from .supplier_service import DB, audit

BUYING_LABELS = {'আপনার পাইকারি মূল্য', 'Your wholesale price'}


def observe_card(supplier, item, actor=None):
    from .supplier_browser import amount
    parts = urlsplit(str(item.get('url') or ''))
    title = str(item.get('title') or '').strip()
    if (parts.scheme == 'https' and parts.hostname in ('businesskoro.com', 'www.businesskoro.com') and
            not parts.username and not parts.password and parts.port in (None, 443) and
            parts.path == '/dashboard/membership' and item.get('access_required') is True and title):
        with transaction.atomic(using=DB):
            held = list(SupplierOffer.objects.using(DB).select_for_update().filter(supplier=supplier, title=title))
            for offer in held:
                offer.match_confirmed = False
                offer.availability, offer.quantity = 'unconfirmed', None
                if offer.state != 'excluded': offer.state = 'needs_data'
                offer.save(using=DB, update_fields=['match_confirmed', 'availability', 'quantity', 'state', 'updated_at'])
        audit('browser_catalogue_membership_required', actor, supplier, title=title[:255],
            existing_offer_ids=[o.pk for o in held],
            url='https://www.businesskoro.com/dashboard/products', notice=str(item.get('stock_text') or '')[:300],
            source_price=None, note='Supplier hides buying price/product access behind membership. No bypass, quote or purchasable offer created.')
        return 'access_required'
    if (parts.scheme != 'https' or parts.hostname not in ('businesskoro.com', 'www.businesskoro.com') or
            parts.username or parts.password or parts.port not in (None, 443) or parts.query or parts.fragment or
            not parts.path.startswith('/dashboard/products/') or not parts.path[len('/dashboard/products/'):].strip('/')):
        raise ValueError('A specific Business Koro reseller product URL is required.')
    if not title or len(title) > 255:
        raise ValueError('A complete visible product title is required.')
    if item.get('price_label') not in BUYING_LABELS:
        raise ValueError('Only the labelled personal wholesale buying price may be collected; never suggested retail or estimated profit.')
    price = amount(item.get('price'))
    if price is None:
        raise ValueError('The labelled buying price must be one unambiguous amount, not a range.')
    price = Decimal(price)
    url = 'https://www.businesskoro.com' + parts.path.rstrip('/')
    if RESTRICTED.search(title):
        audit('browser_restricted_card_skipped', actor, supplier, title=title, url=url)
        return 'restricted_skipped'
    observed = timezone.now()
    detail = {'url': url, 'title': title, 'observed_at': observed.isoformat(), 'buying_price': str(price),
              'price_label': item['price_label'], 'retail_not_used': item.get('retail_text'),
              'stock_text': item.get('stock_text'), 'basis': 'Signed-in reseller card; not bulk wholesale MOQ pricing',
              'variant_stock_confirmed': False}
    with transaction.atomic(using=DB):
        # Reuse a previously recorded URL. Legacy API rows have UUIDs and may
        # have multiple variants: linking a reference must not replace those IDs,
        # per-variant stock/costs or structured identities with a parent-card quote.
        existing = list(SupplierOffer.objects.using(DB).select_for_update().filter(supplier=supplier, url=url))
        if not existing:
            candidates = list(SupplierOffer.objects.using(DB).select_for_update().filter(supplier=supplier, title=title))
            parent_ids = {o.external_id for o in candidates}
            if len(parent_ids) == 1 and candidates and all(o.title.strip() == title and o.source_price == price and
                    o.url.startswith('https://www.businesskoro.com/dashboard/products#') for o in candidates):
                existing = candidates
                for offer in existing:
                    offer.url = url
                    if offer.state == 'ready': offer.state = 'needs_review'
                    offer.save(using=DB, update_fields=['url', 'state', 'updated_at'])
                audit('browser_source_reference_linked', actor, supplier, offer_ids=[o.pk for o in existing],
                    **detail, note='Same-supplier title and buying quote agree. Reference only; identity matching remains unconfirmed.')
                return 'reference_enriched'
            if candidates:
                for offer in candidates:
                    offer.match_confirmed = False
                    if offer.state != 'excluded': offer.state = 'needs_review'
                    offer.save(using=DB, update_fields=['match_confirmed', 'state', 'updated_at'])
                audit('browser_source_reference_needs_review', actor, supplier, offer_ids=[o.pk for o in candidates],
                    **detail, note='Ambiguous parent identity or differing card/variant price; old mappings and prices preserved.')
                return 'conflict'
        if existing:
            changed = [o for o in existing if o.title.strip() != title or o.source_price != price]
            for offer in changed:
                offer.match_confirmed = False
                if offer.state != 'excluded': offer.state = 'needs_review'
                offer.save(using=DB, update_fields=['match_confirmed', 'state', 'updated_at'])
            audit('browser_buying_price_observed', actor, supplier, offer_ids=[o.pk for o in existing], **detail)
            return 'quote_changed' if changed else 'existing'
        stock = str(item.get('stock_text') or '').casefold()
        availability = 'out_of_stock' if 'out of stock' in stock else 'in_stock' if ('in stock' in stock or 'low stock' in stock) else 'unconfirmed'
        # Explicit URL-derived parent identity. Variants, MOQ, weight, tax,
        # authenticity and reservable stock still require detail-page research.
        offer = SupplierOffer.objects.using(DB).create(supplier=supplier,
            external_id='url-' + hashlib.sha256(url.encode()).hexdigest()[:40], vendor_id='not-provided',
            title=title, url=url, source_price=price, availability=availability, quantity=None,
            identity={'authenticity': 'unverified', 'tax_basis': 'unconfirmed'}, single_unit=False,
            observed_at=observed, state='needs_review')
        audit('browser_parent_identity_collected', actor, supplier, offer, **detail,
            identity_kind='URL-derived parent reference, not a supplier-issued product/variant ID')
        return 'new'


def import_catalogue(supplier, items, actor=None):
    if supplier.connector != 'business_koro' or not supplier.enabled or not supplier.terms_confirmed:
        raise ValueError('Use the enabled, approved Business Koro supplier only.')
    if not isinstance(items, list) or not items or len(items) > 1000:
        raise ValueError('Use 1–1000 browser-observed cards per reconciliation.')
    seen, counts, failures = {}, Counter(), []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            failures.append({'row': index + 1, 'reason': 'Invalid card record'}); counts['failed'] += 1; continue
        url = item.get('url')
        key = (url, item.get('title')) if item.get('access_required') else url
        if key in seen:
            if item != seen[key]:
                failures.append({'row': index + 1, 'reason': 'Conflicting repeated source URL; not overwritten'})
                counts['conflict'] += 1
            else: counts['duplicate_on_source'] += 1
            continue
        seen[key] = item
        try: counts[observe_card(supplier, item, actor)] += 1
        except ValueError as exc:
            counts['failed'] += 1; failures.append({'row': index + 1, 'reason': str(exc)})
    result = {'observed_cards': len(items), 'unique_cards': len(seen),
              'accessible_product_urls': len({i.get('url') for i in items if isinstance(i, dict) and not i.get('access_required')}),
              'counts': dict(counts), 'failures': failures}
    audit('browser_catalogue_reconciled', actor, supplier, **result)
    if not failures and not counts.get('conflict'):
        type(supplier).objects.using(DB).filter(pk=supplier.pk).update(last_success_at=timezone.now(),
            health=f'Browser catalogue observed: {len(items)} cards; {counts.get("access_required",0)} membership holds; variant stock unverified',
            updated_at=timezone.now())
    return result
