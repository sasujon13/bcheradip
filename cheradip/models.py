import datetime as dt

from django.contrib.auth.models import Group as AuthGroup, Permission
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.core.validators import MinValueValidator

# ==============================================================================
# FIELDS (DB drivers may return datetime as str; ensure we always have datetime)
# ==============================================================================

class DateTimeFieldSafeTZ(models.DateTimeField):
    """
    DateTimeField that coerces string values from the DB to datetime.
    Fixes 'str' object has no attribute 'utcoffset' when MySQL/PyMySQL returns
    DATETIME columns as strings and code (e.g. timezone.is_aware) expects datetime.
    """

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        if isinstance(value, dt.datetime):
            return value
        if isinstance(value, str):
            parsed = parse_datetime(value)
            if parsed is not None:
                from django.conf import settings
                if getattr(settings, 'USE_TZ', False) and not timezone.is_aware(parsed):
                    return timezone.make_aware(parsed, timezone.get_default_timezone())
                return parsed
        return value


# ==============================================================================
# COUNTRY & LOCATION
# ==============================================================================

class Country(models.Model):
    """Country model (ISO codes, phone code, display order). PK is country_code."""
    country_code = models.CharField(max_length=2, primary_key=True, db_index=True)
    country_code_alpha3 = models.CharField(max_length=3, blank=True, null=True)
    country_code_numeric = models.CharField(max_length=3, blank=True, null=True)
    country_name = models.CharField(max_length=60)
    country_name_native = models.CharField(max_length=60, blank=True, null=True)
    country_name_official = models.CharField(max_length=100, blank=True, null=True)
    flag_emoji = models.CharField(max_length=10, blank=True, null=True)
    flag_url = models.URLField(max_length=255, blank=True, null=True)
    phone_code = models.CharField(max_length=5)
    phone_code_numeric = models.IntegerField(blank=True, null=True)
    phone_format = models.CharField(max_length=30, blank=True, null=True)
    phone_length_min = models.IntegerField(default=10)
    phone_length_max = models.IntegerField(default=10)
    continent = models.CharField(max_length=20, blank=True, null=True)
    region = models.CharField(max_length=30, blank=True, null=True)
    capital = models.CharField(max_length=50, blank=True, null=True)
    currency_code = models.CharField(max_length=3, blank=True, null=True)
    currency_symbol = models.CharField(max_length=10, blank=True, null=True)
    language_codes = models.JSONField(blank=True, null=True)
    timezone = models.CharField(max_length=50, blank=True, null=True)
    time_display = models.CharField(max_length=20, blank=True, null=True)
    display_order = models.IntegerField(default=100)
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = DateTimeFieldSafeTZ(auto_now_add=True)
    updated_at = DateTimeFieldSafeTZ(auto_now=True)

    class Meta:
        db_table = 'cheradip_country'
        verbose_name_plural = 'Countries'
        ordering = ['display_order', 'country_name']
        indexes = [
            models.Index(fields=['country_code']),
            models.Index(fields=['country_name']),
            models.Index(fields=['phone_code']),
            models.Index(fields=['is_featured', 'display_order']),
            models.Index(fields=['continent']),
        ]

    def __str__(self):
        return self.country_name or self.country_code


class Location(models.Model):
    """Address/location (country, division, district, thana, local_address)."""
    id = models.AutoField(primary_key=True)
    country = models.ForeignKey(
        Country,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='locations',
        db_index=True,
    )
    division = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    district = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    thana = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    local_address = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        db_table = 'cheradip_location'
        ordering = ['country', 'division', 'district', 'thana']
        indexes = [
            models.Index(fields=['division', 'district']),
        ]

    def __str__(self):
        parts = [self.division, self.district, self.thana, self.local_address]
        return ', '.join(p for p in parts if p) or (self.country_id or 'N/A')


# ==============================================================================
# E-COMMERCE MODELS
# ==============================================================================

