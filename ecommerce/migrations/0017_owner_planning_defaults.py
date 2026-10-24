from django.db import migrations


def defaults(apps, schema_editor):
    if schema_editor.connection.alias != 'ecommerce':
        return
    Policy = apps.get_model('ecommerce', 'DeliverySettings')
    for policy in Policy.objects.using('ecommerce').all():
        costs = dict(policy.cost_defaults or {})
        # Replace only the superseded initial preset, not a manually set budget.
        if str(costs.get('ads_cost')) in {'275', '275.0', '275.00'}:
            costs['ads_cost'] = '20.00'
        policy.cost_defaults = costs
        policy.delivery_subsidy_enabled = False
        policy.save(using='ecommerce', update_fields=['cost_defaults', 'delivery_subsidy_enabled'])


class Migration(migrations.Migration):
    dependencies = [('ecommerce', '0016_order_costs_supplier_shipping')]
    operations = [migrations.RunPython(defaults, migrations.RunPython.noop)]
