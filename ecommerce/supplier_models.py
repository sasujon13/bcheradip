"""Private sourcing records. Customer identities and accepted commerce orders stay unchanged."""
import uuid
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from .models import TimeStampedModel


class Supplier(TimeStampedModel):
    name = models.CharField(max_length=160, unique=True)
    website = models.URLField(max_length=500)
    enabled = models.BooleanField(default=False)
    connector = models.CharField(max_length=40, default='snapshot', choices=[('snapshot', 'Authorised JSON snapshot'), ('business_koro', 'Business Koro storefront API (read only)'), ('uddoog', 'Uddoog account price/stock API (read only)'), ('resellkori', 'ResellKori tracked price/stock (read only)'), ('dropshipping_bd', 'Dropshipping.com.bd tracked price/stock (read only)'), ('labelled_stock', 'Tracked own-page labelled stock (read only)')])
    terms_confirmed = models.BooleanField(default=False)
    terms_note = models.TextField(blank=True)
    credentials_ciphertext = models.TextField(blank=True, editable=False)
    credential_expires_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    health = models.CharField(max_length=160, default='Not connected — snapshot upload only')

    class Meta:
        ordering = ('name',)
        permissions = [('edit_supplier_credentials', 'Replace encrypted supplier credentials'),
                       ('collect_supplier', 'Collect supplier identities'),
                       ('research_supplier', 'Record supplier market research'),
                       ('screen_supplier', 'Screen supplier offers'),
                       ('approve_supplier', 'Approve supplier offers for draft import'),
                       ('import_supplier', 'Import approved supplier offers as drafts'),
                       ('manage_supplier_catalogue','Switch collected catalogue preview visibility')]

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError
        from .supplier_service import public_url
        try:
            public_url(self.website)
        except ValueError as exc:
            raise ValidationError({'website': str(exc)})
        if (self.enabled or self.terms_confirmed) and not self.terms_note.strip():
            raise ValidationError('Record the permitted data use and fulfilment terms first.')
        if self.enabled and not self.terms_confirmed:
            raise ValidationError('Confirm supplier terms before enabling collection.')


class SupplierPolicy(TimeStampedModel):
    # Singleton also provides a short-lived worker lease; never hold DB locks across network work.
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    evidence_days = models.PositiveSmallIntegerField(default=14)
    retention_days = models.PositiveSmallIntegerField(default=90)
    revision = models.PositiveIntegerField(default=1)
    worker_token = models.CharField(max_length=40, blank=True, editable=False)
    worker_until = models.DateTimeField(null=True, blank=True, editable=False)
    last_nightly_date = models.DateField(null=True, blank=True, editable=False)
    catalogue_mode = models.CharField(max_length=12, default='filtered', choices=[('filtered','Keep Filtered (research-approved only)'),('all','Keep All (manual supplier fulfilment)')])
    catalogue_revision = models.PositiveIntegerField(default=1, editable=False)