class Item(models.Model):
    """Product/Item model for e-commerce"""
    SIZE_CHOICES = [
        ('nctb', 'NCTB'),
        ('book', 'Book'),
        ('guide', 'Guide'),
        ('cheradip', 'Cheradip'),
    ]
    PAYMENT_CHOICES = [
        ('cod', 'Cash on Delivery'),
        ('bkash', 'bKash'),
        ('nagad', 'Nagad'),
        ('dbbl', 'DBBL'),
        ('other', 'Other'),
    ]
    TYPE_CHOICES = [
        ('science', 'Science'),
        ('business', 'Business'),
        ('humanities', 'Humanities'),
        ('compulsory', 'Compulsory'),
        ('sac', 'SAC'),
        ('ac', 'AC'),
        ('sc', 'SC'),
    ]
    PRODUCT_TYPE_CHOICES = [
        ('package', 'Education Package'),
        ('book', 'Book'),
        ('service', 'Question-making / Service'),
        ('other', 'Other'),
    ]

    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=4, unique=True, null=True, blank=True, db_index=True)
    name = models.CharField(max_length=63, null=True, blank=True)
    bangla_name = models.CharField(max_length=63, null=True, blank=True)
    size = models.CharField(max_length=14, choices=SIZE_CHOICES, null=True, blank=True)
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    love = models.BooleanField(default=False)
    add_to_cart = models.BooleanField(default=False)
    in_stock = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    price = models.DecimalField(max_digits=10, decimal_places=0, null=True, blank=True, validators=[MinValueValidator(0)])
    discount = models.DecimalField(max_digits=2, decimal_places=0, default=0, validators=[MinValueValidator(0)])
    quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    image = models.ImageField(upload_to='images/items/', null=True, blank=True)
    videos = models.URLField(blank=True, null=True)
    supplier = models.CharField(max_length=54, null=True, blank=True)
    types = models.CharField(max_length=15, choices=TYPE_CHOICES, default="humanities")
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPE_CHOICES, default='other', blank=True, db_index=True)
    reviews = models.TextField(null=True, blank=True, default="Rated By @Author")
    ratings = models.DecimalField(max_digits=3, decimal_places=2, default=5.00, validators=[MinValueValidator(0)])
    shipping = models.TextField(null=True, blank=True, default="NA")
    payment_method = models.CharField(max_length=28, choices=PAYMENT_CHOICES, default="bkash")
    details = models.TextField(null=True, blank=True, default="NA")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cheradip_items'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['types']),
            models.Index(fields=['name']),
            models.Index(fields=['product_type']),
        ]

    def __str__(self):
        return self.name or f"Item #{self.id}"


