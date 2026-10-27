"""Restore labelled price/stock observations without downloading or publishing."""
import json
import time
from django.db import OperationalError
from django.core.management.base import BaseCommand
from ecommerce.models import SupplierSourceProduct
from ecommerce.supplier_source_repair import restore_observations


class Command(BaseCommand):
    def add_arguments(self,parser):
        parser.add_argument('--supplier-id',type=int)
        parser.add_argument('--after-source-id',type=int,default=0)

    def handle(self,*args,**options):
        qs=SupplierSourceProduct.objects.using('ecommerce').filter(pk__gt=options['after_source_id'],supplier__enabled=True).order_by('pk')
        if options['supplier_id']:qs=qs.filter(supplier_id=options['supplier_id'])
        processed=changed=0;last=options['after_source_id']
        for source_id in qs.values_list('pk',flat=True).iterator(chunk_size=100):
            for attempt in range(3):
                try:
                    changed+=restore_observations(source_id);break
                except OperationalError as exc:
                    if not exc.args or exc.args[0] != 1213 or attempt == 2: raise
                    # The entire atomic observation repair rolled back; retry
                    # that idempotent unit rather than a partially applied row.
                    time.sleep(.2*(attempt+1))
            processed+=1;last=source_id
            if processed%500==0:
                self.stdout.write(json.dumps({'processed':processed,'changed':changed,'last_source_id':last}));self.stdout.flush()
        self.stdout.write(json.dumps({'processed':processed,'changed':changed,'last_source_id':last}))
