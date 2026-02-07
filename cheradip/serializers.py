from rest_framework import serializers
from .models import (Institutes, Item, Token, Merit, Merit5, Merit6, Recommend, Recommend5, Recommend6, 
                     Banbeis, Customer, CheradipUser, Order, Ordered, OrderDetail, Transaction, Notification, Vacancy, 
                     Vacancy5, Vacancy6, Group, Subject, Chapter, Topic, Mcq_ict, Institute, Year, Country,
                     ClassLevel, ClassGroupMapping, Department, Location)


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
# TOKEN AND OTHER SERIALIZERS
# ==============================================================================

class TokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Token
        fields = '__all__'

class InstitutesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institutes
        fields = '__all__'

class RecommendSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recommend
        fields = '__all__'

class Recommend5Serializer(serializers.ModelSerializer):
    class Meta:
        model = Recommend5
        fields = '__all__'

class Recommend6Serializer(serializers.ModelSerializer):
    class Meta:
        model = Recommend6
        fields = '__all__'

class BanbeisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banbeis
        fields = '__all__'

class VacancySerializer(serializers.ModelSerializer):
    class Meta:
        model = Vacancy
        fields = '__all__'

class Vacancy5Serializer(serializers.ModelSerializer):
    class Meta:
        model = Vacancy5
        fields = '__all__'

class Vacancy6Serializer(serializers.ModelSerializer):
    class Meta:
        model = Vacancy6
        fields = '__all__'

class MeritSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merit
        fields = '__all__'

class Merit5Serializer(serializers.ModelSerializer):
    class Meta:
        model = Merit5
        fields = '__all__'

class Merit6Serializer(serializers.ModelSerializer):
    class Meta:
        model = Merit6
        fields = '__all__'

class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = '__all__'


class LocationSerializer(serializers.ModelSerializer):
    """Location (country, division, district, thana, local_address). Loaded by id for profile/orders."""
    class Meta:
        model = Location
        fields = ['id', 'country', 'division', 'district', 'thana', 'local_address']


class CheradipUserSerializer(serializers.ModelSerializer):
    """Write-only serializer for saving signup data into cheradip_users."""
    password = serializers.CharField(write_only=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    class_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    group = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=30)
    department = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=50)
    teacher_level = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    teacher_subject_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=10)
    teacher_department_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = CheradipUser
        fields = [
            'acctype', 'fullName', 'username', 'password', 'date_of_birth',
            'class_name', 'group', 'department', 'teacher_level', 'teacher_subject_code',
            'teacher_department_code', 'gender', 'email', 'country_code',
        ]

    def create(self, validated_data):
        from django.contrib.auth.hashers import make_password
        validated_data['password'] = make_password(validated_data.pop('password'))
        return super().create(validated_data)


class CustomerSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=4, allow_blank=True)
    year_of_birth = serializers.IntegerField(required=False, allow_null=True)
    location = LocationSerializer(read_only=True)
    location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(), write_only=True, required=False, allow_null=True
    )
    
    class Meta:
        model = Customer
        fields = ['acctype', 'fullName', 'username', 'password', 'year_of_birth', 'class_name',
                  'group', 'gender', 'teacher_level', 'teacher_subject_code', 'teacher_department_code',
                  'email', 'location', 'location_id']
        extra_kwargs = {
            'password': {'write_only': True},
            'email': {'required': False, 'allow_blank': True, 'allow_null': True},
            'teacher_level': {'required': False, 'allow_blank': True, 'allow_null': True},
            'teacher_subject_code': {'required': False, 'allow_blank': True, 'allow_null': True},
            'teacher_department_code': {'required': False, 'allow_blank': True, 'allow_null': True},
        }
    
    def generate_default_password(self, fullName, year_of_birth):
        """Generate default password: First 3 letters of name + @ + year of birth (e.g., Sha@1993)"""
        if fullName and year_of_birth:
            # Get first 3 letters of the name (capitalize first letter)
            name_part = fullName[:3].strip()
            if len(name_part) > 0:
                name_part = name_part[0].upper() + name_part[1:].lower()
            return f"{name_part}@{year_of_birth}"
        return None
    
    def create(self, validated_data):
        # Generate default password if not provided
        password = validated_data.pop('password', None)
        location = validated_data.pop('location_id', None)
        if location is not None:
            validated_data['location'] = location
        fullName = validated_data.get('fullName', '')
        year_of_birth = validated_data.get('year_of_birth')
        
        if not password or password == '':
            password = self.generate_default_password(fullName, year_of_birth)
            if not password:
                # Fallback: use first 3 letters of name + @2000
                name_part = fullName[:3].strip() if fullName else 'Usr'
                if len(name_part) > 0:
                    name_part = name_part[0].upper() + name_part[1:].lower()
                password = f"{name_part}@2000"
        
        user = Customer.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        return user
    
    def update(self, instance, validated_data):
        # Handle password update if provided
        password = validated_data.pop('password', None)
        if password and password != '':
            instance.set_password(password)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class CustomerUpdateSerializer(serializers.ModelSerializer):
    location = LocationSerializer(read_only=True)
    location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(), write_only=True, required=False, allow_null=True
    )
    
    class Meta:
        model = Customer
        fields = ['acctype', 'fullName', 'group', 'gender', 'location', 'location_id']

    def update(self, instance, validated_data):
        # Exclude 'username' and 'password' fields from the update
        validated_data.pop('username', None)
        validated_data.pop('password', None)
        location = validated_data.pop('location_id', None)
        if location is not None:
            instance.location = location

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
    
