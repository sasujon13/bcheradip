from rest_framework import serializers
from .models import (
    Item,
    Customer,
    OrderDetail,
    Transaction,
    Notification,
    Country,
    Location,
    Merit5,
    Merit6,
    Merit7,
    Vacancy5,
    Vacancy6,
    Vacancy7,
    Recommend5,
    Recommend6,
    Recommend7,
    Banbeis,
    Institutes,
    Token,
)

# ==============================================================================
# COUNTRY SERIALIZERS
# ==============================================================================

class CountrySerializer(serializers.ModelSerializer):
    """Full country serializer with all fields (including language_codes for UI language)."""
    class Meta:
        model = Country
        fields = [
            'country_code', 'country_code_alpha3', 'country_code_numeric',
            'country_name', 'country_name_native', 'country_name_official',
            'flag_emoji', 'flag_url', 'phone_code', 'phone_code_numeric',
            'phone_format', 'phone_length_min', 'phone_length_max',
            'continent', 'region', 'capital',
            'currency_code', 'currency_symbol', 'timezone',
            'language_codes', 'display_order', 'is_featured', 'is_active',
        ]


class CountryListSerializer(serializers.ModelSerializer):
    """Lightweight country serializer for autocomplete/dropdowns; includes language_codes for translation."""
    class Meta:
        model = Country
        fields = [
            'country_code', 'country_name', 'country_name_native',
            'flag_emoji', 'flag_url', 'phone_code', 'phone_format',
            'phone_length_min', 'phone_length_max', 'is_featured',
            'language_codes',
        ]


# ==============================================================================
# LOCATION
# ==============================================================================

class LocationSerializer(serializers.ModelSerializer):
    """Location (country, division, district, thana, local_address)."""
    class Meta:
        model = Location
        fields = ['id', 'country', 'division', 'district', 'thana', 'local_address']


# ==============================================================================
# ITEM, TRANSACTION, ORDER DETAIL, NOTIFICATION
# ==============================================================================

class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = '__all__'


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = '__all__'


class OrderDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderDetail
        fields = '__all__'


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'text', 'link']


# ==============================================================================
# CUSTOMER
# ==============================================================================

class CustomerSignupSerializer(serializers.ModelSerializer):
    """Write-only serializer for signup: create Customer. Password is hashed on create."""
    password = serializers.CharField(write_only=True, min_length=4)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    country_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=2)
    class_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    group = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=30)
    department = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=50)
    teacher_level = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    teacher_subject_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=10)
    teacher_department_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    teacher_department_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=200)
    gender = serializers.CharField(required=False, allow_blank=True, max_length=10)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Customer
        fields = [
            'acctype', 'fullName', 'username', 'password', 'country_code', 'date_of_birth',
            'class_name', 'group', 'department',
            'teacher_level', 'teacher_subject_code', 'teacher_department_code', 'teacher_department_name',
            'gender', 'email',
            'division', 'district', 'thana', 'union', 'village',
        ]
        extra_kwargs = {
            'division': {'required': False, 'allow_blank': True, 'default': ''},
            'district': {'required': False, 'allow_blank': True, 'default': ''},
            'thana': {'required': False, 'allow_blank': True, 'default': ''},
            'union': {'required': False, 'allow_blank': True, 'default': ''},
            'village': {'required': False, 'allow_blank': True, 'default': ''},
        }

    def create(self, validated_data):
        password = validated_data.pop('password')
        for key in ('division', 'district', 'thana', 'union', 'village'):
            if validated_data.get(key) is None:
                validated_data[key] = ''
        acctype = (validated_data.get('acctype') or 'Student').strip()
        if acctype == 'Job Seeker':
            acctype = 'JobSeeker'
        validated_data['acctype'] = acctype
        validated_data['group'] = validated_data.get('group') or ('Science' if acctype == 'Student' else '')
        validated_data['gender'] = validated_data.get('gender') or ''
        user = Customer.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        return user


