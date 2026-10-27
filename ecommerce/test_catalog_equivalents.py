from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from .models import (Supplier,SupplierRecollectionRun,SupplierSourceProduct,SupplierSourceMedia,
    SupplierOffer,Product,ProductImage,ProductVariant,Category,SupplierPolicy)
from .catalog_equivalents import audit_equivalents,consolidate_group,exact_content_key


class EquivalentCatalogueTests(TestCase):
    databases={'default','ecommerce'}
    def setUp(self):
        SupplierPolicy.objects.create(catalogue_mode='all')
        self.category=Category.objects.create(name='Speakers',slug='speakers')
        self.offers=[]
        for i,price in enumerate([100,120]):
            supplier=Supplier.objects.create(name=f'Source {i}',website=f'https://source{i}.example',enabled=True,terms_confirmed=True)
            run=SupplierRecollectionRun.objects.create(supplier=supplier,mode='full',status='completed')
            source=SupplierSourceProduct.objects.create(supplier=supplier,source_key=str(i),external_id=str(i),
                url=f'https://source{i}.example/product',title='Same model speaker',
                description='Manufacturer model S100. Black speaker, single piece, Bluetooth 5.4. One year manufacturer warranty.',
                content_hash='a'*64,quality={'missing':[]},observed_at=timezone.now(),last_run=run)
            media=SupplierSourceMedia.objects.create(product=source,media_key='main',role='main',kind='image',
                original_url=f'https://source{i}.example/photo.jpg',last_seen_at=timezone.now(),last_run=run,
                metadata={'verified_image':True,'sha256':'a'*64})
            p=Product.objects.create(name=source.title,slug=f'speaker-{i}',category=self.category,status='active',
                description=source.description,attributes={'manual_supplier_catalogue':True,'supplier_publication_ready':True})
            ProductImage.objects.create(product=p,source_media=media,url=media.original_url)
            ProductVariant.objects.create(product=p,sku=f'S-{i}',price=200,cost_price=price,stock=2)
            self.offers.append(SupplierOffer.objects.create(supplier=supplier,external_id=str(i),url=source.url,
                title=source.title,source_product=source,imported_product=p,source_price=price,
                currency='BDT',availability='in_stock',quantity=2,single_unit=True,observed_at=timezone.now()))

    def test_lowest_purchasable_copy_wins_without_removing_source_history(self):
        groups=audit_equivalents()['exact_content_groups'];self.assertEqual(len(groups),1)
        result=consolidate_group(groups[0])
        self.assertEqual(result['canonical_slug'],'speaker-0')
        self.assertEqual(result['archived_slugs'],['speaker-1'])
        self.assertEqual(Product.objects.count(),2);self.assertEqual(SupplierOffer.objects.count(),2)
        self.assertEqual(consolidate_group(groups[0])['state'],'already_single')
        self.assertEqual(ProductVariant.objects.get(sku='S-0').price,Decimal('200'))

    def test_unavailable_low_price_does_not_replace_orderable_product(self):
        SupplierOffer.objects.filter(pk=self.offers[0].pk).update(availability='out_of_stock')
        result=consolidate_group(audit_equivalents()['exact_content_groups'][0])
        self.assertEqual(result['canonical_slug'],'speaker-1')

    def test_same_title_different_variants_or_images_are_not_collapsed(self):
        source=self.offers[1].source_product;source.variants=[{'id':'red','color':'Red'}];source.save()
        self.assertIsNone(exact_content_key(source,'a'*64))
        self.assertEqual(audit_equivalents()['exact_content_groups'],[])
        source.variants=[];source.save()
        self.offers[1].identity={'specifications':{'color':'Red'}};self.offers[1].save()
        result=consolidate_group(audit_equivalents()['exact_content_groups'][0])
        self.assertEqual(result['state'],'needs_review')
        self.assertEqual(Product.objects.filter(status='active').count(),2)

    def test_recheck_can_restore_a_cheaper_retained_alternative(self):
        group=audit_equivalents()['exact_content_groups'][0];consolidate_group(group)
        SupplierOffer.objects.filter(pk=self.offers[1].pk).update(source_price=90)
        ProductVariant.objects.filter(product=self.offers[1].imported_product).update(cost_price=90)
        result=consolidate_group(group)
        self.assertEqual(result['canonical_slug'],'speaker-1')
        self.assertEqual(Product.objects.get(slug='speaker-1').status,'active')
        self.assertEqual(Product.objects.get(slug='speaker-0').status,'archived')