class Transaction(models.Model):
    """Payment Transaction model"""
    PAYMENT_METHODS = [
        ('bkash', 'bKash'),
        ('nagad', 'Nagad'),
        ('dbbl', 'DBBL'),
        ('rocket', 'Rocket'),
        ('cash', 'Cash'),
    ]

    id = models.AutoField(primary_key=True)
    trxid = models.CharField(max_length=31, unique=True, db_index=True)
    username = models.CharField(max_length=11, null=True, blank=True, db_index=True)
    paidFrom = models.CharField(max_length=31, default='', blank=True)
    Paid = models.DecimalField(max_digits=10, decimal_places=0, null=True, blank=True, validators=[MinValueValidator(0)])
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='bkash')
    status = models.CharField(max_length=20, default='pending', choices=[
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cheradip_transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['trxid']),
            models.Index(fields=['username']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"Transaction {self.trxid}"


class OrderDetail(models.Model):
    """Order Detail/Line Item model"""
    id = models.AutoField(primary_key=True)
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_details')
    SN = models.IntegerField(default=0)
    Name = models.CharField(max_length=127)
    Image = models.URLField(blank=True, null=True)
    Weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    Price = models.DecimalField(max_digits=10, decimal_places=0, null=True, blank=True, validators=[MinValueValidator(0)])
    Quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    Discount = models.DecimalField(max_digits=9, decimal_places=0, null=True, blank=True, validators=[MinValueValidator(0)])
    Total = models.DecimalField(max_digits=10, decimal_places=0, null=True, blank=True, validators=[MinValueValidator(0)])
    GrandTotal = models.DecimalField(max_digits=10, decimal_places=0, null=True, blank=True, validators=[MinValueValidator(0)])
    Paid = models.DecimalField(max_digits=10, decimal_places=0, null=True, blank=True, validators=[MinValueValidator(0)])
    Due = models.DecimalField(max_digits=10, decimal_places=0, null=True, blank=True)
    ShipingCost = models.DecimalField(max_digits=8, decimal_places=0, null=True, blank=True, validators=[MinValueValidator(0)], default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cheradip_orderdetail'
        ordering = ['SN']
        indexes = [
            models.Index(fields=['item']),
        ]

    def __str__(self):
        return f"Order Detail: {self.Name}"


# ==============================================================================
# CUSTOMER (AUTH USER)
# ==============================================================================

class CustomerManager(BaseUserManager):
    """Custom User Manager for Customer model"""

    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("The Mobile Number must be set")
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(username, password, **extra_fields)


class Customer(AbstractBaseUser, PermissionsMixin):
    """Customer/User model - Custom User Model"""
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Common', 'Common'),
    ]
    GROUP_CHOICES = [
        ('Science', 'Science'),
        ('Business Studies', 'Business Studies'),
        ('Humanities', 'Humanities'),
    ]
    TYPE_CHOICES = [
        ('Teacher', 'Teacher'),
        ('Student', 'Student'),
        ('JobSeeker', 'Job Seeker'),
    ]

    acctype = models.CharField(max_length=12, choices=TYPE_CHOICES, default="Student")
    username = models.CharField(max_length=15, unique=True, db_index=True)
    password = models.CharField(max_length=128)
    fullName = models.CharField(max_length=31)
    group = models.CharField(max_length=30, blank=True, default="Science")
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, default='')
    country_code = models.CharField(max_length=2, blank=True, null=True, db_index=True)
    date_of_birth = models.DateField(blank=True, null=True)
    class_name = models.CharField(max_length=20, blank=True, null=True)
    department = models.CharField(max_length=50, blank=True, null=True)
    teacher_level = models.CharField(max_length=20, blank=True, null=True)
    teacher_subject_code = models.CharField(max_length=10, blank=True, null=True)
    teacher_department_code = models.CharField(max_length=20, blank=True, null=True)
    teacher_department_name = models.CharField(max_length=200, blank=True, null=True)
    division = models.CharField(max_length=31, blank=True, default='')
    district = models.CharField(max_length=31, blank=True, default='')
    thana = models.CharField(max_length=31, blank=True, default='')
    union = models.CharField(max_length=31, blank=True, default='')
    village = models.CharField(max_length=255, blank=True, default='')
    email = models.EmailField(blank=True, null=True)
    phone_alternate = models.CharField(max_length=11, blank=True, null=True)
    whatsapp_apikey = models.CharField(max_length=255, blank=True, null=True)
    settings = models.JSONField(blank=True, null=True, default=dict, help_text='User preferences as JSON, e.g. export_format: both|pdf|docx')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomerManager()
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ['fullName']

    groups = models.ManyToManyField(AuthGroup, related_name="customer_set", blank=True)
    user_permissions = models.ManyToManyField(
        Permission, related_name="customer_set", blank=True
    )

    class Meta:
        db_table = 'cheradip_customers'
        ordering = ['-date_joined']
        indexes = [
            models.Index(fields=['username']),
            models.Index(fields=['email']),
            models.Index(fields=['acctype']),
            models.Index(fields=['division', 'district']),
        ]

    def __str__(self):
        return f"{self.fullName} ({self.username})"

    def get_full_name(self):
        return self.fullName

    def get_short_name(self):
        return self.fullName.split()[0] if self.fullName else self.username


class CustomerToken(models.Model):
    """Authentication Token for Customer"""
    key = models.CharField("Key", max_length=40, primary_key=True)
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='cheradip_customer_token')
    created = models.DateTimeField("Created", default=timezone.now, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'cheradip_customer_tokens'
        ordering = ['-created']
        indexes = [
            models.Index(fields=['key']),
            models.Index(fields=['customer', 'created']),
        ]

    def __str__(self):
        return f"Token for {self.customer.username}"


class CreatedQuestionSet(models.Model):
    """Saved question set: name + counter (e.g. Subject_Chapter_1_2), question header, and questions JSON. User can rename."""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='created_question_sets', db_index=True)
    name = models.CharField(max_length=200, help_text='Display/save name; user can rename')
    question_header = models.CharField(max_length=255, blank=True)
    questions = models.JSONField(default=list, help_text='List of question objects {question, option_1, ...}')
    layout_settings = models.JSONField(
        default=dict,
        blank=True,
        help_text='Optional layout from creator: pageSize, margins, columns, gap, divider, padding, etc.',
    )
    counter = models.PositiveIntegerField(default=1, help_text='Per-customer sequence for unique filename (name_counter)')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cheradip_created_question_sets'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer', 'counter']),
        ]

    def __str__(self):
        return f"{self.name}_{self.counter} ({self.customer.username})"


