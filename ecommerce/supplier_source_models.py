"""Full source catalogue staging, independent of public listings and financial data."""
import uuid

from django.db import models
from .models import TimeStampedModel


class SupplierRecollectionRun(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey('Supplier', on_delete=models.PROTECT, related_name='recollections')
    mode = models.CharField(max_length=12, choices=[('inspect', 'Sample inspection'), ('full', 'Full recollection')])
    status = models.CharField(max_length=24, default='queued', choices=[(s, s.replace('_', ' ').title()) for s in
        ('queued', 'running', 'paused', 'cancel_requested', 'cancelled', 'completed', 'completed_with_errors', 'failed')])
    mapping_version = models.PositiveIntegerField(default=1)
    expected_total = models.PositiveIntegerField(null=True, blank=True)
    discovered = models.PositiveIntegerField(default=0)
    processed = models.PositiveIntegerField(default=0)
    counts = models.JSONField(default=dict)
    checkpoint = models.JSONField(default=dict)
    activity = models.CharField(max_length=500, blank=True)
    coverage = models.JSONField(default=dict, help_text='Actual source totals, inspected fields, access gaps and traversal evidence.')
    errors = models.JSONField(default=list)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)


class SupplierSourceProduct(TimeStampedModel):
    supplier = models.ForeignKey('Supplier', on_delete=models.PROTECT, related_name='source_products')
    source_key = models.CharField(max_length=64)
    external_id = models.CharField(max_length=255)
    vendor_id = models.CharField(max_length=255, blank=True)
    warehouse_id = models.CharField(max_length=255, blank=True)
    url = models.URLField(max_length=2000)
    title = models.TextField()
    sku = models.CharField(max_length=500, blank=True)
    short_description = models.TextField(blank=True)
    description = models.TextField(blank=True)
    # No supplier-specific information is forced into the small matching identity schema.
    categories = models.JSONField(default=list)
    specifications = models.JSONField(default=dict)
    features = models.JSONField(default=list)
    prices = models.JSONField(default=dict)
    stock = models.JSONField(default=dict)
    variants = models.JSONField(default=list)
    shipping = models.JSONField(default=dict)
    extra = models.JSONField(default=dict, help_text='Brand/model/materials/warranty/tags/ratings/source timestamps and unmapped fields.')
    raw_data = models.JSONField(default=dict, help_text='Product-only source data. Never login responses, credentials, cookies or session scripts.')
    content_hash = models.CharField(max_length=64)
    quality = models.JSONField(default=dict)
    observed_at = models.DateTimeField()
    last_run = models.ForeignKey(SupplierRecollectionRun, on_delete=models.PROTECT, related_name='products')

    class Meta:
        ordering = ('supplier_id', 'id')
        constraints = [models.UniqueConstraint(fields=('supplier', 'source_key'), name='supplier_source_product_key')]
        indexes = [models.Index(fields=('supplier', 'external_id'), name='supplier_source_external_idx')]

    def __str__(self):
        return self.title


class SupplierSourceMedia(TimeStampedModel):
    product = models.ForeignKey(SupplierSourceProduct, on_delete=models.PROTECT, related_name='media')
    media_key = models.CharField(max_length=64)
    kind = models.CharField(max_length=12, choices=[('image', 'Image'), ('video', 'Video')])
    role = models.CharField(max_length=16, default='gallery')
    original_url = models.URLField(max_length=2000)
    stored_url = models.URLField(max_length=2000, blank=True)
    variant_id = models.CharField(max_length=255, blank=True)
    alt_text = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict)
    last_seen_at = models.DateTimeField()
    last_run = models.ForeignKey(SupplierRecollectionRun, on_delete=models.PROTECT)

    class Meta:
        ordering = ('position', 'pk')
        constraints = [models.UniqueConstraint(fields=('product', 'media_key'), name='supplier_source_media_key')]


class SupplierRecollectionItem(TimeStampedModel):
    run = models.ForeignKey(SupplierRecollectionRun, on_delete=models.PROTECT, related_name='items')
    source_key = models.CharField(max_length=64)
    external_id = models.CharField(max_length=255)
    url = models.URLField(max_length=2000)
    status = models.CharField(max_length=16, default='pending', choices=[(s, s.title()) for s in ('pending', 'complete', 'incomplete', 'failed')])
    source_product = models.ForeignKey(SupplierSourceProduct, null=True, blank=True, on_delete=models.PROTECT)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=500, blank=True)
    observed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('run', 'source_key'), name='supplier_recollection_item_key')]
