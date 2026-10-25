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


def round_reference_price_to_ten(value):
    """Round a reference price to whole Tk, then nearest ten (0-3 down, 4-9 up)."""
    whole = money(value, 'Reference price').to_integral_value(rounding=ROUND_HALF_UP)
    remainder = whole % Decimal('10')
    return whole - remainder if remainder <= 3 else whole + (Decimal('10') - remainder)


def discounted_reference_price(reference_price, discount_percent):
    """Apply the discount to the rounded reference, then round payable Tk up."""
    reference = money(reference_price, 'Reference price')
    discount = money(discount_percent, 'Sale discount')
    if discount >= 100:
        raise ValueError('Sale discount must be less than 100%.')
    return (reference * (1 - discount / 100)).to_integral_value(rounding=ROUND_CEILING)


def retail_prices(calculated_price, rules=None):
    """Reserve a reference price, apply the configured discount, then round up.

    The reference increase is expressed to two decimal places (11.11% for
    the default 10% discount), rounded up to whole Tk, then rounded to
    the nearest ten (remainders 0–3 down, 4–9 up). The final discounted taka
    amount is rounded upward, so it can differ slightly from the unrounded
    calculated target.
    """
    original = money(calculated_price, 'Calculated selling price')
    config=normalize_pricing_rules(rules or default_pricing_rules())
    discount=Decimal(config['discount_percent'])
    increase = (discount * 100 / (100 - discount)).quantize(CENT, rounding=ROUND_HALF_UP)
    regular = (original * (1 + increase / 100)).to_integral_value(rounding=ROUND_CEILING)
    regular = round_reference_price_to_ten(regular)
    regular = max(regular, original).to_integral_value(rounding=ROUND_CEILING)
    sale = discounted_reference_price(regular, discount)
    if regular > MAX_MONEY:
        raise ValueError('The discount-reserved price exceeds the supported amount.')
    return {'base_price': str(original), 'sale_price': format(sale, 'f'), 'regular_price': format(regular, 'f'),
            'discount_percent': str(discount), 'reference_increase_percent': str(increase),
            'rounding': 'nearest_ten_remainder_4_rounds_up', 'version': 3}


def reserved_ten_percent_discount(variant):
    """Customer-friendly discount for an unchanged reserved reference price."""
    rule = (variant.product.attributes or {}).get('_retail_pricing', {}).get(str(variant.pk), {})
    try:
        version = rule.get('version')
        if rule.get('mode') != 'reserve' or version not in (1, 2, 3):
            return None
        discount=Decimal(rule.get('discount_percent','10'))
        regular=money(rule['applied_price'],'Reserved reference price')
        sale=discounted_reference_price(regular,discount)
        if (variant.price != regular or variant.compare_at_price or
                money(rule['sale_price'],'Reserved sale price') != sale):
            return None
        return regular - sale
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
