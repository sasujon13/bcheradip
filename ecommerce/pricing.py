"""Private, opt-in listing-price suggestions. Never reprices published items."""
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING, InvalidOperation

CENT = Decimal('.01')
MAX_MONEY = Decimal('999999999999.99')
COST_FIELDS = ('supplier_delivery_max', 'customer_delivery_charge', 'ads_cost',
               'packaging_cost', 'returns_allowance', 'other_costs')


def money(value, label):
    if isinstance(value, bool):
        raise ValueError(f'{label} must be a non-negative amount with at most two decimal places.')
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f'{label} must be a valid amount.')
    if not amount.is_finite() or amount < 0 or amount > MAX_MONEY or amount.as_tuple().exponent < -2:
        raise ValueError(f'{label} must be a non-negative amount with at most two decimal places.')
    return amount.quantize(CENT)


def normalize_costs(costs):
    if not isinstance(costs, dict) or set(costs) - set(COST_FIELDS):
        raise ValueError('Use the supported pricing cost fields only.')
    return {key: str(money(costs.get(key, '0'), key)) for key in COST_FIELDS}


def normalize_default_costs(costs):
    fields = ('ads_cost','packaging_cost','returns_allowance','other_costs')
    if not isinstance(costs, dict) or set(costs) != set(fields):
        raise ValueError('Supply ads, packaging, return allowance and other-cost defaults.')
    return {key: str(money(costs[key], key)) for key in fields}


def calculate_price(source_cost, costs):
    source = money(source_cost, 'Source cost')
    normalized = normalize_costs(costs)
    values = {key: Decimal(value) for key, value in normalized.items()}
    subsidy = max(Decimal('0'), values['supplier_delivery_max'] - values['customer_delivery_charge'])
    total = source + subsidy + sum((values[key] for key in
        ('ads_cost', 'packaging_cost', 'returns_allowance', 'other_costs')), Decimal('0'))
    # Inclusive upper limits: <=100 = 20%, (100,200] = 19%, ... >1000 = 10%.
    band = max(Decimal('0'), (total / 100).to_integral_value(rounding=ROUND_CEILING) - 1)
    rate = max(Decimal('10'), Decimal('20') - band)
    profit = (total * rate / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    price = total + profit
    if price > MAX_MONEY:
        raise ValueError('The calculated price exceeds the supported amount.')
    return {'source_cost': str(source), 'costs': normalized, 'delivery_subsidy': str(subsidy.quantize(CENT)),
            'total_cost': str(total.quantize(CENT)), 'markup_percent': str(rate),
            'profit_amount': str(profit), 'suggested_price': str(price.quantize(CENT)),
            'delivery_basis': 'weight_range_midpoint', 'version': 2}
