import datetime as dt

from django.contrib.auth.models import AbstractUser, Group as AuthGroup, Permission
from django.utils.translation import gettext as _
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
# COUNTRY & LOCATION (must be defined first for views/serializers imports)
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
    """Address/location (country, division, district, thana, local_address). Referenced by Customer, Order, etc."""
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
    
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # Item Details
    code = models.CharField(max_length=4, unique=True, null=True, blank=True, db_index=True)
    name = models.CharField(max_length=63, null=True, blank=True)
    bangla_name = models.CharField(max_length=63, null=True, blank=True)
    size = models.CharField(max_length=14, choices=SIZE_CHOICES, null=True, blank=True)
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    
    # Status Fields
    love = models.BooleanField(default=False)
    add_to_cart = models.BooleanField(default=False)
    in_stock = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    
    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=0, null=True, blank=True, validators=[MinValueValidator(0)])
    discount = models.DecimalField(max_digits=2, decimal_places=0, default=0, validators=[MinValueValidator(0)])
    quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    
    # Media
    image = models.ImageField(upload_to='images/items/', null=True, blank=True)
    videos = models.URLField(blank=True, null=True)
    
    # Additional Info
    supplier = models.CharField(max_length=54, null=True, blank=True)
    types = models.CharField(max_length=15, choices=TYPE_CHOICES, default="humanities")
    reviews = models.TextField(null=True, blank=True, default="Rated By @Author")
    ratings = models.DecimalField(max_digits=3, decimal_places=2, default=5.00, validators=[MinValueValidator(0)])
    shipping = models.TextField(null=True, blank=True, default="NA")
    payment_method = models.CharField(max_length=28, choices=PAYMENT_CHOICES, default="bkash")
    details = models.TextField(null=True, blank=True, default="NA")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'items'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['types']),
            models.Index(fields=['name']),
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
    
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # Transaction Details
    trxid = models.CharField(max_length=31, unique=True, db_index=True)
    username = models.CharField(max_length=11, null=True, blank=True, db_index=True)
    paidFrom = models.CharField(max_length=31, default='', blank=True)
    Paid = models.DecimalField(max_digits=10, decimal_places=0, null=True, blank=True, validators=[MinValueValidator(0)])
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='bkash')
    
    # Status
    status = models.CharField(max_length=20, default='pending', choices=[
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ])
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'transactions'
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
    
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # Foreign Keys
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_details')
    
    # Order Detail Information
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
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'order_details'
        ordering = ['SN']
        indexes = [
            models.Index(fields=['item']),
        ]
    
    def __str__(self):
        return f"Order Detail: {self.Name}"


class Order(models.Model):
    """Order model - Active orders"""
    ORDER_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    PAYMENT_METHODS = [
        ('cod', 'Cash on Delivery'),
        ('bkash', 'bKash'),
        ('nagad', 'Nagad'),
        ('dbbl', 'DBBL'),
        ('other', 'Other'),
    ]
    
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # Foreign Keys
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    
    # Customer Information
    username = models.CharField(max_length=11, db_index=True)
    fullName = models.CharField(max_length=31, null=True, blank=True)
    gender = models.CharField(max_length=10, null=True, blank=True)
    altMobileNo = models.CharField(max_length=11, null=True, blank=True)
    
    # Address Information
    division = models.CharField(max_length=31, null=True, blank=True)
    district = models.CharField(max_length=31, null=True, blank=True)
    thana = models.CharField(max_length=31, null=True, blank=True)
    union = models.CharField(max_length=31, null=True, blank=True)
    village = models.TextField(max_length=255, null=True, blank=True)
    
    # Order Information
    paymentMethod = models.CharField(max_length=31, choices=PAYMENT_METHODS, null=True, blank=True)
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    shipped = models.BooleanField(default=False)
    
    # Relationships
    orderDetails = models.ManyToManyField(OrderDetail, blank=True, related_name='orders')
    transactions = models.ManyToManyField(Transaction, blank=True, related_name='orders')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['username']),
            models.Index(fields=['status']),
            models.Index(fields=['customer', 'created_at']),
        ]
    
    def __str__(self):
        return f"Order #{self.id} - {self.username}"


