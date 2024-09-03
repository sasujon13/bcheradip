from django.contrib.auth.models import AbstractUser, Group, Permission
from django.utils.translation import gettext as _
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone

class Item(models.Model):
    SIZE = [
        ('nctb', 'nctb'),
        ('book', 'book'),
        ('guide', 'guide'),
        ('cheradip', 'cheradip'),
    ]
    code = models.CharField(max_length=4, blank=False, null=True)
    name = models.CharField(max_length=63, blank=False, null=True)
    bangla_name = models.CharField(max_length=63, blank=False, null=True)
    size = models.CharField(max_length=14, choices=SIZE, blank=False, null=True)
    weight = models.DecimalField(max_digits=6, decimal_places=2, blank=False, null=True)
    love = models.BooleanField(default=False, blank=False, null=True)
    add_to_cart = models.BooleanField(default=False, blank=False, null=True)
    discount = models.DecimalField(max_digits=2, decimal_places=0, default=0, blank=False, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=0, blank=False, null=True)
    quantity = models.IntegerField()
    image = models.ImageField(upload_to='images/', blank=False, null=True)
    PAYMENT_CHOICES = [
        ('Cash on Deilivery', 'cod'),
        ('bKash', 'bkash'),
        ('Nagad', 'nagad'),
        ('DBBL', 'dbbl'),
        ('Other', 'other'),
    ]
    TYPES = [
        ('science', 'science'),
        ('business', 'business'),
        ('humanities', 'hamanities'),
        ('compulsory', 'compulsory'),
        ('sac', 'sac'),
        ('ac', 'ac'),
        ('sc', 'sc'),
    ]
    supplier = models.CharField(max_length=54, blank=False, null=True)
    types = models.CharField(max_length=15, choices=TYPES, blank=False, null=True, default="humanities")
    reviews = models.TextField(blank=False, null=True, default="Rated By @Author")
    ratings = models.DecimalField(max_digits=3, decimal_places=2, default="5", blank=False, null=True)
    shipping = models.TextField(max_length=14, blank=False, null=True, default="NA")
    in_stock = models.IntegerField(blank=False, null=True)
    payment_method = models.CharField(max_length=28, choices=PAYMENT_CHOICES, default="bKash", blank=False, null=True)
    details = models.TextField(max_length=512, blank=False, null=True, default="NA")
    videos = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.name


class Transaction(models.Model):
    username = models.CharField(max_length=11, null=True, blank=True, default='')
    trxid = models.CharField(max_length=31, unique=True, default='')
    paidFrom = models.CharField(max_length=31, default='')
    Paid = models.DecimalField(max_digits=10, decimal_places=0, blank=False, null=True)

    def __str__(self):
        return self.trxid
    

class OrderDetail(models.Model):
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True)
    SN = models.IntegerField()
    Name = models.CharField(max_length=127)
    Image = models.URLField()
    Weight = models.DecimalField(max_digits=6, decimal_places=2, blank=False, null=True)
    Price = models.DecimalField(max_digits=10, decimal_places=0, blank=False, null=True)
    Quantity = models.IntegerField(blank=False, null=True)
    Discount = models.DecimalField(max_digits=9, decimal_places=0, blank=False, null=True)
    Total = models.DecimalField(max_digits=10, decimal_places=0, blank=False, null=True)
    GrandTotal = models.DecimalField(max_digits=10, decimal_places=0, blank=False, null=True)
    Paid = models.DecimalField(max_digits=10, decimal_places=0, blank=False, null=True)
    Due = models.DecimalField(max_digits=10, decimal_places=0, blank=False, null=True)
    ShipingCost = models.DecimalField(max_digits=8, decimal_places=0, blank=False, null=True)

    def __str__(self):
        return self.Name

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
    shipped = models.BooleanField(default=False)

    def __str__(self):
        return self.username


class Ordered(models.Model):
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
    shipped = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username
    

class Canceled(models.Model):
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
    shipped = models.BooleanField(default=False)

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
        return self.create_user(username, password, **extra_fields)

