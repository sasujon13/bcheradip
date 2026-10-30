"""Resumable browser-only SelfShop buying-price repair."""
import json
import os
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from ecommerce.models import SupplierSourceProduct
from ecommerce.price_ensure import SAMPLES
from ecommerce.supplier_price_probe import run_probe


class Command(BaseCommand):
    help = 'Revisit every stored SelfShop page and use its visible Price as buying cost. Safe to resume.'

    def add_arguments(self, parser):
        parser.add_argument('--resume', action='store_true')
        parser.add_argument('--limit', type=int)

    def handle(self, *args, **options):
        folder=Path(settings.BASE_DIR)/'private_suppliers'/'catalog_sync'
        folder.mkdir(parents=True,exist_ok=True)
        path=folder/'selfshop-price-recollection.json'
        state=json.loads(path.read_text(encoding='utf-8')) if options['resume'] and path.exists() else {
            'started_at':timezone.now().isoformat(),'rows':[]}
        done={r['source_id'] for r in state['rows'] if r.get('extraction_ok') or 'Product Not Found' in r.get('error','')}
        sample=next(s for s in SAMPLES if s['site']=='selfshop')
        targets=[{**sample,'url':s.url,'source_id':s.pk} for s in
            SupplierSourceProduct.objects.using('ecommerce').filter(supplier_id=4).order_by('pk')
            if s.pk not in done]
        if options['limit']:
            targets=targets[:max(1,options['limit'])]
        state.update(status='running',total=SupplierSourceProduct.objects.using('ecommerce').filter(supplier_id=4).count())

        def save():
            state.update(updated_at=timezone.now().isoformat(),processed=sum(bool(r.get('extraction_ok')) for r in state['rows']),
                         checked=len(state['rows']),unavailable=sum('Product Not Found' in r.get('error','') for r in state['rows']))
            tmp=path.with_suffix('.tmp')
            tmp.write_text(json.dumps(state,ensure_ascii=False),encoding='utf-8')
            os.replace(tmp,path)

        def progress(row):
            source=row['source_id']
            state['rows']=[r for r in state['rows'] if r.get('source_id')!=source]
            state['rows'].append({**row,'source_id':source})
            save()
        save()
        try:
            if targets:
                run_probe('selfshop',targets,progress)
            state['status']='completed' if state['processed']==state['total'] else 'completed_with_errors'
        except Exception as exc:
            state.update(status='failed',error=type(exc).__name__+': browser sign-in or access needs review')
        finally:
            save()
        self.stdout.write(json.dumps({k:state.get(k) for k in ('status','total','processed','error')}))
