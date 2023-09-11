from django.contrib.auth.models import AbstractUser, Group, Permission
from django.utils.translation import gettext as _
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone

class Item(models.Model):
    SIZE = [
        ('XS', 'Extra_small'),
        ('S', 'Small'),
        ('M', 'Medium'),
        ('L', 'Large'),
        ('XL', 'Extra_large'),
        ('XXL', 'Ultra_large'),
    ]
    code = models.CharField(max_length=4, unique=True, blank=False, null=True)
    name = models.CharField(max_length=63, blank=False, null=True)
    bangla_name = models.CharField(max_length=63, blank=False, null=True)
    size = models.CharField(max_length=14, choices=SIZE, blank=False, null=True)
    weight = models.DecimalField(max_digits=6, decimal_places=2, blank=False, null=True)
    love = models.BooleanField(default=False, blank=False, null=True)
    add_to_cart = models.BooleanField(default=False, blank=False, null=True)
    discount = models.DecimalField(max_digits=2, decimal_places=0, default=0, blank=False, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=0, blank=False, null=True)
    probable_weight = models.DecimalField(max_digits=5, decimal_places=2, blank=False, null=True)
    availability = models.BooleanField(default=True, blank=False, null=True)
    quantity = models.IntegerField()
    image = models.ImageField(upload_to='images/', blank=False, null=True)
    PAYMENT_CHOICES = [
        ('Cash on Deilivery', 'cod'),
        ('bKash', 'bkash'),
        ('Nagad', 'nagad'),
        ('DBBL', 'dbbl'),
        ('Other', 'other'),
    ]
    CATEGORY = [
        ('Sea Fish', 'Sea Fish'),
        ('River Fish', 'River Fish'),
        ('Pond Fish', 'Pond Fish'),
        ('Bill Fish', 'Bill Fish'),
        ('other', 'Other'),
    ]
    TYPES = [
        ('Dry', 'Dry'),
        ('Soft', 'Soft'),
    ]
    VARIENTS = [
        ('Whole Fish', 'Whole Fish'),
        ('Half', 'Half'),
        ('One Third', 'One Third'),
        ('Quarter', 'Quarter'),
        ('NA', 'NA'),
    ]
    category = models.CharField(max_length=28, choices=CATEGORY, blank=False, null=True)
    supplier = models.CharField(max_length=54, blank=False, null=True)
    variants = models.CharField(max_length=15, choices=VARIENTS, blank=False, null=True, default="NA")
    types = models.CharField(max_length=15, choices=TYPES, blank=False, null=True, default="Soft")
    reviews = models.TextField(blank=False, null=True, default="Rated By @Author")
    ratings = models.DecimalField(max_digits=3, decimal_places=2, default="5", blank=False, null=True)
    shipping = models.TextField(max_length=14, blank=False, null=True, default="NA")
    in_stock = models.DecimalField(max_digits=6, decimal_places=2, blank=False, null=True)
    payment_method = models.CharField(max_length=28, choices=PAYMENT_CHOICES, default="bKash", blank=False, null=True)
    details = models.TextField(max_length=512, blank=False, null=True, default="NA")
    videos = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.name

class Cart(models.Model):
    VARIENTS = [
        ('Whole Fish', 'Whole Fish'),
        ('Half', 'Half'),
        ('One Third', 'One Third'),
        ('Quarter', 'Quarter'),
        ('NA', 'NA'),
    ]
    customer_id = models.PositiveIntegerField(default=timezone.now, blank=False, null=True)
    code = models.CharField(max_length=4, blank=False, null=True)
    variants = models.CharField(max_length=15, choices=VARIENTS, blank=False, null=True)
    weight = models.DecimalField(max_digits=6, decimal_places=2, blank=False, null=True)
    probable_weight = models.DecimalField(max_digits=5, decimal_places=2, blank=False, null=True)
    quantity = models.PositiveIntegerField(default=1, blank=False, null=True)

    def __str__(self):
        return self.customer_id


class Transaction(models.Model):
    username = models.CharField(max_length=11)
    trxid = models.CharField(max_length=31, unique=True, default='')
    paidFrom = models.CharField(max_length=31, default='')
    Paid = models.DecimalField(max_digits=10, decimal_places=0, blank=False, null=True)

    def __str__(self):
        return self.username
    

