"""Read-only supplier reconciliation totals. These records never transfer money."""
from decimal import Decimal
from .models import SupplierSettlementEntry


SIGNS = {'cod_collected': 1, 'supplier_refund': 1, 'source_charge': -1, 'other_charge': -1,
         'delivery_charge': -1, 'customer_refund': -1, 'settlement_received': -1}


def signed(entry):
    if entry.kind == 'reversal':
        return -entry.amount * SIGNS[entry.reversal_of.kind]
    return entry.amount * SIGNS[entry.kind]


def receivables():
    groups = {}
    entries = SupplierSettlementEntry.objects.using('ecommerce').select_related('supplier', 'reversal_of').order_by('pk')
    for entry in entries.iterator(chunk_size=250):
        group = groups.setdefault(entry.supplier_id, {'supplier': entry.supplier.name,
            'balance': Decimal('0'), 'entries': 0, 'last_recorded_at': entry.created_at})
        group['balance'] += signed(entry)
        group['entries'] += 1
        group['last_recorded_at'] = entry.created_at
    return list(groups.values())