class Ordered(models.Model):
    """Completed/Delivered Orders model"""
    ORDER_STATUS = [
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
    ]
    
    PAYMENT_METHODS = [
        ('cod', 'Cash on Delivery'),
        ('bkash', 'bKash'),
        ('nagad', 'Nagad'),
        ('dbbl', 'DBBL'),
        ('other', 'Other'),
    ]
    
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # Foreign Keys
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='ordered_items')
    
    # Customer Information
    username = models.CharField(max_length=11, db_index=True)
    fullName = models.CharField(max_length=31, null=True, blank=True)
    gender = models.CharField(max_length=10, null=True, blank=True)
    altMobileNo = models.CharField(max_length=11, null=True, blank=True)
    
    # Address Information
    division = models.CharField(max_length=31, null=True, blank=True)
    district = models.CharField(max_length=31, null=True, blank=True)
    thana = models.CharField(max_length=31, null=True, blank=True)
    union = models.CharField(max_length=31, null=True, blank=True)
    village = models.TextField(max_length=255, null=True, blank=True)
    
    # Order Information
    paymentMethod = models.CharField(max_length=31, choices=PAYMENT_METHODS, null=True, blank=True)
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='delivered')
    shipped = models.BooleanField(default=True)
    
    # Relationships
    orderDetails = models.ManyToManyField(OrderDetail, blank=True, related_name='ordered_items')
    transactions = models.ManyToManyField(Transaction, blank=True, related_name='ordered_items')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'ordered'
        ordering = ['-delivered_at', '-created_at']
        indexes = [
            models.Index(fields=['username']),
            models.Index(fields=['status']),
            models.Index(fields=['customer', 'delivered_at']),
        ]
    
    def __str__(self):
        return f"Ordered #{self.id} - {self.username}"


class Canceled(models.Model):
    """Cancelled Orders model"""
    PAYMENT_METHODS = [
        ('cod', 'Cash on Delivery'),
        ('bkash', 'bKash'),
        ('nagad', 'Nagad'),
        ('dbbl', 'DBBL'),
        ('other', 'Other'),
    ]
    
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # Foreign Keys
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='cancelled_orders')
    
    # Customer Information
    username = models.CharField(max_length=11, db_index=True)
    fullName = models.CharField(max_length=31, null=True, blank=True)
    gender = models.CharField(max_length=10, null=True, blank=True)
    altMobileNo = models.CharField(max_length=11, null=True, blank=True)
    
    # Address Information
    division = models.CharField(max_length=31, null=True, blank=True)
    district = models.CharField(max_length=31, null=True, blank=True)
    thana = models.CharField(max_length=31, null=True, blank=True)
    union = models.CharField(max_length=31, null=True, blank=True)
    village = models.TextField(max_length=255, null=True, blank=True)
    
    # Order Information
    paymentMethod = models.CharField(max_length=31, choices=PAYMENT_METHODS, null=True, blank=True)
    shipped = models.BooleanField(default=False)
    cancellation_reason = models.TextField(null=True, blank=True)
    
    # Relationships
    orderDetails = models.ManyToManyField(OrderDetail, blank=True, related_name='cancelled_orders')
    transactions = models.ManyToManyField(Transaction, blank=True, related_name='cancelled_orders')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'canceled'
        ordering = ['-cancelled_at']
        indexes = [
            models.Index(fields=['username']),
            models.Index(fields=['customer', 'cancelled_at']),
        ]
    
    def __str__(self):
        return f"Cancelled Order #{self.id} - {self.username}"


# ==============================================================================
# USER MANAGEMENT MODELS
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
    
    # Primary Key (inherited from AbstractBaseUser)
    # id is auto-created
    
    # Account Information
    acctype = models.CharField(max_length=12, choices=TYPE_CHOICES, default="Student")
    username = models.CharField(max_length=15, unique=True, db_index=True)
    password = models.CharField(max_length=128)  # This is handled by AbstractBaseUser
    fullName = models.CharField(max_length=31)
    group = models.CharField(max_length=30, blank=True, default="Science")
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default="Male")
    country_code = models.CharField(max_length=2, blank=True, null=True, db_index=True)
    date_of_birth = models.DateField(blank=True, null=True)
    # Student/JobSeeker
    class_name = models.CharField(max_length=20, blank=True, null=True)
    department = models.CharField(max_length=50, blank=True, null=True)
    # Teacher
    teacher_level = models.CharField(max_length=20, blank=True, null=True)
    teacher_subject_code = models.CharField(max_length=10, blank=True, null=True)
    teacher_department_code = models.CharField(max_length=20, blank=True, null=True)
    teacher_department_name = models.CharField(max_length=200, blank=True, null=True)
    # Address Information
    division = models.CharField(max_length=31, blank=True, default='')
    district = models.CharField(max_length=31, blank=True, default='')
    thana = models.CharField(max_length=31, blank=True, default='')
    union = models.CharField(max_length=31, blank=True, default='')
    village = models.CharField(max_length=255, blank=True, default='')
    # Additional Fields
    email = models.EmailField(blank=True, null=True)
    phone_alternate = models.CharField(max_length=11, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    
    # Timestamps (last_login from AbstractBaseUser)
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
    # Primary Key
    key = models.CharField("Key", max_length=40, primary_key=True)
    
    # Foreign Keys
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='cheradip_customer_token')
    
    # Timestamps
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


