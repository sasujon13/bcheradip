import secrets
import uuid

from django.db import models
from django.utils import timezone
from django.utils.text import slugify


def generate_token():
    return secrets.token_urlsafe(24)


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Category(TimeStampedModel):
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children', on_delete=models.SET_NULL)
    description = models.TextField(blank=True)
    image_url = models.URLField(max_length=1000, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ecommerce_category'
        ordering = ('sort_order', 'name')
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name


class Brand(TimeStampedModel):
    name = models.CharField(max_length=160, unique=True)
    slug = models.SlugField(max_length=180, unique=True)
    logo_url = models.URLField(max_length=1000, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ecommerce_brand'
        ordering = ('name',)

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    STATUS_CHOICES = [('draft', 'Draft'), ('active', 'Active'), ('archived', 'Archived')]
    TYPE_CHOICES = [('physical', 'Physical'), ('digital', 'Digital'), ('service', 'Service')]

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    short_description = models.CharField(max_length=500, blank=True)
    category = models.ForeignKey(Category, related_name='products', on_delete=models.PROTECT)
    brand = models.ForeignKey(Brand, null=True, blank=True, related_name='products', on_delete=models.SET_NULL)
    product_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='physical')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    featured = models.BooleanField(default=False, db_index=True)
    tags = models.CharField(max_length=1000, blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    seo_title = models.CharField(max_length=255, blank=True)
    seo_description = models.CharField(max_length=500, blank=True)
    source_url = models.URLField(max_length=1000, blank=True)
    is_sample = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = 'ecommerce_product'
        ordering = ('-featured', '-created_at')
        indexes = [models.Index(fields=['status', 'category']), models.Index(fields=['slug'])]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or uuid.uuid4().hex[:12]
            self.slug = base
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductVariant(TimeStampedModel):
    product = models.ForeignKey(Product, related_name='variants', on_delete=models.CASCADE)
    title = models.CharField(max_length=255, default='Default')
    sku = models.CharField(max_length=120, unique=True)
    barcode = models.CharField(max_length=120, blank=True, db_index=True)
    option1_name = models.CharField(max_length=100, blank=True)
    option1_value = models.CharField(max_length=160, blank=True)
    option2_name = models.CharField(max_length=100, blank=True)
    option2_value = models.CharField(max_length=160, blank=True)
    option3_name = models.CharField(max_length=100, blank=True)
    option3_value = models.CharField(max_length=160, blank=True)
    price = models.DecimalField(max_digits=14, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cost_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='BDT')
    stock = models.IntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    weight_grams = models.PositiveIntegerField(default=0)
    requires_shipping = models.BooleanField(default=True)
    allow_backorder = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ecommerce_product_variant'
        ordering = ('product_id', 'id')

    def __str__(self):
        return f'{self.product.name} - {self.title}'


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, related_name='images', on_delete=models.CASCADE)
    url = models.URLField(max_length=1000)
    alt_text = models.CharField(max_length=255, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'ecommerce_product_image'
        ordering = ('position', 'id')


class InventoryMovement(TimeStampedModel):
    REASONS = [('import', 'Import'), ('sale', 'Sale'), ('cancel', 'Cancellation'), ('return', 'Return'), ('adjustment', 'Adjustment')]
    variant = models.ForeignKey(ProductVariant, related_name='inventory_movements', on_delete=models.CASCADE)
    quantity = models.IntegerField()
    reason = models.CharField(max_length=20, choices=REASONS)
    reference = models.CharField(max_length=160, blank=True)
    note = models.CharField(max_length=500, blank=True)
    actor_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'ecommerce_inventory_movement'
        ordering = ('-created_at',)


class Cart(TimeStampedModel):
    token = models.CharField(max_length=80, unique=True, default=generate_token)
    customer_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    checked_out = models.BooleanField(default=False)

    class Meta:
        db_table = 'ecommerce_cart'


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, related_name='cart_items', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'ecommerce_cart_item'
        constraints = [models.UniqueConstraint(fields=['cart', 'variant'], name='ecommerce_cart_variant_unique')]


class Coupon(TimeStampedModel):
    DISCOUNT_TYPES = [('percent', 'Percent'), ('fixed', 'Fixed amount'), ('shipping', 'Free shipping')]
    code = models.CharField(max_length=80, unique=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES)
    value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    minimum_order = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ecommerce_coupon'


class Order(TimeStampedModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'), ('confirmed', 'Confirmed'), ('processing', 'Processing'),
        ('shipped', 'Shipped'), ('delivered', 'Delivered'), ('cancelled', 'Cancelled'),
        ('returned', 'Returned'), ('refunded', 'Refunded'),
    ]
    PAYMENT_STATUS = [('unpaid', 'Unpaid'), ('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed'), ('refunded', 'Refunded')]

    number = models.CharField(max_length=32, unique=True, db_index=True)
    tracking_token = models.CharField(max_length=64, unique=True, default=generate_token)
    customer_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    customer_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=40)
    shipping_address = models.JSONField(default=dict)
    billing_address = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='unpaid', db_index=True)
    currency = models.CharField(max_length=3, default='BDT')
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    shipping_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    coupon_code = models.CharField(max_length=80, blank=True)
    customer_note = models.TextField(blank=True)
    admin_note = models.TextField(blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ecommerce_order'
        ordering = ('-created_at',)

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = f'CH-{timezone.now():%y%m%d}-{secrets.token_hex(3).upper()}'
        super().save(*args, **kwargs)

    def __str__(self):
        return self.number


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product_id = models.BigIntegerField()
    variant_id = models.BigIntegerField()
    product_name = models.CharField(max_length=255)
    variant_title = models.CharField(max_length=255, blank=True)
    sku = models.CharField(max_length=120)
    image_url = models.URLField(max_length=1000, blank=True)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = 'ecommerce_order_item'


class Payment(TimeStampedModel):
    METHODS = [('wallet', 'Cheradip Wallet'), ('cod', 'Cash on delivery'), ('bkash', 'bKash'), ('nagad', 'Nagad'), ('bank', 'Bank transfer'), ('card', 'Card'), ('other', 'Other')]
    STATUS_CHOICES = [('pending', 'Pending'), ('confirmed', 'Confirmed'), ('failed', 'Failed'), ('refunded', 'Refunded')]
    order = models.ForeignKey(Order, related_name='payments', on_delete=models.CASCADE)
    method = models.CharField(max_length=20, choices=METHODS)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    transaction_id = models.CharField(max_length=160, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    proof_url = models.URLField(max_length=1000, blank=True)
    payer_phone = models.CharField(max_length=40, blank=True)
    confirmed_by = models.BigIntegerField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = 'ecommerce_payment'
        ordering = ('-created_at',)


class Shipment(TimeStampedModel):
    order = models.ForeignKey(Order, related_name='shipments', on_delete=models.CASCADE)
    carrier = models.CharField(max_length=120, blank=True)
    tracking_number = models.CharField(max_length=160, blank=True, db_index=True)
    tracking_url = models.URLField(max_length=1000, blank=True)
    status = models.CharField(max_length=80, default='preparing')
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ecommerce_shipment'
        ordering = ('-created_at',)


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, related_name='history', on_delete=models.CASCADE)
    status = models.CharField(max_length=40)
    note = models.CharField(max_length=500, blank=True)
    actor_id = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ecommerce_order_status_history'
        ordering = ('created_at',)


class Review(TimeStampedModel):
    product = models.ForeignKey(Product, related_name='reviews', on_delete=models.CASCADE)
    customer_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    customer_name = models.CharField(max_length=160)
    rating = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    is_approved = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = 'ecommerce_review'
        ordering = ('-created_at',)


class CommerceNotification(TimeStampedModel):
    KINDS = [('order', 'Order'), ('payment', 'Payment'), ('inventory', 'Inventory'), ('import', 'Import'), ('system', 'System')]
    kind = models.CharField(max_length=20, choices=KINDS, default='system')
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    link = models.CharField(max_length=500, blank=True)
    customer_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    admin_only = models.BooleanField(default=False, db_index=True)
    is_read = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = 'ecommerce_notification'
        ordering = ('-created_at',)


class ImportJob(TimeStampedModel):
    STATUS_CHOICES = [('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')]
    filename = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='processing')
    total_rows = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    created_by = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'ecommerce_import_job'
        ordering = ('-created_at',)


