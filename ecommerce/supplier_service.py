"""Deterministic sourcing decisions, bounded resumable jobs and draft-only imports.

No undocumented supplier requests, external purchases or automatic publication.
"""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import re
import uuid
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone
from .models import (Supplier, SupplierPolicy, SupplierOffer, SupplierDecision, SupplierJob,
                     SupplierAudit, Product, ProductVariant, Category, CommerceNotification, DeliverySettings)
from .pricing import calculate_price, money, normalize_default_costs

DB = 'ecommerce'
ACTIVE = ('queued', 'running', 'cancel_requested')
MONEY_COSTS = ('ads_cost', 'packaging_cost', 'returns_allowance', 'other_costs')
SNAPSHOT_FIELDS = {'external_id', 'variant_id', 'vendor_id', 'warehouse_id', 'title', 'url', 'identity',
                   'source_price', 'currency', 'availability', 'quantity', 'weight_grams', 'single_unit', 'observed_at', 'preview_images'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def audit(action, actor=None, supplier=None, offer=None, **detail):
    return SupplierAudit.objects.using(DB).create(action=action, actor_id=actor, supplier=supplier, offer=offer, detail=detail)


def public_url(value):
    # Stored reference only: there is deliberately no arbitrary HTTP-fetch API.
    parts = urlsplit(str(value))
    if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username or parts.password:
        raise ValueError('Use a public HTTP/HTTPS reference URL without embedded credentials.')
    if parts.hostname.lower() in ('localhost', 'localhost.localdomain') or ':' in parts.hostname:
        raise ValueError('Use a public website URL.')
    import ipaddress
    try:
        if not ipaddress.ip_address(parts.hostname).is_global:
            raise ValueError('Private network URLs are not allowed.')
    except ValueError as exc:
        if 'not allowed' in str(exc):
            raise
    return str(value)


def match_key(identity):
    """Exact structured identifiers only. Matching still requires explicit staff confirmation."""
    required = ('brand', 'model', 'variant', 'pack_count', 'condition', 'warranty', 'accessories', 'authenticity')
    if not isinstance(identity, dict) or any(identity.get(k) in (None, '') for k in required):
        return ''
    if identity['authenticity'] == 'unverified':
        return ''
    result = {k: str(identity[k]).strip().casefold() for k in (*required, 'gtin') if k in identity}
    # Never collapse different materials/specifications or dimensions into a title-only match.
    for key in ('specifications', 'dimensions'):
        if identity.get(key):
            result[key] = identity[key]
    return digest(result)


def policy():
    return SupplierPolicy.objects.using(DB).get_or_create(pk=1)[0]


def costs_for(offer):
    # Use existing central NON-DELIVERY defaults, never a delivery-inclusive floor.
    defaults = normalize_default_costs(DeliverySettings.current().cost_defaults)
    costs = offer.costs
    if not isinstance(costs, dict) or set(costs) - set((*MONEY_COSTS, 'supplier_shipping', 'customer_shipping', 'fees', 'taxes')):
        raise ValueError('Unsupported sourcing cost fields.')
    return {k: money(costs.get(k, defaults.get(k, '0')), k) for k in
            (*MONEY_COSTS, 'supplier_shipping', 'customer_shipping', 'fees', 'taxes')}


def fingerprint(offer, config):
    return digest({'source': [offer.source_price, offer.currency, offer.availability, offer.quantity,
        offer.observed_at, offer.single_unit, offer.match_key, offer.match_confirmed, offer.costs,
        offer.weight_grams, offer.excluded_reason, offer.identity, offer.url], 'costs': costs_for(offer),
        'supplier': [offer.supplier.enabled, offer.supplier.terms_confirmed, offer.supplier.updated_at],
        'policy': [config.revision, config.evidence_days, DeliverySettings.current().pricing_rules],
        'alternative_sources': list(valid_alternatives(offer, config).values('pk', 'source_price', 'observed_at', 'state', 'supplier__updated_at')),
        'evidence': list(offer.evidence.order_by('pk').values('id', 'seller', 'url', 'price', 'observed_at',
                                               'exact_match', 'match_confidence', 'available', 'match_key'))})


def valid_alternatives(offer, config):
    if offer.currency != 'BDT' or offer.source_price is None or not offer.match_key or offer.match_key != match_key(offer.identity):
        return SupplierOffer.objects.using(DB).none()
    return SupplierOffer.objects.using(DB).filter(match_key=offer.match_key, match_confirmed=True,
        currency='BDT', source_price__isnull=False, single_unit=True, availability='in_stock', excluded_reason='', supplier__enabled=True,
        supplier__terms_confirmed=True, observed_at__gte=timezone.now() - timedelta(days=config.evidence_days),
        observed_at__lte=timezone.now()).exclude(quantity=0).exclude(pk=offer.pk).order_by('source_price', 'pk')


def screen(offer, actor=None):
    with transaction.atomic(using=DB):
        offer = SupplierOffer.objects.using(DB).select_for_update().select_related('supplier').get(pk=offer.pk)
        config = policy()
        now = timezone.now()
        cutoff = now - timedelta(days=config.evidence_days)
        result = {'rule_version': 3, 'policy_revision': config.revision, 'checked_at': now.isoformat(),
                  'research_method': 'Staff-entered evidence; no automated market search configured'}
        state, reasons = 'needs_data', []
        costs = costs_for(offer)
        # Never add an unconverted foreign price to BDT cost defaults.
        comparable = offer.currency == 'BDT' and offer.source_price is not None
        floor = (offer.source_price + sum((costs[k] for k in MONEY_COSTS), Decimal('0')) + costs['fees'] + costs['taxes']) if comparable else None
        suggested = Decimal(calculate_price(floor, {},rules=DeliverySettings.current().pricing_rules)['suggested_price']) if comparable else None
        fulfilled = floor + costs['supplier_shipping'] - costs['customer_shipping'] if comparable else None
        all_cost_quote = calculate_price(floor, {'supplier_delivery_max': str(costs['supplier_shipping']),
                                               # Viability diagnostic, never an automatically
                                               # applied delivery subsidy or selling price.
                                               'customer_delivery_charge': str(costs['customer_shipping'])}, subsidy_enabled=True,rules=DeliverySettings.current().pricing_rules) if comparable else {}
        offers = offer.evidence.filter(match_key=offer.match_key,
                                       observed_at__gte=cutoff, observed_at__lte=now).order_by('-observed_at', '-pk')
        # Keep the newest observation per seller AND listing; repeated adverts are not independent evidence.
        sellers, urls, newest = set(), set(), []
        for entry in offers:
            seller = re.sub(r'\W+', '', entry.seller.casefold())
            url = entry.url.split('?')[0].rstrip('/').casefold()
            if not seller or seller in sellers or url in urls:
                continue
            sellers.add(seller); urls.add(url)
            # A newer unavailable/unconfirmed observation must invalidate the old valid advert.
            if entry.exact_match and entry.available:
                newest.append(entry)
        selected = sorted(newest, key=lambda x: (x.price, x.pk))[:3]
        result.update(source_currency=offer.currency, cost_floor=str(floor) if comparable else None,
            suggested_price=str(suggested) if comparable else None, full_cost_after_delivery_recovery=str(fulfilled) if comparable else None,
            costs={k: str(v) for k, v in costs.items()}, evidence_ids=[x.pk for x in selected],
            competitor_prices=[str(x.price) for x in selected], benchmark=None,
            competitor_observations=[{'id': x.pk, 'seller': x.seller, 'marketplace': x.marketplace, 'url': x.url,
                'price': str(x.price), 'delivery': str(x.delivery) if x.delivery is not None else None,
                'similarity_percent': str(x.match_confidence) if x.match_confidence is not None else None,
                'observed_at': x.observed_at.isoformat()} for x in selected],
            source_above_all_observed=(bool(newest) and all(offer.source_price > x.price for x in newest)) if comparable else None,
            valid_independent_seller_count=len(newest),
            delivered_profit_at_suggested=str(suggested - fulfilled) if comparable else None,
            all_cost_suggested_price=all_cost_quote.get('suggested_price'),
            all_cost_markup_percent=all_cost_quote.get('markup_percent'),
            cost_origins={k: 'staff_entered' if k in offer.costs else 'central_estimate' if k in MONEY_COSTS else 'not_provided' for k in costs},
            price_band_warning='Inclusive markup bands can create price drops at boundaries; smoothing is not enabled.')
        if offer.excluded_reason:
            state = 'excluded'; reasons.append(offer.excluded_reason)
        elif offer.source_price is None:
            reasons.append('Source price is unconfirmed, not free. Obtain an actual supplier quote before screening or import.')
        elif not offer.match_key or offer.match_key != match_key(offer.identity) or not offer.match_confirmed:
            state = 'needs_review'; reasons.append('Confirm model, variant, pack, condition, warranty, accessories and authenticity. Unknown authenticity cannot establish an exact match.')
        elif offer.currency != 'BDT':
            reasons.append('Verified currency conversion and import costs are required; BDT only for this release.')
        elif not offer.single_unit or offer.availability != 'in_stock' or offer.quantity == 0:
            reasons.append('Single-unit eligibility and available source stock must be confirmed.')
        elif not offer.observed_at or offer.observed_at < cutoff or offer.observed_at > now:
            reasons.append('Source observation is stale or invalid. Upload a freshly verified snapshot.')
        elif len(selected) < 3:
            reasons.append('Need three fresh, independent, exact-match seller observations.')
        elif not offer.supplier.enabled or not offer.supplier.terms_confirmed:
            state = 'needs_review'; reasons.append('Supplier must be enabled with documented permitted data use and fulfilment terms.')
        elif offer.identity.get('tax_basis') not in ('included', 'excluded'):
            state = 'needs_review'; reasons.append('Confirm whether supplier taxes are included or excluded; missing tax information is not a verified zero cost.')
        elif offer.identity.get('tax_basis') == 'excluded' and 'taxes' not in offer.costs:
            state = 'needs_review'; reasons.append('Record the verified additional tax amount, including explicit zero only when confirmed.')
        elif offer.identity.get('tax_basis') == 'included' and costs['taxes']:
            state = 'needs_review'; reasons.append('Taxes are marked included but an additional tax cost is entered. Resolve possible double counting.')
        elif 'fees' not in offer.costs:
            state = 'needs_review'; reasons.append('Record verified allocated supplier/payment fees, including explicit zero only when confirmed.')
        else:
            benchmark = (sum((x.price for x in selected), Decimal('0')) / 3).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            profit = benchmark - floor
            result.update(benchmark=str(benchmark), available_profit=str(profit),
                achievable_markup=str((profit / floor * 100).quantize(Decimal('.01'))) if floor else None,
                achievable_margin=str((profit / benchmark * 100).quantize(Decimal('.01'))) if benchmark else None,
                delivered_profit_at_benchmark=str(benchmark - fulfilled),
                normal_profit=str(suggested - floor), profit_shortfall=str(max(Decimal('0'), suggested - benchmark)))
            if floor > benchmark:
                state = 'blacklist'; reasons.append('Non-delivery cost floor exceeds the three-price arithmetic average.')
            elif floor == benchmark:
                state = 'zero_margin'; reasons.append('Break-even is not profitable.')
            elif suggested > benchmark:
                state = 'reduced_margin'; reasons.append('Reduced profit requires a separate approved pricing rule; no automatic reduction.')
            elif offer.weight_grams is None or costs.get('supplier_shipping') is None or 'supplier_shipping' not in offer.costs:
                state = 'needs_review'; reasons.append('Confirm weight and actual shipment cost before approving fulfilled profit.')
            elif suggested <= fulfilled:
                state = 'needs_review'; reasons.append('Product-only comparison passes but delivered profit is not positive.')
            else:
                state = 'ready'; reasons.append('Screening passed; separate staff approval and draft import still required.')
        result['reasons'] = reasons
        alternatives = valid_alternatives(offer, config) if offer.match_key else SupplierOffer.objects.none()
        lowest = alternatives.first()
        result['source_alternatives'] = list(alternatives.values_list('id', flat=True)[:50])
        result['lowest_source_offer'] = lowest.pk if lowest and lowest.source_price < offer.source_price else offer.pk
        eligible_lower = alternatives.exclude(state__in=('blacklist', 'zero_margin', 'excluded')).filter(source_price__lt=offer.source_price).first() if offer.source_price is not None else None
        if state == 'ready' and eligible_lower:
            state = 'needs_review'
            reasons.append(f'Exact equivalent source offer {eligible_lower.pk} has a lower source price and is not rejected. Review that offer first; no silent supplier substitution.')
        decision = SupplierDecision.objects.using(DB).create(offer=offer, state=state,
            fingerprint=fingerprint(offer, config), result=result, actor_id=actor)
        offer.state, offer.current_decision = state, decision
        offer.save(using=DB, update_fields=['state', 'current_decision', 'updated_at'])
        audit('screen', actor, offer.supplier, offer, decision=decision.pk, state=state)
        return decision


def assert_current(offer):
    decision = offer.current_decision
    config = policy()
    cutoff = timezone.now() - timedelta(days=config.evidence_days)
    if (not decision or decision.state != 'ready' or offer.state != 'ready' or
            decision.result.get('rule_version') != 3 or offer.match_key != match_key(offer.identity) or
            decision.created_at < cutoff or decision.fingerprint != fingerprint(offer, config)):
        raise ValueError('Screening is missing, stale or changed. Re-screen and approve this offer first.')
    # Evidence freshness is measured by observation time, not screening time.
    ids = decision.result.get('evidence_ids', [])
    if offer.observed_at < cutoff or offer.evidence.filter(pk__in=ids, observed_at__gte=cutoff).count() != 3:
        raise ValueError('Source or market evidence expired. Refresh and re-screen.')
    return decision


def approve(offer, actor, note):
    with transaction.atomic(using=DB):
        offer = SupplierOffer.objects.using(DB).select_for_update().select_related('supplier', 'current_decision').get(pk=offer.pk)
        decision = assert_current(offer)
        if not note.strip():
            raise ValueError('Record the approval reason and fulfilment checks.')
        decision.approved_at, decision.approved_by, decision.approval_note = timezone.now(), actor, note[:1000]
        decision.save(using=DB, update_fields=['approved_at', 'approved_by', 'approval_note'])
        audit('approve_draft_import', actor, offer.supplier, offer, decision=decision.pk, note=note[:1000])


def import_draft(offer, category_id, actor):
    with transaction.atomic(using=DB):
        offer = SupplierOffer.objects.using(DB).select_for_update().select_related('supplier', 'current_decision').get(pk=offer.pk)
        decision = assert_current(offer)
        if not decision.approved_at:
            raise ValueError('A staff approval is required before import.')
        if offer.imported_product_id:
            return offer.imported_product, False  # Local content, stock and price are never overwritten.
        existing = SupplierOffer.objects.using(DB).filter(import_key=offer.match_key).first()
        if existing:
            raise ValueError(f'Equivalent product already imported from offer {existing.pk}. Existing supplier selection is preserved; source switching is not automatic.')
        Category.objects.using(DB).get(pk=category_id, is_active=True)
        product = Product.objects.using(DB).create(name=offer.title, slug=f'sourced-{offer.pk}-{uuid.uuid4().hex[:8]}',
            category_id=category_id, status='draft', short_description='Supplier draft — verify content, imagery, stock and fulfilment before publication.')
        ProductVariant.objects.using(DB).create(product=product, sku=f'SOURCE-{offer.pk}', title='Default',
            price=decision.result['suggested_price'], cost_price=offer.source_price, stock=0,
            weight_grams=offer.weight_grams or 0, currency='BDT', allow_backorder=False)
        offer.imported_product = product
        offer.import_key = offer.match_key
        offer.save(using=DB, update_fields=['imported_product', 'import_key', 'updated_at'])
        audit('import_draft', actor, offer.supplier, offer, product_id=product.pk, decision=decision.pk)
        return product, True


def queue_job(supplier_id, action, actor=None, rows=None, offer_ids=None, bulk=False):
    if action not in dict(SupplierJob.ACTIONS):
        raise ValueError('Unsupported action.')
    with transaction.atomic(using=DB):
        supplier = Supplier.objects.using(DB).select_for_update().get(pk=supplier_id)
        if not supplier.enabled or not supplier.terms_confirmed:
            raise ValueError('Enable this supplier and confirm data-use terms first.')
        if SupplierJob.objects.using(DB).filter(supplier=supplier, status__in=ACTIVE).exists():
            raise ValueError('A job is already active for this supplier. Wait or cancel it.')
        if action in ('collect', 'update'):
            from .supplier_connectors import LIVE
            if rows is None and supplier.connector in LIVE:
                if not supplier.credentials_ciphertext:
                    raise ValueError('Store API credentials securely before requesting live collection.')
                job = SupplierJob.objects.using(DB).create(supplier=supplier, action=action,
                    payload={'live': True, **({'offer_ids': list(offer_ids)} if offer_ids is not None else {})}, total=0, actor_id=actor,
                    activity='Queued: waiting to read the documented supplier product API')
                audit('queue_live_' + action, actor, supplier, job_id=str(job.pk))
                return job
            if not isinstance(rows, list) or not rows or len(rows) > 1000:
                raise ValueError('Upload 1–1000 authorised snapshot rows per batch. No remote connector is configured.')
            # Payload contains validated identity data only, not uploaded arbitrary keys/secrets.
            from .supplier_api import SnapshotSerializer
            serializer = SnapshotSerializer(data=rows, many=True)
            serializer.is_valid(raise_exception=True)
            payload = json.loads(json.dumps(serializer.validated_data, default=str))
            total = len(payload)
            payload = {'rows': payload}
        else:
            queryset = SupplierOffer.objects.using(DB).filter(supplier=supplier)
            if action == 'recheck':
                queryset = queryset.filter(state='blacklist')
            if offer_ids is not None:
                queryset = queryset.filter(pk__in=offer_ids)
            if offer_ids is not None:
                maximum = 100000 if bulk else 1000
                ids = list(queryset.order_by('pk').values_list('pk', flat=True)[:maximum + 1])
                if len(ids) > maximum:
                    raise ValueError(f'Select at most {maximum} offers per screening batch.')
                payload, total = {'ids': ids}, len(ids)
            else:
                # Freeze a supplier-wide boundary, then read bounded keyset chunks.
                # New discoveries after queueing are not silently added to scope.
                through = queryset.order_by('-pk').values_list('pk', flat=True).first() or 0
                total = queryset.filter(pk__lte=through).count()
                payload = {'scope': 'supplier', 'through_id': through, 'after_id': 0}
            if not total:
                raise ValueError('No matching offers in this scope.')
        job = SupplierJob.objects.using(DB).create(supplier=supplier, action=action, payload=payload, total=total, actor_id=actor)
        audit('queue_' + action, actor, supplier, job_id=str(job.pk), total=total)
        return job


def snapshot_row(supplier, row, update=False):
    from .supplier_media import safe_images
    row=dict(row)
    images=safe_images(row.pop('preview_images',[]))
    identity = {key: row[key] for key in ('external_id', 'variant_id', 'vendor_id', 'warehouse_id')}
    with transaction.atomic(using=DB):
        offer = SupplierOffer.objects.using(DB).select_for_update().filter(supplier=supplier, **identity).first()
        if update:
            if not offer:
                return 'skipped'
            # Nightly/update mode can NEVER add identities, content, matching, weight, prices in shop or images.
            from django.utils.dateparse import parse_datetime
            observed = parse_datetime(row['observed_at'])
            if offer.observed_at and observed <= offer.observed_at:
                return 'skipped'
            from .supplier_source_publish import trusted_stock_identity, refresh_listing_stock
            verified_source = trusted_stock_identity(offer, row)
            if not verified_source and (offer.identity != row['identity'] or (not offer.match_key and offer.title != row['title'])):
                # A reused source ID must not update the price of a different historical product.
                quarantine(offer, row['identity'], 'update', row['title'])
                return 'conflict'
            offer.source_price, offer.availability, offer.quantity = row['source_price'], row['availability'], row['quantity']
            offer.observed_at = observed
            if offer.state not in ('excluded', 'blacklist'):
                offer.state = 'needs_review'
            offer.save(using=DB, update_fields=['source_price', 'availability', 'quantity', 'observed_at', 'state', 'updated_at'])
            if verified_source:
                refresh_listing_stock(offer)
            audit('price_stock_observed', supplier=supplier, offer=offer, observed_at=row['observed_at'])
            return 'updated'
        if offer:
            if offer.identity != row['identity'] or (not offer.match_key and offer.title != row['title']):
                quarantine(offer, row['identity'], 'collect', row['title'])
                return 'conflict'
            if images and not offer.preview_images:
                offer.preview_images=images
                offer.save(using=DB,update_fields=['preview_images','updated_at'])
                audit('preview_photos_collected',supplier=supplier,offer=offer,count=len(images))
            return 'existing'
        offer = SupplierOffer.objects.using(DB).create(supplier=supplier, **row, preview_images=images, match_key=match_key(row['identity']))
        return 'new'


def quarantine(offer, incoming, source, title=None):
    if offer.state != 'excluded':
        offer.state = 'needs_review'
    offer.match_confirmed = False
    offer.save(using=DB, update_fields=['state', 'match_confirmed', 'updated_at'])
    if offer.source_product_id and offer.imported_product_id:
        product = Product.objects.using(DB).select_for_update().get(pk=offer.imported_product_id)
        Product.objects.using(DB).filter(pk=product.pk).update(status='archived',
            attributes={**product.attributes, 'supplier_publication_ready': False})
    audit('identity_conflict', supplier=offer.supplier, offer=offer, source=source,
          incoming_identity=incoming, incoming_title=title,
          note='Possible identifier reuse or changed source title: previous identity and price preserved; manual review required.')


def actor_authorized(job):
    if job.actor_id is None:
        return True  # Only trusted server code can enqueue a system job without an actor.
    from django.contrib.auth import get_user_model
    actor = get_user_model().objects.using('default').filter(pk=job.actor_id, is_active=True, is_staff=True).first()
    permission = 'manage_supplier_catalogue' if job.action == 'publish_catalogue' else ('collect_supplier' if job.action in ('collect', 'update') else 'screen_supplier')
    return bool(actor and (actor.is_superuser or (actor.has_perm('ecommerce.view_supplier') and actor.has_perm('ecommerce.' + permission))))


def run_jobs(max_items=100):
    """One lease-protected worker, per-item checkpoints, cancellation and crash resumption."""
    config = policy()
    token = uuid.uuid4().hex
    now = timezone.now()
    with transaction.atomic(using=DB):
        config = SupplierPolicy.objects.using(DB).select_for_update().get(pk=1)
        if config.worker_until and config.worker_until > now:
            return 0
        config.worker_token, config.worker_until = token, now + timedelta(minutes=5)
        config.save(using=DB, update_fields=['worker_token', 'worker_until'])
    count = 0
    try:
        while count < max_items:
            job = SupplierJob.objects.using(DB).filter(status__in=ACTIVE, runner='worker').order_by('created_at').first()
            if not job:
                break
            if job.payload.get('live') and 'rows' not in job.payload:
                if not prepare_live_job(job.pk, token):
                    if not SupplierPolicy.objects.using(DB).filter(pk=1, worker_token=token).exists():
                        return count
                    continue
            with transaction.atomic(using=DB):
                fence = SupplierPolicy.objects.using(DB).select_for_update().get(pk=1)
                if fence.worker_token != token:
                    return count  # A replacement worker acquired the lease; the old process is fenced out.
                job = SupplierJob.objects.using(DB).select_for_update().select_related('supplier').get(pk=job.pk)
                if job.status not in ACTIVE:
                    continue
                if job.status == 'cancel_requested':
                    finish(job, 'cancelled', 'Cancelled; completed work has not been reversed.')
                    continue
                if job.action not in dict(SupplierJob.ACTIONS):
                    finish(job, 'failed', 'Unsupported persisted action. Review this job before queueing a replacement.')
                    continue
                if not job.supplier.enabled or not job.supplier.terms_confirmed:
                    finish(job, 'failed', 'Supplier disabled or terms revoked. No further work performed.')
                    continue
                if not actor_authorized(job):
                    finish(job, 'failed', 'The submitting staff account is inactive or no longer has the required sourcing permission.')
                    continue
                if job.processed >= job.total:
                    finish(job, 'completed_with_errors' if job.errors or job.counts.get('invalid_skipped') else 'completed', 'Batch finished')
                    continue
                job.status = 'running'
                index = job.processed
                try:
                    # Nested savepoint prevents a failed row from poisoning the checkpoint transaction.
                    with transaction.atomic(using=DB):
                        if job.action == 'publish_catalogue':
                            from .manual_catalogue import import_offer
                            outcome = import_offer(job.payload['ids'][index])
                        elif job.action in ('collect', 'update'):
                            outcome = snapshot_row(job.supplier, job.payload['rows'][index], job.action == 'update')
                        else:
                            if job.payload.get('scope') == 'supplier':
                                candidates = SupplierOffer.objects.using(DB).filter(supplier=job.supplier,
                                    pk__gt=job.payload['after_id'], pk__lte=job.payload['through_id']).order_by('pk')
                                if job.action == 'recheck':
                                    candidates = candidates.filter(state='blacklist')
                                offer = candidates.first()
                                if offer is None:
                                    finish(job, 'completed_with_errors', 'Scope changed during processing; review remaining count before retrying.')
                                    continue
                                job.payload = {**job.payload, 'after_id': offer.pk}
                            else:
                                offer = SupplierOffer.objects.using(DB).get(pk=job.payload['ids'][index], supplier=job.supplier)
                            outcome = screen(offer, job.actor_id).state
                        job.counts[outcome] = job.counts.get(outcome, 0) + 1
                except (KeyError, IndexError, TypeError):
                    finish(job, 'failed', 'Invalid persisted job/checkpoint format. Review this job before queueing a replacement.')
                    continue
                except (ValueError, ValidationError, SupplierOffer.DoesNotExist, IntegrityError) as exc:
                    job.counts['failed'] = job.counts.get('failed', 0) + 1
                    message = 'Source identity violates a database constraint; review this row.' if isinstance(exc, IntegrityError) else str(exc)[:300]
                    job.errors = (job.errors + [{'row': index + 1, 'message': message}])[:100]
                job.processed += 1
                job.activity = f'Processed {job.processed}/{job.total}'
                job.save(using=DB)
                if job.processed == job.total:
                    finish(job, 'completed_with_errors' if job.errors or job.counts.get('invalid_skipped') else 'completed', 'Batch finished')
                count += 1
                SupplierPolicy.objects.using(DB).filter(pk=1, worker_token=token).update(worker_until=timezone.now() + timedelta(minutes=5))
        return count
    finally:
        SupplierPolicy.objects.using(DB).filter(pk=1, worker_token=token).update(worker_token='', worker_until=None)


def prepare_live_job(job_id, token):
    """Read network data WITHOUT holding policy/job database locks."""
    from .supplier_connectors import collect, ConnectorError
    from .supplier_api import SnapshotSerializer
    def allowed():
        owns = SupplierPolicy.objects.using(DB).filter(pk=1, worker_token=token).update(
            worker_until=timezone.now() + timedelta(minutes=5))
        current = SupplierJob.objects.using(DB).select_related('supplier').get(pk=job_id)
        return bool(owns and current.status in ('queued', 'running') and current.supplier.enabled and
                    current.supplier.terms_confirmed and actor_authorized(current))
    job = SupplierJob.objects.using(DB).select_related('supplier').get(pk=job_id)
    if allowed():
        SupplierJob.objects.using(DB).filter(pk=job.pk, status__in=('queued', 'running')).update(
            status='running', activity='Reading supplier product identities; total is not known yet')
        try:
            rows, stats = collect(job.supplier, allowed)
            if job.action == 'update':
                tracked_offers = job.supplier.offers.all()
                if 'offer_ids' in job.payload:
                    tracked_offers = tracked_offers.filter(pk__in=job.payload['offer_ids'])
                tracked = set(tracked_offers.values_list('external_id', 'variant_id', 'vendor_id', 'warehouse_id'))
                rows = [r for r in rows if tuple(r[k] for k in ('external_id', 'variant_id', 'vendor_id', 'warehouse_id')) in tracked]
                returned = {tuple(r[k] for k in ('external_id', 'variant_id', 'vendor_id', 'warehouse_id')) for r in rows}
                stats = {**stats, 'requested_tracked': len(tracked), 'unreturned_tracked': len(tracked - returned)}
            serializer = SnapshotSerializer(data=rows, many=True)
            if not serializer.is_valid():
                raise ConnectorError('Supplier returned source identities outside the supported schema. No partial feed was committed.')
            rows = json.loads(json.dumps(serializer.validated_data, default=str))
            error = None
        except ConnectorError as exc:
            rows, stats, error = [], {}, str(exc)
    else:
        rows, stats, error = [], {}, 'Job access was revoked or cancellation was requested.'
    with transaction.atomic(using=DB):
        fence = SupplierPolicy.objects.using(DB).select_for_update().get(pk=1)
        if fence.worker_token != token:
            return False
        job = SupplierJob.objects.using(DB).select_for_update().select_related('supplier').get(pk=job_id)
        if job.status not in ACTIVE:
            return False
        if job.status == 'cancel_requested':
            finish(job, 'cancelled', 'Cancelled after the in-flight read; no collected rows were committed.')
            return False
        if error or not job.supplier.enabled or not job.supplier.terms_confirmed or not actor_authorized(job):
            finish(job, 'failed', error or 'Supplier or staff access changed while reading the API.')
            return False
        job.payload, job.total, job.counts = {'live': True, 'rows': rows}, len(rows), stats
        if stats.get('unreturned_tracked'):
            job.errors = (job.errors + [{'message': f'{stats["unreturned_tracked"]} tracked identities were not returned by this API. Cached prices/stock were not refreshed or set to zero; reconcile them through browser collection.'}])[:100]
        job.activity = f'Supplier read complete: {len(rows)} identities ready for collection'
        job.save(using=DB)
        if not rows:
            finish(job, 'completed_with_errors' if job.errors or stats.get('invalid_skipped') else 'completed',
                   'Supplier read completed with no eligible identities in this scope.')
            return False
    return True


def finish(job, status, message):
    job.status, job.activity, job.finished_at = status, message, timezone.now()
    # Finished job payloads can be discarded: checkpoint counts/audit are sufficient and identities already persisted.
    if job.runner != 'browser' or status == 'completed':
        job.payload = {}
    job.save(using=DB)
    if status == 'completed' and job.action in ('collect', 'update'):
        from .supplier_connectors import LIVE
        Supplier.objects.using(DB).filter(pk=job.supplier_id).update(last_success_at=timezone.now(), health=
            'Authorised browser catalogue collected; unattended API refresh not configured' if job.runner == 'browser' else
            'Documented read-only API processed; publication and supplier orders remain disabled' if job.supplier.connector in LIVE else
            'Authorised snapshot processed; live API not configured')
    CommerceNotification.objects.using(DB).create(admin_only=True, title=f'Supplier job: {status}',
        message=f'{job.supplier.name}: {job.action} — {job.processed}/{job.total}. {message}',
        link='/ecommerce/manage?section=suppliers')
    audit('job_' + status, job.actor_id, job.supplier, job_id=str(job.pk), counts=job.counts)


def nightly():
    """Explicit Dhaka clock, single daily catch-up; no fabricated stock update without a connector."""
    from zoneinfo import ZoneInfo
    now = timezone.now().astimezone(ZoneInfo('Asia/Dhaka'))
    with transaction.atomic(using=DB):
        policy()
        config = SupplierPolicy.objects.using(DB).select_for_update().get(pk=1)
        # Once daily after 23:59, or next-day catch-up for an unfinished previous date.
        target = now.date() if (now.hour, now.minute) >= (23, 59) else now.date() - timedelta(days=1)
        if config.last_nightly_date and config.last_nightly_date >= target:
            return 0
        config.last_nightly_date = target
        config.save(using=DB, update_fields=['last_nightly_date'])
        count = 0
        for supplier in Supplier.objects.using(DB).filter(enabled=True):
            if not supplier.offers.exists():
                continue
            from .supplier_connectors import LIVE
            if supplier.connector in LIVE:
                if not supplier.jobs.filter(status__in=ACTIVE).exists():
                    queue_job(supplier.pk, 'update')
                count += 1
                continue
            supplier.health = 'Needs fresh snapshot — live price/quantity connector not configured'
            supplier.save(using=DB, update_fields=['health'])
            CommerceNotification.objects.using(DB).create(admin_only=True, title='Supplier refresh needs connection',
                message=f'{supplier.name}: source checks pending for {target}; no live connector. Upload an authorised price/quantity snapshot. Cached timestamps have NOT been refreshed.',
                link='/ecommerce/manage?section=suppliers')
            count += 1
        return count


def cleanup():
    cutoff = timezone.now() - timedelta(days=policy().retention_days)
    # Financial/order and decision/audit records are deliberately excluded.
    return SupplierJob.objects.using(DB).exclude(status__in=ACTIVE).filter(finished_at__lt=cutoff).delete()[0]
