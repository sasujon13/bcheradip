"""Staff-only supplier APIs. No credentials or wholesale data in public serializers."""
import json
from decimal import Decimal
from datetime import timedelta
from django.core import signing
from django.db import transaction, IntegrityError
from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import (Supplier, SupplierOffer, SupplierEvidence, SupplierDecision, SupplierJob, SupplierAudit,
                     Product, ProductVariant, SupplierSourceProduct, Order)
from .permissions import IsCommerceAdmin
from .views import CommerceAdminAuthMixin, StorefrontProductPagination
from .supplier_service import (DB, ACTIVE, MONEY_COSTS, approve, assert_current, audit, import_draft,
    match_key, money, public_url, queue_job, policy, screen)


def require(user, codename):
    if not (user.is_authenticated and user.is_active and user.is_staff and
            (user.is_superuser or user.has_perm('ecommerce.' + codename))):
        raise PermissionDenied('Required permission: ' + codename.replace('_', ' '))


def checked_url(value):
    try:
        return public_url(value)
    except ValueError as exc:
        raise ValidationError(str(exc))


class DimensionsSerializer(serializers.Serializer):
    length_cm = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal('0.01'))
    width_cm = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal('0.01'))
    height_cm = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal('0.01'))


class IdentitySerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=120, required=False)
    gtin = serializers.CharField(max_length=40, required=False)
    brand = serializers.CharField(max_length=120, required=False)
    model = serializers.CharField(max_length=160, required=False)
    variant = serializers.CharField(max_length=200, required=False)
    pack_count = serializers.IntegerField(min_value=1, max_value=100000, required=False)
    condition = serializers.ChoiceField(choices=['new', 'used', 'refurbished'], required=False)
    warranty = serializers.CharField(max_length=200, required=False)
    accessories = serializers.CharField(max_length=300, required=False)
    category = serializers.CharField(max_length=160, required=False)
    authenticity = serializers.ChoiceField(choices=['genuine', 'generic', 'replica', 'unverified'], required=False)
    tax_basis = serializers.ChoiceField(choices=['included', 'excluded', 'unconfirmed'], required=False)
    specifications = serializers.DictField(child=serializers.CharField(max_length=200), required=False)
    dimensions = DimensionsSerializer(required=False)

    def validate_specifications(self, value):
        if len(value) > 40 or any(not key.strip() or len(key) > 80 for key in value):
            raise ValidationError('Use at most 40 named specifications with keys up to 80 characters.')
        return value


class SnapshotSerializer(serializers.Serializer):
    external_id = serializers.CharField(max_length=120)
    variant_id = serializers.CharField(max_length=120, required=False, default='', allow_blank=True)
    vendor_id = serializers.CharField(max_length=120)
    warehouse_id = serializers.CharField(max_length=120, required=False, default='', allow_blank=True)
    title = serializers.CharField(max_length=255)
    url = serializers.URLField(max_length=1000)
    identity = IdentitySerializer()
    source_price = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, allow_null=True, required=False, default=None)
    currency = serializers.ChoiceField(choices=['BDT'], default='BDT')
    availability = serializers.ChoiceField(choices=['in_stock', 'out_of_stock', 'unconfirmed', 'missing'])
    quantity = serializers.IntegerField(min_value=0, max_value=100000000, allow_null=True, default=None)
    weight_grams = serializers.IntegerField(min_value=1, max_value=1000000, allow_null=True, default=None)
    single_unit = serializers.BooleanField(default=False)
    observed_at = serializers.DateTimeField()
    preview_images = serializers.ListField(child=serializers.CharField(max_length=1000),max_length=20,required=False)

    def validate_preview_images(self,value):
        from .supplier_media import safe_images
        clean=safe_images(value)
        if len(set(value))!=len(clean):
            raise ValidationError('Use unsigned public HTTPS image references only, without query strings or private hosts.')
        return clean

    def validate_url(self, value):
        return checked_url(value)

    def validate_observed_at(self, value):
        if value > timezone.now() or value < timezone.now() - timedelta(days=365):
            raise ValidationError('Use the actual source observation time within the past year, not a future timestamp.')
        return value


class BrowserLoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=160, write_only=True)
    password = serializers.CharField(max_length=4096, trim_whitespace=False, write_only=True)


