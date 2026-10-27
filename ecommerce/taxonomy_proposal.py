"""Read-only candidate vocabulary for the two-level taxonomy review.

These are evidence-search rules, not approved product assignments. Multiple
matches and unknown gender remain review cases; this module never writes data.
"""
import re
import unicodedata

TYPES = {
    "Women's Fashion": {
        'Sarees': r'saree|sharee|\bshari\b|sari\b|শাড়ি|শাড়ি|শাড়ী|শাড়ী',
        'Three-Piece Sets': r'three[ -]?piece|থ্রি.?পিস|থ্রী.?পিস|salwar.*set|shalwar.*set',
        'Kurtis': r'kurti|কুর্তি', 'Abayas': r'abaya|আবায়া|আবায়া',
        'Burqas': r'burqa|burka|borka|বোরকা|বোরখা', 'Hijabs': r'hijab|হিজাব',
        'Niqabs': r'niqab|নিকাব', 'Maxi Dresses': r'maxi|ম্যাক্সি',
        'Gowns': r'\bgown\b|গাউন', 'Lehengas': r'lehenga|লেহেঙ্গা',
        'Nightwear Sets': r'nightwear|night suit|pajama set|pyjama set|\bpj set\b',
        'Skirt Sets': r'skirt.*set|স্কার্ট.*সেট',
        'Gharara Sets': r'gararah|gharara|গারারা',
        'Bras': r'\bbra\b|ব্রা\b', 'Khimar Sets': r'khimar|খিমার',
        'Party Dresses': r'party dress|পার্টি ড্রেস',
        'Overcoats': r'ladies.*overcoat|লেডিস.*ও[বভ]ারকোট',
        'Skirts': r'\bskirt\b|স্কার্ট', 'Scarves': r'\bscarf\b|scarves|স্কার্ফ',
        'Nightdresses': r'night dress|nightdress|nighty|নাইটি',
        'Co-ord Sets': r'co[ -]?ord|two piece|four piece',
    },
    "Men's Fashion": {'Panjabis': r'panjabi|punjabi|পাঞ্জাবি', 'Fatuas': r'fatua|katu[aw]?a|ফতুয়া|ফতুয়া|কাতুয়া'},
    'Electronics': {
        'Wireless Earbuds': r'earbuds?|\btws\b|ইয়ারবাড|ইয়ারবাড',
        'Bluetooth Speakers': r'bluetooth.*speaker|স্পিকার',
        'Neckband Earphones': r'neckband|নেকব্যান্ড',
        'Microphones': r'microphone|ল্যাভালিয়ার|মাইক্রোফোন',
        'Power Banks': r'power\s*bank|পাওয়ার ব্যাংক|পাওয়ার ব্যাংক',
        'Smartwatches': r'smart\s*watch|স্মার্ট.?ওয়াচ|স্মার্ট.?ওয়াচ',
        'TV Streaming Boxes': r'tv\s*(?:box|stick)|ott streamer|টিভি বক্স',
        'Security Cameras': r'cctv|security camera|wifi camera|ip camera|সিসিটিভি',
        'Rechargeable Batteries': r'rechargeable battery|lithium.*battery|রিচার্জেবল ব্যাটারি',
        'Game Consoles': r'game console|গেম কনসোল',
        'Solar Charge Controllers': r'solar charge controller',
        'Doorbells': r'doorbell|calling bell|ডোরবেল',
        'Bluetooth Trackers': r'bluetooth tracker|\bmitag\b',
    },
    'Mobile & Accessories': {
        'Phone Chargers': r'phone charger|usb.*charger|wall charger|fast charger|মোবাইল চার্জার',
        'Charging Cables': r'usb.*cable|charging cable|type.?c.*cable|চার্জিং ক্যাবল',
        'Phone Holders': r'phone holder|mobile holder|ফোন হোল্ডার',
        'Phone Cooling Fans': r'(?:phone|mobile).*cooler|ফোন কুলার',
        'Phone Cases': r'phone case|mobile cover|ফোন কভার',
        'Selfie Sticks': r'selfie stick|সেলফি স্টিক',
    },
    'Computer & Accessories': {
        'Memory Cards': r'memory card|micro\s*sd|\bsd(?:hc|xc)?\s+card|মেমোরি কার্ড',
        'USB Flash Drives': r'pen drive|pendrive|flash drive|পেনড্রাইভ',
        'Wi-Fi Routers': r'\brouter\b|রাউটার',
        'Keyboards': r'keyboard|কিবোর্ড', 'Computer Mice': r'\bmouse\b|মাউস',
        'Laptop Stands': r'laptop stand|ল্যাপটপ স্ট্যান্ড',
    },
    'Kitchen & Dining': {
        'Blenders': r'\bblender\b|ব্লেন্ডার', 'Rice Cookers': r'rice cooker|রাইস কুকার',
        'Electric Kettles': r'kettle|কেটলি', 'Food Choppers': r'chopper|চপার',
        'Food Storage Containers': r'food storage|food container|egg box|egg organizer',
        'Lunch Boxes': r'lunch box|টিফিন বক্স', 'Water Bottles': r'water bottle|পানির বোতল',
        'Thermal Flasks': r'flask|ফ্লাস্ক', 'Vegetable Peelers': r'peeler|পিলার',
        'Water Filters': r'water filter|পানি.*ফিল্টার',
        'Electric Hotplates': r'hotplate|electric stove|ইলেকট্রিক চুলা',
    },
    'Home & Living': {
        'Bed Sheets': r'bed[ -]*sheet|বেডশিট|বেডশীট|বিছানার চাদর',
        'Quilts': r'ac katha|কাঁথা', 'Tablecloths': r'table cloth|tablecloth|টেবিল ক্লথ',
        'Comforter Sets': r'comforter|কমফোর্টার|কম্ফর্টার', 'Blankets': r'blanket|কম্বল|ব্লাঙ্কেট',
        'Mosquito Nets': r'mosquito net|মশারি', 'Curtains': r'curtain|পর্দা',
        'Wall Clocks': r'wall clock|দেয়াল ঘড়ি|দেয়াল ঘড়ি',
        'Alarm Clocks': r'alarm clock|অ্যালার্ম ঘড়ি',
        'Table Lamps': r'(?:table|desk) lamp|টেবিল ল্যাম্প',
        'LED Strip Lights': r'strip light|rope light|নিয়ন লাইট|নিয়ন লাইট',
        'Table Fans': r'table fan|desk fan|টেবিল ফ্যান',
        'Portable Fans': r'portable fan|mini fan|মিনি ফ্যান',
        'Clothes Irons': r'dry iron|steam iron|ইস্ত্রি',
        'Vacuum Cleaners': r'vacuum|ভ্যাকুয়াম|ভ্যাকুয়াম',
        'Clothes Hangers': r'clothes hanger|হ্যাঙ্গার',
        'Shoe Racks': r'shoe rack|জুতার র‍্যাক',
    },
    'Beauty & Personal Care': {
        'Hair Clippers & Trimmers': r'trimmer|hair clipper|ট্রিমার',
        'Hair Dryers': r'hair dryer|হেয়ার ড্রায়ার',
        'Hair Straighteners': r'hair straightener|হেয়ার স্ট্রেইটনার',
        'Perfumes': r'perfume|পারফিউম|আতর|attar',
        'Shampoos': r'shampoo|শ্যাম্পু', 'Face Washes': r'face wash|ফেসওয়াশ',
        'Sunscreens': r'sunscreen|sunblock|সানস্ক্রিন',
        'Lipsticks': r'lipstick|লিপস্টিক', 'Toothbrushes': r'toothbrush|টুথব্রাশ',
    },
    'Bags & Luggage': {
        'Backpacks': r'backpack|ব্যাকপ্যাক', 'Handbags': r'hand\s*bag|ladies bag|হ্যান্ডব্যাগ',
        'Tote Bags': r'tote bag|টোট ব্যাগ',
        'Wallets': r'wallet|মানিব্যাগ', 'Travel Bags': r'travel bag|ট্রাভেল ব্যাগ',
        'Laptop Bags': r'laptop bag|ল্যাপটপ ব্যাগ',
    },
    'Shoes & Footwear': {
        'Sneakers': r'sneaker|স্নিকার', 'Sandals': r'sandal|sandle|স্যান্ডেল',
        'Shoe Cleaning Kits': r'shoe clean|shoe polish|জুতা.*পরিষ্কার',
    },
    'Watches & Accessories': {
        'Wristwatches': r'quartz.*watch|analog watch|wristwatch|formal watch',
        'Watch Straps': r'watch strap|smartwatch.*strap|strap.*smartwatch',
        'Sunglasses': r'sunglass|সানগ্লাস', 'Bracelets': r'bracelet|ব্রেসলেট',
        'Pendant Necklaces': r'pendant|পেন্ডেন্ট',
    },
    'Health & Wellness': {'Massage Guns': r'massage gun|ম্যাসাজ গান', 'Blood Pressure Monitors': r'blood pressure|ব্লাড প্রেসার', 'Thermometers': r'thermometer|থার্মোমিটার'},
    'Office & Stationery': {'LCD Writing Tablets': r'lcd writing|লেখার ট্যাব', 'Label Printers': r'label printer|price tag label'},
    'Tools & Home Improvement': {'Multimeters': r'multimeter|মাল্টিমিটার', 'Soldering Irons': r'soldering iron|সোল্ডারিং আয়রন'},
}

