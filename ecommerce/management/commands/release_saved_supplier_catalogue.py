"""Checkpointed owner-requested release of complete original supplier content."""
import json
from collections import Counter
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from ecommerce.models import SupplierSourceProduct
from ecommerce.supplier_source_repair import restore_observations
from ecommerce.supplier_source_publish import publish_source


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--after-source-id',type=int,default=0)
        parser.add_argument('--limit',type=int,default=0)
        parser.add_argument('--apply',action='store_true')
        parser.add_argument('--resume',action='store_true')

    def handle(self,*args,**options):
        path=Path(settings.BASE_DIR)/'private_suppliers/recollection/saved-release.json'
        previous=json.loads(path.read_text()) if options['resume'] and path.exists() else {}
        after=max(options['after_source_id'],previous.get('last_source_id',0))
        qs=SupplierSourceProduct.objects.using('ecommerce').filter(pk__gt=after,supplier__enabled=True,
            supplier_id__in=(1,2,3,6,7,8,9)).order_by('pk')
        if options['limit']: qs=qs[:options['limit']]
        counts,failures,last=Counter(),[],after
        def save():
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps({'last_source_id':last,'counts':counts,'failures':failures[-100:]},ensure_ascii=False))
        # Bounded iteration; successful transactions survive a later interruption.
        for source in qs.iterator(chunk_size=50):
            if options['apply']:
                counts['observations_restored']+=restore_observations(source.pk)
                try: counts.update(publish_source(source.pk))
                except (ValueError,OSError) as exc:
                    counts['held_sources']+=1
                    failures.append({'source_id':source.pk,'reason':str(exc)[:250]})
            counts['processed']+=1;last=source.pk
            if counts['processed']%25==0:
                if options['apply']: save()
                self.stdout.write(json.dumps({'last_source_id':last,'counts':counts}));self.stdout.flush()
        if options['apply']: save()
        self.stdout.write(json.dumps({'last_source_id':last,'counts':counts,'held_samples':failures[-10:]}))