class SupplierSerializer(serializers.ModelSerializer):
    credentials_set = serializers.SerializerMethodField()
    counts = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()
    operation = serializers.SerializerMethodField()
    catalogue = serializers.SerializerMethodField()
    fresh_source = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = ('id', 'name', 'website', 'enabled', 'connector', 'terms_confirmed', 'terms_note',
                  'credential_expires_at', 'last_success_at', 'health', 'credentials_set', 'counts', 'capabilities', 'operation', 'catalogue', 'fresh_source')
        read_only_fields = ('health', 'last_success_at')

    def get_credentials_set(self, obj):
        return bool(obj.credentials_ciphertext)

    def get_fresh_source(self, obj):
        # Explicit projection: never load/return supplier raw content or secrets.
        row=obj.recollections.filter(mode='full').values(
            'id','status','processed','expected_total','counts','activity','updated_at','finished_at','coverage').first()
        if row:
            row['publication']=row.pop('coverage',{}).get('publication')
        return row

    def get_catalogue(self, obj):
        latest = SupplierAudit.objects.using(DB).filter(supplier=obj, action='browser_catalogue_reconciled').first()
        if not latest: return None
        return {'checked_at': latest.created_at, 'observed_cards': latest.detail.get('observed_cards'),
                'accessible_product_urls': latest.detail.get('accessible_product_urls'), 'counts': latest.detail.get('counts', {})}

    def get_counts(self, obj):
        rows = obj.offers.aggregate(total=Count('id'), products=Count('external_id', distinct=True), imported=Count('id', filter=Q(imported_product__isnull=False)),
            ready=Count('id', filter=Q(state='ready')), blacklist=Count('id', filter=Q(state='blacklist')),
            available=Count('id', filter=Q(availability='in_stock') & (Q(quantity__isnull=True) | Q(quantity__gt=0))),
            unavailable=Count('id', filter=Q(availability__in=('out_of_stock', 'missing')) | Q(quantity=0)),
            unconfirmed=Count('id', filter=Q(availability='unconfirmed')))
        rows['vendors'] = obj.offers.exclude(vendor_id__in=('', 'not-provided')).values('vendor_id').distinct().count()
        rows['vendor_unconfirmed'] = obj.offers.filter(vendor_id__in=('', 'not-provided')).count()
        rows['categorized'] = obj.offers.filter(identity__has_key='category').exclude(identity__category='').count()
        return rows

    def get_capabilities(self, obj):
        from .supplier_connectors import LIVE
        from .supplier_browser import site_for_supplier
        from .supplier_source_clients import SUPPLIER_IDS
        return {'full_collection': obj.pk in SUPPLIER_IDS.values(),
                'snapshot_collection': True, 'live_api': obj.connector in LIVE, 'automatic_orders': False,
                'preferred_collection': 'browser',
                'browser_collection': bool(site_for_supplier(obj)),
                'credential_status': 'expired' if obj.credential_expires_at and obj.credential_expires_at <= timezone.now() else
                    ('stored_unverified' if obj.credentials_ciphertext else 'not_set'),
                'market_search': False, 'note': LIVE.get(obj.connector,
                    'Authorised browser collection or JSON snapshots; unattended API price refresh is not configured.'
                    if site_for_supplier(obj) else 'Authorised JSON snapshots only. Live access is not configured.')}

    def get_operation(self, obj):
        fields = ('id', 'action', 'status', 'processed', 'total', 'activity', 'finished_at')
        active = obj.jobs.filter(status__in=ACTIVE).order_by('created_at').values(*fields).first()
        latest = obj.jobs.order_by('-created_at').values(*fields).first()
        collection = obj.jobs.filter(action='collect').order_by('-created_at').values(*fields).first()
        return {'active': active, 'latest': latest, 'latest_collection': collection}

    def validate_website(self, value):
        return checked_url(value)

    def validate(self, data):
        enabled = data.get('enabled', self.instance.enabled if self.instance else False)
        terms = data.get('terms_confirmed', self.instance.terms_confirmed if self.instance else False)
        note = data.get('terms_note', self.instance.terms_note if self.instance else '')
        if (enabled or terms) and not note.strip():
            raise ValidationError('Record the permitted source access, identity collection and fulfilment terms first.')
        if enabled and not terms:
            raise ValidationError('Confirm supplier terms before enabling collection.')
        return data