class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = '__all__'

class OrderDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderDetail
        fields = '__all__'

class OrderSerializer(serializers.ModelSerializer):
    orderDetails = OrderDetailSerializer(many=True, read_only=True)
    transaction = TransactionSerializer(many=True, read_only=True)
    class Meta:
        model = Order
        fields = '__all__'   

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'text', 'link']


# MCQ and Related Model Serializers
class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['group_code', 'group_name']


class YearSerializer(serializers.ModelSerializer):
    class Meta:
        model = Year
        fields = ['year_code', 'year_name']


class InstituteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institute
        fields = ['institute_code', 'institute_name', 'institute_type']


class SubjectSerializer(serializers.ModelSerializer):
    """Subject with groups (list on model); group_list = resolved Group objects for those codes.
    Primary key is id = country_code + '_' + subject_code (e.g. BD_101)."""
    group_list = serializers.SerializerMethodField()
    
    class Meta:
        model = Subject
        fields = ['id', 'subject_code', 'level', 'country', 'subject_name', 'subject_name_bn', 'groups', 'group_list', 'created_at', 'updated_at']
    
    def get_group_list(self, obj):
        codes = getattr(obj, 'groups', None) or []
        if not codes:
            return []
        from .models import Group
        qs = Group.objects.filter(group_code__in=codes).order_by('group_code')
        return GroupSerializer(qs, many=True).data


class ClassLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassLevel
        fields = ['class_code', 'class_name', 'class_name_bn', 'has_groups', 'has_departments', 'display_order']


class ClassGroupMappingSerializer(serializers.ModelSerializer):
    class_level = ClassLevelSerializer(read_only=True)
    group_list = serializers.SerializerMethodField()
    
    class Meta:
        model = ClassGroupMapping
        fields = ['id', 'class_level', 'group_codes', 'group_list']
    
    def get_group_list(self, obj):
        return obj.get_group_list()


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['dept_code', 'dept_name', 'dept_name_bn', 'dept_name_short', 'faculty', 'faculty_bn', 'degree_type', 'display_order']


class ChapterSerializer(serializers.ModelSerializer):
    subject = SubjectSerializer(read_only=True)
    subject_code = serializers.CharField(source='subject.subject_code', read_only=True)
    subject_name = serializers.CharField(source='subject.subject_name', read_only=True)
    
    class Meta:
        model = Chapter
        fields = ['id', 'subject', 'subject_code', 'subject_name', 'chapter_no', 'chapter_name']


class TopicSerializer(serializers.ModelSerializer):
    chapter = ChapterSerializer(read_only=True)
    chapter_no = serializers.CharField(source='chapter.chapter_no', read_only=True)
    chapter_name = serializers.CharField(source='chapter.chapter_name', read_only=True)
    subject_code = serializers.CharField(source='chapter.subject.subject_code', read_only=True)
    
    class Meta:
        model = Topic
        fields = ['id', 'chapter', 'chapter_no', 'chapter_name', 'subject_code', 'topic_no', 'topic_name']


