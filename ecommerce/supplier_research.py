"""Small, persistent staff/assistant research batches. No implicit AI API or quota claim."""
from django.db import transaction
from django.db.models import Case, When, IntegerField
from .models import Supplier, SupplierOffer, SupplierResearchBatch, SupplierResearchItem
from .supplier_service import policy, audit, screen

DB='ecommerce'


def snapshot(batch):
    if not batch:
        return None
    items=list(batch.items.select_related('offer__supplier','offer__current_decision','decision'))
    done=sum(item.status in ('reviewed','needs_data') for item in items)
    return {'id':str(batch.pk), 'status':batch.status, 'supplier_ids':batch.supplier_ids,
        'done':done, 'total':len(items), 'updated_at':batch.updated_at,
        'publication_blocker':'Keep All lists collected products for manual supplier fulfilment. Research approval controls Keep Filtered, not Keep All. Automatic supplier purchasing remains OFF; stock, supplier price and delivery still need confirmation before staff fulfilment.',
        'items':[{'id':i.pk,'offer_id':i.offer_id,'title':i.offer.title,'supplier':i.offer.supplier.name,
                  'url':i.offer.url,'source_price':i.offer.source_price,'state':i.offer.state,'status':i.status,
                  'variant':i.offer.identity.get('variant','Unconfirmed variant'),'availability':i.offer.availability,
                  'quantity':i.offer.quantity,'weight_grams':i.offer.weight_grams,
                  'note':i.note,'decision_state':i.decision.state if i.decision else None,
                  'decision_result': (i.decision or i.offer.current_decision).result if (i.decision or i.offer.current_decision) else None} for i in items]}


@transaction.atomic(using=DB)
def start(actor, supplier_ids=None, size=3):
    # The policy singleton is only a short transaction lock; no network work occurs here.
    config=policy()
    type(config).objects.using(DB).select_for_update().get(pk=config.pk)
    existing=SupplierResearchBatch.objects.using(DB).filter(status__in=['active','paused']).first()
    if existing:
        existing.status='active';existing.actor_id=actor
        existing.save(using=DB,update_fields=['status','actor_id','updated_at'])
        audit('research_resumed',actor,batch_id=str(existing.pk))
        return existing
    suppliers=Supplier.objects.using(DB).filter(enabled=True,terms_confirmed=True)
    if supplier_ids:
        suppliers=suppliers.filter(pk__in=supplier_ids)
    ids=list(suppliers.values_list('pk',flat=True))
    candidates=SupplierOffer.objects.using(DB).filter(supplier_id__in=ids,excluded_reason='',currency='BDT',
        source_price__gt=0,research_item__isnull=True).exclude(state='excluded').exclude(availability__in=['out_of_stock','missing'])
    candidates=candidates.annotate(priority=Case(When(supplier__connector='business_koro',then=0),default=1,output_field=IntegerField()),
        stock_priority=Case(When(availability='in_stock',then=0),default=1,output_field=IntegerField())).order_by('priority','stock_priority','pk')
    offers=list(candidates[:size])
    if not offers:
        raise ValueError('No unreviewed, priced source identities in this scope. Missing source costs must be collected first; do not fabricate a buying price.')
    batch=SupplierResearchBatch.objects.using(DB).create(supplier_ids=ids,actor_id=actor)
    SupplierResearchItem.objects.using(DB).bulk_create([SupplierResearchItem(batch=batch,offer=offer,actor_id=actor) for offer in offers])
    audit('research_started',actor,batch_id=str(batch.pk),offer_ids=[o.pk for o in offers])
    return batch


@transaction.atomic(using=DB)
def update(actor, batch_id, action, item_id=None, note=None, checkpoints=None):
    batch=SupplierResearchBatch.objects.using(DB).select_for_update().get(pk=batch_id)
    if action in ('pause','resume'):
        if batch.status=='completed':
            raise ValueError('This batch is complete. Start the next batch to continue.')
        if action=='pause' and checkpoints:
            for saved in checkpoints:
                item=SupplierResearchItem.objects.using(DB).select_for_update().get(pk=saved['id'],batch=batch)
                if item.status in ('pending','researching'):
                    item.note=saved['note'];item.actor_id=actor
                    if item.note.strip(): item.status='researching'
                    item.save(using=DB)
        batch.status='paused' if action=='pause' else 'active'
    else:
        if batch.status!='active':
            raise ValueError('Resume this batch before editing research checkpoints.')
        item=SupplierResearchItem.objects.using(DB).select_for_update().select_related('offer').get(pk=item_id,batch=batch)
        if item.status in ('reviewed','needs_data'):
            raise ValueError('This checkpoint is complete; its notes and evidence remain saved for review.')
        if note is not None:
            item.note=note
        if action=='save':
            item.status='researching'
        else:
            if not item.note.strip():
                raise ValueError('Record source checks, evidence links and remaining blockers before finishing an item.')
            item.decision=screen(item.offer,actor)
            item.status='reviewed' if item.decision.state=='ready' else 'needs_data'
        item.actor_id=actor;item.save(using=DB)
        if not batch.items.filter(status__in=['pending','researching']).exists():
            batch.status='completed'
    batch.actor_id=actor;batch.save(using=DB,update_fields=['status','actor_id','updated_at'])
    audit('research_'+action,actor,batch_id=str(batch.pk),item_id=item_id,note=note)
    return batch