class SupplierOffer(TimeStampedModel):
    STATES = [(x, x.replace('_', ' ').title()) for x in
              ('collected', 'needs_data', 'needs_review', 'ready', 'reduced_margin', 'blacklist', 'zero_margin', 'excluded')]
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='offers')
    external_id = models.CharField(max_length=120)
    variant_id = models.CharField(max_length=120, blank=True)
    vendor_id = models.CharField(max_length=120)
    warehouse_id = models.CharField(max_length=120, blank=True)
    title = models.CharField(max_length=255)
    url = models.URLField(max_length=1000)
    identity = models.JSONField(default=dict)
    match_key = models.CharField(max_length=64, blank=True, db_index=True)
    match_confirmed = models.BooleanField(default=False)
    source_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='BDT')
    availability = models.CharField(max_length=20, default='unconfirmed', choices=[(x, x.title()) for x in ('in_stock', 'out_of_stock', 'unconfirmed', 'missing')])
    quantity = models.PositiveIntegerField(null=True, blank=True)
    weight_grams = models.PositiveIntegerField(null=True, blank=True)
    single_unit = models.BooleanField(default=False)
    observed_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(max_length=25, choices=STATES, default='collected', db_index=True)
    excluded_reason = models.CharField(max_length=500, blank=True)
    costs = models.JSONField(default=dict)
    current_decision = models.ForeignKey('SupplierDecision', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    imported_product = models.OneToOneField('Product', null=True, blank=True, on_delete=models.PROTECT, related_name='supplier_offer')
    import_key = models.CharField(max_length=64, unique=True, null=True, blank=True, editable=False)
    preview_images = models.JSONField(default=list, blank=True, help_text='Public image references only; never supplier session URLs or credentials.')
    source_product = models.ForeignKey('SupplierSourceProduct', null=True, blank=True, on_delete=models.PROTECT,
        related_name='linked_offers', help_text='Fresh full source content. Kept separate from matching identity and shop edits.')

    class Meta:
        ordering = ('id',)
        constraints = [models.UniqueConstraint(fields=('supplier', 'external_id', 'variant_id', 'vendor_id', 'warehouse_id'), name='supplier_offer_identity')]


class SupplierEvidence(TimeStampedModel):
    offer = models.ForeignKey(SupplierOffer, on_delete=models.PROTECT, related_name='evidence')
    seller = models.CharField(max_length=160, help_text='Stable independent seller identity, not just marketplace name')
    marketplace = models.CharField(max_length=160)
    url = models.URLField(max_length=1000)
    price = models.DecimalField(max_digits=14, decimal_places=2)
    delivery = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    observed_at = models.DateTimeField()
    exact_match = models.BooleanField(default=False)
    match_confidence = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Assessed similarity percent, 0–100. Not a substitute for verified exact matching.')
    available = models.BooleanField(default=True)
    match_key = models.CharField(max_length=64)
    note = models.CharField(max_length=1000)
    actor_id = models.BigIntegerField()


class SupplierDecision(TimeStampedModel):
    offer = models.ForeignKey(SupplierOffer, on_delete=models.PROTECT, related_name='decisions')
    state = models.CharField(max_length=25)
    fingerprint = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    actor_id = models.BigIntegerField(null=True)
    approved_at = models.DateTimeField(null=True)
    approved_by = models.BigIntegerField(null=True)
    approval_note = models.CharField(max_length=1000, blank=True)


class SupplierJob(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ACTIONS = [(x, x.replace('_', ' ').title()) for x in ('collect', 'update', 'filter', 'recheck', 'publish_catalogue')]
    action = models.CharField(max_length=20, choices=ACTIONS)
    runner = models.CharField(max_length=12, default='worker', choices=[('worker', 'API / snapshot worker'), ('browser', 'Authorised browser collector')])
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='jobs')
    status = models.CharField(max_length=30, default='queued', db_index=True,
        choices=[(x, x.replace('_', ' ').title()) for x in ('queued', 'running', 'cancel_requested', 'cancelled', 'completed', 'completed_with_errors', 'failed')])
    payload = models.JSONField(default=dict, editable=False)
    total = models.PositiveIntegerField(default=0)
    processed = models.PositiveIntegerField(default=0)
    counts = models.JSONField(default=dict)
    errors = models.JSONField(default=list)
    activity = models.CharField(max_length=300, default='Waiting for worker')
    actor_id = models.BigIntegerField(null=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ('-created_at',)


class SupplierAudit(TimeStampedModel):
    supplier = models.ForeignKey(Supplier, null=True, on_delete=models.PROTECT)
    offer = models.ForeignKey(SupplierOffer, null=True, on_delete=models.PROTECT)
    actor_id = models.BigIntegerField(null=True)
    action = models.CharField(max_length=80)
    detail = models.JSONField(default=dict)

    class Meta:
        ordering = ('-created_at',)


class SupplierSettlementEntry(TimeStampedModel):
    """Staff-verified statement entries, retained separately from operational logs."""
    KINDS = [('cod_collected','Customer COD collected by supplier'), ('source_charge','Supplier product charge'),
             ('delivery_charge','Supplier delivery charge'), ('other_charge','Verified supplier fees / other charge'), ('customer_refund','Customer refund charged to supplier balance'),
             ('supplier_refund','Cost credited back by supplier'), ('settlement_received','Payout received by Cheradip'),
             ('reversal','Reverse an incorrect statement entry')]
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='settlement_entries')
    order = models.ForeignKey('Order', on_delete=models.PROTECT, null=True, blank=True)
    kind = models.CharField(max_length=30, choices=KINDS)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=160, help_text='Unique supplier statement / payout reference; never enter bank credentials.')
    note = models.CharField(max_length=1000, help_text='Record the statement evidence and reconciliation reason.')
    reversal_of = models.OneToOneField('self', null=True, blank=True, on_delete=models.PROTECT, related_name='reversal')
    actor_id = models.BigIntegerField(editable=False)

    def __str__(self):
        return f'{self.supplier.name} · {self.get_kind_display()} · BDT {self.amount} · {self.reference}'

    class Meta:
        ordering = ('-created_at',)
        constraints = [models.UniqueConstraint(fields=('supplier','reference'),name='supplier_statement_reference')]
        verbose_name_plural = 'Supplier settlement entries'

    def clean(self):
        from django.core.exceptions import ValidationError
        from .pricing import money
        try:
            if money(self.amount,'Statement amount') <= 0:
                raise ValueError('Statement amounts must be positive.')
        except ValueError as exc:
            raise ValidationError({'amount':str(exc)})
        if not str(self.reference or '').strip() or not str(self.note or '').strip():
            raise ValidationError('Statement reference and evidence note are required.')
        if self.kind == 'reversal':
            parent = self.reversal_of if self.reversal_of_id else None
            if not parent or parent.kind == 'reversal' or parent.supplier_id != self.supplier_id or parent.order_id != self.order_id or parent.amount != self.amount:
                raise ValidationError('A reversal must match the original supplier, order and amount; reversals cannot themselves be reversed.')
        elif self.reversal_of_id:
            raise ValidationError('Only reversal entries may reference an earlier entry.')

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        if self.pk:
            raise ValidationError('Statement entries are immutable. Add a reversal and a corrected entry.')
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Statement entries cannot be deleted. Record a reversal instead.')