# ==============================================================================
# EDUCATIONAL CONTENT MODELS
# ==============================================================================

class Group(models.Model):
    """Educational Group model (Science, Business, Humanities)"""
    # Primary Key
    group_code = models.CharField(max_length=1, unique=True, primary_key=True, db_index=True)
    
    # Group Information
    group_name = models.CharField(max_length=50, default="")
    group_name_bn = models.CharField(max_length=50, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'groups'
        ordering = ['group_code']
        indexes = [
            models.Index(fields=['group_code']),
        ]
    
    def __str__(self):
        return f"{self.group_code} - {self.group_name}"


class ClassLevel(models.Model):
    """Class level (e.g. 5, 8, 9-10, 11-12, 13-16) with flags for groups/departments."""
    class_code = models.CharField(max_length=10, primary_key=True, unique=True, db_index=True)
    class_name = models.CharField(max_length=50)
    class_name_bn = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    has_groups = models.BooleanField(default=False)
    has_departments = models.BooleanField(default=False)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'class_levels'
        ordering = ['display_order', 'class_code']
        indexes = [
            models.Index(fields=['class_code']),
            models.Index(fields=['has_groups', 'has_departments']),
        ]

    def __str__(self):
        return f"{self.class_code} - {self.class_name}"


class Department(models.Model):
    """Department (e.g. for 13-16 / university)."""
    dept_code = models.CharField(max_length=20, primary_key=True, unique=True, db_index=True)
    dept_name = models.CharField(max_length=100)
    dept_name_bn = models.CharField(max_length=100, blank=True, null=True)
    dept_name_short = models.CharField(max_length=20, blank=True, null=True)
    faculty = models.CharField(max_length=100, blank=True, null=True, help_text='Faculty name (e.g., Engineering, Arts)')
    faculty_bn = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    degree_type = models.CharField(max_length=50, blank=True, null=True, help_text='e.g., BSc, BA, BBA, MBBS')
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'departments'
        ordering = ['display_order', 'dept_name']
        indexes = [
            models.Index(fields=['dept_code']),
            models.Index(fields=['faculty']),
            models.Index(fields=['is_active', 'display_order']),
        ]

    def __str__(self):
        return f"{self.dept_code} - {self.dept_name}"


class ClassGroupMapping(models.Model):
    """Maps a class level to allowed group codes (comma-separated)."""
    id = models.BigAutoField(primary_key=True, auto_created=True)
    class_level = models.ForeignKey(ClassLevel, on_delete=models.CASCADE, related_name='group_mappings')
    group_codes = models.CharField(max_length=50, help_text='Comma-separated group codes (e.g., S,A,B)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'class_group_mappings'
        unique_together = (('class_level', 'group_codes'),)
        indexes = [
            models.Index(fields=['class_level']),
        ]

    def get_group_list(self):
        """Return list of Group serialized data for group_codes."""
        from .serializers import GroupSerializer
        codes = [c.strip() for c in self.group_codes.split(',') if c.strip()]
        qs = Group.objects.filter(group_code__in=codes).order_by('group_code')
        return GroupSerializer(qs, many=True).data

    def __str__(self):
        return f"{self.class_level_id} -> {self.group_codes}"


class Subject(models.Model):
    """Subject model (e.g., ICT, Physics, Chemistry)"""
    # Primary Key
    subject_code = models.CharField(max_length=4, unique=True, primary_key=True, db_index=True)
    
    # Subject Information
    subject_name = models.CharField(max_length=50, blank=True)
    subject_name_tr = models.CharField(max_length=50, blank=True, null=True)  # copied from cheradip_subject_translated.subject_name
    subject_name_bn = models.CharField(max_length=50, blank=True, null=True)
    
    # Relationships
    groups = models.ManyToManyField(Group, related_name='subjects', db_table='subject_groups')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'subjects'
        ordering = ['subject_code']
        indexes = [
            models.Index(fields=['subject_code']),
        ]
    
    def __str__(self):
        group_codes = ', '.join([group.group_code for group in self.groups.all()])
        return f"{group_codes} {self.subject_code} - {self.subject_name}"


class Chapter(models.Model):
    """Chapter model - Chapters within a Subject"""
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # Foreign Keys
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='chapters', db_index=True)
    
    # Chapter Information
    chapter_no = models.CharField(max_length=2, blank=True, db_index=True)
    chapter_name = models.CharField(max_length=100, blank=True)
    chapter_name_bn = models.CharField(max_length=100, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'chapters'
        ordering = ['subject', 'chapter_no']
        unique_together = ('subject', 'chapter_no')
        indexes = [
            models.Index(fields=['subject', 'chapter_no']),
        ]
    
    def __str__(self):
        return f"{self.subject.subject_code} Chapter {self.chapter_no} - {self.chapter_name}"


class Topic(models.Model):
    """Topic model - Topics within a Chapter"""
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # Foreign Keys
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='topics', db_index=True)
    
    # Topic Information
    topic_no = models.CharField(max_length=2, blank=True, db_index=True)
    topic_name = models.CharField(max_length=100, blank=True)
    topic_name_bn = models.CharField(max_length=100, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'topics'
        ordering = ['chapter', 'topic_no']
        unique_together = ('chapter', 'topic_no')
        indexes = [
            models.Index(fields=['chapter', 'topic_no']),
        ]
    
    def __str__(self):
        return f"{self.chapter.subject.subject_code} Topic {self.topic_no} - {self.topic_name}"


class Institute(models.Model):
    """Institute model - Educational Institutes (MCQ / NTRCA filter)"""
    # Primary Key
    institute_code = models.CharField(max_length=14, unique=True, primary_key=True, db_index=True)
    
    # Institute Information
    institute_name = models.CharField(max_length=127, blank=True, unique=True)
    institute_name_bn = models.CharField(max_length=127, blank=True, null=True)
    institute_type = models.CharField(max_length=127, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'cheradip_institute'
        ordering = ['institute_name']
        indexes = [
            models.Index(fields=['institute_code']),
            models.Index(fields=['institute_name']),
            models.Index(fields=['institute_type']),
        ]
    
    def __str__(self):
        return f"{self.institute_code} - {self.institute_name} ({self.institute_type})"


class Year(models.Model):
    """Year model - Academic Years"""
    # Primary Key
    year_code = models.CharField(max_length=5, unique=True, primary_key=True, db_index=True)
    
    # Year Information
    year_name = models.CharField(max_length=9, blank=True, unique=True)
    year_name_bn = models.CharField(max_length=9, blank=True, null=True)
    start_year = models.IntegerField(null=True, blank=True)
    end_year = models.IntegerField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'years'
        ordering = ['-year_code']
        indexes = [
            models.Index(fields=['year_code']),
        ]
    
    def __str__(self):
        return f"{self.year_code} - {self.year_name}"


def question_image_path(instance, filename):
    """Generate path for question images"""
    return f'images/mcq/{instance.subject.subject_code}/{instance.chapter.chapter_no}/{instance.qid}/{filename}'


class Mcq_ict(models.Model):
    """MCQ/ICT Question model"""
    ANSWER_CHOICES = [
        ('1', 'ক'),
        ('2', 'খ'),
        ('3', 'গ'),
        ('4', 'ঘ'),
    ]
    
    # Primary Key
    qid = models.CharField(max_length=10, unique=True, editable=False, primary_key=True, db_index=True)
    
    # Foreign Keys
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='questions', db_index=True)
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='questions', db_index=True)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='questions', db_index=True)
    
    # Question Content
    uddipok = models.TextField(null=True, blank=True, max_length=1000, help_text="Question context/hint")
    question = models.TextField(max_length=300)
    option1 = models.TextField(max_length=200)
    option2 = models.TextField(max_length=200)
    option3 = models.TextField(max_length=200)
    option4 = models.TextField(max_length=200)
    answer = models.CharField(max_length=1, choices=ANSWER_CHOICES)
    explanation = models.TextField(null=True, blank=True, max_length=1000)
    
    # Images
    img_uddipok = models.ImageField(upload_to=question_image_path, null=True, blank=True)
    img_question = models.ImageField(upload_to=question_image_path, null=True, blank=True)
    img_explanation = models.ImageField(upload_to=question_image_path, null=True, blank=True)
    
    # Relationships
    institutes = models.ManyToManyField(Institute, related_name='questions', blank=True, db_table='mcq_institutes')
    years = models.ManyToManyField(Year, related_name='questions', blank=True, db_table='mcq_years')
    
    # Metadata
    difficulty_level = models.CharField(max_length=20, choices=[
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ], default='medium', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'mcq_ict'
        ordering = ['subject', 'chapter', 'topic', 'qid']
        indexes = [
            models.Index(fields=['qid']),
            models.Index(fields=['subject', 'chapter', 'topic']),
            models.Index(fields=['is_active']),
            models.Index(fields=['difficulty_level']),
        ]
    
    def __str__(self):
        return f"Question {self.qid} ({self.subject.subject_code})"
    
    def save(self, *args, **kwargs):
        if not self.qid:
            # Zero-pad chapter_no and topic_no to ensure they are two digits
            try:
                chapter_no = f'{int(self.chapter.chapter_no):02d}'
                topic_no = f'{int(self.topic.topic_no):02d}'
            except (ValueError, AttributeError):
                chapter_no = self.chapter.chapter_no.zfill(2) if self.chapter.chapter_no else '00'
                topic_no = self.topic.topic_no.zfill(2) if self.topic.topic_no else '00'
            
            # Generate qid as subject_code + chapter_no + topic_no + 3 digit sequence number
            last_question = Mcq_ict.objects.filter(
                subject=self.subject,
                chapter=self.chapter,
                topic=self.topic
            ).order_by('qid').last()
            
            if last_question:
                try:
                    last_qid = int(last_question.qid[-3:])
                    new_qid = f'{last_qid + 1:03d}'
                except ValueError:
                    new_qid = '001'
            else:
                new_qid = '001'
            
            self.qid = f'{self.subject.subject_code}{chapter_no}{topic_no}{new_qid}'
        
        super().save(*args, **kwargs)


# ==============================================================================
# NOTIFICATION MODELS
# ==============================================================================

class Notification(models.Model):
    """Notification model – table cheradip_notification has only: id (bigint), text (longtext), link (varchar 512)."""
    id = models.BigAutoField(primary_key=True)
    text = models.TextField(null=True, blank=True)
    link = models.URLField(max_length=512, null=True, blank=True)

    class Meta:
        db_table = 'cheradip_notification'

    def __str__(self):
        return f"Notification: {(self.text or '')[:50]}"


# ==============================================================================
# JOB/VACANCY MODELS
# ==============================================================================

class Vacancy(models.Model):
    """Vacancy model - General vacancies"""
    VACANCY_TYPES = [
        ('regular', 'Regular'),
        ('temporary', 'Temporary'),
        ('contract', 'Contract'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('filled', 'Filled'),
    ]
    
    # Primary Key
    VPID = models.BigIntegerField(primary_key=True, db_index=True)
    
    # Vacancy Information
    EIIN = models.BigIntegerField(db_index=True)
    Name = models.CharField(max_length=255, db_index=True)
    District = models.CharField(max_length=255, db_index=True)
    Thana = models.CharField(max_length=255)
    Designation = models.CharField(max_length=255)
    Subject = models.CharField(max_length=255)
    Vacancy = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    Type = models.CharField(max_length=15, choices=VACANCY_TYPES, default='regular')
    Status = models.CharField(max_length=31, choices=STATUS_CHOICES, default='open')
    
    # Additional Info
    description = models.TextField(null=True, blank=True)
    salary_range = models.CharField(max_length=100, null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deadline = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'vacancies'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['VPID']),
            models.Index(fields=['EIIN']),
            models.Index(fields=['Status', 'Type']),
            models.Index(fields=['District', 'Thana']),
            models.Index(fields=['Subject']),
        ]
    
    def __str__(self):
        return f"{self.Name} - {self.Designation} ({self.Subject})"


class Vacancy5(models.Model):
    """Vacancy model for Grade 5 positions"""
    VACANCY_TYPES = [
        ('regular', 'Regular'),
        ('temporary', 'Temporary'),
        ('contract', 'Contract'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('filled', 'Filled'),
    ]
    
    # Primary Key
    VPID = models.BigIntegerField(primary_key=True, db_index=True)
    
    # Vacancy Information
    EIIN = models.BigIntegerField(db_index=True)
    Name = models.CharField(max_length=255, db_index=True)
    District = models.CharField(max_length=255, db_index=True)
    Thana = models.CharField(max_length=255)
    Designation = models.CharField(max_length=255)
    Subject = models.CharField(max_length=255)
    Vacancy = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    Type = models.CharField(max_length=15, choices=VACANCY_TYPES, default='regular')
    Status = models.CharField(max_length=31, choices=STATUS_CHOICES, default='open')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deadline = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'vacancies_5'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['VPID']),
            models.Index(fields=['EIIN']),
            models.Index(fields=['Status']),
            models.Index(fields=['District', 'Subject']),
        ]
    
    def __str__(self):
        return f"Grade 5: {self.Name} ({self.Subject})"


