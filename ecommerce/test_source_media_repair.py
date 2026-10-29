from django.test import TestCase
from django.utils import timezone
from . import test_supplier_source_publish as fixtures
from .models import SupplierRecollectionRun
from .source_media_repair import repair_media_membership


class SourceMediaMembershipTests(TestCase):
    databases={'default','ecommerce'}
    setUp=fixtures.SourcePublicationTests.setUp
    def test_repair_requires_the_exact_original_url_and_keeps_real_byte_check_date(self):
        media=self.source.media.get();old_run=media.last_run_id
        media.metadata={'verified_image':True,'verified_at':'2026-10-01T00:00:00Z'};media.save()
        run=SupplierRecollectionRun.objects.create(supplier=self.supplier,mode='full',status='completed')
        self.source.last_run=run;self.source.raw_data={'product':{'images':[{'url':media.original_url}]}}
        self.source.observed_at=timezone.now();self.source.save()
        self.assertEqual(repair_media_membership()['proven_current_reference'],1)
        self.assertEqual(repair_media_membership(apply=True)['repaired'],1)
        media.refresh_from_db()
        self.assertEqual(media.last_run_id,run.pk)
        self.assertEqual(media.metadata['verified_at'],'2026-10-01T00:00:00Z')
        self.assertEqual(repair_media_membership(apply=True)['repaired'],0)

    def test_missing_reference_never_promotes_an_old_gallery(self):
        run=SupplierRecollectionRun.objects.create(supplier=self.supplier,mode='full',status='completed')
        self.source.last_run=run;self.source.raw_data={'product':{'images':['https://cdn.businesskoro.com/other.jpg']}};self.source.save()
        result=repair_media_membership(apply=True)
        self.assertEqual(result['repaired'],0);self.assertEqual(result['unproven_held'],1)

    def test_sync_byte_cache_timestamp_does_not_replace_a_newer_gallery_observation(self):
        import gzip
        import json
        import tempfile
        from datetime import timedelta
        from pathlib import Path
        from .catalog_sync import export_catalog, import_catalog
        from .models import SupplierSourceMedia
        media=self.source.media.get()
        old_seen=timezone.now()-timedelta(days=2)
        SupplierSourceMedia.objects.filter(pk=media.pk).update(last_seen_at=old_seen)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'old-gallery.gz'
            export_catalog(path)
            with gzip.open(path,'rt') as stream:rows=[json.loads(line) for line in stream]
            row=next(r for r in rows[1:] if r['model']=='SupplierSourceMedia')
            # A remote image-byte check happened later, but its source gallery
            # membership still refers to the old run.
            row['updated_at']=(timezone.now()+timedelta(minutes=1)).isoformat()
            with gzip.open(path,'wt') as stream:
                for entry in rows:stream.write(json.dumps(entry)+'\n')
            current=SupplierRecollectionRun.objects.create(supplier=self.supplier,mode='full',status='completed')
            new_seen=timezone.now()
            SupplierSourceMedia.objects.filter(pk=media.pk).update(last_run=current,last_seen_at=new_seen,position=2)
            import_catalog(path)
            media.refresh_from_db()
            self.assertEqual(media.last_run_id,current.pk)
            self.assertEqual(media.last_seen_at,new_seen)
            self.assertEqual(media.position,2)