class PendingQuestion(models.Model):
    """User-submitted question; pending until approved, then inserted into HSC subject question table with qid."""
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [(STATUS_PENDING, 'Pending'), (STATUS_APPROVED, 'Approved'), (STATUS_REJECTED, 'Rejected')]

    level_tr = models.CharField(max_length=100, blank=True)
    class_level = models.CharField(max_length=50, blank=True)
    subject_tr = models.CharField(max_length=255)
    chapter_no = models.CharField(max_length=50, blank=True)
    chapter = models.CharField(max_length=255)
    topic_no = models.CharField(max_length=50, blank=True)
    topic = models.CharField(max_length=255)
    question = models.TextField()
    option_1 = models.CharField(max_length=500, blank=True)
    option_2 = models.CharField(max_length=500, blank=True)
    option_3 = models.CharField(max_length=500, blank=True)
    option_4 = models.CharField(max_length=500, blank=True)
    answer = models.CharField(max_length=500, blank=True)
    explanation = models.TextField(blank=True)
    explanation2 = models.TextField(blank=True)
    explanation3 = models.TextField(blank=True)
    type = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_qid = models.CharField(max_length=64, blank=True, help_text='qid assigned when approved')

    class Meta:
        db_table = 'cheradip_pending_questions'
        ordering = ['-created_at']

    def __str__(self):
        return f"PendingQuestion {self.id} ({self.subject_tr} / {self.chapter} / {self.topic})"


# ==============================================================================
# NOTIFICATION & JSON DATA
# ==============================================================================

class Notification(models.Model):
    """Notification model – table cheradip_notification."""
    id = models.BigAutoField(primary_key=True)
    text = models.TextField(null=True, blank=True)
    link = models.URLField(max_length=512, null=True, blank=True)

    class Meta:
        db_table = 'cheradip_notification'

    def __str__(self):
        return f"Notification: {(self.text or '')[:50]}"


class JsonData(models.Model):
    """JSON Data storage model for flexible data storage"""
    id = models.AutoField(primary_key=True)
    data = models.JSONField()
    data_type = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cheradip_json_data'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['data_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"JSON Data #{self.id} - Type: {self.data_type or 'N/A'}"


# ==============================================================================
# JOB DB MODELS (cheradip_job) – NTRCA / institutes / tokens
# Tables created by ensure_job or import_to_job; managed=False.
# ==============================================================================

class _MeritBase(models.Model):
    """Base fields for merit5/merit6/merit7 (same structure)."""
    id = models.AutoField(primary_key=True)
    Code = models.BigIntegerField()
    Name = models.CharField(max_length=255)
    Batch = models.BigIntegerField()
    Roll = models.BigIntegerField()
    Mark = models.BigIntegerField()
    Rank = models.BigIntegerField()
    SL = models.BigIntegerField()
    Subject = models.CharField(max_length=127)

    class Meta:
        abstract = True


class Merit5(_MeritBase):
    class Meta:
        db_table = 'cheradip_merit5'
        managed = False


