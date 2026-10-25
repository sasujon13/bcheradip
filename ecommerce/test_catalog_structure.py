from decimal import Decimal
from io import StringIO
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient
from .catalog_structure import classify
from .product_content import content_rows, safe_description
from .models import Category, Product, ProductVariant, OrderItem, SupplierOffer
from . import test_supplier_source_publish as fixtures
from .supplier_source_publish import publish_source
from .supplier_recollection import save_record


class CatalogContentTests(SimpleTestCase):
    def test_generic_size_categories_are_not_classification_evidence(self):
        self.assertEqual(classify('Cotton Hoodie', ['Extra Large'])['path'], ['Clothing','Tops','Hoodies & Sweatshirts'])
        self.assertEqual(classify('MicroSD Memory Card 256GB', ['All Products'])['path'], ['Electronics','Storage & Memory'])
        self.assertEqual(classify('Unidentified item 123', ['Large Products'])['status'], 'needs_review')
        self.assertEqual(classify('5 Piece Comforter Set', ['All Products'])['path'], ['Home & Living','Bedding'])

    def test_properties_exclude_missing_and_private_values_and_flag_conflicts(self):
        from types import SimpleNamespace
        source=SimpleNamespace(specifications={'Material':'Cotton','source_price':'100','Warranty':'N/A'},
            extra={}, features=[{'html':'<p>Material: Polyester</p><p>Color: Blue</p>'}],
            description='<table><tr><th>Capacity</th><td>256 GB</td></tr></table>')
        rows, conflicts, _ = content_rows(source)
        values={r['feature']:r['value'] for r in rows}
        self.assertEqual(values['Capacity'],'256 GB');self.assertEqual(values['Color'],'Blue')
        self.assertNotIn('Material',values);self.assertIn('Material',conflicts)
        self.assertNotIn('source_price',values);self.assertNotIn('Warranty',values)

    def test_description_retains_structure_but_not_executable_content(self):
        result=safe_description('<p onclick="bad()">Original</p><script>bad()</script><table><tr><td>100% cotton</td></tr></table><img src="javascript:bad()">')
        self.assertIn('<p>Original</p>',result);self.assertIn('<table>',result)
        self.assertNotIn('script',result);self.assertNotIn('onclick',result)

    def test_author_is_public_but_connection_keys_are_not(self):
        rows,_,_=content_rows(attributes={'Author':'A real author','apiKey':'private','session':'private'})
        self.assertEqual(rows,[{'feature':'Author','value':'A real author'}])

    def test_long_available_properties_are_preserved_for_wrapping(self):
        value='Compatible device ' * 90
        rows,_,_=content_rows(attributes={'Compatibility':value})
        self.assertEqual(rows,[{'feature':'Compatibility','value':value.strip()}])