class EvidenceSerializer(serializers.ModelSerializer):
    match_confidence = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)
    class Meta:
        model = SupplierEvidence
        fields = ('id', 'offer', 'seller', 'marketplace', 'url', 'price', 'delivery', 'observed_at', 'exact_match', 'match_confidence', 'available', 'note', 'match_key')
        read_only_fields = ('match_key',)

    def validate_url(self, value):
        return checked_url(value)

    def validate(self, data):
        if data['price'] <= 0 or (data.get('delivery') is not None and data['delivery'] < 0):
            raise ValidationError('Use positive full product prices and non-negative delivery charges.')
        if data['observed_at'] > timezone.now():
            raise ValidationError('Evidence cannot be dated in the future.')
        if not data['note'].strip():
            raise ValidationError('Record the exact variant, quantity, condition and warranty match, not just a similar title.')
        if data.get('exact_match', False) and not data['offer'].match_key:
            raise ValidationError('Complete the structured product identity before recording an exact match. Unconfirmed observations may be saved for research only.')
        return data


class OfferSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    decision = serializers.SerializerMethodField()

    class Meta:
        model = SupplierOffer
        exclude = ('current_decision',)
        read_only_fields = tuple(f.name for f in SupplierOffer._meta.fields)

    def get_decision(self, obj):
        d = obj.current_decision
        return {'id': d.pk, 'state': d.state, 'result': d.result, 'approved_at': d.approved_at} if d else None


class JobSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    class Meta:
        model = SupplierJob
        exclude = ('payload',)
        read_only_fields = tuple(f.name for f in SupplierJob._meta.fields)


