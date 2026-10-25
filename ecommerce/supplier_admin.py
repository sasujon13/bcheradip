from django.contrib import admin
from django import forms
from django.db import transaction
from django.utils.html import format_html
from .models import Supplier, SupplierPolicy, SupplierOffer, SupplierEvidence, SupplierDecision, SupplierJob, SupplierAudit, SupplierSettlementEntry, SupplierResearchBatch, SupplierResearchItem, SupplierPilotCheck
from .models import SupplierRecollectionRun, SupplierRecollectionItem, SupplierSourceProduct, SupplierSourceMedia


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'enabled', 'terms_confirmed', 'connector', 'health', 'last_success_at')
    list_filter = ('enabled', 'terms_confirmed')
    search_fields = ('name',)
    readonly_fields = ('health', 'last_success_at', 'workspace')
    exclude = ('credentials_ciphertext',)

    def save_model(self, request, obj, form, change):
        from .supplier_service import audit
        with transaction.atomic(using='ecommerce'):
            if change:
                current = Supplier.objects.using('ecommerce').select_for_update().get(pk=obj.pk)
                for field in form.changed_data:
                    setattr(current, field, getattr(obj, field))
                current.full_clean(exclude=['credentials_ciphertext'])
                current.save(using='ecommerce', update_fields=list(form.changed_data) + ['updated_at'])
                obj.refresh_from_db(using='ecommerce')
            else:
                super().save_model(request, obj, form, change)
            audit('supplier_configuration', request.user.pk, obj, fields=list(form.changed_data), source='django_admin')

    @admin.display(description='Secure sourcing workspace')
    def workspace(self, obj):
        return format_html('<a href="/ecommerce/manage?section=suppliers">Open Suppliers — credentials, identities, research, jobs and draft imports</a>')


