from datetime import timedelta
from decimal import Decimal
from django.test import TransactionTestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from . import test_suppliers as fixtures
from .models import SupplierPilotCheck, ProductImage, ProductVariant, Order, OrderItem, SupplierOffer
from .supplier_service import approve, import_draft
from .supplier_pilot import record_check, CHECKS, current_release, validate_checkout
from .supplier_guards import is_supplier_staging
from .order_service import change_order


class PilotTests(TransactionTestCase):
    databases={'default','ecommerce'}
    setUp=fixtures.SupplierTests.setUp
    row=fixtures.SupplierTests.row
    ready=fixtures.SupplierTests.ready
    offer=fixtures.SupplierTests.offer
    evidence=fixtures.SupplierTests.evidence

    def product(self):
        offer=self.ready(); approve(offer,self.user.pk,'Verified draft import')
        product,_=import_draft(offer,self.category.pk,self.user.pk)
        offer.refresh_from_db(using='ecommerce')
        product.description='Reviewed real product'; product.supplier_delivery_rates={
            'dhaka':[{'up_to_grams':1000,'charge':'80'}], 'outside':[{'up_to_grams':1000,'charge':'120'}]}
        product.save(using='ecommerce')
        ProductImage.objects.using('ecommerce').create(product=product,url='https://supplier.example/photo.jpg')
        variant=product.variants.get(); variant.stock=5; variant.save(using='ecommerce')
        return offer,product,variant

    def check(self,product,variant,**kw):
        return SupplierPilotCheck(product=product,expected_source_price='100',expected_selling_price=variant.price,
            verified_quantity=5,expires_at=timezone.now()+timedelta(hours=1),checks=dict.fromkeys(CHECKS,True),note='Test-only source quote, exact variant, stock, rates, costs and content verified.',**kw)

    def test_release_is_individual_and_does_not_automatically_publish(self):
        _,p,v=self.product()
        self.assertTrue(is_supplier_staging(p.pk))
        record_check(self.check(p,v),self.user)
        p.refresh_from_db(); self.assertEqual(p.status,'draft')
        p.status='active'; p.save(using='ecommerce')
        self.assertFalse(is_supplier_staging(p.pk))
        result=self.client.get('/api/ecommerce/products/')
        self.assertEqual(result.data['count'],1)
        self.assertEqual(self.client.get('/api/ecommerce/categories/').data[0]['product_count'],1)
        self.assertFalse(self.client.get('/api/ecommerce/admin/supplier-workspace/').data['auto_place_orders'])

    def test_changed_content_price_or_expired_release_fails_closed(self):
        _,p,v=self.product(); check=record_check(self.check(p,v),self.user)
        p.status='active'; p.save(using='ecommerce')
        v.price+=1; v.save(using='ecommerce')
        self.assertTrue(is_supplier_staging(p.pk))
        self.assertEqual(self.client.get('/api/ecommerce/products/').data['count'],0)
        v.price-=1; v.save(using='ecommerce')
        SupplierPilotCheck.objects.using('ecommerce').filter(pk=check.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertTrue(is_supplier_staging(p.pk))

    def test_admin_publication_checks_only_the_edited_product(self):
        from unittest.mock import patch, MagicMock
        from .supplier_guards import check_publication
        _,product,_ = self.product()
        product.status='active'
        eligible=MagicMock()
        eligible.filter.return_value.exists.return_value=True
        with patch('ecommerce.manual_catalogue.public_ids',return_value=eligible):
            check_publication(product)
        eligible.filter.assert_called_once_with(imported_product_id=product.pk)
        eligible.__iter__.assert_not_called()

    def test_all_checks_permissions_prices_and_quantity_required(self):
        _,p,v=self.product()
        row=self.check(p,v); row.checks['delivery']=False
        with self.assertRaises(ValueError): record_check(row,self.user)
        row=self.check(p,v); row.expected_source_price=1
        with self.assertRaises(ValueError): record_check(row,self.user)
        row=self.check(p,v); row.verified_quantity=1
        with self.assertRaises(ValueError): record_check(row,self.user)
        self.user.is_superuser=False; self.user.save()
        with self.assertRaises(ValueError): record_check(self.check(p,v),self.user)
        self.assertEqual(SupplierPilotCheck.objects.using('ecommerce').count(),0)

    def test_source_identity_and_tariffs_cannot_be_replaced_by_checkboxes(self):
        offer,p,v=self.product(); offer.match_confirmed=False; offer.save(using='ecommerce')
        with self.assertRaises(ValueError): record_check(self.check(p,v),self.user)
        offer.match_confirmed=True; offer.save(using='ecommerce')
        p.supplier_delivery_rates={}; p.save(using='ecommerce')
        with self.assertRaises(ValueError): record_check(self.check(p,v),self.user)

    def test_loss_coupon_and_shipping_subsidy_blocked(self):
        _,p,v=self.product(); record_check(self.check(p,v),self.user)
        totals={'subtotal':v.price,'discount_total':Decimal('50'),'shipping_total':Decimal('80'),
                'delivery_details':{'supplier_shipments':[{'charged':'80'}]}}
        with self.assertRaises(ValueError): validate_checkout([(v,1)],totals)
        totals['discount_total']=Decimal('0'); totals['shipping_total']=Decimal('0')
        with self.assertRaises(ValueError): validate_checkout([(v,1)],totals)

    def test_pending_order_requires_its_own_check_and_is_not_auto_completed(self):
        _,p,v=self.product(); record_check(self.check(p,v),self.user)
        order=Order.objects.using('ecommerce').create(customer_name='Test',phone='01710000000',email='test@example.com',
            subtotal=v.price,shipping_total=80,grand_total=v.price+80,shipping_address={'district':'Dhaka','address':'Test road'})
        OrderItem.objects.using('ecommerce').create(order=order,product_id=p.pk,variant_id=v.pk,product_name=p.name,sku=v.sku,quantity=1,unit_price=v.price,line_total=v.price)
        with self.assertRaises(ValueError): change_order(order.pk,'completed',self.user.pk)
        record_check(self.check(p,v,order=order),self.user)
        result=change_order(order.pk,'confirmed',self.user.pk)
        self.assertEqual(result.status,'confirmed'); self.assertEqual(result.payment_status,'unpaid')

    def test_check_records_are_immutable(self):
        _,p,v=self.product(); row=record_check(self.check(p,v),self.user)
        with self.assertRaises(ValidationError): row.save()
        with self.assertRaises(ValidationError): row.delete()

    def test_admin_add_form_has_six_required_verifications(self):
        from .supplier_admin import PilotCheckForm
        self.assertTrue(all(PilotCheckForm.base_fields[k].required for k in CHECKS))

    def test_api_cart_quote_checkout_pending_then_staff_confirmation(self):
        _,p,v=self.product(); record_check(self.check(p,v),self.user)
        p.status='active'; p.save(using='ecommerce')
        detail=self.client.get(f'/api/ecommerce/products/{p.slug}/').data
        self.assertEqual(detail['fulfilment_mode'],'staff_confirmed_supplier_pilot')
        self.assertNotIn('supplier_offer',detail); self.assertNotIn('cost_price',detail['variants'][0])
        cart=self.client.post('/api/ecommerce/cart/',{'variant_id':v.pk,'quantity':1},format='json')
        self.assertEqual(cart.status_code,200,cart.data)
        payload={'cart_token':cart.data['token'],'customer_name':'Pilot Test','phone':'01710000000','email':'test@example.com',
                 'shipping_address':{'country_code':'BD','district':'Dhaka','thana':'Savar','address':'Test road'},'payment_method':'cod'}
        quote=self.client.post('/api/ecommerce/checkout/quote/',payload,format='json')
        self.assertEqual(quote.status_code,200,quote.data); self.assertEqual(quote.data['shipping_total'],Decimal('80'))
        response=self.client.post('/api/ecommerce/checkout/',{**payload,'quoted_total':str(quote.data['grand_total'])},format='json')
        self.assertEqual(response.status_code,201,response.data)
        order=Order.objects.using('ecommerce').get(); self.assertEqual(order.status,'pending')
        v.refresh_from_db(); self.assertEqual(v.stock,4)
        self.assertFalse(is_supplier_staging(p.pk))
        with self.assertRaises(ValueError): change_order(order.pk,'confirmed',self.user.pk)
        record_check(self.check(p,v,order=order),self.user)
        change_order(order.pk,'confirmed',self.user.pk)
        again=self.client.post('/api/ecommerce/checkout/',payload,format='json')
        self.assertEqual(again.status_code,200,again.data)
        v.refresh_from_db(); self.assertEqual(v.stock,4); self.assertEqual(Order.objects.using('ecommerce').count(),1)

    def test_revoke_source_change_and_quantity_caps(self):
        offer,p,v=self.product(); row=record_check(self.check(p,v),self.user)
        v.stock=6; v.save(using='ecommerce'); self.assertTrue(is_supplier_staging(p.pk))
        v.stock=5; v.save(using='ecommerce')
        SupplierPilotCheck.objects.using('ecommerce').filter(pk=row.pk).update(revoked_at=timezone.now())
        self.assertTrue(is_supplier_staging(p.pk))
        record_check(self.check(p,v),self.user)
        offer.source_price=Decimal('101'); offer.save(using='ecommerce')
        self.assertTrue(is_supplier_staging(p.pk))

    def test_order_check_invalidated_by_address_or_amount_change(self):
        _,p,v=self.product()
        order=Order.objects.using('ecommerce').create(customer_name='Test',phone='01710000000',email='test@example.com',
            subtotal=v.price,shipping_total=80,grand_total=v.price+80,shipping_address={'district':'Dhaka','address':'Test road'})
        OrderItem.objects.using('ecommerce').create(order=order,product_id=p.pk,variant_id=v.pk,product_name=p.name,sku=v.sku,quantity=1,unit_price=v.price,line_total=v.price)
        record_check(self.check(p,v,order=order),self.user)
        order.shipping_address={'district':'Dinajpur','address':'Another road'}; order.save(using='ecommerce')
        with self.assertRaises(ValueError): change_order(order.pk,'confirmed',self.user.pk)

    def test_catalogue_modes_restore_only_current_releases_and_preserve_research(self):
        from .supplier_service import policy
        from .models import Product
        offer,p,v=self.product(); record_check(self.check(p,v),self.user)
        p.status='archived'; p.save(using='ecommerce')
        own=Product.objects.using('ecommerce').create(name='Ordinary stock',slug='ordinary',category=self.category,status='active')
        revision=policy().revision; decision=offer.current_decision_id
        def apply(mode):
            preview=self.client.post('/api/ecommerce/admin/supplier-catalogue-mode/',{'mode':mode},format='json')
            self.assertEqual(preview.status_code,200,preview.data)
            result=self.client.post('/api/ecommerce/admin/supplier-catalogue-mode/',{'mode':mode,'preview':False,'preview_token':preview.data['preview_token']},format='json')
            self.assertEqual(result.status_code,200,result.data)
        apply('all'); p.refresh_from_db(); self.assertEqual(p.status,'active')
        listing=self.client.get('/api/ecommerce/products/').data
        self.assertEqual(listing['count'],2)
        apply('filtered'); self.assertEqual(policy().revision,revision)
        offer.refresh_from_db(); self.assertEqual(offer.current_decision_id,decision)
        v.stock=0; v.save(using='ecommerce')
        apply('all'); p.refresh_from_db(); self.assertEqual(p.status,'archived')
        self.assertEqual(self.client.get('/api/ecommerce/products/').data['count'],1)
        v.stock=5; v.save(using='ecommerce')
        apply('all'); p.refresh_from_db(); self.assertEqual(p.status,'active')
        offer.source_price+=1; offer.save(using='ecommerce')
        apply('all'); p.refresh_from_db(); own.refresh_from_db()
        self.assertEqual(p.status,'archived'); self.assertEqual(own.status,'active')