class SupplierResearchBatch(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=20, default='active', choices=[(s,s.title()) for s in ('active','paused','completed')])
    supplier_ids = models.JSONField(default=list)
    actor_id = models.BigIntegerField()

    class Meta:
        ordering = ('-created_at',)


class SupplierResearchItem(TimeStampedModel):
    batch = models.ForeignKey(SupplierResearchBatch, on_delete=models.PROTECT, related_name='items')
    offer = models.OneToOneField(SupplierOffer, on_delete=models.PROTECT, related_name='research_item')
    status = models.CharField(max_length=20, default='pending', choices=[(s,s.replace('_',' ').title()) for s in ('pending','researching','needs_data','reviewed')])
    note = models.TextField(blank=True, max_length=6000)
    actor_id = models.BigIntegerField()
    decision = models.ForeignKey(SupplierDecision, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ('pk',)


class SupplierPilotCheck(TimeStampedModel):
    product = models.ForeignKey('Product', on_delete=models.PROTECT, related_name='pilot_checks')
    order = models.ForeignKey('Order', null=True, blank=True, on_delete=models.PROTECT, related_name='pilot_checks', help_text='Blank: publication release. Set: separate pre-confirmation fulfilment verification.')
    expected_source_price = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    expected_selling_price = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    verified_quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    expires_at = models.DateTimeField(help_text='Must be within 24 hours; confirm actual stock again when expired.')
    checks = models.JSONField(default=dict)
    note = models.TextField(max_length=2000, help_text='Source quote/reference, exact variant, available quantity, delivery, full costs/margin and reviewed content.')
    snapshot = models.JSONField(default=dict, editable=False)
    fingerprint = models.CharField(max_length=64, editable=False)
    actor_id = models.BigIntegerField(editable=False)
    revoked_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ('-pk',)
        permissions = [('publish_supplier_pilot','Verify supplier pilot publication'),('confirm_supplier_pilot','Verify manual supplier fulfilment before order confirmation')]

    def save(self,*args,**kwargs):
        from django.core.exceptions import ValidationError
        if self.pk:
            raise ValidationError('Pilot checks are immutable. Revoke and record a new verification.')
        super().save(*args,**kwargs)

    def delete(self,*args,**kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Keep the audit history; revoke this check instead.')


