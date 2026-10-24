from django.apps import apps
from django.test import SimpleTestCase
from .management.commands.verify_deploy_schema import SAFE_ADDITIONS, SAFE_SOURCE_TABLES


class DeploymentSchemaAllowlistTests(SimpleTestCase):
    def test_supplier_additions_preserve_existing_business_values(self):
        for model_name, field_name, expected in (
            ('product', 'supplier_delivery_rates', {}),
            ('order', 'cost_snapshot', {}),
            ('deliverysettings', 'delivery_subsidy_enabled', False),
        ):
            self.assertIn(('ecommerce', 'ecommerce', model_name, field_name), SAFE_ADDITIONS)
            field = apps.get_model('ecommerce', model_name)._meta.get_field(field_name)
            self.assertEqual(field.get_default(), expected)

    def test_business_amount_and_identity_changes_are_not_allowlisted(self):
        for model, field in (('order', 'grand_total'), ('productvariant', 'price'), ('supplier', 'credentials_ciphertext')):
            self.assertNotIn(('ecommerce', 'ecommerce', model, field), SAFE_ADDITIONS)

    def test_original_source_additions_are_nullable_and_private(self):
        for model, field in (('productimage', 'source_media'), ('supplieroffer', 'source_product')):
            self.assertIn(('ecommerce', 'ecommerce', model, field), SAFE_ADDITIONS)
            self.assertTrue(apps.get_model('ecommerce', model)._meta.get_field(field).null)
        self.assertEqual(len(SAFE_SOURCE_TABLES), 4)
