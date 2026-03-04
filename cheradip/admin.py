from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import (
    Institutes, Item, Token, Banbeis, Recommend, Recommend5, Recommend6, 
    Vacancy, Vacancy5, Vacancy6, Merit, Merit5, Merit6, Customer,
    CustomerToken, Order, Ordered, Canceled, OrderDetail, Transaction, 
    Group, Subject, Chapter, Topic, Mcq_ict, Notification, Institute, Year, JsonData,
)

admin.site.register(Item)
admin.site.register(OrderDetail)
admin.site.register(JsonData)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('username', 'fullName', 'acctype', 'group', 'email', 'is_active', 'date_joined')
    search_fields = ('username', 'fullName', 'email', 'division', 'district')
    list_filter = ('acctype', 'group', 'gender', 'is_active', 'date_joined')
    readonly_fields = ('date_joined', 'last_login', 'updated_at')


@admin.register(CustomerToken)
class CustomerTokenAdmin(admin.ModelAdmin):
    list_display = ('key', 'customer', 'created', 'expires_at')
    search_fields = ('key', 'customer__username', 'customer__fullName')
    list_filter = ('created', 'expires_at')
    readonly_fields = ('key', 'created')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('trxid', 'username', 'paidFrom', 'Paid', 'payment_method', 'status', 'created_at')
    search_fields = ('trxid', 'username')
    list_filter = ('status', 'payment_method', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'fullName', 'status', 'paymentMethod', 'shipped', 'created_at')
    search_fields = ('username', 'fullName', 'district', 'thana')
    list_filter = ('status', 'paymentMethod', 'shipped', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Ordered)
class OrderedAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'fullName', 'status', 'shipped', 'delivered_at', 'created_at')
    search_fields = ('username', 'fullName', 'district')
    list_filter = ('status', 'shipped', 'delivered_at', 'created_at')
    readonly_fields = ('created_at', 'updated_at', 'delivered_at')


@admin.register(Canceled)
class CanceledAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'fullName', 'shipped', 'cancelled_at', 'created_at')
    search_fields = ('username', 'fullName', 'cancellation_reason')
    list_filter = ('shipped', 'cancelled_at', 'created_at')
    readonly_fields = ('created_at', 'cancelled_at')

@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = ('Token','Counter',)
    search_fields = ('Token','Counter',)

@admin.register(Banbeis)
class BanbeisAdmin(admin.ModelAdmin):
    list_display = ('EIIN','Mouza',)
    search_fields = ('EIIN','Mouza',)

@admin.register(Recommend)
class RecommendAdmin(admin.ModelAdmin):
    list_display = ('id', 'EIIN', 'Name', 'Roll', 'Subject', 'Rank')
    search_fields = ('EIIN', 'Name', 'Roll', 'Subject', 'District', 'Thana')
    list_filter = ('Subject', 'District')


@admin.register(Recommend5)
class Recommend5Admin(admin.ModelAdmin):
    list_display = ('id', 'EIIN', 'Name', 'Roll', 'Subject', 'Rank')
    search_fields = ('EIIN', 'Name', 'Roll', 'Subject', 'District', 'Thana')


@admin.register(Recommend6)
class Recommend6Admin(admin.ModelAdmin):
    list_display = ('id', 'EIIN', 'Name', 'Roll', 'Subject', 'Rank')
    search_fields = ('EIIN', 'Name', 'Roll', 'Subject', 'District', 'Thana')

@admin.register(Merit)
class MeritAdmin(admin.ModelAdmin):
    list_display = ('Code', 'Name', 'Batch', 'Roll', 'Mark', 'Rank', 'SL', 'Subject')
    search_fields = ('Code', 'Name', 'Batch', 'Roll', 'Mark', 'Rank', 'SL', 'Subject')

@admin.register(Merit5)
class Merit5Admin(admin.ModelAdmin):
    list_display = ('Code', 'Name', 'Batch', 'Roll', 'Mark', 'Rank', 'SL', 'Subject')
    search_fields = ('Code', 'Name', 'Batch', 'Roll', 'Mark', 'Rank', 'SL', 'Subject')

@admin.register(Merit6)
class Merit6Admin(admin.ModelAdmin):
    list_display = ('Code', 'Name', 'Batch', 'Roll', 'Mark', 'Rank', 'SL', 'Subject')
    search_fields = ('Code', 'Name', 'Batch', 'Roll', 'Mark', 'Rank', 'SL', 'Subject')

@admin.register(Vacancy)
class VacancyAdmin(admin.ModelAdmin):
    list_display = ('EIIN', 'Name', 'District', 'Thana', 'Designation', 'Subject', 'Vacancy')
    search_fields = ('EIIN', 'Name', 'District', 'Thana', 'Designation', 'Subject')

@admin.register(Vacancy5)
class Vacancy5Admin(admin.ModelAdmin):
    list_display = ('EIIN', 'Name', 'District', 'Thana', 'Designation', 'Subject', 'Vacancy')
    search_fields = ('EIIN', 'Name', 'District', 'Thana', 'Designation', 'Subject')