class SupplierViewSet(CommerceAdminAuthMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.using(DB).all()
    serializer_class = SupplierSerializer
    permission_classes = [IsCommerceAdmin]
    pagination_class = StorefrontProductPagination
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    @property
    def permission_requirements(self):
        return {'POST': ((Supplier, 'view'),)} if getattr(self, 'action', '') in ('credentials', 'connection', 'browser_collection') else {}

    def perform_create(self, serializer):
        obj = serializer.save()
        audit('supplier_created', self.request.user.pk, obj)

    def perform_update(self, serializer):
        with transaction.atomic(using=DB):
            serializer.instance = Supplier.objects.using(DB).select_for_update().get(pk=serializer.instance.pk)
            obj = serializer.save()
            audit('supplier_configuration', self.request.user.pk, obj, fields=list(serializer.validated_data))

    @action(detail=True, methods=['post'], permission_classes=[IsCommerceAdmin])
    def credentials(self, request, pk=None):
        require(request.user, 'edit_supplier_credentials')
        obj = self.get_object()
        value = request.data.get('credentials')
        if not isinstance(value, dict) or len(json.dumps(value)) > 10000 or any(k not in {'api_key', 'api_secret', 'username', 'password', 'domain', 'account_id', 'authorization', 'client_id', 'client_secret'} for k in value) or any(not isinstance(v, str) or len(v) > 4096 or '\r' in v or '\n' in v for v in value.values()):
            raise ValidationError('Use supported credential fields only (maximum 10 KB). Browser cookies are not supported.')
        # Separate commerce key, not customer/tutor encryption. No key => fail closed.
        try:
            from .supplier_crypto import encrypt
            merge = serializers.BooleanField().run_validation(request.data.get('merge', False))
            # Blank editor fields preserve issued secrets. Nothing is sent back to the browser.
            if merge:
                from .supplier_crypto import decrypt
                with transaction.atomic(using=DB):
                    current = Supplier.objects.using(DB).select_for_update().get(pk=obj.pk)
                    value = {**(decrypt(current) if current.credentials_ciphertext else {}), **value}
                    ciphertext = encrypt(value) if value else ''
                    current.credentials_ciphertext = ciphertext
                    current.save(using=DB, update_fields=['credentials_ciphertext', 'updated_at'])
                    audit('credentials_updated', request.user.pk, current, fields=list(request.data.get('credentials', {})))
                return Response({'credentials_set': bool(value), 'connection_verified': False})
            ciphertext = encrypt(value) if value else ''
        except (ValueError, TypeError):
            raise ValidationError('Server administrator must configure valid supplier credential encryption before storing credentials.')
        with transaction.atomic(using=DB):
            Supplier.objects.using(DB).select_for_update().get(pk=obj.pk)
            Supplier.objects.using(DB).filter(pk=obj.pk).update(credentials_ciphertext=ciphertext, updated_at=timezone.now())
            audit('credentials_replaced' if value else 'credentials_cleared', request.user.pk, obj)
        return Response({'credentials_set': bool(value), 'connection_verified': False})

    @action(detail=True, methods=['post'])
    def connection(self, request, pk=None):
        obj = self.get_object()
        from .supplier_connectors import LIVE, collect, ConnectorError
        if obj.connector in LIVE:
            require(request.user, 'collect_supplier')
            if not obj.enabled or not obj.terms_confirmed:
                raise ValidationError('Enable this supplier with recorded permitted API access first.')
            try:
                rows, stats = collect(obj)
            except ConnectorError as exc:
                return Response({'connected': False, 'connector': obj.connector, 'detail': str(exc)}, status=409)
            return Response({'connected': True, 'connector': obj.connector, 'identity_count': len(rows), 'counts': stats,
                             'detail': 'Read-only product API verified. No products were imported or orders placed.'})
        return Response({'connected': False, 'connector': obj.connector,
            'detail': 'Snapshot connector available. Live supplier authentication and stock/order APIs have not been configured or tested.'})

    @action(detail=True, methods=['post'], url_path='browser-collection')
    def browser_collection(self, request, pk=None):
        require(request.user, 'collect_supplier')
        supplier = self.get_object()
        login = BrowserLoginSerializer(data=request.data)
        login.is_valid(raise_exception=True)
        from .supplier_browser import launch_job, CollectionStopped
        try:
            job = launch_job(supplier, login.validated_data['username'], login.validated_data['password'], request.user.pk)
        except CollectionStopped as exc:
            return Response({'detail': str(exc)}, status=409)
        return Response({'id': str(job.pk), 'status': 'queued',
                         'detail': 'Read-only browser collection queued. Login is used for this run only; it is not saved.'}, status=202)

    @action(detail=True, methods=['post'], url_path='full-collection')
    def full_collection(self, request, pk=None):
        require(request.user, 'collect_supplier')
        supplier = self.get_object()
        from .supplier_source_clients import SUPPLIER_IDS
        site = next((site for site, pk in SUPPLIER_IDS.items() if pk == supplier.pk), None)
        if not site or not supplier.enabled or not supplier.terms_confirmed:
            raise ValidationError(supplier.health or 'Enable authorised supplier access first.')
        if not supplier.credentials_ciphertext and site != 'selfshop':
            raise ValidationError('Save supplier sign-in credentials before collecting full details.')
        if supplier.recollections.filter(status__in=('running', 'queued', 'cancel_requested')).exists():
            raise ValidationError('Full collection is already running for this supplier.')
        if supplier.jobs.filter(status__in=ACTIVE).exists():
            raise ValidationError('A supplier job is already running. Wait or cancel it before starting browser collection.')
        import subprocess
        import sys
        from pathlib import Path
        from django.conf import settings
        # The per-supplier file lock also closes the race between two staff clicks.
        root = Path(settings.BASE_DIR) / 'private_suppliers' / 'recollection'
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        stream = (root / (site + '-workspace.log')).open('ab')
        try:
            subprocess.Popen([sys.executable, str(Path(settings.BASE_DIR) / 'manage.py'),
                'collect_supplier_full', '--supplier', site,'--actor-id',str(request.user.pk)], cwd=settings.BASE_DIR,
                stdout=stream, stderr=stream, stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        finally:
            stream.close()
        audit('full_source_collection_requested', request.user.pk, supplier)
        return Response({'status': 'queued', 'detail': 'Browser-visible catalogue verification started; buying prices and orderable stock are read from the account website. Unclear products remain for review.'}, status=202)

    @action(detail=True, methods=['post'], url_path='cancel-full-collection')
    def cancel_full_collection(self, request, pk=None):
        require(request.user, 'collect_supplier')
        supplier = self.get_object()
        count = supplier.recollections.filter(status__in=('running', 'queued')).update(status='cancel_requested',updated_at=timezone.now())
        count += supplier.jobs.filter(runner='browser',action='collect',status__in=('running','queued')).update(status='cancel_requested',updated_at=timezone.now())
        return Response({'cancel_requested': count})


class OfferViewSet(CommerceAdminAuthMixin, viewsets.ReadOnlyModelViewSet):
    queryset = SupplierOffer.objects.using(DB).select_related('supplier', 'current_decision').all()
    serializer_class = OfferSerializer
    permission_classes = [IsCommerceAdmin]
    permission_model = Supplier
    permission_requirements = {'POST': ((Supplier, 'view'),)}
    pagination_class = StorefrontProductPagination

    def get_queryset(self):
        qs = super().get_queryset()
        for key in ('supplier_id', 'state', 'vendor_id', 'availability'):
            value = self.request.query_params.get(key)
            if value:
                if key == 'supplier_id' and not value.isdigit():
                    raise ValidationError('Invalid supplier ID.')
                qs = qs.filter(**{key: value})
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(external_id__icontains=search))
        price_bounds = {}
        for param, lookup in (('min_price', 'source_price__gte'), ('max_price', 'source_price__lte')):
            if self.request.query_params.get(param):
                try:
                    price_bounds[param] = money(self.request.query_params[param], param)
                    qs = qs.filter(**{lookup: price_bounds[param]})
                except ValueError as exc:
                    raise ValidationError(str(exc))
        if 'min_price' in price_bounds and 'max_price' in price_bounds and price_bounds['min_price'] > price_bounds['max_price']:
            raise ValidationError('Minimum price cannot exceed maximum price.')
        if self.request.query_params.get('category'):
            qs = qs.filter(identity__category__iexact=self.request.query_params['category'])
        ordering = self.request.query_params.get('ordering', 'id')
        return qs.order_by(ordering, 'id') if ordering in ('source_price', '-source_price', 'observed_at', '-observed_at') else qs.order_by('id')

    @action(detail=False, methods=['get'])
    def selection(self, request):
        size = request.query_params.get('selection', 'all')
        if size not in ('100', '500', '1000', 'all'):
            raise ValidationError('Choose 100, 500, 1000 or all matching products.')
        qs = self.get_queryset()
        total = qs.count()
        if size == 'all' and total > 100000:
            raise ValidationError('More than 100,000 products match. Narrow the supplier/category filter before selecting all.')
        ids = list(qs.values_list('pk', flat=True)[:int(size) if size != 'all' else 100000])
        return Response({'ids': ids, 'count': len(ids), 'total': total})

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        require(request.user, 'research_supplier')
        offer = self.get_object()
        with transaction.atomic(using=DB):
            offer = SupplierOffer.objects.using(DB).select_for_update().get(pk=offer.pk)
            if 'url' in request.data:
                url = serializers.URLField(max_length=1000).run_validation(request.data['url'])
                offer.url = checked_url(url)
            if 'identity' in request.data:
                identity = IdentitySerializer(data=request.data['identity'])
                identity.is_valid(raise_exception=True)
                validated_identity = json.loads(json.dumps(identity.validated_data, default=str))
                if offer.imported_product_id and validated_identity != offer.identity:
                    raise ValidationError('An imported product identity cannot be remapped. Preserve historical source mapping and review a new offer separately.')
                offer.identity = validated_identity
                offer.match_key = match_key(offer.identity)
                offer.match_confirmed = False
            if 'match_confirmed' in request.data:
                confirmed = serializers.BooleanField().run_validation(request.data['match_confirmed'])
                if confirmed and not offer.match_key:
                    raise ValidationError('Required exact-identity fields are missing. Recollect with corrected identity after review.')
                offer.match_confirmed = confirmed
            if 'costs' in request.data:
                costs = request.data['costs']
                if not isinstance(costs, dict) or set(costs) - set((*MONEY_COSTS, 'supplier_shipping', 'customer_shipping', 'fees', 'taxes')):
                    raise ValidationError('Use the supported sourcing cost fields only.')
                try:
                    offer.costs = {k: str(money(v, k)) for k, v in costs.items()}
                except ValueError as exc:
                    raise ValidationError(str(exc))
            if 'excluded_reason' in request.data:
                require(request.user, 'approve_supplier')
                offer.excluded_reason = serializers.CharField(max_length=500, allow_blank=True).run_validation(request.data['excluded_reason'])
            offer.state = 'excluded' if offer.excluded_reason else 'needs_review'
            offer.save(using=DB)
            audit('offer_review', request.user.pk, offer.supplier, offer, fields=list(request.data))
        return Response(OfferSerializer(offer).data)

    @action(detail=True, methods=['get', 'post'])
    def evidence(self, request, pk=None):
        offer = self.get_object()
        if request.method == 'GET':
            return Response(EvidenceSerializer(offer.evidence.order_by('-observed_at')[:100], many=True).data)
        require(request.user, 'research_supplier')
        with transaction.atomic(using=DB):
            previous_key = request.data.get('expected_match_key', offer.match_key)
            offer = SupplierOffer.objects.using(DB).select_for_update().get(pk=offer.pk)
            if previous_key != offer.match_key:
                raise ValidationError('Product identity changed while researching. Refresh the offer and verify the listing again.')
            serializer = EvidenceSerializer(data={**request.data, 'offer': offer.pk})
            serializer.is_valid(raise_exception=True)
            serializer.save(actor_id=request.user.pk, match_key=offer.match_key)
            if not offer.excluded_reason:
                SupplierOffer.objects.using(DB).filter(pk=offer.pk).update(state='needs_review')
            audit('market_evidence', request.user.pk, offer.supplier, offer, evidence_id=serializer.instance.pk)
        return Response(serializer.data, status=201)

    @action(detail=True, methods=['post'])
    def approval(self, request, pk=None):
        require(request.user, 'approve_supplier')
        try:
            approve(self.get_object(), request.user.pk, serializers.CharField(max_length=1000).run_validation(request.data.get('note')))
        except ValueError as exc:
            raise ValidationError(str(exc))
        return Response({'detail': 'Approved for draft import only. Publication and live purchasing remain separate.'})


class JobViewSet(CommerceAdminAuthMixin, viewsets.ReadOnlyModelViewSet):
    queryset = SupplierJob.objects.using(DB).select_related('supplier').all()
    serializer_class = JobSerializer
    permission_classes = [IsCommerceAdmin]
    permission_model = Supplier
    permission_requirements = {'POST': ((Supplier, 'view'),)}
    pagination_class = StorefrontProductPagination

    @action(detail=False, methods=['post'])
    def selected(self, request):
        operation = serializers.ChoiceField(choices=['update', 'filter']).run_validation(request.data.get('action'))
        require(request.user, 'collect_supplier' if operation == 'update' else 'screen_supplier')
        ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=100000).run_validation(request.data.get('offer_ids'))
        groups = {}
        for pk, supplier_id in SupplierOffer.objects.using(DB).filter(pk__in=set(ids)).order_by('supplier_id', 'pk').values_list('pk', 'supplier_id'):
            groups.setdefault(supplier_id, []).append(pk)
        if sum(map(len, groups.values())) != len(set(ids)):
            raise ValidationError('Some selected source identities no longer exist. Select the products again.')
        from .supplier_connectors import LIVE
        queued, skipped = [], []
        for supplier in Supplier.objects.using(DB).filter(pk__in=groups).order_by('pk'):
            if operation == 'update' and supplier.connector not in LIVE:
                skipped.append({'supplier': supplier.pk, 'name': supplier.name, 'count': len(groups[supplier.pk]),
                    'reason': 'No unattended stock/price connector. Use authorised browser collection or a fresh supplier snapshot; saved stock has not been changed.'})
                continue
            try:
                job = queue_job(supplier.pk, operation, request.user.pk, offer_ids=groups[supplier.pk], bulk=True)
                queued.append({'id': str(job.pk), 'supplier': supplier.pk, 'count': len(groups[supplier.pk])})
            except ValueError as exc:
                skipped.append({'supplier': supplier.pk, 'name': supplier.name, 'count': len(groups[supplier.pk]), 'reason': str(exc)})
        return Response({'queued': queued, 'skipped': skipped, 'selected_count': len(set(ids))}, status=202)

    def create(self, request):
        action_name = request.data.get('action')
        require(request.user, 'collect_supplier' if action_name in ('collect', 'update') else 'screen_supplier')
        supplier_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('supplier'))
        ids = request.data.get('offer_ids')
        if ids is not None:
            ids = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=1000).run_validation(ids)
        try:
            job = queue_job(supplier_id, action_name, request.user.pk, request.data.get('rows'), ids)
        except (ValueError, Supplier.DoesNotExist) as exc:
            raise ValidationError(str(exc) if isinstance(exc, ValueError) else 'Supplier not found.')
        return Response(JobSerializer(job).data, status=202)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        job = self.get_object()
        require(request.user, 'collect_supplier' if job.action in ('collect', 'update') else 'screen_supplier')
        SupplierJob.objects.using(DB).filter(pk=job.pk, status__in=ACTIVE).update(status='cancel_requested')
        audit('cancel_requested', request.user.pk, job.supplier, job_id=str(job.pk))
        return Response({'detail': 'Cancel requested; the worker will stop at the next safe checkpoint.'})