class OrderDetail(models.Model):
    SN = models.IntegerField()
    Name = models.CharField(max_length=127)
    Image = models.URLField()
    Weight = models.DecimalField(max_digits=6, decimal_places=2, blank=False, null=True)
    Price = models.DecimalField(max_digits=10, decimal_places=0, blank=False, null=True)
    Quantity = models.IntegerField()
    Discount = models.DecimalField(max_digits=9, decimal_places=0, blank=False, null=True)
    Total = models.DecimalField(max_digits=10, decimal_places=0, blank=False, null=True)
    GrandTotal = models.DecimalField(max_digits=10, decimal_places=0, blank=False, null=True)
    Paid = models.DecimalField(max_digits=10, decimal_places=0, blank=False, null=True)
    Due = models.DecimalField(max_digits=10, decimal_places=0, blank=False, null=True)
    ShipingCost = models.DecimalField(max_digits=8, decimal_places=0, blank=False, null=True)

    def __str__(self):
        return self.Name

class NewOrder(models.Model):
    division = models.CharField(max_length=31, null=True, blank=True)
    district = models.CharField(max_length=31, null=True, blank=True)
    thana = models.CharField(max_length=31, null=True, blank=True)
    paymentMethod = models.CharField(max_length=31, null=True, blank=True)
    username = models.CharField(max_length=11)
    fullName = models.CharField(max_length=31, null=True, blank=True)
    gender = models.CharField(max_length=10, null=True, blank=True)
    union = models.CharField(max_length=31, null=True, blank=True)
    village = models.TextField(max_length=255, null=True, blank=True)
    altMobileNo = models.CharField(max_length=11, null=True, blank=True)
    orderDetails = models.ManyToManyField(OrderDetail, blank=True)
    transaction = models.ManyToManyField(Transaction, blank=True)
    def __str__(self):
        return self.username


class Order(models.Model):
    division = models.CharField(max_length=31, null=True, blank=True)
    district = models.CharField(max_length=31, null=True, blank=True)
    thana = models.CharField(max_length=31, null=True, blank=True)
    paymentMethod = models.CharField(max_length=31, null=True, blank=True)
    username = models.CharField(max_length=11)
    fullName = models.CharField(max_length=31, null=True, blank=True)
    gender = models.CharField(max_length=10, null=True, blank=True)
    union = models.CharField(max_length=31, null=True, blank=True)
    village = models.TextField(max_length=255, null=True, blank=True)
    altMobileNo = models.CharField(max_length=11, null=True, blank=True)
    orderDetails = models.ManyToManyField(OrderDetail, blank=True)
    transaction = models.ManyToManyField(Transaction, blank=True)

    def __str__(self):
        return self.username


class CustomerManager(BaseUserManager):
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

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(username, password, **extra_fields)
    
      
class Customer(AbstractBaseUser, PermissionsMixin):
    GENDER = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Common', 'Common'),
    ]
    username = models.CharField(max_length=11, unique=True, blank=False, null=True)
    password = models.CharField(max_length=14, blank=False, null=True)
    fullName = models.CharField(max_length=31, blank=False, null=True)
    gender = models.CharField(max_length=6, choices=GENDER, blank=False, null=True)
    division = models.CharField(max_length=31, blank=False, null=True)
    district = models.CharField(max_length=31, blank=False, null=True)
    thana = models.CharField(max_length=31, blank=False, null=True)
    union = models.CharField(max_length=31, blank=True, null=True)
    village = models.CharField(max_length=255, blank=False, null=True)

    objects = CustomerManager()

    USERNAME_FIELD = "username"

    groups = models.ManyToManyField(Group, related_name="customer_set", blank=True)
    user_permissions = models.ManyToManyField(
        Permission, related_name="customer_set", blank=True
    )

    def __str__(self):
        return self.fullName

    def get_full_name(self):
        return self.fullName

    def get_short_name(self):
        return self.fullName
    

class CustomerToken(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE)
    key = models.CharField("Key", max_length=40, primary_key=True)
    created = models.DateTimeField("Created", default=timezone.now)

    def __str__(self):
        return f"Token for {self.customer.username}"
    

class JsonData(models.Model):
    data = models.JSONField()

    def __str__(self):
        return f"JSON Data #{self.id}"
