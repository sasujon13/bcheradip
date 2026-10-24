"""Private, opt-in listing-price suggestions. Never reprices published items."""
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING, InvalidOperation

CENT = Decimal('.01')
MAX_MONEY = Decimal('999999999999.99')
COST_FIELDS = ('supplier_delivery_max', 'customer_delivery_charge', 'ads_cost',
               'packaging_cost', 'returns_allowance', 'other_costs')

def default_pricing_rules():
    return {'start_percent':'20','minimum_percent':'10','step_percent':'1','band_size':'100','discount_percent':'10'}


def normalize_pricing_rules(value):
    if not isinstance(value,dict) or set(value)!=set(default_pricing_rules()):
        raise ValueError('Supply starting/minimum markup, decrease per band, band size and sale discount.')
    result={k:money(v,k) for k,v in value.items()}
    if not 0<=result['minimum_percent']<=result['start_percent']<=100 or not 0<=result['step_percent']<=100:
        raise ValueError('Markup percentages must be between 0 and 100; minimum cannot exceed starting markup.')
    if result['band_size']<=0 or not 0<=result['discount_percent']<100:
        raise ValueError('Band size must be positive and sale discount must be less than 100%.')
    return {k:str(v) for k,v in result.items()}


def retail_prices(calculated_price, rules=None):
    """Round once, after costs/markup; reserve 10% without compounding reruns.

    Whole-taka regular prices cannot always yield an exact whole-taka price at
    precisely 10% off. The explicit sale price preserves the rounded target;
    its saving can exceed 10% by less than one taka.
    """
    original = money(calculated_price, 'Calculated selling price')
    sale = original.to_integral_value(rounding=ROUND_CEILING)
    config=normalize_pricing_rules(rules or default_pricing_rules())
    discount=Decimal(config['discount_percent'])
    regular = (sale / (1-discount/100)).to_integral_value(rounding=ROUND_CEILING)
    if regular > MAX_MONEY:
        raise ValueError('The discount-reserved price exceeds the supported amount.')
    return {'base_price': str(original), 'sale_price': format(sale, 'f'), 'regular_price': format(regular, 'f'),
            'discount_percent': str(discount), 'rounding': 'ceiling_after_calculation', 'version': 1}


def reserved_ten_percent_discount(variant):
    """Customer-friendly whole-taka discount for an unchanged reserved price.

    R = ceil(B / .9); R - ceil(R * .1) = B for integer B. Round each
    eligible unit, not the cart: quantities must retain the same target price.
    Manual prices, other coupon percentages and ordinary products are untouched.
    """
    rule = (variant.product.attributes or {}).get('_retail_pricing', {}).get(str(variant.pk), {})
    try:
        if rule.get('mode') != 'reserve' or rule.get('version') != 1:
            return None
        pair = retail_prices(rule['base_price'])
        regular = Decimal(pair['regular_price'])
        if (variant.price != regular or Decimal(rule['applied_price']) != regular or
                Decimal(rule['sale_price']) != Decimal(pair['sale_price']) or variant.compare_at_price):
            return None
        return regular - Decimal(pair['sale_price'])
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None


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


def calculate_price(source_cost, costs, *, subsidy_enabled=False, rules=None):
    source = money(source_cost, 'Source cost')
    normalized = normalize_costs(costs)
    values = {key: Decimal(value) for key, value in normalized.items()}
    subsidy = max(Decimal('0'), values['supplier_delivery_max'] - values['customer_delivery_charge']) if subsidy_enabled else Decimal('0')
    total = source + subsidy + sum((values[key] for key in
        ('ads_cost', 'packaging_cost', 'returns_allowance', 'other_costs')), Decimal('0'))
    # Inclusive upper limits: <=100 = 20%, (100,200] = 19%, ... >1000 = 10%.
    config=normalize_pricing_rules(rules or default_pricing_rules())
    band = max(Decimal('0'), (total / Decimal(config['band_size'])).to_integral_value(rounding=ROUND_CEILING) - 1)
    rate = max(Decimal(config['minimum_percent']), Decimal(config['start_percent']) - band*Decimal(config['step_percent']))
    profit = (total * rate / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    price = total + profit
    if price > MAX_MONEY:
        raise ValueError('The calculated price exceeds the supported amount.')
    return {'source_cost': str(source), 'costs': normalized, 'delivery_subsidy': str(subsidy.quantize(CENT)),
            'total_cost': str(total.quantize(CENT)), 'markup_percent': format(rate.normalize(),'f'),
            'profit_amount': str(profit), 'suggested_price': str(price.quantize(CENT)),
            'delivery_subsidy_enabled': subsidy_enabled, 'delivery_basis': 'charged_separately', 'version': 3,'rules':config}