class Merit6(_MeritBase):
    class Meta:
        db_table = 'cheradip_merit6'
        managed = False


class Merit7(_MeritBase):
    class Meta:
        db_table = 'cheradip_merit7'
        managed = False


class _VacancyBase(models.Model):
    VPID = models.BigIntegerField(primary_key=True)
    EIIN = models.BigIntegerField()
    Name = models.CharField(max_length=255)
    District = models.CharField(max_length=255)
    Thana = models.CharField(max_length=255)
    Designation = models.CharField(max_length=255)
    Subject = models.CharField(max_length=255)
    Vacancy = models.IntegerField()
    Type = models.CharField(max_length=15)
    Status = models.CharField(max_length=31)

    class Meta:
        abstract = True


class Vacancy5(_VacancyBase):
    class Meta:
        db_table = 'cheradip_vacancy5'
        managed = False


class Vacancy6(_VacancyBase):
    class Meta:
        db_table = 'cheradip_vacancy6'
        managed = False


class Vacancy7(_VacancyBase):
    class Meta:
        db_table = 'cheradip_vacancy7'
        managed = False


class Recommend5(models.Model):
    id = models.AutoField(primary_key=True)
    EIIN = models.BigIntegerField(null=True, blank=True)
    District = models.CharField(max_length=127, null=True, blank=True)
    Thana = models.CharField(max_length=127, null=True, blank=True)
    Designation = models.CharField(max_length=255, null=True, blank=True)
    Post = models.CharField(max_length=255, null=True, blank=True, db_column='Batch')
    Merit = models.CharField(max_length=63, null=True, blank=True)
    Roll = models.BigIntegerField(null=True, blank=True)
    Name = models.CharField(max_length=255, null=True, blank=True)
    Code = models.IntegerField(null=True, blank=True)
    Mark = models.IntegerField(null=True, blank=True)
    Rank = models.IntegerField(null=True, blank=True)
    Serial = models.IntegerField(null=True, blank=True)
    Subject = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'cheradip_recommend5'
        managed = False


class Recommend6(models.Model):
    id = models.AutoField(primary_key=True)
    EIIN = models.BigIntegerField(null=True, blank=True)
    District = models.CharField(max_length=127, null=True, blank=True)
    Thana = models.CharField(max_length=127, null=True, blank=True)
    Designation = models.CharField(max_length=255, null=True, blank=True)
    Post = models.CharField(max_length=255, null=True, blank=True, db_column='Batch')
    Merit = models.CharField(max_length=63, null=True, blank=True)
    Roll = models.BigIntegerField(null=True, blank=True)
    Name = models.CharField(max_length=255, null=True, blank=True)
    Code = models.IntegerField(null=True, blank=True)
    Mark = models.IntegerField(null=True, blank=True)
    Rank = models.IntegerField(null=True, blank=True)
    Serial = models.IntegerField(null=True, blank=True)
    Subject = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'cheradip_recommend6'
        managed = False


class Recommend7(models.Model):
    id = models.AutoField(primary_key=True)
    EIIN = models.BigIntegerField(null=True, blank=True)
    District = models.CharField(max_length=127, null=True, blank=True)
    Thana = models.CharField(max_length=127, null=True, blank=True)
    Designation = models.CharField(max_length=255, null=True, blank=True)
    Post = models.CharField(max_length=255, null=True, blank=True, db_column='Batch')
    Merit = models.CharField(max_length=63, null=True, blank=True)
    Roll = models.BigIntegerField(null=True, blank=True)
    Name = models.CharField(max_length=255, null=True, blank=True)
    Code = models.IntegerField(null=True, blank=True)
    Mark = models.IntegerField(null=True, blank=True)
    Rank = models.IntegerField(null=True, blank=True)
    Serial = models.IntegerField(null=True, blank=True)
    Subject = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'cheradip_recommend7'
        managed = False