@admin.register(Vacancy6)
class Vacancy6Admin(admin.ModelAdmin):
    list_display = ('EIIN', 'Name', 'District', 'Thana', 'Designation', 'Subject', 'Vacancy')
    search_fields = ('EIIN', 'Name', 'District', 'Thana', 'Designation', 'Subject')

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('group_code', 'group_name', 'group_name_bn', 'created_at')
    search_fields = ('group_code', 'group_name', 'group_name_bn')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'text', 'link')
    search_fields = ('text', 'link')

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'level', 'level_tr', 'groups', 'get_class_display', 'subject_name', 'subject_translated', 'subject_code', 'country_id', 'language_code', 'created_at', 'updated_at')
    search_fields = ('subject_code', 'subject_name', 'subject_translated', 'level', 'level_tr')
    list_filter = ('country_id', 'language_code', 'level', 'class_level')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject_code', 'chapter_no', 'chapter_name', 'chapter_name_bn', 'created_at')
    search_fields = ('subject_code', 'chapter_no', 'chapter_name', 'chapter_name_bn')
    list_filter = ('subject_code', 'chapter_no', 'created_at')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('id', 'chapter', 'topic_no', 'topic_name', 'topic_name_bn', 'created_at')
    search_fields = ('chapter__chapter_name', 'chapter__subject_code', 'topic_no', 'topic_name', 'topic_name_bn')
    list_filter = ('chapter', 'chapter__subject_code', 'topic_no', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


class InstituteNameByTypeFilter(admin.SimpleListFilter):
    title = 'Institute Name'
    parameter_name = 'institute_name'

    def lookups(self, request, model_admin):
        # Check if an institute type is selected in InstituteTypeFilter
        selected_type = request.GET.get('institute_type')
        
        if selected_type:
            # Fetch institute names for the selected institute type
            names = Institute.objects.filter(institute_type=selected_type).values_list('institute_name', flat=True).distinct()
            return [(name, name) for name in names]
        return []

    def queryset(self, request, queryset):
        if self.value():
            # Filter queryset by selected institute_name
            return queryset.filter(institutes__institute_name=self.value()).distinct()
        return queryset


class InstituteTypeFilter(admin.SimpleListFilter):
    title = 'Institute Type'
    parameter_name = 'institute_type'

    def lookups(self, request, model_admin):
        # Get distinct institute types
        types = Institute.objects.values_list('institute_type', flat=True).distinct()
        return [(institute_type, institute_type) for institute_type in types if institute_type]

    def queryset(self, request, queryset):
        if self.value():
            # Filter by the selected institute type
            return queryset.filter(institutes__institute_type=self.value()).distinct()
        return queryset


@admin.register(Mcq_ict)
class McqIctAdmin(admin.ModelAdmin):
    list_display = ('qid', 'subject_code', 'chapter', 'topic', 'difficulty_level', 'is_active', 'answer', 'created_at')
    search_fields = (
        'qid', 'question', 'uddipok', 'answer', 'explanation',
        'subject_code', 'chapter__chapter_no', 'chapter__chapter_name',
        'topic__topic_no', 'topic__topic_name',
    )
    list_filter = ('subject_code', 'chapter', 'topic', 'difficulty_level', 'is_active', 'answer', InstituteTypeFilter, InstituteNameByTypeFilter, 'years', 'created_at')
    filter_horizontal = ('institutes', 'years')
    readonly_fields = ('qid', 'created_at', 'updated_at')
    fieldsets = (
        ('Question Information', {
            'fields': ('qid', 'subject_code', 'chapter', 'topic', 'question', 'uddipok', 'img_question', 'img_uddipok')
        }),
        ('Options', {
            'fields': ('option1', 'option2', 'option3', 'option4', 'answer')
        }),
        ('Additional Information', {
            'fields': ('explanation', 'img_explanation', 'difficulty_level', 'is_active')
        }),
        ('Relationships', {
            'fields': ('institutes', 'years')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Institute)
class InstituteAdmin(admin.ModelAdmin):
    list_display = ('institute_code', 'institute_name', 'institute_name_bn', 'institute_type', 'created_at')
    search_fields = ('institute_code', 'institute_name', 'institute_name_bn', 'institute_type')
    list_filter = ('institute_type', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Year)
class YearAdmin(admin.ModelAdmin):
    list_display = ('year_code', 'year_name', 'year_name_bn', 'start_year', 'end_year', 'created_at')
    search_fields = ('year_code', 'year_name', 'year_name_bn')
    list_filter = ('year_code', 'start_year', 'end_year', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Institutes)
class InstitutesAdmin(admin.ModelAdmin):
    list_display = ('eiinNo', 'instituteName', 'instituteTypeName', 'districtName', 'isGovt')
    search_fields = ('eiinNo', 'instituteName', 'instituteNameBn', 'districtName', 'thanaName')
    list_filter = ('instituteTypeName', 'isGovt', 'divisionName', 'districtName')