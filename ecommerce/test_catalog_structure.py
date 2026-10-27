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
    def test_taxonomy_proposal_is_two_levels_and_does_not_guess_unknown_products(self):
        from .taxonomy_proposal import candidates
        self.assertEqual(candidates('Ven-Dens 10000mAh Power Bank'), [('Electronics', 'Power Banks')])
        self.assertEqual(candidates('Premium unknown item'), [])
        self.assertEqual(candidates('Hoodie', 'Gender: Male and Female'),
                         [("Men's Fashion", 'Hoodies'), ("Women's Fashion", 'Hoodies')])
        self.assertEqual(candidates('Baby Hoodie'), [('Kids & Baby', "Children's Hoodies")])
        self.assertEqual(candidates('Saree'), [("Women's Fashion", 'Sarees')])

    def test_children_and_matching_sets_are_not_adult_tops(self):
        self.assertEqual(classify('Elegant Stylish Baby Hoodie Set')['path'], ['Kids & Toys', 'Children’s Clothing'])
        self.assertEqual(classify('Premium Kids Sherpa Padding Jacket')['path'], ['Kids & Toys', 'Children’s Clothing'])
        self.assertEqual(classify('Cotton T-shirt and Trouser Set')['path'], ['Clothing', 'Matching Sets'])
        self.assertEqual(classify('Mash T-Shirt and Short Pant Set')['path'], ['Clothing', 'Matching Sets'])

    def test_supplier_size_formats_do_not_turn_measurements_into_choices(self):
        from types import SimpleNamespace
        from .product_content import description_sizes
        cases = [
            ('<p>সাইজ ৩৬/৩৮/৪০/৪২/৪৪/৪৬</p>', ['36','38','40','42','44','46']),
            ('<p>সাইজ ডিটেইলসঃ</p><p>M=38</p><p>L=42</p><p>XL=46</p>', ['M','L','XL']),
            ('<p>Body size = M=36-38, L=40-42, XL=44-46</p>', ['M','L','XL']),
            ('<p>Free size 36-46 inches. Unstitched fabric.</p>', []),
            ('<p>T-Shirt Size: M, L, XL</p>', ['M', 'L', 'XL']),
            ('<p>-M Size • Length: 38" • Waist: 30–33"</p><p>-L Size • Length: 39" • Waist: 32–35"</p>', ['M', 'L']),
            ('<p>Hoodie Size:</p><p>2-3Y = Chest 24" Length 16"</p><p>4–5Y= chest 26" long 18"</p><p>10-11 = Chest 36" Length 21"</p>', ['2-3Y', '4-5Y', '10-11']),
            ('<p>6M = Sweetshirt Length &gt; 14", Chest &gt; 11"</p><p>1-2Y = Sweet-shirt Length &gt; 15", Chest &gt; 12"</p>', ['6M', '1-2Y']),
            ('<p>📏সাইজঃ M, L, XL</p><p>M = Body-40 | Long-28</p>', ['M', 'L', 'XL']),
            ('<p>𝐒𝐢𝐳𝐞 𝐃𝐞𝐭𝐚𝐢𝐥𝐬: M, L, XL,XXL</p>', ['M', 'L', 'XL', 'XXL']),
            ('<p>Available Sizes: M, L, XL, 2XL</p>', ['M', 'L', 'XL', '2XL']),
            ('<p>🔹 *M* → Chest 40&quot; | Length 28&quot;</p><p>🔹 *L* → Chest 42&quot; | Length 29&quot;</p>', ['M', 'L']),
            ('<p>For ages 2-12 years. Length: 28. Waist: 30–33.</p>', []),
            ('<p>Storage 6M. Cable Length: 2-3Y.</p>', []),
        ]
        for description, expected in cases:
            with self.subTest(description=description):
                source = SimpleNamespace(description=description, specifications={}, extra={}, features=[])
                self.assertEqual(description_sizes(SimpleNamespace(_content_source=source), []), expected)

    def test_bengali_color_choices_preserve_combining_marks(self):
        from types import SimpleNamespace
        from .product_content import description_colors
        source = SimpleNamespace(title='Rajeshwari Katan Saree', specifications={}, extra={}, features=[],
                                 description='<p>🌸 দুইটি আকর্ষণীয় কালার: পিংক ও নীল</p>')
        product = SimpleNamespace(_content_source=source)
        self.assertEqual(description_colors(product, []), [])
        from .product_content import color_interpretation
        self.assertEqual(color_interpretation(product)['label'], 'Pink & Blue')
        self.assertTrue(color_interpretation(product)['needs_review'])
        product.attributes = {'_catalog': {'color_decision': {'mode': 'separate', 'choices': ['Pink', 'Blue']}}}
        self.assertEqual(description_colors(product, []), ['Pink', 'Blue'])
        self.assertFalse(color_interpretation(product)['needs_review'])
        product.attributes = {'_catalog': {'color_decision': {'mode': 'mixed', 'label': 'Pink & Blue'}}}
        self.assertEqual(description_colors(product, []), [])
        product.attributes = {}
        source.description = '<p>নীল আর গোলাপি রঙের অপূর্ব মেলবন্ধনে তৈরি শাড়ি</p>'
        self.assertEqual(description_colors(product, []), [])

    def test_saree_and_three_piece_are_not_clocks(self):
        self.assertEqual(classify('Puja Special Saree নিয়ে এলাম')['path'], ['Clothing', 'Ethnic Wear', 'Sarees'])
        self.assertEqual(classify('Sequence Embroidery Three Piece নিয়ে এলাম')['path'], ['Clothing', 'Ethnic Wear', 'Salwar Kameez'])
    def test_generic_size_categories_are_not_classification_evidence(self):
        self.assertEqual(classify('Cotton Hoodie', ['Extra Large'])['path'], ['Clothing','Tops','Hoodies & Sweatshirts'])
        self.assertEqual(classify("Gent's Sweetshirt", ['All Products'])['path'], ['Clothing','Tops','Hoodies & Sweatshirts'])
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
        # Simulate a pre-normalization legacy row; new saves reject level 3.
        self.leaf=Category.objects.bulk_create([Category(name='Shirts',slug='clothing-tops-shirts',parent=self.middle)])[0]
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

    def test_secondary_category_filters_and_department_counts_are_distinct(self):
        secondary = Category.objects.create(name='Casual Shirts', slug='casual-shirts', parent=self.root)
        self.product.secondary_categories.add(secondary)
        listing = self.client.get('/api/ecommerce/products/?category=casual-shirts').data
        self.assertEqual(listing['count'], 1)
        self.assertEqual(self.client.get('/api/ecommerce/products/?category=clothing').data['count'], 1)
        categories = self.client.get('/api/ecommerce/categories/').data
        self.assertEqual(next(c for c in categories if c['id'] == self.root.pk)['product_count'], 1)
        self.assertEqual(next(c for c in categories if c['id'] == secondary.pk)['product_count'], 1)

    def test_admin_rejects_new_third_level_categories(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.leaf.clean()

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
        self.product.refresh_from_db();self.assertEqual(self.product.category.slug,'clothing-fashion-shirts')
        self.assertEqual(self.client.get('/api/ecommerce/products/?category=large-products').data['count'],1)
        self.red.refresh_from_db();self.assertEqual(self.red.price,Decimal('100'))

    def test_normalizer_snapshots_and_preserves_status_price_and_manual_category(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            call_command('normalize_storefront_taxonomy', report=str(Path(folder)/'preview.json'), stdout=StringIO())
            self.product.refresh_from_db()
            self.assertEqual(self.product.category_id, self.leaf.pk)
            call_command('normalize_storefront_taxonomy', apply=True, report=str(Path(folder)/'apply.json'), stdout=StringIO())
            self.product.refresh_from_db(); self.red.refresh_from_db()
            self.assertEqual(self.product.category.name, 'Casual Shirts')
            self.assertEqual(self.product.status, 'active')
            self.assertEqual(self.red.price, Decimal('100'))
            self.assertFalse(Category.objects.filter(parent__parent__isnull=False).exists())
            self.assertEqual(self.client.get('/api/ecommerce/products/?category=clothing-tops-shirts').data['count'], 1)


class SourceOptionTests(TestCase):
    databases={'default','ecommerce'}
    setUp=fixtures.SourcePublicationTests.setUp

    def test_reviewed_description_choices_release_old_listing_and_variant_hold(self):
        publish_source(self.source.pk)
        product = Product.objects.get()
        product.variants.update(option1_name='', option1_value='', option2_name='', option2_value='')
        self.source.variants = []
        self.source.description = '<p>T-Shirt Size: M, L, XL</p>'
        self.source.save()
        product.attributes = {**product.attributes, '_catalog': {'variant_review': True}}
        product.save()
        call_command('resolve_catalog_choices', through_id=product.pk, stdout=StringIO())
        product.refresh_from_db()
        self.assertTrue(product.attributes['_catalog']['variant_review'])
        call_command('resolve_catalog_choices', through_id=product.pk, apply=True, stdout=StringIO())
        product.refresh_from_db()
        self.assertFalse(product.attributes['_catalog']['variant_review'])
        detail = APIClient().get('/api/ecommerce/products/' + product.slug + '/').data
        self.assertEqual(detail['description_sizes'], ['M', 'L', 'XL'])
        self.assertTrue(all(v['purchasable'] for v in detail['variants']))
        self.source.description = '<p>Supplier has not supplied size choices.</p>'
        self.source.save()
        product.attributes['_catalog']['variant_review'] = True
        product.save()
        call_command('resolve_catalog_choices', through_id=product.pk, apply=True, stdout=StringIO())
        product.refresh_from_db()
        self.assertTrue(product.attributes['_catalog']['variant_review'])

    def test_explicit_color_and_size_choices_remain_distinct_through_order(self):
        publish_source(self.source.pk)
        product=Product.objects.get()
        product.variants.update(option1_name='',option1_value='',option2_name='',option2_value='',option3_name='',option3_value='')
        self.source.variants=[]
        self.source.description='<p>Color: Red, Blue, Green</p><p>Size: M, L, XL, XXL</p>'
        self.source.save()
        client=APIClient()
        detail=client.get('/api/ecommerce/products/'+product.slug+'/').data
        self.assertEqual(detail['description_colors'], ['Red','Blue','Green'])
        self.assertEqual(detail['description_sizes'], ['M','L','XL','XXL'])
        variant=product.variants.get()
        self.assertEqual(client.post('/api/ecommerce/cart/',{'variant_id':variant.pk,'requested_size':'M'},format='json').status_code,409)
        first=client.post('/api/ecommerce/cart/',{'variant_id':variant.pk,'requested_size':'M','requested_color':'Red'},format='json')
        self.assertEqual(first.status_code,200,first.data)
        token=first.data['token']
        second=client.post('/api/ecommerce/cart/'+token+'/',{'variant_id':variant.pk,'requested_size':'M','requested_color':'Blue'},format='json')
        self.assertEqual(second.status_code,200,second.data)
        self.assertEqual(len(second.data['items']),2)
        changed=client.patch('/api/ecommerce/cart/'+token+'/',{'item_id':second.data['items'][0]['id'],'variant_id':variant.pk,'requested_color':'Green'},format='json')
        self.assertEqual(changed.status_code,200,changed.data)
        order=client.post('/api/ecommerce/checkout/',{'cart_token':token,'customer_name':'Customer','email':'test@example.com',
            'phone':'01710000000','shipping_address':{'country_code':'BD','district':'Dhaka','thana':'Savar','address':'Road 1'},'payment_method':'cod'},format='json')
        self.assertEqual(order.status_code,201,order.data)
        self.assertEqual({i.variant_title for i in OrderItem.objects.all()},
                         {variant.title+' · Color: Green · Size: M', variant.title+' · Color: Blue · Size: M'})

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