class Banbeis(models.Model):
    id = models.AutoField(primary_key=True)
    EIIN = models.BigIntegerField()
    Name = models.CharField(max_length=255, null=True, blank=True)
    District = models.CharField(max_length=255, null=True, blank=True)
    Thana = models.CharField(max_length=255, null=True, blank=True)
    Rejion = models.CharField(max_length=255, null=True, blank=True)
    PostOffice = models.CharField(max_length=127, null=True, blank=True)
    PostCode = models.CharField(max_length=7, null=True, blank=True)
    WardNo = models.CharField(max_length=7, null=True, blank=True)
    Mouza = models.CharField(max_length=127, null=True, blank=True)
    InstituteType = models.CharField(max_length=127, null=True, blank=True)
    EducationLevels = models.CharField(max_length=255, null=True, blank=True)
    SSCDepts = models.CharField(max_length=255, null=True, blank=True)
    HSCDepts = models.CharField(max_length=255, null=True, blank=True)
    Linked = models.TextField(null=True, blank=True)
    MPO = models.CharField(max_length=255, null=True, blank=True)
    PreStats = models.TextField(null=True, blank=True)
    Record = models.TextField(null=True, blank=True)
    Record2 = models.TextField(null=True, blank=True)
    Contact = models.CharField(max_length=255, null=True, blank=True)
    GovtStatus = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'cheradip_banbeis'
        managed = False


class Institutes(models.Model):
    id = models.IntegerField(null=True, blank=True)
    mobile = models.CharField(max_length=15, null=True, blank=True)
    mobileAlternate = models.CharField(max_length=15, null=True, blank=True)
    instituteName = models.CharField(max_length=255, null=True, blank=True)
    instituteNameBn = models.CharField(max_length=255, null=True, blank=True)
    eiinNo = models.CharField(max_length=15, primary_key=True)
    year = models.IntegerField(null=True, blank=True)
    divisionName = models.CharField(max_length=100, null=True, blank=True)
    divisionNameBn = models.CharField(max_length=100, null=True, blank=True)
    districtName = models.CharField(max_length=100, null=True, blank=True)
    districtNameBn = models.CharField(max_length=100, null=True, blank=True)
    thanaName = models.CharField(max_length=100, null=True, blank=True)
    thanaNameBn = models.CharField(max_length=100, null=True, blank=True)
    instituteTypeName = models.CharField(max_length=100, null=True, blank=True)
    instituteTypeNameBn = models.CharField(max_length=100, null=True, blank=True)
    submissionDate = models.DateField(null=True, blank=True)
    mouzaName = models.CharField(max_length=255, null=True, blank=True)
    mouzaNameBn = models.CharField(max_length=255, null=True, blank=True)
    email = models.CharField(max_length=100, null=True, blank=True)
    isGovt = models.BooleanField(null=True, blank=True)

    class Meta:
        db_table = 'cheradip_institutes'
        managed = False


class Token(models.Model):
    """NTRCA token – table cheradip_tokens. Status: 0=unused, 1=used."""
    id = models.AutoField(primary_key=True)
    Token = models.BigIntegerField()
    Counter = models.CharField(max_length=255, null=True, blank=True)
    Status = models.IntegerField(default=0)  # 0=not used, 1=used

    class Meta:
        db_table = 'cheradip_tokens'
        managed = False


class TrxManagement(models.Model):
    """
    Payment / SMS-parse ingest (e.g. Nagad). Lives in default DB ``cheradip_cheradip``.
    Posted as JSON to ``/api/trxid/``.
    """

    id = models.AutoField(primary_key=True)
    media = models.CharField(max_length=64)
    received_amount = models.DecimalField(max_digits=14, decimal_places=4)
    currency = models.CharField(max_length=16)
    sender_contact = models.CharField(max_length=32)
    trxid = models.CharField(max_length=128, db_index=True)
    transaction_date = models.CharField(max_length=32)
    transaction_time = models.CharField(max_length=16)
    confidence = models.DecimalField(max_digits=7, decimal_places=5)
    status = models.IntegerField(default=0)
    token = models.IntegerField(default=0)

    class Meta:
        db_table = 'cheradip_trxmanagement'
        ordering = ['-id']

    def __str__(self):
        return f"{self.trxid} ({self.media})"