class CatalogJourneyTests(TestCase):
    databases={'default','ecommerce'}

    def setUp(self):
        self.root=Category.objects.create(name='Clothing',slug='clothing')
        self.middle=Category.objects.create(name='Tops',slug='clothing-tops',parent=self.root)
        self.leaf=Category.objects.create(name='Shirts',slug='clothing-tops-shirts',parent=self.middle)
        self.product=Product.objects.create(name='Cotton Shirt',slug='cotton-shirt',status='active',category=self.leaf,
            description='<p>Material: Cotton</p>')
        self.red=ProductVariant.objects.create(product=self.product,sku='red-m',title='Red / M',price=100,stock=5,
            option1_name='Color',option1_value='Red',option2_name='Size',option2_value='M')
        self.blue=ProductVariant.objects.create(product=self.product,sku='blue-l',title='Blue / L',price=120,stock=5,
            option1_name='Color',option1_value='Blue',option2_name='Size',option2_value='L')
        self.client=APIClient();self.client.credentials(HTTP_X_FORWARDED_PROTO='https')

    def test_ancestor_categories_include_nested_products_and_spec_table_has_values(self):
        categories=self.client.get('/api/ecommerce/categories/').data
        self.assertEqual(next(c for c in categories if c['id']==self.root.pk)['product_count'],1)
        listing=self.client.get('/api/ecommerce/products/?category=clothing').data
        self.assertEqual(listing['count'],1)
        detail=self.client.get('/api/ecommerce/products/cotton-shirt/').data
        self.assertTrue(any(r['feature']=='Material' and r['value']=='Cotton' for r in detail['specifications']))

    def test_price_range_uses_full_public_catalog_not_price_filter_or_page(self):
        hidden=Product.objects.create(name='Private draft',slug='private-draft',status='draft',category=self.leaf)
        ProductVariant.objects.create(product=hidden,sku='hidden',price=99999,stock=1)
        response=self.client.get('/api/ecommerce/products/price-range/?max_price=1&limit=1')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(Decimal(response.data['max_price']),Decimal('100'))
        self.assertEqual(response.data['min_price'],'0.00')

    def test_public_responses_do_not_leak_private_source_fields(self):
        self.product.attributes={'supplier_cost':'99','api_secret':'private','Material':'Cotton',
                                 'procurement':{'password':'private'}}
        self.product.save()
        detail=self.client.get('/api/ecommerce/products/cotton-shirt/').data
        self.assertEqual(detail['attributes']['Material'],'Cotton')
        self.assertTrue(set(detail['attributes']) <= {'Material','Color','Size'})
        listing=self.client.get('/api/ecommerce/products/').data
        self.assertNotIn('source_url',listing['results'][0])

    def test_cart_variant_replacement_changes_price_and_order_snapshot(self):
        cart=self.client.post('/api/ecommerce/cart/',{'variant_id':self.red.pk,'quantity':2},format='json').data
        response=self.client.patch('/api/ecommerce/cart/'+cart['token']+'/',{'item_id':cart['items'][0]['id'],'variant_id':self.blue.pk},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['items'][0]['variant_id'],self.blue.pk)
        self.assertEqual(response.data['subtotal'],Decimal('240'))
        order=self.client.post('/api/ecommerce/checkout/',{'cart_token':cart['token'],'customer_name':'Customer','email':'test@example.com',
            'phone':'01710000000','shipping_address':{'country_code':'BD','district':'Dhaka','thana':'Savar','address':'Road 1'},'payment_method':'cod'},format='json')
        self.assertEqual(order.status_code,201,order.data)
        item=OrderItem.objects.get();self.assertEqual(item.variant_id,self.blue.pk);self.assertEqual(item.unit_price,Decimal('120'))

    def test_invalid_cart_replacement_leaves_original_item_unchanged(self):
        cart=self.client.post('/api/ecommerce/cart/',{'variant_id':self.red.pk,'quantity':2},format='json').data
        self.blue.stock=1;self.blue.save()
        path='/api/ecommerce/cart/'+cart['token']+'/'
        self.assertEqual(self.client.patch(path,{'item_id':cart['items'][0]['id'],'variant_id':self.blue.pk},format='json').status_code,400)
        self.assertEqual(self.client.get(path).data['items'][0]['variant_id'],self.red.pk)

    def test_missing_option_mapping_is_enforced_by_cart_and_checkout(self):
        cart=self.client.post('/api/ecommerce/cart/',{'variant_id':self.red.pk,'quantity':1},format='json').data
        self.product.attributes={'_catalog':{'variant_review':True}};self.product.save()
        self.assertEqual(self.client.post('/api/ecommerce/cart/',{'variant_id':self.red.pk},format='json').status_code,409)
        payload={'cart_token':cart['token'],'customer_name':'Customer','email':'test@example.com','phone':'01710000000',
            'shipping_address':{'country_code':'BD','district':'Dhaka','thana':'Savar','address':'Road 1'},'payment_method':'cod'}
        self.assertEqual(self.client.post('/api/ecommerce/checkout/quote/',payload,format='json').status_code,409)
        self.assertEqual(self.client.post('/api/ecommerce/checkout/',payload,format='json').status_code,409)

    def test_category_repair_preserves_legacy_filter_and_is_repeatable(self):
        old=Category.objects.create(name='Large Products',slug='large-products')
        self.product.category=old;self.product.save()
        call_command('organize_product_catalog',stdout=StringIO())
        self.product.refresh_from_db();self.assertEqual(self.product.category_id,old.pk)
        call_command('organize_product_catalog',apply=True,stdout=StringIO())
        call_command('organize_product_catalog',apply=True,stdout=StringIO())
        self.product.refresh_from_db();self.assertEqual(self.product.category.slug,'clothing-tops-shirts')
        self.assertEqual(self.client.get('/api/ecommerce/products/?category=large-products').data['count'],1)
        self.red.refresh_from_db();self.assertEqual(self.red.price,Decimal('100'))