class McqIctSerializer(serializers.ModelSerializer):
    subject = SubjectSerializer(read_only=True)
    subject_code = serializers.CharField(source='subject.subject_code', read_only=True, required=False)
    chapter = ChapterSerializer(read_only=True)
    chapter_no = serializers.CharField(source='chapter.chapter_no', read_only=True, required=False)
    chapter_name = serializers.CharField(source='chapter.chapter_name', read_only=True, required=False)
    topic = TopicSerializer(read_only=True)
    topic_no = serializers.CharField(source='topic.topic_no', read_only=True, required=False)
    topic_name = serializers.CharField(source='topic.topic_name', read_only=True, required=False)
    institutes = InstituteSerializer(many=True, read_only=True)
    years = YearSerializer(many=True, read_only=True)
    
    # For write operations
    subject_code_write = serializers.CharField(write_only=True, required=False)
    chapter_no_write = serializers.CharField(write_only=True, required=False)
    topic_no_write = serializers.CharField(write_only=True, required=False)
    institute_codes = serializers.ListField(
        child=serializers.CharField(), 
        write_only=True, 
        required=False,
        allow_empty=True
    )
    year_codes = serializers.ListField(
        child=serializers.CharField(), 
        write_only=True, 
        required=False,
        allow_empty=True
    )
    
    # Image fields with full URLs
    img_uddipok = serializers.ImageField(required=False, allow_null=True)
    img_question = serializers.ImageField(required=False, allow_null=True)
    img_explanation = serializers.ImageField(required=False, allow_null=True)
    
    class Meta:
        model = Mcq_ict
        fields = [
            'qid', 'subject', 'subject_code', 'chapter', 'chapter_no', 'chapter_name',
            'topic', 'topic_no', 'topic_name', 'uddipok', 'question', 'option1', 
            'option2', 'option3', 'option4', 'answer', 'explanation',
            'img_uddipok', 'img_question', 'img_explanation',
            'institutes', 'years',
            # Write-only fields
            'subject_code_write', 'chapter_no_write', 'topic_no_write',
            'institute_codes', 'year_codes'
        ]
        read_only_fields = ['qid']
    
    def to_representation(self, instance):
        """Override to include full image URLs"""
        representation = super().to_representation(instance)
        
        # Add full URLs for images
        request = self.context.get('request')
        if request:
            for img_field in ['img_uddipok', 'img_question', 'img_explanation']:
                if representation.get(img_field):
                    representation[img_field] = request.build_absolute_uri(representation[img_field])
            # Use HOST_URL from settings if request not available
        else:
            from django.conf import settings
            base_url = getattr(settings, 'HOST_URL', '')
            for img_field in ['img_uddipok', 'img_question', 'img_explanation']:
                if representation.get(img_field):
                    representation[img_field] = f"{base_url}/manage/media/{representation[img_field]}"
        
        return representation
    
    def create(self, validated_data):
        # Extract write-only fields
        subject_code = validated_data.pop('subject_code_write', None)
        chapter_no = validated_data.pop('chapter_no_write', None)
        topic_no = validated_data.pop('topic_no_write', None)
        institute_codes = validated_data.pop('institute_codes', [])
        year_codes = validated_data.pop('year_codes', [])
        
        # Get related objects (subject_code is local code; use filter().first() when id not provided)
        if subject_code:
            subject = Subject.objects.filter(subject_code=subject_code).first()
            if not subject:
                raise serializers.ValidationError(f"Subject with code {subject_code} does not exist")
            validated_data['subject'] = subject
        
        if chapter_no and subject_code:
            subject = validated_data.get('subject')
            if subject:
                try:
                    chapter = Chapter.objects.get(subject=subject, chapter_no=chapter_no)
                    validated_data['chapter'] = chapter
                except Chapter.DoesNotExist:
                    raise serializers.ValidationError(f"Chapter {chapter_no} not found for subject {subject_code}")
        
        if topic_no and chapter_no and subject_code:
            chapter = validated_data.get('chapter')
            if chapter:
                try:
                    topic = Topic.objects.get(chapter=chapter, topic_no=topic_no)
                    validated_data['topic'] = topic
                except Topic.DoesNotExist:
                    raise serializers.ValidationError(f"Topic {topic_no} not found")
        
        # Create question
        question = Mcq_ict.objects.create(**validated_data)
        
        # Add many-to-many relationships
        if institute_codes:
            institutes = Institute.objects.filter(institute_code__in=institute_codes)
            question.institutes.set(institutes)
        
        if year_codes:
            years = Year.objects.filter(year_code__in=year_codes)
            question.years.set(years)
        
        return question
    
    def update(self, instance, validated_data):
        # Extract write-only fields
        subject_code = validated_data.pop('subject_code_write', None)
        chapter_no = validated_data.pop('chapter_no_write', None)
        topic_no = validated_data.pop('topic_no_write', None)
        institute_codes = validated_data.pop('institute_codes', None)
        year_codes = validated_data.pop('year_codes', None)
        
        # Update related objects if provided
        if subject_code:
            subject = Subject.objects.filter(subject_code=subject_code).first()
            if not subject:
                raise serializers.ValidationError(f"Subject with code {subject_code} does not exist")
            validated_data['subject'] = subject
        
        if chapter_no:
            subject_obj = validated_data.get('subject', instance.subject)
            try:
                chapter = Chapter.objects.get(subject=subject_obj, chapter_no=chapter_no)
                validated_data['chapter'] = chapter
            except Chapter.DoesNotExist:
                raise serializers.ValidationError(f"Chapter {chapter_no} not found")
        
        if topic_no:
            chapter_obj = validated_data.get('chapter', instance.chapter)
            try:
                topic = Topic.objects.get(chapter=chapter_obj, topic_no=topic_no)
                validated_data['topic'] = topic
            except Topic.DoesNotExist:
                raise serializers.ValidationError(f"Topic {topic_no} not found")
        
        # Update instance
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update many-to-many relationships
        if institute_codes is not None:
            institutes = Institute.objects.filter(institute_code__in=institute_codes)
            instance.institutes.set(institutes)
        
        if year_codes is not None:
            years = Year.objects.filter(year_code__in=year_codes)
            instance.years.set(years)
        
        return instance