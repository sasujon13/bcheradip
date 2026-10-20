"""Weight-based indicative ranges. All money arithmetic stays decimal."""
import re
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from urllib.parse import urlparse
from .pricing import money

ZONES = ('dhaka', 'suburbs', 'outside')


def normalize_profiles(profiles):
    if not isinstance(profiles, list) or not profiles or len(profiles) > 20:
        raise ValueError('Supply 1–20 courier profiles.')
    result = []
    for profile in profiles:
        if not isinstance(profile, dict) or not isinstance(profile.get('zones'), dict):
            raise ValueError('Each courier profile needs zones and weight bands.')
        name = str(profile.get('name', '')).strip()
        url = str(profile.get('source_url', '')).strip()
        if not name or len(name) > 100 or urlparse(url).scheme not in ('http','https') or not urlparse(url).netloc:
            raise ValueError('Use a courier name and an HTTP(S) source URL.')
        zones = {}
        if not profile['zones'] or set(profile['zones']) - set(ZONES):
            raise ValueError('Use dhaka, suburbs and/or outside zones.')
        for key, rule in profile['zones'].items():
            bands = rule.get('bands') if isinstance(rule, dict) else None
            if not isinstance(bands, list) or not 1 <= len(bands) <= 20:
                raise ValueError('Each zone needs 1–20 ordered weight bands.')
            previous = 0; normalized = []
            for band in bands:
                if not isinstance(band, dict): raise ValueError('Invalid weight band.')
                grams = band.get('up_to_grams')
                if isinstance(grams, bool) or not isinstance(grams, int) or not previous < grams <= 1000000:
                    raise ValueError('Weight limits must be increasing positive integer grams, up to 1,000,000.')
                normalized.append({'up_to_grams': grams, 'charge': str(money(band.get('charge'), 'Courier charge'))})
                previous = grams
            maximum = rule.get('max_weight_grams', previous)
            if isinstance(maximum, bool) or not isinstance(maximum, int) or not previous <= maximum <= 1000000:
                raise ValueError('Maximum weight must cover the last band and be at most 1,000,000 grams.')
            zones[key] = {'bands': normalized, 'extra_per_kg': str(money(rule.get('extra_per_kg',0),'Extra per kg')),
                          'max_weight_grams': maximum}
        result.append({'name': name, 'source_url': url, 'reviewed_on': str(profile.get('reviewed_on',''))[:10], 'zones': zones})
    return result


def delivery_zone(address):
    clean = lambda text: re.sub(r'[\s._-]+', '', str(text).casefold())
    district, thana = clean(address.get('district','')), clean(address.get('thana',''))
    if district in ('gazipur','গাজীপুর','narayanganj','নারায়ণগঞ্জ','নারায়ণগঞ্জ'):
        return 'suburbs'
    if district in ('dhaka','dhakadistrict','ঢাকা','ঢাকাজেলা'):
        return 'suburbs' if any(word in thana for word in ('savar','সাভার','keraniganj','কেরানীগঞ্জ','কেরানিগঞ্জ')) else 'dhaka'
    return 'outside'


def weight_range(policy, grams, zone):
    if isinstance(grams, bool) or not isinstance(grams, int) or grams <= 0:
        raise ValueError('A positive parcel weight in grams is required.')
    rates = []
    for provider in normalize_profiles(policy.courier_profiles):
        rule = provider['zones'].get(zone)
        if not rule or grams > rule['max_weight_grams']: continue
        bands = rule['bands']
        charge = next((Decimal(b['charge']) for b in bands if grams <= b['up_to_grams']), None)
        if charge is None:
            steps = (Decimal(grams - bands[-1]['up_to_grams']) / 1000).to_integral_value(rounding=ROUND_CEILING)
            charge = Decimal(bands[-1]['charge']) + steps * Decimal(rule['extra_per_kg'])
        rates.append({'name': provider['name'], 'charge': str(charge), 'source_url': provider['source_url']})
    if not rates: raise ValueError('This parcel needs a manual courier quote. Contact support before ordering.')
    low, high = min(Decimal(r['charge']) for r in rates), max(Decimal(r['charge']) for r in rates)
    return {'zone': zone, 'weight_grams': grams, 'minimum': str(low), 'maximum': str(high),
            'midpoint': str(((low+high)/2).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)), 'rates': rates}


def listing_defaults(policy, weight_grams=0):
    from .pricing import normalize_default_costs
    estimated = not weight_grams
    grams = weight_grams or 1000  # Explicit planning assumption only, never a checkout weight.
    ranges = [weight_range(policy, grams, zone) for zone in ZONES]
    return {**normalize_default_costs(policy.cost_defaults),
            'supplier_delivery_max': str(max(Decimal(r['maximum']) for r in ranges)),
            'customer_delivery_charge': str(min(Decimal(r['midpoint']) for r in ranges))}, estimated