APPAREL = {'Hoodies': r'hoodie|hoddie|হুডি', 'Sweatshirts': r'sweatshirt|sweetshirt|সুইটশার্ট|সোয়েটশার্ট',
    'Sweaters': r'sweater|সোয়েটার|সুয়েটার', 'Polo Shirts': r'polo|পলো',
    'T-Shirts': r'\bt[ -]?shirt|টিশার্ট|টি.?শার্ট', 'Jeans': r'jeans|denim pant|জিন্স',
    'Trousers': r'trouser|ট্রাউজার', 'Jackets': r'jacket|জ্যাকেট'}
APPAREL.update({'Casual Shirts': r'(?<!t[ -])\bshirts?\b|শার্ট',
                'Formal Shirts': r'formal.*shirt|office.*shirt',
                'Matching Sets': r'(?:t[ -]?shirt|polo).*?(?:trouser|pant).*?(?:set|combo)|(?:t[ -]?shirt|polo).*?(?:set|combo).*?(?:trouser|pant)'})


def candidates(title, description=''):
    # This deliberately returns alternatives rather than picking the first hit.
    text = unicodedata.normalize('NFKC', title).casefold()
    text = re.split(r'\b(?:fabrics?|material|gsm|size|product type|gender)\s*[:：]|ফেব্রিক্স[ঃ:]|ডিটেইলস[ঃ:]', text)[0][:180]
    if re.search(r'couple|কাপল', text) and re.search(r'dress|set|saree|sharee|panjabi|ড্রেস|শাড়ি|পাঞ্জাবি', text):
        return [('Clothing & Fashion', 'Couple Outfit Sets')]
    found = [(department, kind) for department, types in TYPES.items() for kind, pattern in types.items()
             if re.search(pattern, text, re.I)]
    context = text + ' ' + description.casefold()
    child = bool(re.search(r'\bbaby\b|\bkids?\b|children|\bboys?\b|\bgirls?\b|বেবি|বাচ্চা', text))
    female = bool(re.search(r'\bwomen\b|\bladies\b|\bfemale\b|মহিলা|লেডিস', context))
    male = bool(re.search(r'\bmen\b|\bmens\b|\bman\b|\bgents?\b|\bmale\b|পুরুষ', context))
    for kind, pattern in APPAREL.items():
        if not re.search(pattern, text, re.I): continue
        if child: found.append(('Kids & Baby', "Children's " + kind))
        else:
            if male: found.append(("Men's Fashion", kind))
            if female: found.append(("Women's Fashion", kind))
            if not male and not female: found.append(('Clothing & Fashion', kind))
    if child:
        found = [('Kids & Baby', "Children's " + kind) if department in ("Women's Fashion", "Men's Fashion") and kind != 'Bras' else (department, kind) for department, kind in found]
    kinds = {kind.removeprefix("Children's ") for _, kind in found}
    discard = set()
    if 'Matching Sets' in kinds: discard |= {'T-Shirts', 'Polo Shirts', 'Trousers', 'Casual Shirts'}
    if kinds & {'T-Shirts', 'Polo Shirts', 'Sweatshirts', 'Formal Shirts'}: discard.add('Casual Shirts')
    if 'Polo Shirts' in kinds: discard |= {'T-Shirts', 'Formal Shirts'}
    if 'Skirt Sets' in kinds: discard |= {'Skirts', 'T-Shirts', 'Casual Shirts'}
    if 'Lehengas' in kinds: discard |= {'Party Dresses', 'Gowns'}
    if 'Gowns' in kinds: discard.add('Co-ord Sets')
    if 'Watch Straps' in kinds: discard.add('Smartwatches')
    found = [(department, kind) for department, kind in found if kind.removeprefix("Children's ") not in discard]
    return sorted(set(found))


def normalized_classification(title, categories=(), description=''):
    """Conflicting types remain review cases, never first-keyword-wins."""
    paths = candidates(title, description)
    if len(paths) == 1 or (paths and len({p[1] for p in paths}) == 1):
        return {'path': list(paths[0]), 'secondary_paths': [list(p) for p in paths[1:]],
                'status': 'assigned', 'reason': 'normalized_product_type_evidence', 'version': 2}
    return {'path': [], 'secondary_paths': [], 'status': 'needs_review',
            'reason': 'Conflicting product types' if paths else 'Specific product type needs review',
            'candidates': [list(p) for p in paths], 'version': 2}