class ImportSelectionView(CommerceAdminAuthMixin, APIView):
    permission_classes = [IsCommerceAdmin]
    permission_model = Supplier
    permission_requirements = {'POST': ((Supplier, 'view'),)}

    def post(self, request):
        require(request.user, 'import_supplier')
        require(request.user, 'add_product')
        require(request.user, 'add_productvariant')
        ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=100).run_validation(request.data.get('ids'))
        category = serializers.IntegerField(min_value=1).run_validation(request.data.get('category'))
        preview = serializers.BooleanField().run_validation(request.data.get('preview', True))
        if not Category.objects.using(DB).filter(pk=category, is_active=True).exists():
            raise ValidationError('Choose an existing active import category before previewing or importing.')
        ids = sorted(set(ids))
        preview_record = None
        if not preview:
            try:
                preview_record = signing.loads(request.data.get('preview_token', ''), salt='commerce-supplier-import', max_age=600)
            except (signing.BadSignature, TypeError, ValueError):
                raise ValidationError('Import preview is missing or expired. Preview the selected changes again.')
            if not isinstance(preview_record, dict) or any(preview_record.get(k) != v for k, v in
                    {'actor': request.user.pk, 'category': category, 'ids': ids}.items()):
                raise ValidationError('Import selection or category changed. Preview these changes again.')
        results, decisions = [], {}
        with transaction.atomic(using=DB):
            for offer_id in ids:
                try:
                    offer = SupplierOffer.objects.using(DB).select_for_update().select_related('supplier', 'current_decision').get(pk=offer_id)
                    d = assert_current(offer)
                    if not d.approved_at:
                        raise ValueError('Staff approval is missing.')
                    current = [d.pk, d.fingerprint, d.result['suggested_price'], offer.imported_product_id]
                    decisions[str(offer_id)] = current
                    if preview_record is not None and preview_record.get('decisions', {}).get(str(offer_id)) != current:
                        raise ValueError('Screening or import status changed since the preview. Preview again.')
                    if preview:
                        results.append({'id': offer.pk, 'name': offer.title, 'price': d.result['suggested_price'],
                                        'status': 'draft', 'existing_product': offer.imported_product_id, 'stock': 0})
                    else:
                        product, created = import_draft(offer, category, request.user.pk)
                        results.append({'id': offer.pk, 'product': product.pk, 'created': created})
                except (ValueError, SupplierOffer.DoesNotExist, Category.DoesNotExist, IntegrityError) as exc:
                    if isinstance(exc, IntegrityError):
                        raise ValidationError('An equivalent product was imported concurrently. Refresh the selection; no duplicate was created.')
                    raise ValidationError(f'Offer {offer_id}: {exc}')
        token = signing.dumps({'actor': request.user.pk, 'category': category, 'ids': ids, 'decisions': decisions},
            salt='commerce-supplier-import', compress=True) if preview else None
        return Response({'preview': preview, 'results': results, 'preview_token': token})


