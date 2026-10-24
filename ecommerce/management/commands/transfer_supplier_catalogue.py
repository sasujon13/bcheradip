"""Narrow, empty-target catalogue bootstrap. Never transfers customers or orders.

The transport file contains private source costs/URLs, but no credentials.
Transfer over SSH only; delete the transport file when verified.
"""
import gzip
import json
import os
import base64
from pathlib import Path
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from ecommerce import models

NAMES = ('Supplier','SupplierPolicy','Category','Brand','SupplierRecollectionRun','SupplierSourceProduct',
         'SupplierSourceMedia','SupplierRecollectionItem','Product','ProductVariant','ProductImage',
         'SupplierOffer','SupplierEvidence','SupplierDecision')


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--export', dest='export_path')
        parser.add_argument('--import-empty', dest='import_path')
        parser.add_argument('--recipient-public-key', help='Optional remote RSA public PEM; credentials are encrypted for that server only.')
        parser.add_argument('--recipient-private-key', help='Remote-only private PEM to unwrap the credential envelope.')
        parser.add_argument('--research-only', action='store_true', help='Transfer saved research checkpoints only, after the catalogue exists.')

    def handle(self, *args, **options):
        names = ('SupplierResearchBatch','SupplierResearchItem') if options['research_only'] else NAMES
        if bool(options['export_path']) == bool(options['import_path']):
            raise CommandError('Choose --export or --import-empty.')
        if options['export_path']:
            rows = []
            for name in names:
                model = getattr(models, name)
                qs = model.objects.using('ecommerce').order_by('pk')
                if name == 'Product': qs = qs.filter(supplier_offer__isnull=False)
                if name in ('ProductVariant','ProductImage'): qs = qs.filter(product__supplier_offer__isnull=False)
                records = json.loads(serializers.serialize('json', qs))
                for record in records:
                    fields = record['fields']
                    if name == 'Supplier':
                        fields.update(credentials_ciphertext='',credential_expires_at=None,health='Manual catalogue; reconnect credentials for API updates')
                    if name == 'SupplierPolicy':
                        fields.update(worker_token='',worker_until=None)
                    # Actor IDs are historical provenance, not cross-database
                    # foreign keys or permission grants. Preserve them.
                rows.extend(records)
            payload = {'format':1,'records':rows}
            if options.get('recipient_public_key'):
                from cryptography.fernet import Fernet
                from cryptography.hazmat.primitives import serialization, hashes
                from cryptography.hazmat.primitives.asymmetric import padding
                from ecommerce.supplier_crypto import decrypt
                public = serialization.load_pem_public_key(Path(options['recipient_public_key']).read_bytes())
                secrets = {str(s.pk):decrypt(s) for s in models.Supplier.objects.using('ecommerce').exclude(credentials_ciphertext='')}
                transport = Fernet.generate_key()
                payload['credentials'] = {'key':base64.b64encode(public.encrypt(transport,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))).decode(),
                    'data':Fernet(transport).encrypt(json.dumps(secrets).encode()).decode()}
            path = Path(options['export_path']).resolve()
            with gzip.open(path, 'wt', encoding='utf-8') as stream:
                json.dump(payload, stream, ensure_ascii=False)
            os.chmod(path, 0o600)
            self.stdout.write(f'Private catalogue bootstrap exported: {len(rows)} records; credential envelope {"encrypted for remote server" if payload.get("credentials") else "not included"}; no customers, orders or wallets.')
            return
        # Fail closed instead of overwriting existing business inventory or IDs.
        for name in names:
            if name == 'SupplierPolicy': continue
            if getattr(models,name).objects.using('ecommerce').exists():
                raise CommandError(f'Target {name} is not empty. No rows imported; use a reviewed incremental migration instead.')
        with gzip.open(options['import_path'],'rt',encoding='utf-8') as stream:
            payload = json.load(stream)
        allowed = {'ecommerce.'+n.lower() for n in names}
        if payload.get('format') != 1 or any(r['model'] not in allowed for r in payload['records']):
            raise CommandError('Invalid catalogue bootstrap scope.')
        secrets = {}
        if payload.get('credentials'):
            if not options.get('recipient_private_key'): raise CommandError('Remote recipient private key required.')
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives import serialization, hashes
            from cryptography.hazmat.primitives.asymmetric import padding
            from ecommerce.supplier_crypto import encrypt
            private = serialization.load_pem_private_key(Path(options['recipient_private_key']).read_bytes(),password=None)
            transport = private.decrypt(base64.b64decode(payload['credentials']['key']),padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
            secrets = json.loads(Fernet(transport).decrypt(payload['credentials']['data'].encode()))
            for row in payload['records']:
                if row['model']=='ecommerce.supplier' and str(row['pk']) in secrets:
                    row['fields']['credentials_ciphertext'] = encrypt(secrets[str(row['pk'])])
                    row['fields']['health'] = 'Credentials transferred securely; test source connection'
        links = []
        for row in payload['records']:
            if row['model']=='ecommerce.supplieroffer':
                decision = row['fields'].get('current_decision')
                if decision:
                    links.append((row['pk'],decision)); row['fields']['current_decision'] = None
        with transaction.atomic(using='ecommerce'):
            for obj in serializers.deserialize('json',json.dumps(payload['records']),using='ecommerce'):
                obj.save(using='ecommerce')
            for offer_id, decision_id in links:
                models.SupplierOffer.objects.using('ecommerce').filter(pk=offer_id).update(current_decision_id=decision_id)
        self.stdout.write(f'Imported {len(payload["records"])} catalogue records; {len(secrets)} supplier credentials re-encrypted locally. Customer, order, wallet and unrelated databases unchanged.')
