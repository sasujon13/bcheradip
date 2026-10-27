import json
from pathlib import Path
from django.core.management.base import BaseCommand
from ecommerce.catalog_equivalents import audit_equivalents,consolidate_group


class Command(BaseCommand):
    help='Audit all supplier records; keep only the lowest purchasable exact duplicate when --apply is explicit.'
    def add_arguments(self,parser):
        parser.add_argument('--apply',action='store_true')
        parser.add_argument('--report',required=True)
    def handle(self,*args,**options):
        result=audit_equivalents()
        if options['apply']:
            from .recollect_supplier_catalogue import database_retry
            for group in result['exact_content_groups']:
                group['result']=database_retry(lambda:consolidate_group(group))
        path=Path(options['report']);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        self.stdout.write(json.dumps({'source_records_checked':result['source_records_checked'],
            'title_review_groups':len(result['same_title_review_groups']),
            'exact_content_groups':len(result['exact_content_groups']),
            'archived':sum(len(g.get('result',{}).get('archived_slugs',[])) for g in result['exact_content_groups']),
            'report':str(path)}))