class SupplierWorkspaceView(CommerceAdminAuthMixin, APIView):
    permission_classes = [IsCommerceAdmin]
    permission_model = Supplier

    def get(self, request):
        config = policy()
        from .supplier_connectors import LIVE
        from pathlib import Path
        from django.conf import settings
        sync = None
        try:
            path = Path(settings.BASE_DIR)/'private_suppliers'/'catalog_sync'/'status.json'
            if path.stat().st_size < 4096:
                sync = json.loads(path.read_text(encoding='utf-8'))
                import re
                token=sync.get('run','')
                if sync.get('status')=='running' and re.fullmatch(r'\d{8}T\d{6}Z-[a-f0-9]{6}',token):
                    for progress in (path.parent/token).glob('*.import-progress.json'):
                        if progress.stat().st_size>4096:continue
                        value=json.loads(progress.read_text(encoding='utf-8'))
                        if value.get('updated_at','')>=sync.get('updated_at',''):
                            sync={**sync,'activity':f"Applying catalog changes: {int(value.get('records',0)):,} records checked on this server",
                                  'updated_at':value['updated_at']}
        except (OSError, ValueError): pass
        return Response({'timezone': 'Asia/Dhaka', 'nightly_time': '23:59', 'evidence_days': config.evidence_days,
            'catalog_sync':sync,
            'retention_days': config.retention_days, 'last_nightly_date': config.last_nightly_date,
            'auto_place_orders': False, 'live_connectors': list(LIVE), 'market_search_connected': False,
            'catalogue_mode':config.catalogue_mode,'catalogue_revision':config.catalogue_revision,
            'message': 'Read-only product collection for documented configured APIs; other suppliers use authorised snapshots. No real supplier orders can be submitted.',
            'permissions': {x: request.user.is_superuser or request.user.has_perm('ecommerce.' + x) for x in
                ('collect_supplier', 'research_supplier', 'screen_supplier', 'approve_supplier', 'import_supplier', 'edit_supplier_credentials', 'add_supplier', 'change_supplier', 'publish_supplier_pilot', 'confirm_supplier_pilot','manage_supplier_catalogue')},
            'active_jobs': SupplierJob.objects.using(DB).filter(status__in=ACTIVE).count()})


