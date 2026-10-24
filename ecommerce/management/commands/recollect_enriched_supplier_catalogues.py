"""Finite, resumable owner-requested reinspection/full recollection. No supplier purchases."""
import json
from pathlib import Path
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand,CommandError
from django.utils import timezone
from ecommerce.models import Supplier,SupplierRecollectionRun
from ecommerce.supplier_source_clients import SUPPLIER_IDS
from ecommerce.supplier_recollection import MAPPING_VERSION

SITES=('business_koro','uddoog','dropshipping','selfshop','dropify','dropbazar','shopbase','resellkori')


def publication_counts(run):
    coverage=run.coverage or {}
    counts=dict(coverage.get('publication',{}).get('counts_this_attempt',{}))
    # A bounded, audited follow-up can resolve original holds without rewriting
    # the historical release result or pretending the whole catalogue was rerun.
    followup=coverage.get('publication_followup',{})
    resolved=len(set(followup.get('resolved_source_ids',[])))
    if resolved:
        counts['held_sources']=max(0,counts.get('held_sources',0)-resolved)
        counts['published']=counts.get('published',0)+followup.get('counts',{}).get('published',0)
    return counts


class Command(BaseCommand):
    help='Reinspect then fully recollect each authorised supplier with the current mapper; use --apply explicitly. No real orders.'

    def add_arguments(self,parser):
        parser.add_argument('--apply',action='store_true')
        parser.add_argument('--supplier',choices=SITES,help='Optional one-supplier scope; default all eight.')

    def handle(self,*args,**options):
        sites=(options['supplier'],) if options['supplier'] else SITES
        if not options['apply']:
            self.stdout.write(json.dumps({'scope':sites,'mapping_version':MAPPING_VERSION,'dry_run':True,
                'disabled_suppliers_skipped':True,'supplier_purchasing':False}));return
        root=Path(settings.BASE_DIR)/'private_suppliers'/'recollection'
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        path=root/f'recollection-v{MAPPING_VERSION}-state.json'
        state=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'version':MAPPING_VERSION,'suppliers':{}}
        def save():
            state['updated_at']=timezone.now().isoformat()
            temporary=path.with_suffix('.pending')
            temporary.write_text(json.dumps(state,indent=2),encoding='utf-8');temporary.replace(path)
        # Inspect EVERY accessible supplier before any new full catalogue starts.
        for mode in ('inspect','full'):
            for site in sites:
                supplier=Supplier.objects.using('ecommerce').get(pk=SUPPLIER_IDS[site])
                item=state['suppliers'].setdefault(site,{})
                if not supplier.enabled or not supplier.terms_confirmed:
                    item.update(status='blocked',reason='Supplier access disabled or terms unconfirmed; no request made.');save();continue
                if item.get('status') in ('completed','completed_with_holds'):
                    # Earlier coordinator versions recorded traversal completion
                    # without distinguishing a successful release with holds.
                    previous=SupplierRecollectionRun.objects.using('ecommerce').filter(pk=item.get('full_run')).first()
                    counts=publication_counts(previous) if previous else {}
                    if counts.get('held') or counts.get('held_sources'):
                        item.update(status='completed_with_holds',publication_counts=counts,
                            reason='Original catalogue saved; some items remain held for source/content/identity review.');save()
                    elif previous and previous.status=='completed' and site!='selfshop':
                        item.update(status='completed',publication_counts=counts,reason='');save()
                    continue
                try:
                    if mode=='full':
                        inspected=SupplierRecollectionRun.objects.using('ecommerce').filter(
                            pk=item.get('inspect_run'),status='completed',processed__gte=3,mapping_version=MAPPING_VERSION).exists()
                        if not inspected:continue
                    saved_id=item.get(mode+'_run')
                    run=SupplierRecollectionRun.objects.using('ecommerce').filter(pk=saved_id).first() if saved_id else None
                    finished=run and (run.status=='completed' if mode=='inspect' else
                        run.status in ('completed','completed_with_errors') and run.coverage.get('full_traversal'))
                    if not finished:
                        item.update(status=mode,started_at=timezone.now().isoformat());save()
                        params={'supplier':site,'mode':mode,'use_saved_credentials':True,'public_only':site=='selfshop',
                                'stdout':self.stdout,'stderr':self.stderr}
                        if run and run.status in ('failed','paused','completed_with_errors'):params['run_id']=str(run.pk)
                        try:call_command('recollect_supplier_catalogue',**params)
                        finally:
                            latest=SupplierRecollectionRun.objects.using('ecommerce').filter(supplier=supplier,mode=mode,
                                mapping_version=MAPPING_VERSION).order_by('-created_at').first()
                            if latest:item[mode+'_run']=str(latest.pk);save()
                        run=latest
                    if mode=='inspect' and (not run or run.status!='completed' or run.processed<3):
                        raise CommandError('Three complete current-version sample inspections are required before full traversal.')
                    if mode=='full':
                        if site!='selfshop':
                            item['status']='publishing';save()
                            call_command('publish_fresh_supplier_catalogue',run_id=str(run.pk),apply=True,resume=True,stdout=self.stdout,stderr=self.stderr)
                        run.refresh_from_db(using='ecommerce')
                        counts=publication_counts(run)
                        held=site=='selfshop' or run.status=='completed_with_errors' or counts.get('held') or counts.get('held_sources')
                        reason=('Private source data collected; buying prices remain unverified.' if site=='selfshop' else
                            'Original catalogue saved; some items remain held for source/content/identity review.' if held else '')
                        item.update(status='completed_with_holds' if held else 'completed',publication_counts=counts,
                            finished_at=timezone.now().isoformat(),reason=reason)
                    else:item['status']='inspected'
                except (CommandError,ValueError) as exc:
                    item.update(status='failed',reason=str(exc)[:500])
                    self.stderr.write(f'{site}: stopped safely; saved checkpoint retained. Other authorised suppliers can continue.')
                save()
        self.stdout.write(json.dumps(state,ensure_ascii=True))