class Vacancy6(models.Model):
    """Vacancy model for Grade 6 positions"""
    VACANCY_TYPES = [
        ('regular', 'Regular'),
        ('temporary', 'Temporary'),
        ('contract', 'Contract'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('filled', 'Filled'),
    ]
    
    # Primary Key
    VPID = models.BigIntegerField(primary_key=True, db_index=True)
    
    # Vacancy Information
    EIIN = models.BigIntegerField(db_index=True)
    Name = models.CharField(max_length=255, db_index=True)
    District = models.CharField(max_length=255, db_index=True)
    Thana = models.CharField(max_length=255)
    Designation = models.CharField(max_length=255)
    Subject = models.CharField(max_length=255)
    Vacancy = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    Type = models.CharField(max_length=15, choices=VACANCY_TYPES, default='regular')
    Status = models.CharField(max_length=31, choices=STATUS_CHOICES, default='open')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deadline = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'vacancies_6'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['VPID']),
            models.Index(fields=['EIIN']),
            models.Index(fields=['Status']),
            models.Index(fields=['District', 'Subject']),
        ]
    
    def __str__(self):
        return f"Grade 6: {self.Name} ({self.Subject})"


# ==============================================================================
# MERIT LIST MODELS
# ==============================================================================

class Merit(models.Model):
    """Merit list model - General merit positions"""
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # Merit Information
    Code = models.IntegerField(db_index=True)
    Name = models.CharField(max_length=255, db_index=True)
    Batch = models.IntegerField(db_index=True)
    Roll = models.BigIntegerField(db_index=True)
    Mark = models.IntegerField()
    Rank = models.IntegerField()
    SL = models.IntegerField()
    Subject = models.CharField(max_length=127, db_index=True)
    
    # Additional Info
    EIIN = models.BigIntegerField(null=True, blank=True, db_index=True)
    InstituteName = models.CharField(max_length=255, null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'merits'
        ordering = ['Batch', 'Rank', 'SL']
        indexes = [
            models.Index(fields=['Code']),
            models.Index(fields=['Batch', 'Rank']),
            models.Index(fields=['Roll']),
            models.Index(fields=['Subject', 'Rank']),
            models.Index(fields=['EIIN']),
        ]
        unique_together = ('Batch', 'Roll', 'Subject')
    
    def __str__(self):
        return f"Batch {self.Batch} - Roll {self.Roll} - Mark {self.Mark} - Rank {self.Rank}"


class Merit5(models.Model):
    """Merit list model for Grade 5"""
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # Merit Information
    Code = models.IntegerField(db_index=True)
    Name = models.CharField(max_length=255, db_index=True)
    Batch = models.IntegerField(db_index=True)
    Roll = models.BigIntegerField(db_index=True)
    Mark = models.IntegerField()
    Rank = models.IntegerField()
    SL = models.IntegerField()
    Subject = models.CharField(max_length=127, db_index=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'merits_5'
        ordering = ['Batch', 'Rank', 'SL']
        indexes = [
            models.Index(fields=['Batch', 'Rank']),
            models.Index(fields=['Roll']),
            models.Index(fields=['Subject']),
        ]
        unique_together = ('Batch', 'Roll', 'Subject')
    
    def __str__(self):
        return f"Grade 5 - Batch {self.Batch} - Roll {self.Roll} - Rank {self.Rank}"


class Merit6(models.Model):
    """Merit list model for Grade 6"""
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # Merit Information
    Code = models.IntegerField(db_index=True)
    Name = models.CharField(max_length=255, db_index=True)
    Batch = models.IntegerField(db_index=True)
    Roll = models.BigIntegerField(db_index=True)
    Mark = models.IntegerField()
    Rank = models.IntegerField()
    SL = models.IntegerField()
    Subject = models.CharField(max_length=127, db_index=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'merits_6'
        ordering = ['Batch', 'Rank', 'SL']
        indexes = [
            models.Index(fields=['Batch', 'Rank']),
            models.Index(fields=['Roll']),
            models.Index(fields=['Subject']),
        ]
        unique_together = ('Batch', 'Roll', 'Subject')
    
    def __str__(self):
        return f"Grade 6 - Batch {self.Batch} - Roll {self.Roll} - Rank {self.Rank}"


# ==============================================================================
# RECOMMENDATION MODELS
# ==============================================================================

class Recommend(models.Model):
    """Recommendation model - General recommendations"""
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # Recommendation Information
    EIIN = models.BigIntegerField(db_index=True)
    District = models.CharField(max_length=127, null=True, blank=True, db_index=True)
    Thana = models.CharField(max_length=127, null=True, blank=True)
    Designation = models.CharField(max_length=255, null=True, blank=True)
    Post = models.CharField(max_length=255, null=True, blank=True)
    Batch = models.CharField(max_length=255, null=True, blank=True)
    Merit = models.CharField(max_length=63, null=True, blank=True)
    Roll = models.BigIntegerField(null=True, blank=True, db_index=True)
    Name = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    Code = models.IntegerField(null=True, blank=True)
    Mark = models.IntegerField(null=True, blank=True)
    Rank = models.IntegerField(null=True, blank=True)
    Serial = models.IntegerField(null=True, blank=True)
    Subject = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    
    # Status
    status = models.CharField(max_length=50, default='pending', choices=[
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ])
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'recommendations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['EIIN']),
            models.Index(fields=['Roll']),
            models.Index(fields=['Name']),
            models.Index(fields=['Subject', 'Rank']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Recommendation: {self.Name or 'N/A'} ({self.Roll or 'N/A'})"


class Recommend5(models.Model):
    """Recommendation model for Grade 5"""
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # Recommendation Information
    EIIN = models.BigIntegerField(db_index=True)
    District = models.CharField(max_length=127, null=True, blank=True)
    Thana = models.CharField(max_length=127, null=True, blank=True)
    Designation = models.CharField(max_length=255, null=True, blank=True)
    Batch = models.CharField(max_length=255, null=True, blank=True)
    Merit = models.CharField(max_length=63, null=True, blank=True)
    Roll = models.BigIntegerField(null=True, blank=True, db_index=True)
    Name = models.CharField(max_length=255, null=True, blank=True)
    Code = models.IntegerField(null=True, blank=True)
    Mark = models.IntegerField(null=True, blank=True)
    Rank = models.IntegerField(null=True, blank=True)
    Serial = models.IntegerField(null=True, blank=True)
    Subject = models.CharField(max_length=255, null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'recommendations_5'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['EIIN', 'Roll']),
            models.Index(fields=['Subject']),
        ]
    
    def __str__(self):
        return f"Grade 5 Recommendation: {self.Name or 'N/A'} ({self.Roll or 'N/A'})"


class Recommend6(models.Model):
    """Recommendation model for Grade 6"""
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # Recommendation Information
    EIIN = models.BigIntegerField(db_index=True)
    District = models.CharField(max_length=127, null=True, blank=True)
    Thana = models.CharField(max_length=127, null=True, blank=True)
    Designation = models.CharField(max_length=255, null=True, blank=True)
    Batch = models.CharField(max_length=255, null=True, blank=True)
    Merit = models.CharField(max_length=63, null=True, blank=True)
    Roll = models.BigIntegerField(null=True, blank=True, db_index=True)
    Name = models.CharField(max_length=255, null=True, blank=True)
    Code = models.IntegerField(null=True, blank=True)
    Mark = models.IntegerField(null=True, blank=True)
    Rank = models.IntegerField(null=True, blank=True)
    Serial = models.IntegerField(null=True, blank=True)
    Subject = models.CharField(max_length=255, null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'recommendations_6'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['EIIN', 'Roll']),
            models.Index(fields=['Subject']),
        ]
    
    def __str__(self):
        return f"Grade 6 Recommendation: {self.Name or 'N/A'} ({self.Roll or 'N/A'})"


# ==============================================================================
# INSTITUTE DATA MODELS
# ==============================================================================

class Banbeis(models.Model):
    """BANBEIS (Bangladesh Bureau of Educational Information and Statistics) Institute Data"""
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # Institute Information
    EIIN = models.BigIntegerField(unique=True, db_index=True)
    Name = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    District = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    Thana = models.CharField(max_length=255, null=True, blank=True)
    Rejion = models.CharField(max_length=255, null=True, blank=True)  # Note: Typo in original field name
    PostOffice = models.CharField(max_length=127, null=True, blank=True)
    PostCode = models.CharField(max_length=7, null=True, blank=True)
    WardNo = models.CharField(max_length=7, null=True, blank=True)
    Mouza = models.CharField(max_length=127, null=True, blank=True)
    
    # Institute Details
    InstituteType = models.CharField(max_length=127, null=True, blank=True, db_index=True)
    EducationLevels = models.CharField(max_length=255, null=True, blank=True)
    SSCDepts = models.CharField(max_length=255, null=True, blank=True)
    HSCDepts = models.CharField(max_length=255, null=True, blank=True)
    
    # Additional Information
    Linked = models.TextField(null=True, blank=True)
    MPO = models.CharField(max_length=255, null=True, blank=True)
    PreStats = models.TextField(null=True, blank=True)
    Record = models.TextField(null=True, blank=True)
    Record2 = models.TextField(null=True, blank=True)
    Contact = models.CharField(max_length=255, null=True, blank=True)
    GovtStatus = models.IntegerField(null=True, blank=True, choices=[
        (0, 'Non-Government'),
        (1, 'Government'),
    ])
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'banbeis'
        ordering = ['EIIN']
        indexes = [
            models.Index(fields=['EIIN']),
            models.Index(fields=['Name']),
            models.Index(fields=['District', 'Thana']),
            models.Index(fields=['InstituteType']),
            models.Index(fields=['GovtStatus']),
        ]
    
    def __str__(self):
        return f"EIIN: {self.EIIN} | {self.Name or 'N/A'} | Type: {self.InstituteType or 'N/A'}"


class Institutes(models.Model):
    """Institute model - Detailed institute information"""
    # Primary Key
    eiinNo = models.CharField(max_length=15, primary_key=True, db_index=True)
    
    # Basic Information
    id = models.IntegerField(null=True, blank=True)
    instituteName = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    instituteNameBn = models.CharField(max_length=255, null=True, blank=True)
    
    # Contact Information
    mobile = models.CharField(max_length=15, null=True, blank=True)
    mobileAlternate = models.CharField(max_length=15, null=True, blank=True)
    email = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    
    # Location Information
    year = models.IntegerField(null=True, blank=True)
    divisionName = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    divisionNameBn = models.CharField(max_length=100, null=True, blank=True)
    districtName = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    districtNameBn = models.CharField(max_length=100, null=True, blank=True)
    thanaName = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    thanaNameBn = models.CharField(max_length=100, null=True, blank=True)
    mouzaName = models.CharField(max_length=255, null=True, blank=True)
    mouzaNameBn = models.CharField(max_length=255, null=True, blank=True)
    
    # Institute Details
    instituteTypeName = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    instituteTypeNameBn = models.CharField(max_length=100, null=True, blank=True)
    isGovt = models.BooleanField(null=True, blank=True, default=False)
    submissionDate = models.DateField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'cheradip_institutes'
        ordering = ['eiinNo']
        indexes = [
            models.Index(fields=['eiinNo']),
            models.Index(fields=['instituteName']),
            models.Index(fields=['divisionName', 'districtName', 'thanaName']),
            models.Index(fields=['instituteTypeName']),
            models.Index(fields=['isGovt']),
        ]
    
    def __str__(self):
        return f"{self.eiinNo} - {self.instituteName or 'N/A'}"


# ==============================================================================
# UTILITY MODELS
# ==============================================================================

class Token(models.Model):
    """Token model for various token-based operations"""
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # Token Information
    Token = models.BigIntegerField(unique=True, db_index=True)
    Counter = models.CharField(max_length=255, null=True, blank=True)
    Status = models.IntegerField(null=True, blank=True, default=1, choices=[
        (0, 'Inactive'),
        (1, 'Active'),
        (2, 'Used'),
        (3, 'Expired'),
    ])
    
    # Additional Info
    purpose = models.CharField(max_length=50, null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tokens'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['Token']),
            models.Index(fields=['Status']),
            models.Index(fields=['purpose']),
        ]
    
    def __str__(self):
        return f"Token: {self.Token} | Counter: {self.Counter or 'N/A'} | Status: {self.Status}"


class JsonData(models.Model):
    """JSON Data storage model for flexible data storage"""
    # Primary Key
    id = models.AutoField(primary_key=True)
    
    # JSON Data
    data = models.JSONField()
    
    # Metadata
    data_type = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'json_data'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['data_type']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"JSON Data #{self.id} - Type: {self.data_type or 'N/A'}"
