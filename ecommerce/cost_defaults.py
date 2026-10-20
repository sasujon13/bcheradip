"""Reviewed 2026-10-20 planning presets, not live booking/advertising quotes."""

def initial_cost_defaults():
    # Median of three published Meta/ecommerce CPA range midpoints: 235, 275, 625.
    # Packaging: sample material-unit prices 3.90, 11, 26.63 -> median 11.
    # Returns: 20% failures / 80% successes * Tk195 failed-parcel example.
    return {'ads_cost': '275.00', 'packaging_cost': '11.00',
            'returns_allowance': '48.75', 'other_costs': '0.00'}


def initial_courier_profiles():
    def zone(prices, extra=0, maximum=20000):
        return {'bands': [{'up_to_grams': grams, 'charge': str(price)} for grams, price in prices],
                'extra_per_kg': str(extra), 'max_weight_grams': maximum}
    return [
        {'name': 'Pathao', 'source_url': 'https://pathao.com/courier/?lang=en', 'reviewed_on': '2026-10-20',
         'zones': {'dhaka': zone([(500,60),(1000,70),(2000,90)],15),
                   'suburbs': zone([(500,80),(1000,100),(2000,130)],25),
                   'outside': zone([(500,110),(1000,130),(2000,170)],25)}},
        {'name': 'eCourier', 'source_url': 'https://ecourier.com.bd/pricing-information/', 'reviewed_on': '2026-10-20',
         # Bulk pricing starts at 3kg: do not extrapolate the small-parcel plan.
         'zones': {'dhaka': zone([(1000,80)],30,2000),
                   'outside': zone([(1000,130)],30,2000)}},
        {'name': 'eCourier Thana/Union', 'source_url': 'https://ecourier.com.bd/pricing-information/', 'reviewed_on': '2026-10-20',
         'zones': {'outside': zone([(1000,160)],30,2000)}},
        {'name': 'Steadfast', 'source_url': 'https://www.steadfast.com.bd/index.php', 'reviewed_on': '2026-10-20',
         # Only the published 1kg FAQ tariff is seeded, not guessed heavier rates.
         'zones': {'dhaka': zone([(1000,70)],0,1000),
                   'suburbs': zone([(1000,100)],0,1000), 'outside': zone([(1000,130)],0,1000)}},
    ]


RESEARCH_NOTES = {
    'reviewed_on': '2026-10-20',
    'courier_origin': 'Dhaka metro pickup; regular small-parcel home delivery. Indicative published base fares, not negotiated, tax-inclusive or live booking quotes.',
    'excluded': 'Sundarban publishes item-specific prices and destination surcharges; not comparable to generic weight tariffs. The outside range includes eCourier metro and Thana/Union alternatives as an estimate, not a coverage promise. Bulky/fragile services, volumetric pricing and exact coverage require manual review.',
    'ads': 'Tk275 is the median of three published Meta/ecommerce CPA range midpoints (235,275,625), not an audited all-social-media/national average. One sold item per acquired order is assumed. Replace with your actual spend per delivered sale; organic sales may use zero.',
    'packaging': 'Tk11 is a small illustrative material-cost median (bag 3.90, small carton 11, narrow carton 26.63); not a standard all-product packaging cost. Fragile/large items need overrides.',
    'returns': 'Tk48.75 planning reserve = 20% / 80% * Tk195 failed-parcel cost from Pathao example; not a measured Cheradip return rate and excludes damage/lost stock.',
    'sources': [
        'https://pathao.com/courier/?lang=en', 'https://ecourier.com.bd/pricing-information/',
        'https://www.steadfast.com.bd/index.php', 'https://rate.sundarbancourierltd.com/',
        'https://ihtahim.com/blog/meta-ads-budget-bangladesh/',
        'https://kuiperz.io/blog/bangladesh-facebook-ads-2025-cost-benchmarks-ctr-cpa-ranges-and-a-simple-budget-calculator/',
        'https://arafatlabs.com/blog/facebook-ads-cost-bangladesh-2026-benchmarks',
        'https://saleup.com.bd/product/courier-poly-10-by-14-inch-size-100-pcs/',
        'https://saleup.com.bd/product-category/packaging/?per_row=4&shop_view=grid',
        'https://pathao.com/blog/how-delivery-success-rate-affects-your-business-growth/?lang=en',
    ],
}