class CustomerSerializer(serializers.ModelSerializer):
    """Serializer for Customer (auth table)."""
    password = serializers.CharField(write_only=True, required=False, min_length=4, allow_blank=True)

    class Meta:
        model = Customer
        fields = [
            'acctype', 'fullName', 'username', 'password', 'group', 'gender',
            'division', 'district', 'thana', 'union', 'village', 'email',
        ]
        extra_kwargs = {
            'password': {'write_only': True},
            'email': {'required': False, 'allow_blank': True, 'allow_null': True},
            'division': {'required': False, 'allow_blank': True, 'default': ''},
            'district': {'required': False, 'allow_blank': True, 'default': ''},
            'thana': {'required': False, 'allow_blank': True, 'default': ''},
            'union': {'required': False, 'allow_blank': True, 'default': ''},
            'village': {'required': False, 'allow_blank': True, 'default': ''},
        }

    def generate_default_password(self, fullName, year_of_birth=None):
        name_part = (fullName or '')[:3].strip()
        if not name_part:
            name_part = 'Usr'
        else:
            name_part = name_part[0].upper() + name_part[1:].lower()
        year = year_of_birth if year_of_birth else 2000
        return f"{name_part}@{year}"

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        fullName = validated_data.get('fullName', '')
        for key in ('division', 'district', 'thana', 'union', 'village'):
            validated_data.setdefault(key, '')
        if not password or password == '':
            password = self.generate_default_password(fullName)
        user = Customer.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        if password and password != '':
            instance.set_password(password)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class CustomerUpdateSerializer(serializers.ModelSerializer):
    """Profile update: no location FK on Customer; address fields only."""
    division = serializers.CharField(required=False, allow_blank=True, max_length=31)
    district = serializers.CharField(required=False, allow_blank=True, max_length=31)
    thana = serializers.CharField(required=False, allow_blank=True, max_length=31)
    union = serializers.CharField(required=False, allow_blank=True, max_length=31)
    village = serializers.CharField(required=False, allow_blank=True, max_length=255)
    country_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=2)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    class_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    department = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=50)
    teacher_level = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    teacher_subject_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=10)
    teacher_department_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    teacher_department_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=200)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Customer
        fields = [
            'acctype', 'fullName', 'group', 'gender',
            'country_code', 'date_of_birth', 'class_name', 'department',
            'teacher_level', 'teacher_subject_code', 'teacher_department_code', 'teacher_department_name',
            'email',
            'division', 'district', 'thana', 'union', 'village',
        ]

    def update(self, instance, validated_data):
        validated_data.pop('username', None)
        validated_data.pop('password', None)
        validated_data.pop('countryCode', None)
        for attr, value in validated_data.items():
            if hasattr(instance, attr):
                setattr(instance, attr, value)
        instance.save()
        return instance


# ==============================================================================
# JOB DB SERIALIZERS (cheradip_job – NTRCA / institutes / tokens)
# ==============================================================================

class Merit5Serializer(serializers.ModelSerializer):
    class Meta:
        model = Merit5
        fields = '__all__'


class Merit6Serializer(serializers.ModelSerializer):
    class Meta:
        model = Merit6
        fields = '__all__'


class Merit7Serializer(serializers.ModelSerializer):
    class Meta:
        model = Merit7
        fields = '__all__'


class Vacancy5Serializer(serializers.ModelSerializer):
    class Meta:
        model = Vacancy5
        fields = '__all__'


class Vacancy6Serializer(serializers.ModelSerializer):
    class Meta:
        model = Vacancy6
        fields = '__all__'


class Vacancy7Serializer(serializers.ModelSerializer):
    class Meta:
        model = Vacancy7
        fields = '__all__'


class Recommend5Serializer(serializers.ModelSerializer):
    class Meta:
        model = Recommend5
        fields = '__all__'


class Recommend6Serializer(serializers.ModelSerializer):
    class Meta:
        model = Recommend6
        fields = '__all__'


class Recommend7Serializer(serializers.ModelSerializer):
    class Meta:
        model = Recommend7
        fields = '__all__'


class BanbeisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banbeis
        fields = '__all__'


class InstitutesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institutes
        fields = '__all__'


class TokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Token
        fields = '__all__'