class SupplierReportsView(CommerceAdminAuthMixin, APIView):
    permission_classes = [IsCommerceAdmin]
    permission_model = Supplier

    def get(self, request):
        raw = (request.query_params.get('supplier') or '').strip()
        suppliers = Supplier.objects.using(DB).order_by('name')
        selected = None
        if raw:
            try:
                selected = int(raw)
            except (TypeError, ValueError):
                raise ValidationError('Select a supplier by id.')
            suppliers = suppliers.filter(pk=selected)
            if not suppliers.exists():
                raise ValidationError('Unknown supplier.')
        supplier_rows = list(suppliers.values('id', 'name', 'enabled'))
        ids = [row['id'] for row in supplier_rows]
        collected = dict(SupplierSourceProduct.objects.using(DB).filter(supplier_id__in=ids).values('supplier_id').annotate(
            n=Count('id')).values_list('supplier_id', 'n'))
        hosted = dict(Product.objects.using(DB).filter(status='active', supplier_offer__supplier_id__in=ids).values(
            'supplier_offer__supplier_id').annotate(n=Count('id')).values_list('supplier_offer__supplier_id', 'n'))
        on_shop = SupplierOffer.objects.using(DB).filter(
            source_product_id=OuterRef('pk'), imported_product__status='active')
        unhosted = dict(SupplierSourceProduct.objects.using(DB).filter(supplier_id__in=ids).annotate(
            on_shop=Exists(on_shop)).filter(on_shop=False).values('supplier_id').annotate(
            n=Count('id')).values_list('supplier_id', 'n'))
        blacklisted = dict(SupplierOffer.objects.using(DB).filter(supplier_id__in=ids, state='blacklist').values(
            'supplier_id').annotate(n=Count('id')).values_list('supplier_id', 'n'))
        rows = [{
            'supplier_id': row['id'], 'supplier_name': row['name'], 'enabled': row['enabled'],
            'collected': int(collected.get(row['id'], 0)), 'hosted': int(hosted.get(row['id'], 0)),
            'unhosted': int(unhosted.get(row['id'], 0)), 'blacklisted': int(blacklisted.get(row['id'], 0)),
        } for row in supplier_rows]
        return Response({
            'selected_supplier': selected,
            'suppliers': list(Supplier.objects.using(DB).order_by('name').values('id', 'name', 'enabled')),
            'rows': rows,
            'totals': {
                'suppliers': Supplier.objects.using(DB).count() if selected is None else 1,
                'collected': sum(row['collected'] for row in rows),
                'hosted': sum(row['hosted'] for row in rows),
                'unhosted': sum(row['unhosted'] for row in rows),
                'blacklisted': sum(row['blacklisted'] for row in rows),
            },
            'definitions': {
                'collected': 'Source catalogue records stored from supplier recollection.',
                'hosted': 'Imported products currently active on the shop.',
                'unhosted': 'Collected source records with no active shop listing.',
                'blacklisted': 'Supplier offers marked blacklist.',
            },
        })