class Book(TimeStampedModel):
    BOOK_TYPES = [
        ('test_paper', 'Test Paper'), ('job_solution', 'Job Solution'),
        ('admission_guide', 'Admission Guide'), ('academic_guide', 'Academic Guide'),
        ('teacher_guide', 'Teacher Guide'), ('textbook', 'Textbook'),
        ('grammar', 'Grammar'), ('story', 'Story / Fiction'),
        ('literature', 'Literature'), ('writer_book', "Writer's Book"),
        ('reference', 'Reference'), ('creative', 'Creative / Essay'), ('other', 'Other'),
    ]
    AUDIENCES = [
        ('student', 'Students'), ('job_seeker', 'Job Seekers'),
        ('teacher', 'Teachers'), ('children', 'Children'), ('general', 'General Readers'),
    ]
    SOURCE_TYPES = [
        ('question_sets', 'Created from question sets'),
        ('exam_sets', 'Created from exam sets'),
        ('uploaded', 'Uploaded publication'), ('manual', 'Written manually'),
    ]
    STATUS_CHOICES = [('draft', 'Draft'), ('review', 'In review'), ('published', 'Published'), ('archived', 'Archived')]

    product = models.OneToOneField(Product, null=True, blank=True, related_name='book_record', on_delete=models.SET_NULL)
    title = models.CharField(max_length=255)
    title_bn = models.CharField(max_length=255, blank=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    subtitle = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    author = models.CharField(max_length=255, blank=True)
    editor = models.CharField(max_length=255, blank=True)
    publisher = models.CharField(max_length=255, default='Cheradip')
    isbn = models.CharField(max_length=32, blank=True, db_index=True)
    language = models.CharField(max_length=80, default='Bangla', db_index=True)
    edition = models.CharField(max_length=100, blank=True)
    publication_year = models.PositiveSmallIntegerField(null=True, blank=True)
    page_count = models.PositiveIntegerField(default=0)
    book_type = models.CharField(max_length=40, choices=BOOK_TYPES, default='other', db_index=True)
    audience = models.CharField(max_length=30, choices=AUDIENCES, default='student', db_index=True)
    source_type = models.CharField(max_length=30, choices=SOURCE_TYPES, default='uploaded')
    source_config = models.JSONField(default=dict, blank=True, help_text='Question/exam set IDs, curriculum filters, section order and generation options.')
    cover_image = models.FileField(upload_to='ebooks/covers/', blank=True)
    wide_cover_image = models.FileField(upload_to='ebooks/covers/wide/', blank=True)
    cover_design = models.JSONField(default=dict, blank=True, help_text='Smart cover colours, title placement and logo settings.')
    preview_text = models.TextField(blank=True)
    video_url = models.URLField(max_length=1000, blank=True)
    digital_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    compare_at_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    hard_copy_available = models.BooleanField(default=False, db_index=True)
    hard_copy_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    hard_copy_quantity = models.PositiveIntegerField(default=0)
    weight_grams = models.PositiveIntegerField(default=0)
    featured = models.BooleanField(default=False, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    tags = models.CharField(max_length=1000, blank=True)
    created_by = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'ecommerce_book'
        ordering = ('-featured', '-created_at')
        indexes = [models.Index(fields=['status', 'book_type']), models.Index(fields=['audience', 'language'])]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title) or f'book-{uuid.uuid4().hex[:12]}'
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class BookAsset(TimeStampedModel):
    ASSET_TYPES = [
        ('ebook', 'eBook'), ('sample', 'Sample'), ('video', 'Video'),
        ('audio', 'Audio'), ('worksheet', 'Worksheet'), ('supplement', 'Supplement'),
    ]
    FORMATS = [
        ('pdf', 'PDF'), ('doc', 'DOC'), ('docx', 'DOCX'), ('html', 'HTML'),
        ('epub', 'EPUB'), ('txt', 'Text'), ('mp4', 'MP4'), ('webm', 'WebM'),
        ('mp3', 'MP3'), ('url', 'External URL'), ('other', 'Other'),
    ]

    book = models.ForeignKey(Book, related_name='assets', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    asset_type = models.CharField(max_length=20, choices=ASSET_TYPES, default='ebook')
    file_format = models.CharField(max_length=20, choices=FORMATS, default='pdf')
    file = models.FileField(upload_to='ebooks/files/', blank=True)
    external_url = models.URLField(max_length=1000, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    is_downloadable = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'ecommerce_book_asset'
        ordering = ('sort_order', 'id')

    def save(self, *args, **kwargs):
        if self.file and not self.file_size:
            self.file_size = getattr(self.file, 'size', 0) or 0
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.book.title} - {self.title}'


class BookBuildJob(TimeStampedModel):
    OUTPUT_FORMATS = [('pdf', 'PDF'), ('docx', 'DOCX'), ('html', 'HTML'), ('epub', 'EPUB')]
    STATUS_CHOICES = [('queued', 'Queued'), ('building', 'Building'), ('completed', 'Completed'), ('failed', 'Failed')]

    book = models.ForeignKey(Book, related_name='build_jobs', on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued', db_index=True)
    output_format = models.CharField(max_length=12, choices=OUTPUT_FORMATS, default='pdf')
    source_config = models.JSONField(default=dict, blank=True)
    progress = models.PositiveSmallIntegerField(default=0)
    message = models.TextField(blank=True)
    result_asset = models.ForeignKey(BookAsset, null=True, blank=True, related_name='build_results', on_delete=models.SET_NULL)
    created_by = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'ecommerce_book_build_job'
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.book.title} - {self.output_format} - {self.status}'

