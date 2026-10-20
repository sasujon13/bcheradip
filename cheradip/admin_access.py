"""Native Django account/group tools for the shared Customer account table."""
import hashlib
import json

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm, AdminUserCreationForm, UserChangeForm
from django.contrib.auth.models import Group, Permission

from .models import Customer, CustomerToken


class CustomerCreationForm(AdminUserCreationForm):
    class Meta(AdminUserCreationForm.Meta):
        model = Customer
        fields = ('username', 'fullName', 'acctype', 'email')


def settings_revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


class LazySettingsWidget(forms.Textarea):
    """Render an empty editor first; retrieve private JSON only on demand."""
    template_name = 'admin/cheradip/customer/lazy_settings_widget.html'
    loaded = False
    revision = ''

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget'].update(loaded=self.loaded, revision=self.revision)
        return context

    class Media:
        js = ('admin/js/customer_lazy_settings.js',)
        css = {'all': ('admin/css/customer_lazy_settings.css',)}


class CustomerChangeForm(UserChangeForm):
    # A separate, non-model field prevents model_to_dict from reading the JSON
    # during initial form construction. The real settings field stays deferred.
    settings_editor = forms.JSONField(label='Settings', required=False, widget=LazySettingsWidget,
                                     help_text='Loaded only when opened. Unopened settings are never replaced when you save this profile.')

    class Meta(UserChangeForm.Meta):
        model = Customer
        fields = '__all__'
        exclude = ('settings',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings_changed = False
        field = self.fields.get('settings_editor')
        if field and self.is_bound and self.data.get('settings_editor_loaded') == '1':
            field.widget.loaded = True
            field.widget.revision = self.data.get('settings_editor_revision', '')

    def clean_referred_by(self):
        referrer = self.cleaned_data.get('referred_by')
        if referrer and referrer.pk == self.instance.pk:
            raise forms.ValidationError('An account cannot refer itself.')
        return referrer

    def clean(self):
        cleaned = super().clean()
        if ('settings_editor' not in self.fields or 'settings_editor' in self.errors
                or self.data.get('settings_editor_loaded') != '1'):
            return cleaned
        revision = self.data.get('settings_editor_revision', '')
        if not revision:
            self.add_error('settings_editor', 'Reload Settings before editing it.')
            return cleaned
        self.settings_changed = settings_revision(cleaned.get('settings_editor')) != revision
        if self.settings_changed:
            # Admin wraps change-form POSTs in a transaction. Lock the latest JSON
            # while checking it so a profile edit cannot overwrite newer balances.
            current = Customer.objects.select_for_update().only('settings').get(pk=self.instance.pk)
            if settings_revision(current.settings) != revision:
                self.settings_changed = False
                self.add_error('settings_editor', 'Settings changed since you opened them. Reload this page and Settings before saving your edits; newer wallet/account data has been preserved.')
        return cleaned


class CustomerPasswordChangeForm(AdminPasswordChangeForm):
    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            CustomerToken.objects.filter(customer=user).delete()
            from .ext_account_sync import sync_customer_to_ext
            sync_customer_to_ext(user, raw_password=self.cleaned_data.get('password1'), sync_password=True)
        return user


class SuperuserAccessAdminMixin:
    """Editing a permission/group can grant access to every member of that group."""
    def has_module_permission(self, request):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)


class AccessGroupAdmin(SuperuserAccessAdminMixin, GroupAdmin):
    list_display = ('name', 'permission_count')

    @admin.display(description='Assigned permissions')
    def permission_count(self, obj):
        return obj.permissions.count()

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('permissions')


class AccessPermissionAdmin(SuperuserAccessAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'codename', 'content_type')
    list_filter = ('content_type__app_label', 'content_type')
    search_fields = ('name', 'codename', 'content_type__app_label', 'content_type__model')
    list_select_related = ('content_type',)
    ordering = ('content_type__app_label', 'content_type__model', 'codename')
    fields = ('name', 'content_type', 'codename')


if admin.site.is_registered(Group):
    admin.site.unregister(Group)
admin.site.register(Group, AccessGroupAdmin)
if not admin.site.is_registered(Permission):
    admin.site.register(Permission, AccessPermissionAdmin)