class SourceOptionTests(TestCase):
    databases={'default','ecommerce'}
    setUp=fixtures.SourcePublicationTests.setUp

    def test_description_sizes_are_required_and_preserved_without_fabricated_variants(self):
        publish_source(self.source.pk)
        product=Product.objects.get()
        product.variants.update(option1_name='',option1_value='',option2_name='',option2_value='',option3_name='',option3_value='')
        self.source.variants=[]
        self.source.description='<p>সাইজ: M, L, XL, XXL</p><p>Size Measurement: M = Chest: 39&quot; | Length: 27&quot;</p>'
        self.source.save()
        client=APIClient()
        detail=client.get('/api/ecommerce/products/'+product.slug+'/').data
        self.assertEqual(detail['description_sizes'],['M','L','XL','XXL'])
        self.assertTrue(detail['purchasable'])
        variant=product.variants.get()
        self.assertEqual(client.post('/api/ecommerce/cart/',{'variant_id':variant.pk},format='json').status_code,409)
        self.assertEqual(client.post('/api/ecommerce/cart/',{'variant_id':variant.pk,'requested_size':'XXXL'},format='json').status_code,409)
        response=client.post('/api/ecommerce/cart/',{'variant_id':variant.pk,'requested_size':'L'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        cart=response.data
        self.assertEqual(cart['items'][0]['requested_size'],'L')
        second=client.post('/api/ecommerce/cart/'+cart['token']+'/',{'variant_id':variant.pk,'requested_size':'M'},format='json')
        self.assertEqual(second.status_code,200,second.data)
        self.assertEqual(len(second.data['items']),2)
        changed=client.patch('/api/ecommerce/cart/'+cart['token']+'/',{'item_id':cart['items'][0]['id'],'variant_id':variant.pk,'requested_size':'XL'},format='json')
        self.assertEqual(changed.status_code,200,changed.data)
        self.assertEqual({i['requested_size'] for i in changed.data['items']},{'M','XL'})
        self.assertEqual(product.variants.count(),1)
        order=client.post('/api/ecommerce/checkout/',{'cart_token':cart['token'],'customer_name':'Customer','email':'test@example.com',
            'phone':'01710000000','shipping_address':{'country_code':'BD','district':'Dhaka','thana':'Savar','address':'Road 1'},'payment_method':'cod'},format='json')
        self.assertEqual(order.status_code,201,order.data)
        self.assertEqual({i.variant_title for i in OrderItem.objects.all()},{variant.title+' · Size: XL',variant.title+' · Size: M'})

    def test_measurement_chart_sizes_do_not_create_supplier_variant_ids(self):
        from .product_content import description_sizes
        publish_source(self.source.pk)
        product=Product.objects.get()
        product.variants.update(option1_name='',option1_value='',option2_name='',option2_value='',option3_name='',option3_value='')
        self.source.variants=[]
        self.source.description='<p>Size Measurement:</p><p>M — Length 27&quot; | Chest 38&quot;</p><p>L — Length 28&quot; | Chest 40&quot;</p>'
        self.source.save()
        self.assertEqual(description_sizes(product),['M','L'])
        self.assertEqual(product.variants.count(),1)

    def test_old_clear_flag_does_not_bypass_new_missing_source_choices(self):
        publish_source(self.source.pk)
        product=Product.objects.get()
        product.attributes={**product.attributes,'_catalog':{'variant_review':False}}
        product.save()
        product.variants.update(option1_name='',option1_value='',option2_name='',option2_value='',option3_name='',option3_value='')
        response=APIClient().post('/api/ecommerce/cart/',{'variant_id':product.variants.get().pk,'quantity':1},format='json')
        self.assertEqual(response.status_code,409,response.data)

    def test_exact_supplier_siblings_are_options_without_merging_historical_products(self):
        self.source.variants.append({'id':'real-blue-m','color':{'name':'Blue'},'size':{'name':'M'},'stockQuantity':5})
        self.source.save()
        publish_source(self.source.pk)
        products=list(Product.objects.all())
        self.assertEqual(len(products),2)
        detail=APIClient().get('/api/ecommerce/products/'+products[0].slug+'/').data
        self.assertEqual(len(detail['variants']),2)
        self.assertEqual({v['option2_value'] for v in detail['variants']},{'L','M'})

    def test_description_size_list_is_reviewed_not_invented_as_variants(self):
        from .product_content import option_review
        self.source.description='<p>Available sizes: M, L, XL</p>'
        self.assertTrue(option_review(self.source, []))
        self.source.variants=[]
        self.source.description='<p>Size chart</p><p>M - Chest 38</p><p>L - Chest 40</p>'
        self.assertFalse(option_review(self.source, []))
