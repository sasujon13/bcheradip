from django.core.exceptions import ValidationError
from django.test import TransactionTestCase
from .test_checkout_hardening import CheckoutHardeningTests as Fixtures
from .models import Supplier, SupplierSettlementEntry, Order
from .settlements import receivables


class SupplierSettlementTests(TransactionTestCase):
    databases = {'default','ecommerce'}
    setUp = Fixtures.setUp

    def supplier(self):
        return Supplier.objects.using('ecommerce').create(name='Statement source',website='https://supplier.example')

    def entry(self, supplier, kind, amount, ref, **extra):
        return SupplierSettlementEntry.objects.using('ecommerce').create(supplier=supplier,kind=kind,
            amount=amount,reference=ref,note='Synthetic reconciled statement for testing only',actor_id=self.user.pk,**extra)

    def test_supplier_balance_is_separate_and_deducts_refunds_payouts_and_costs_once(self):
        s=self.supplier()
        for kind,amount,ref in [('cod_collected',1000,'collection'),('source_charge',500,'goods'),
                ('delivery_charge',80,'courier'),('other_charge',20,'fee'),('customer_refund',100,'refund'),
                ('supplier_refund',50,'cost-credit'),('settlement_received',200,'payout')]:
            self.entry(s,kind,amount,ref)
        self.assertEqual(receivables()[0]['balance'],150)
        self.assertEqual(receivables()[0]['entries'],7)
        self.user.refresh_from_db()
        self.assertNotIn('balance',self.user.settings or {})

    def test_duplicate_references_and_second_reversal_are_refused(self):
        s=self.supplier(); parent=self.entry(s,'source_charge',80,'original')
        with self.assertRaises(ValidationError): self.entry(s,'source_charge',80,'original')
        with self.assertRaises(ValidationError): self.entry(s,'reversal',79,'wrong',reversal_of=parent)
        reversal=self.entry(s,'reversal',80,'correct',reversal_of=parent)
        self.assertEqual(receivables()[0]['balance'],0)
        with self.assertRaises(ValidationError): self.entry(s,'reversal',80,'again',reversal_of=parent)
        with self.assertRaises(ValidationError): self.entry(s,'reversal',80,'nested',reversal_of=reversal)
        with self.assertRaises(ValidationError): parent.delete()
        parent.note='Changed'
        with self.assertRaises(ValidationError): parent.save(using='ecommerce')

    def test_unconfirmed_balances_never_default_to_confirmed_zero_and_public_has_no_access(self):
        self.assertEqual(receivables(),[])
        self.assertIn(self.guest.get('/api/ecommerce/admin/dashboard/').status_code,(401,403))
        self.user.is_staff=True;self.user.is_superuser=True;self.user.save()
        response=self.client.get('/api/ecommerce/admin/dashboard/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['supplier_receivables'],[])
        self.assertEqual(response.data['contribution']['net'],0)

    def test_order_view_permission_does_not_grant_supplier_statement_access(self):
        self.user.is_staff=True;self.user.save()
        Fixtures.grant(self,Order,'view')
        response=self.client.get('/api/ecommerce/admin/dashboard/')
        self.assertEqual(response.status_code,200)
        self.assertIsNone(response.data['supplier_receivables'])