class SalesReportsView(CommerceAdminAuthMixin, APIView):
    permission_classes = [IsCommerceAdmin]
    permission_model = Order

    def get(self, request):
        from .sales_reporting import build_sales_report
        return Response(build_sales_report(request.query_params))


class EnsurePricesView(CommerceAdminAuthMixin, APIView):
    permission_classes = [IsCommerceAdmin]
    permission_model = Supplier

    def get(self, request):
        require(request.user, 'collect_supplier')
        from .price_ensure import last_price_report
        return Response(last_price_report() or {'saved': False, 'rows': []})

    def post(self, request):
        require(request.user, 'collect_supplier')
        live = request.data.get('live') in (True, 'true', '1', 1)
        from .price_ensure import ensure_prices
        return Response(ensure_prices(live=live))


class CatalogSyncView(CommerceAdminAuthMixin, APIView):
    permission_classes = [IsCommerceAdmin]
    permission_model = Supplier

    def get(self, request):
        require(request.user, 'collect_supplier')
        from .catalog_sync_control import last_catalog_report
        return Response(last_catalog_report() or {'saved': False, 'status': 'idle'})

    def post(self, request):
        require(request.user, 'collect_supplier')
        from .catalog_sync_control import queue_or_run_sync
        return Response(queue_or_run_sync())


class UploadBuildView(CommerceAdminAuthMixin, APIView):
    permission_classes = [IsCommerceAdmin]
    permission_model = Supplier

    def get(self, request):
        require(request.user, 'collect_supplier')
        from .upload_build import last_deploy_report
        return Response(last_deploy_report() or {'saved': False, 'status': 'idle'})

    def post(self, request):
        require(request.user, 'collect_supplier')
        from .upload_build import queue_or_run_deploy
        return Response(queue_or_run_deploy())


# Kept here to avoid introducing a public supplier endpoint or arbitrary fetch proxy.
from .models import Category  # noqa: E402