class Customer(AbstractBaseUser, PermissionsMixin):
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
    ]
    acctype = models.CharField(max_length=7, choices=TYPE_CHOICES, default="Student")
    fullName = models.CharField(max_length=31)
    username = models.CharField(max_length=11, unique=True)
    password = models.CharField(max_length=128) 
    group = models.CharField(max_length=18, choices=GROUP_CHOICES, default="Science")
    gender = models.CharField(max_length=6, choices=GENDER_CHOICES, default="Male")
    division = models.CharField(max_length=31)
    district = models.CharField(max_length=31)
    thana = models.CharField(max_length=31)
    union = models.CharField(max_length=31, blank=True)
    village = models.CharField(max_length=255)

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


class Group(models.Model):
    GROUP_CHOICES = [
        ('Science', 'Science'),
        ('Business Studies', 'Business Studies'),
        ('Humanities', 'Humanities'),
    ]
    group_name = models.CharField(max_length=50, choices=GROUP_CHOICES, default="Science")
    group_code = models.CharField(max_length=1, unique=True)

    def __str__(self):
        return f"{self.group_code} {self.group_name}"


class Subject(models.Model):
    group = models.ManyToManyField(Group, related_name='subjects')
    subject_code = models.CharField(max_length=3, unique=True)
    subject_name = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"{self.group} {self.subject_code} {self.subject_name}"


class Chapter(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='chapters')
    chapter_no = models.CharField(max_length=2, blank=True)
    chapter_name = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ('subject', 'chapter_no')

    def __str__(self):
        return f"{self.subject.subject_code} {self.chapter_no} {self.chapter_name}"


class Topic(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='topics')
    topic_no = models.CharField(max_length=2, blank=True)
    topic_name = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ('chapter', 'topic_no')

    def __str__(self):
        return f"{self.chapter.subject.subject_code} {self.topic_no} {self.topic_name}"


class Subtopic(models.Model):
    topic = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='subtopics')
    subtopic_no = models.CharField(max_length=2, blank=True)
    subtopic_name = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ('topic', 'subtopic_no')

    def __str__(self):
        return f"{self.chapter.subject.subject_code} {self.subtopic_no} {self.subtopic_name}"


def question_image_path(instance, filename):
    # File will be uploaded to MEDIA_ROOT/images/mcq/<subject_code>/<chapter_no>/<filename>
    return f'images/mcq/{instance.subject.subject_code}/{instance.chapter.chapter_no}/{filename}'


class Mcq_ict(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='questions')
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='questions')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='questions')
    subtopic = models.ForeignKey(Subtopic, on_delete=models.CASCADE, related_name='questions')
    uddipok = models.TextField(null=True, blank=True, max_length=1000)
    question = models.TextField(max_length=300)
    option1 = models.TextField(max_length=200)
    option2 = models.TextField(max_length=200)
    option3 = models.TextField(max_length=200)
    option4 = models.TextField(max_length=200)
    answer = models.CharField(max_length=1, choices=[('1', 'ক'), ('2', 'খ'), ('3', 'গ'), ('4', 'ঘ')])
    explanation = models.TextField(null=True, blank=True, max_length=1000)
    image = models.ImageField(upload_to=question_image_path, null=True, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    board = models.CharField(max_length=100, null=True, blank=True)
    qid = models.CharField(max_length=10, unique=True, editable=False)

    def __str__(self):
        return f"Question ID: {self.qid} ({self.subject.subject_code})"

    def save(self, *args, **kwargs):
        if not self.qid:
            # Zero-pad chapter_no and topic_no to ensure they are two digits
            chapter_no = f'{int(self.chapter.chapter_no):02}'
            topic_no = f'{int(self.topic.topic_no):02}'
            
            # Generate qid as subject_code + chapter_no + topic_no + 3 digit sequence number
            last_question = Question.objects.filter(
                subject=self.subject,
                chapter=self.chapter,
                topic=self.topic
            ).order_by('qid').last()
            
            if last_question:
                last_qid = int(last_question.qid[-3:])
                new_qid = f'{last_qid + 1:03}'
            else:
                new_qid = '001'
            
            self.qid = f'{self.subject.subject_code}{chapter_no}{topic_no}{new_qid}'
        
        super().save(*args, **kwargs)



class Notifications(models.Model):
    text = models.TextField(max_length=1024, null=True, blank=True)
    link = models.URLField(max_length=512, null=True, blank=True)

    def __str__(self):
        return self.text
                   