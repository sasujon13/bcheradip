import gzip
import json
import tempfile
from pathlib import Path
from decimal import Decimal
from django.test import TestCase,TransactionTestCase
from django.utils import timezone
from .models import Category, Product, ProductVariant, CatalogSyncIdentity
from .catalog_sync import Codec, export_catalog, import_catalog


class CatalogSyncTests(TestCase):
    databases = {'default', 'ecommerce'}

    def setUp(self):
        self.root = Category.objects.create(name='Electronics', slug='electronics')
        self.leaf = Category.objects.create(name='Smartwatches', slug='smartwatches', parent=self.root)
        self.product = Product.objects.create(name='Original name', slug='watch', category=self.leaf, status='active')
        self.variant = ProductVariant.objects.create(product=self.product, sku='watch', price=100, stock=5)

    def test_transfer_remaps_ids_preserves_status_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'catalog.json.gz'
            export_catalog(path)
            old_id = self.product.pk
            ProductVariant.objects.all().delete(); Product.objects.all().delete()
            Category.objects.all().delete(); CatalogSyncIdentity.objects.all().delete()
            Category.objects.create(name='Unrelated department', slug='unrelated')
            imported = import_catalog(path)
            product = Product.objects.get(slug='watch')
            self.assertNotEqual(product.pk, old_id)
            self.assertEqual(product.category.parent.slug, 'electronics')
            self.assertEqual(product.status, 'active')
            self.assertEqual(product.variants.get().price, Decimal('100'))
            self.assertGreater(imported['created'], 0)
            self.assertEqual(import_catalog(path)['created'], 0)
            self.assertEqual(Product.objects.count(), 1)

    def test_stable_identity_survives_slug_change(self):
        codec = Codec()
        before = codec.identity(self.product).uid
        codec.flush()
        Product.objects.filter(pk=self.product.pk).update(slug='renamed-watch')
        self.product.refresh_from_db()
        self.assertEqual(Codec().identity(self.product).uid, before)

    def test_bounded_export_includes_required_parents_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bounded.json.gz'
            export_catalog(path, include_names={'Product'})
            with gzip.open(path, 'rt', encoding='utf-8') as stream:
                rows = [json.loads(line) for line in stream][1:]
            self.assertEqual({row['model'] for row in rows}, {'Category', 'Product'})
            with self.assertRaisesRegex(ValueError, 'unsupported'):
                export_catalog(path, include_names={'Customer'})

    def test_old_inflight_snapshot_does_not_resurrect_a_later_deleted_attribute(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'initial.gz';old=Path(directory)/'inflight.gz';probe=Path(directory)/'probe.gz'
            Product.objects.filter(pk=self.product.pk).update(attributes={'existing':'preserved'},updated_at=timezone.now())
            export_catalog(path);import_catalog(path)
            Product.objects.filter(pk=self.product.pk).update(attributes={'existing':'preserved','marker':'old'},updated_at=timezone.now())
            export_catalog(old)
            Product.objects.filter(pk=self.product.pk).update(attributes={'existing':'preserved','marker':'new'},updated_at=timezone.now())
            export_catalog(probe);import_catalog(probe)
            Product.objects.filter(pk=self.product.pk).update(attributes={'existing':'preserved'},updated_at=timezone.now())
            import_catalog(old)
            self.product.refresh_from_db()
            self.assertEqual(self.product.attributes,{'existing':'preserved'})

    def test_newly_supported_collection_items_backfill_after_existing_checkpoint(self):
        from datetime import timedelta
        from .models import Supplier, SupplierRecollectionRun, SupplierRecollectionItem
        supplier = Supplier.objects.create(name='Collection source', website='https://collection.example')
        run = SupplierRecollectionRun.objects.create(supplier=supplier, mode='full')
        item = SupplierRecollectionItem.objects.create(run=run, source_key='original-key',
            external_id='original-id', url='https://collection.example/product', status='failed',
            error='Original page unavailable')
        cutoff = timezone.now()
        SupplierRecollectionItem.objects.filter(pk=item.pk).update(updated_at=cutoff-timedelta(days=2))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'items.gz'
            export_catalog(path, since=cutoff)
            with gzip.open(path, 'rt') as stream:
                rows = [json.loads(line) for line in stream][1:]
            self.assertEqual(sum(r['model']=='SupplierRecollectionItem' for r in rows), 1)
            # Export alone does not advance a received baseline.
            export_catalog(path, since=cutoff)
            with gzip.open(path, 'rt') as stream:
                self.assertIn('SupplierRecollectionItem', stream.read())
            SupplierRecollectionItem.objects.all().delete()
            SupplierRecollectionRun.objects.all().delete()
            Supplier.objects.all().delete()
            CatalogSyncIdentity.objects.filter(model_name__in=('Supplier','SupplierRecollectionRun','SupplierRecollectionItem')).delete()
            import_catalog(path)
            imported = SupplierRecollectionItem.objects.get()
            self.assertEqual(imported.error, 'Original page unavailable')
            self.assertEqual(imported.run.supplier.website, 'https://collection.example')
            self.assertEqual(import_catalog(path)['created'], 0)
            export_catalog(path, since=timezone.now()+timedelta(days=1))
            with gzip.open(path, 'rt') as stream:
                self.assertNotIn('SupplierRecollectionItem', stream.read())

    def test_regular_sync_skips_old_collection_checks_but_includes_new_changes(self):
        from datetime import timedelta
        from .models import Supplier, SupplierRecollectionRun, SupplierRecollectionItem
        supplier = Supplier.objects.create(name='Collection source', website='https://collection.example')
        run = SupplierRecollectionRun.objects.create(supplier=supplier, mode='full')
        item = SupplierRecollectionItem.objects.create(run=run, source_key='old-check',
            external_id='old', url='https://collection.example/product', status='failed')
        cutoff = timezone.now()
        SupplierRecollectionItem.objects.filter(pk=item.pk).update(updated_at=cutoff-timedelta(days=2))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'recent.gz'
            export_catalog(path, since=cutoff, backfill_collection_items=False)
            with gzip.open(path, 'rt', encoding='utf-8') as stream:
                self.assertNotIn('SupplierRecollectionItem', stream.read())
            SupplierRecollectionItem.objects.filter(pk=item.pk).update(updated_at=timezone.now())
            export_catalog(path, since=cutoff, backfill_collection_items=False)
            with gzip.open(path, 'rt', encoding='utf-8') as stream:
                self.assertIn('SupplierRecollectionItem', stream.read())

    def test_legacy_identity_alias_reuses_evidence_and_preserves_precise_dates(self):
        import uuid
        from .models import Supplier,SupplierOffer,SupplierEvidence
        supplier=Supplier.objects.create(name='Alias supplier',website='https://alias.example')
        offer=SupplierOffer.objects.create(supplier=supplier,external_id='alias',title='Alias product',url='https://alias.example/product')
        observed=timezone.now().replace(microsecond=123456)
        evidence=SupplierEvidence.objects.create(offer=offer,seller='Seller',marketplace='Shop',url='https://shop.example/product',price=100,observed_at=observed,actor_id=1)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'alias.gz'
            export_catalog(path)
            with gzip.open(path,'rt') as stream:rows=[json.loads(line) for line in stream]
            row=next(row for row in rows[1:] if row['model']=='SupplierEvidence')
            self.assertIn('123456',row['fields']['observed_at'])
            old_uid=row['uid'];new_uid=str(uuid.uuid5(uuid.NAMESPACE_URL,'legacy rounded evidence'))
            row['uid']=new_uid
            with gzip.open(path,'wt') as stream:
                for row in rows:stream.write(json.dumps(row)+'\n')
            import_catalog(path)
            self.assertEqual(SupplierEvidence.objects.count(),1)
            self.assertEqual(CatalogSyncIdentity.objects.filter(model_name='SupplierEvidence').count(),1)
            codec=Codec()
            self.assertEqual(codec.by_uid[old_uid].object_pk,str(evidence.pk))
            self.assertEqual(codec.by_uid[new_uid].object_pk,str(evidence.pk))
            self.assertEqual(codec.uid(codec.identity(evidence)),min(old_uid,new_uid))

    def test_edit_made_after_export_is_not_falsely_marked_as_already_sent(self):
        with tempfile.TemporaryDirectory() as directory:
            old=Path(directory)/'old.gz';new=Path(directory)/'new.gz'
            export_catalog(old)
            old_time=self.product.updated_at
            self.product.name='Changed while sync was running';self.product.save()
            import_catalog(old)
            self.product.refresh_from_db();self.assertEqual(self.product.name,'Changed while sync was running')
            export_catalog(new)
            # Simulate the other node, which only received the old snapshot.
            Product.objects.filter(pk=self.product.pk).update(name='Original name',updated_at=old_time)
            import_catalog(new)
            self.product.refresh_from_db();self.assertEqual(self.product.name,'Changed while sync was running')

    def test_shared_source_stock_keeps_receiving_orders_reserved(self):
        from .models import Supplier, SupplierOffer, Order, OrderItem
        from .catalog_sync import reconcile_received_stock
        supplier=Supplier.objects.create(name='Test supplier',website='https://supplier.example')
        self.product.attributes={'manual_supplier_catalogue':True};self.product.save()
        SupplierOffer.objects.create(supplier=supplier,external_id='stock-test',title='Stock test',
            url='https://supplier.example/product',imported_product=self.product,quantity=5,availability='in_stock')
        order=Order.objects.create(customer_name='Synthetic',email='test@example.test',phone='01700000000',status='confirmed')
        OrderItem.objects.create(order=order,product_id=self.product.pk,variant_id=self.variant.pk,
            product_name='Watch',sku=self.variant.sku,quantity=2,unit_price=100,line_total=200)
        ProductVariant.objects.filter(pk=self.variant.pk).update(stock=999)
        reconcile_received_stock([self.variant.pk])
        self.variant.refresh_from_db();self.assertEqual(self.variant.stock,3)
        order.status='cancelled';order.save()
        reconcile_received_stock([self.variant.pk])
        self.variant.refresh_from_db();self.assertEqual(self.variant.stock,5)

    def test_independent_field_changes_merge_and_customer_models_are_not_exported(self):
        with tempfile.TemporaryDirectory() as directory:
            initial = Path(directory) / 'initial.gz'
            export_catalog(initial); import_catalog(initial)
            outgoing = Path(directory) / 'changed.gz'
            self.product.name = 'New name'; self.product.save()
            export_catalog(outgoing)
            Product.objects.filter(pk=self.product.pk).update(name='Original name', short_description='Other side edit', updated_at=timezone.now())
            import_catalog(outgoing)
            self.product.refresh_from_db()
            self.assertEqual(self.product.name, 'New name')
            self.assertEqual(self.product.short_description, 'Other side edit')
            with gzip.open(outgoing, 'rt') as stream:
                rows = [json.loads(line) for line in stream][1:]
            self.assertFalse({'Order', 'Payment', 'Customer', 'Cart'} & {r['model'] for r in rows})
            self.assertTrue(all('credentials_ciphertext' not in r['fields'] for r in rows))


class CatalogSyncCommitTests(TransactionTestCase):
    databases={'default','ecommerce'}

    def test_interrupted_batch_keeps_checkpoint_and_retry_finishes_staged_products(self):
        category=Category.objects.create(name='Department',slug='department')
        leaf=Category.objects.create(name='Product type',slug='product-type',parent=category)
        Product.objects.bulk_create([Product(name=f'Item {n}',slug=f'item-{n}',category=leaf,status='active') for n in range(210)])
        with tempfile.TemporaryDirectory() as directory:
            good=Path(directory)/'good.gz';bad=Path(directory)/'bad.gz'
            export_catalog(good)
            with gzip.open(good,'rt') as stream:rows=[json.loads(line) for line in stream]
            rows[201]={**rows[201],'model':'RefusedModel'}
            with gzip.open(bad,'wt') as stream:
                for row in rows:stream.write(json.dumps(row)+'\n')
            Product.objects.all().delete();Category.objects.all().delete();CatalogSyncIdentity.objects.all().delete()
            with self.assertRaises(ValueError):import_catalog(bad)
            self.assertEqual(Product.objects.count(),198)
            self.assertFalse(Product.objects.filter(status='active').exists())
            import_catalog(good,after_record=200)
            self.assertEqual(Product.objects.count(),210)
            self.assertEqual(Product.objects.filter(status='active').count(),210)