class SourcingRecordAdmin(admin.ModelAdmin):
    def has_change_permission(self, request, obj=None):
        return False
    def get_readonly_fields(self, request, obj=None):
        return tuple(f.name for f in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SourceCategoryReviewFilter(admin.SimpleListFilter):
    title = 'Category review'
    parameter_name = 'category_review'
    def lookups(self, request, model_admin): return [('pending', 'Needs category review'), ('assigned', 'Category assigned')]
    def queryset(self, request, queryset):
        if self.value() == 'pending': return queryset.filter(extra___cheradip_catalog__status='needs_review')
        if self.value() == 'assigned': return queryset.filter(extra___cheradip_catalog__status='assigned')
        return queryset


@admin.register(SupplierSourceProduct)
class SupplierSourceProductAdmin(SourcingRecordAdmin):
    list_display = ('title', 'supplier', 'external_id', 'sku', 'observed_at')
    list_filter = ('supplier', SourceCategoryReviewFilter)
    search_fields = ('title', 'external_id', 'sku')
    list_select_related = ('supplier',)


@admin.register(SupplierSourceMedia)
class SupplierSourceMediaAdmin(SourcingRecordAdmin):
    list_display = ('product', 'kind', 'role', 'variant_id', 'position', 'last_seen_at')
    list_filter = ('kind', 'role', 'product__supplier')
    search_fields = ('product__title', 'original_url', 'variant_id')
    list_select_related = ('product',)


@admin.register(SupplierRecollectionRun)
class SupplierRecollectionRunAdmin(SourcingRecordAdmin):
    list_display = ('supplier', 'mode', 'status', 'discovered', 'processed', 'expected_total', 'updated_at')
    list_filter = ('supplier', 'mode', 'status')
    list_select_related = ('supplier',)


@admin.register(SupplierRecollectionItem)
class SupplierRecollectionItemAdmin(SourcingRecordAdmin):
    list_display = ('external_id', 'run', 'status', 'attempts', 'observed_at')
    list_filter = ('status', 'run__supplier')
    search_fields = ('external_id', 'url', 'error')
    list_select_related = ('run',)


@admin.register(SupplierOffer)
class SupplierOfferAdmin(SourcingRecordAdmin):
    list_display = ('title', 'supplier', 'vendor_id', 'source_price', 'availability', 'state', 'observed_at')
    search_fields = ('title', 'external_id', 'vendor_id')
    list_filter = ('supplier', 'state', 'availability')


class PilotCheckForm(forms.ModelForm):
    price = forms.BooleanField(label='Buying price and selling price checked')
    variant = forms.BooleanField(label='Exact variant, pack, warranty and source identity checked')
    stock = forms.BooleanField(label='Exact source variant quantity checked (not parent stock)')
    delivery = forms.BooleanField(label='Actual area/weight tariff and parcel origin checked')
    margin = forms.BooleanField(label='All costs, discounts and delivered profit checked')
    content = forms.BooleanField(label='Product images, description and permitted branding checked')

    class Meta:
        model=SupplierPilotCheck
        fields=('product','order','expected_source_price','expected_selling_price','verified_quantity','expires_at','note')

    def clean(self):
        data=super().clean()
        required=('product','expected_source_price','expected_selling_price','verified_quantity','expires_at','note')
        if all(k in data for k in required):
            from .supplier_pilot import record_check,CHECKS
            for k in (*required,'order'): setattr(self.instance,k,data.get(k))
            self.instance.checks={k:data.get(k,False) for k in CHECKS}
            try: record_check(self.instance,self.actor,save=False)
            except (ValueError,SupplierOffer.DoesNotExist) as exc:
                raise forms.ValidationError(str(exc) if isinstance(exc,ValueError) else 'Choose an imported supplier product, not ordinary inventory.')
        return data


@admin.register(SupplierPilotCheck)
class SupplierPilotCheckAdmin(admin.ModelAdmin):
    form=PilotCheckForm
    list_display=('product','order','actor_id','verified_quantity','expires_at','revoked_at')
    list_filter=('revoked_at',)
    search_fields=('product__name','order__number','note')
    autocomplete_fields=('product','order')
    readonly_fields=('actor_id','snapshot','fingerprint','checks','revoked_at','created_at')
    actions=('revoke',)

    def get_form(self,request,obj=None,**kwargs):
        base=super().get_form(request,obj,**kwargs)
        class BoundForm(base):
            actor=request.user
        return BoundForm

    def get_readonly_fields(self,request,obj=None):
        return tuple(f.name for f in self.model._meta.fields) if obj else ()

    def get_fields(self,request,obj=None):
        if obj: return tuple(f.name for f in self.model._meta.fields)
        from .supplier_pilot import CHECKS
        return ('product','order','expected_source_price','expected_selling_price','verified_quantity','expires_at',*CHECKS,'note')

    def has_add_permission(self,request):
        return super().has_add_permission(request) and (request.user.has_perm('ecommerce.publish_supplier_pilot') or request.user.has_perm('ecommerce.confirm_supplier_pilot'))

    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False

    def save_model(self,request,obj,form,change):
        from .supplier_pilot import record_check
        record_check(obj,request.user)

    @admin.action(description='Revoke selected pilot checks (preserves history)',permissions=['revoke'])
    def revoke(self,request,queryset):
        from django.utils import timezone
        from .supplier_service import audit
        for row in queryset.filter(revoked_at__isnull=True):
            required='confirm_supplier_pilot' if row.order_id else 'publish_supplier_pilot'
            if request.user.has_perm('ecommerce.'+required):
                queryset.filter(pk=row.pk,revoked_at__isnull=True).update(revoked_at=timezone.now())
                audit('manual_pilot_revoked',request.user.pk,check_id=row.pk,product_id=row.product_id,order_id=row.order_id)

    def has_revoke_permission(self,request):
        return request.user.has_perm('ecommerce.publish_supplier_pilot') or request.user.has_perm('ecommerce.confirm_supplier_pilot')


@admin.register(SupplierJob)
class SupplierJobAdmin(SourcingRecordAdmin):
    list_display = ('supplier', 'action', 'status', 'processed', 'total', 'created_at')
    list_filter = ('status', 'action', 'supplier')
    exclude = ('payload',)
    def get_readonly_fields(self, request, obj=None):
        return tuple(f.name for f in self.model._meta.fields if f.name != 'payload')


class SupplierPolicyForm(forms.ModelForm):
    evidence_days = forms.IntegerField(min_value=1, max_value=90)
    retention_days = forms.IntegerField(min_value=30, max_value=3650)

    class Meta:
        model = SupplierPolicy
        fields = ('evidence_days', 'retention_days')


@admin.register(SupplierPolicy)
class SupplierPolicyAdmin(admin.ModelAdmin):
    form = SupplierPolicyForm
    fields = ('evidence_days', 'retention_days', 'revision', 'last_nightly_date')
    readonly_fields = ('revision', 'last_nightly_date')

    def has_add_permission(self, request):
        return not SupplierPolicy.objects.using('ecommerce').exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        from .supplier_service import audit
        with transaction.atomic(using='ecommerce'):
            SupplierPolicy.objects.using('ecommerce').get_or_create(pk=1)
            current = SupplierPolicy.objects.using('ecommerce').select_for_update().get(pk=1)
            current.evidence_days, current.retention_days = obj.evidence_days, obj.retention_days
            current.revision += 1
            current.save(using='ecommerce', update_fields=['evidence_days', 'retention_days', 'revision', 'updated_at'])
            obj.pk, obj.revision = 1, current.revision
            audit('supplier_policy_changed', request.user.pk, revision=current.revision,
                  evidence_days=current.evidence_days, retention_days=current.retention_days)


for model in (SupplierEvidence, SupplierDecision, SupplierAudit):
    admin.site.register(model, SourcingRecordAdmin)


@admin.register(SupplierResearchBatch)
class ResearchBatchAdmin(SourcingRecordAdmin):
    list_display=('id','status','actor_id','updated_at')


@admin.register(SupplierResearchItem)
class ResearchItemAdmin(SourcingRecordAdmin):
    list_display=('offer','status','batch','updated_at')
    search_fields=('offer__title','note')
    list_filter=('status',)


@admin.register(SupplierSettlementEntry)
class SupplierSettlementEntryAdmin(admin.ModelAdmin):
    list_display = ('supplier', 'kind', 'amount', 'reference', 'order', 'created_at')
    list_filter = ('supplier', 'kind')
    search_fields = ('reference', 'order__number', 'supplier__name')
    autocomplete_fields = ('supplier', 'order', 'reversal_of')
    readonly_fields = ('actor_id','created_at','updated_at')
    actions = None

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.actor_id = request.user.pk
        obj.save(using='ecommerce')
