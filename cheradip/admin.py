from django.contrib import admin
from .models import Item, Customer, Order, Ordered, Canceled, OrderDetail, Transaction, Group, Subject, Chapter, Topic, Mcq_ict, Notification, Institute, Year

admin.site.register(Customer)
admin.site.register(Item)
admin.site.register(Order)
admin.site.register(Ordered)
admin.site.register(Canceled)
admin.site.register(OrderDetail)


def completed_button(self, obj):
        if obj.pk:
            move_url = reverse('move_completed_orders', args=[obj.pk])
            return format_html(
                '<div id="move_button"><a class="button move_button" href="{}" target="_blank">Move</a></div><div style="margin-top: 10px; color: red; margin-left:5px; display:none" id="snackbar_container_{}">Error !</div>',
                move_url, obj.pk
            )
        else:
            return '-'

    # completed_button.short_description = "Actions" def move_completed_orders(request, pk):


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('group_code', 'group_name')
    search_fields = ('group_code', 'group_name')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('text', 'link')
    search_fields = ('text', 'link')

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('subject_name', 'subject_code')
    search_fields = ('subject_name', 'subject_code')

@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ('subject', 'chapter_no', 'chapter_name')
    search_fields = ('subject__subject_name', 'chapter_no', 'chapter_name')
    list_filter = ('subject', 'chapter_no')

@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('chapter', 'topic_no', 'topic_name')
    search_fields = ('chapter__chapter_name', 'topic_no', 'topic_name')
    list_filter = ('chapter', 'topic_no')


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
    list_display = ('qid', 'subject', 'chapter', 'topic', 'question', 'option1', 'option2', 'option3', 'option4', 'answer', 'explanation', 'img_uddipok', 'img_question')
    search_fields = (
        'qid',
        'question',
        'answer',
        'explanation',
        'subject__subject_code',  # Search in related Subject model
        'chapter__chapter_no',    # Search in related Chapter model
        'topic__topic_no',        # Search in related Topic model
    )
    list_filter = ('qid', 'subject', 'chapter', 'topic', InstituteTypeFilter, InstituteNameByTypeFilter, 'years')


@admin.register(Institute)
class InstituteAdmin(admin.ModelAdmin):
    list_display = ('institute_code', 'institute_name', 'institute_type')
    search_fields = ('institute_code', 'institute_name', 'institute_type')
    list_filter = ('institute_code', 'institute_name', 'institute_type')

@admin.register(Year)
class YearAdmin(admin.ModelAdmin):
    list_display = ('year_code', 'year_name')
    search_fields = ('year_code', 'year_name')
    list_filter = ('year_code', 'year_name')