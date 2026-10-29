"""Title classifiers for the reviewed two-level category suggestions.

These pick among existing (or explicitly created kids) types. Unmatched titles
return None so listings can stay on their current department.
"""
import re
import unicodedata


def norm(text):
    return unicodedata.normalize('NFKC', str(text or '')).casefold()


def product_text(product):
    return norm(f'{product.name} {product.short_description or ""} {product.description or ""}')


COLOR_ONLY = re.compile(r'baby\s+(?:pink|blue)|বেবি\s*পিংক')
KIDS_HINT = re.compile(
    r'\bkids?\b|\bbaby\b|\bchildren(?:[\'’]s)?\b|\bchild\b|\binfant\b|\btoddler\b|\bnewborn\b|'
    r'বেবি|বাচ্চা|কিডস|শিশু|বয়েজ|গার্লস|'
    r'\b\d+\s*(?:[-–to]{1,3}\s*\d+\s*)?(?:years?|yrs?|y\b|বছর)|'
    r'[০-৯]+\s*(?:[-–]?\s*[০-৯]+\s*)?(?:বছর|মাস)|'
    r'ছেলেদের|মেয়েদের'
)
COUPLE = re.compile(r'\bcouple\b|কাপল')
JEWELRY = re.compile(
    r'kundan|necklace|earring|pendant|bracelet|jewellery|\bjewelry\b|'
    r'gold-?plated|anti-?tarnish|oxidized|polki|minakari|'
    r'\bwatch(?:es)?\b|wristwatch|quartz analog|chronograph'
)
SUNGLASSES = re.compile(r'sunglass|eyewear|\bframes?\b|vintage glasses|optical')


def is_kids(text):
    cleaned = COLOR_ONLY.sub(' ', text)
    if COUPLE.search(cleaned) and not re.search(r'\bkids?\b|বাচ্চাদের|বেবি', cleaned):
        return False
    return bool(KIDS_HINT.search(cleaned))


def first_match(text, rules):
    for pattern, destination in rules:
        if re.search(pattern, text):
            return destination
    return None


KIDS_RULES = (
    (r'diaper|ডায়াপার|ডায়পার|ডায়পার', ('Kids & Baby', 'Diapers')),
    (r'breast\s*pump|feeder|feeding|mumpot|mash bowl|silicon(?:e)? spoon|'
     r'feeder brush|baby bib|tray bib|silicon(?:e)? baby bib', ('Kids & Baby', 'Baby Feeding')),
    (r'baby\s*(?:blanket|sleeping)|wrap blanket|sleeping bag|protector bed|'
     r'receiving blanket|nursery wrap|শিশুর আরাম', ('Kids & Baby', 'Baby Bedding')),
    (r'carrier|bouncer|dolna|cradle|walking assistant|baby keeper',
     ('Kids & Baby', 'Baby Gear')),
    (r'potty|bather|helmet|head protector|knee protector|anti[ -]?lost|'
     r'safety belt|raincoat|swimming|inflatable.{0,20}bath|urin pot|'
     r'finger brush|commode|shower cap|safety head', ('Kids & Baby', 'Baby Care')),
    (r'\btoys?\b|খেলনা|die-?cast|game box|spelling|bubble|tent house|'
     r'drawing art|talking tom|drone|spinner|rocker|intelligence|'
     r'preschool|boxing set|painting for kids|walkie talkie|'
     r'chess|stress relief ball|water painting|logarithmic|'
     r'play tent|ball pit', ('Kids & Baby', 'Toys')),
    (r'drawing projector|projector torch|torch.*projector',
     ('Kids & Baby', 'Drawing & Projection Toys')),
    (r'(?:hoodie|t[ -]?shirt|jersey|polo).{0,40}(?:trouser|pant|set)|'
     r'two[ -]?piece|2[ -]?piece|co-?ord|matching set|combo set|'
     r'sweep combo|টু ?পি|pant set|প্যান্ট সেট|এন্ড প্যান্ট',
     ('Kids & Baby', "Children's Matching Sets")),
    (r'burqa|বোরকা|বোরখা', ('Kids & Baby', "Children's Burqas")),
    (r'hoodie|হুডি', ('Kids & Baby', "Children's Hoodies")),
    (r'sweatshirt|সুইটশার্ট', ('Kids & Baby', "Children's Sweatshirts")),
    (r'polo|পলো', ('Kids & Baby', "Children's Polo Shirts")),
    (r't[ -]?shirt|টি[ -]?শার্ট|jersey', ('Kids & Baby', "Children's T-Shirts")),
    (r'jacket|জ্যাকেট', ('Kids & Baby', "Children's Jackets")),
    (r'party(?: princess)? frock|party dress|ফ্রক', ('Kids & Baby', "Children's Party Dresses")),
    (r'\bgown\b|গাউন', ('Kids & Baby', "Children's Gowns")),
    (r'kurti|কুর্তি', ('Kids & Baby', "Children's Kurtis")),
    (r'lehenga|sharara|লেহেঙ্গা', ('Kids & Baby', "Children's Lehengas")),
    (r'panjabi|পাঞ্জাবি', ('Kids & Baby', "Children's Panjabis")),
    (r'fatua|ফতুয়া|ফতুয়া', ('Kids & Baby', "Children's Fatuas")),
    (r'saree|শাড়ি|শাড়ি', ('Kids & Baby', "Children's Sarees")),
    (r'trouser| pant\b|\bpants\b|প্লাজু|পায়জামা|জগার|baggy',
     ('Kids & Baby', "Children's Trousers")),
    (r'frock|jumpsuit|winter|শীতের|raincoat|মোজা|নিমা সেট|কটি সেট|'
     r"children[’']?s clothing|baby cloth", ('Kids & Baby', "Children's Clothing")),
)


def kids_destination(text, assume_kids=False):
    text = norm(text)
    if not assume_kids and not is_kids(text):
        return None
    hit = first_match(text, KIDS_RULES)
    if hit:
        return hit
    if assume_kids or is_kids(text):
        return ('Kids & Baby',)
    return None


ELECTRONICS_RULES = (
    (r'power\s*bank|\d[\d,.]*\s*mah', ('Electronics', 'Power Banks')),
    (r'(?:usb|type-?c|lightning).{0,20}cable|charging cable|data cable',
     ('Electronics', 'Charging Cables')),
    (r'phone cooler|mobile cooler|semiconductor.{0,12}cool',
     ('Electronics', 'Phone Cooling Fans')),
    (r'selfie stick|সেলফি স্টিক', ('Electronics', 'Selfie Sticks')),
    (r'phone holder|mobile holder|ফোন হোল্ডার|মোবাইল হোল্ডার',
     ('Electronics', 'Phone Holders')),
    (r'phone case|mobile cover|back cover|screen protector|ফোন কভার',
     ('Electronics', 'Phone Cases & Accessories')),
    (r'gan.{0,12}charg|wall charg|fast charg(?:er|ing)|phone charg|'
     r'power adapter|travel adapter|charge separator',
     ('Electronics', 'Phone Chargers')),
    (r'neckband|নেকব্যান্ড', ('Electronics', 'Neckband Earphones')),
    (r'earbuds?|\btws\b|true wireless.{0,24}ear|in-ear(?! monitor)',
     ('Electronics', 'Wireless Earbuds')),
    (r'bluetooth.{0,20}speaker|portable wireless.{0,20}speaker|'
     r'mini bluetooth|স্পিকার', ('Electronics', 'Bluetooth Speakers')),
    (r'microphone|lavalier|collar clip.{0,12}wireless|মাইক্রোফোন',
     ('Electronics', 'Microphones')),
    (r'headphone|headset|হেডফোন', ('Electronics', 'Audio & Headphones')),
    (r'\bkeyboard\b|কিবোর্ড', ('Electronics', 'Keyboards')),
    (r'\bmouse\b|মাউস', ('Electronics', 'Computer Mice')),
    (r'\brouter\b|wifi repeater|রাউটার', ('Electronics', 'Wi-Fi Routers')),
    (r'cctv|security camera|ip camera|nanny cam|wifi cam|bulb.{0,8}cam|'
     r'\bv380\b|\bimou\b|\bezviz\b|সিসিটিভি', ('Electronics', 'Security Cameras')),
    (r'button phone|dual sim|feature phone|\bnokia\b|smartphone|'
     r'mobile phone|মোবাইল ফোন', ('Electronics', 'Phones & Tablets')),
    (r'doorbell|calling bell|ডোরবেল', ('Electronics', 'Doorbells')),
    (r'smart\s*watch|smartwatch|স্মার্ট.?ওয়াচ', ('Electronics', 'Smartwatches')),
    (r'gamepad|handheld gaming|game console|game valley', ('Electronics', 'Gaming')),
    (r'label printer|price tag', ('Electronics', 'Label Printers')),
    (r'memory card|micro\s*sd|flash drive|pen drive', ('Electronics', 'Memory Cards')),
    (r'laptop stand', ('Electronics', 'Laptop Stands')),
    (r'star(?:ry)?(?: sky)? projector|galaxy.{0,12}projector|night light projector',
     ('Home & Living', 'Projection Night Lights')),
    (r'led strip|fairy string|neon rgb|rope light', ('Home & Living', 'LED Strip Lights')),
    (r'led bulb|self-ballasted|bulb combo|night light', ('Home & Living', 'Lighting')),
    (r'kemei|hair clipper|trimmer|ট্রিমার', ('Beauty & Personal Care', 'Hair Clippers & Trimmers')),
    (r'\bshaver\b|\brazor\b', ('Beauty & Personal Care', 'Grooming')),
    (r'soldering', ('Tools & Home Improvement', 'Soldering Irons')),
    (r'walkie talkie|die-?cast|kids.{0,12}(?:toy|game|tent)', ('Kids & Baby', 'Toys')),
)


def electronics_destination(text):
    return first_match(norm(text), ELECTRONICS_RULES)


BEAUTY_RULES = (
    (r'sunscreen|sunblock|sun gel|sun milk|spf\s*50', ('Beauty & Personal Care', 'Sunscreens')),
    (r'face\s*wash|facial gel wash|cleanser|cleansing foam|ফেসওয়াশ',
     ('Beauty & Personal Care', 'Face Washes')),
    (r'toothbrush|টুথব্রাশ', ('Beauty & Personal Care', 'Toothbrushes')),
    (r'toothpaste|toothgel|টুথপেস্ট', ('Beauty & Personal Care', 'Oral Care')),
    (r'lipstick|makeup pen|লিপস্টিক', ('Beauty & Personal Care', 'Lipsticks')),
    (r'shampoo|keratin|hair oil|চুল.{0,12}কালো|শ্যাম্পু',
     ('Beauty & Personal Care', 'Hair Care')),
    (r'straightener|straightner|heat comb|hair dryer|হেয়ার',
     ('Beauty & Personal Care', 'Hair Straighteners')),
    (r'perfume|attar|পারফিউম|আতর', ('Beauty & Personal Care', 'Perfumes')),
    (r'deodorant|aftershave|body deodor', ('Beauty & Personal Care', 'Fragrances')),
    (r'trimmer|clipper|ট্রিমার', ('Beauty & Personal Care', 'Hair Clippers & Trimmers')),
    (r'toner|ampoule|serum|essence|cream|lotion|mask|scrub|moisturi|'
     r'niacinamide|centella|snail|kojic|whitening|peeling|compact powder|'
     r'aloe vera gel|aloe propolis|aloe moistur|facial|skin care|'
     r'সিরাম|ক্রিম', ('Beauty & Personal Care', 'Skin Care & Cosmetics')),
)


def beauty_destination(text):
    return first_match(norm(text), BEAUTY_RULES)


def _gendered_apparel(text, kind):
    male = bool(re.search(r"\bmen(?:'s)?\b|\bmens\b|\bman\b|\bgents?\b|পুরুষ", text))
    female = bool(re.search(r"\bwomen(?:'s)?\b|\bladies\b|\bfemale\b|মহিলা|লেডিস", text))
    if male and not female:
        return ("Men's Fashion", kind)
    if female and not male:
        return ("Women's Fashion", kind)
    return ('Clothing & Fashion', kind)


CLOTHING_RULES = (
    (r'three[ -]?piece|3\s*pis|থ্রি ?পি[চস]|থ্রী ?পিস|unstitched',
     ("Women's Fashion", 'Three-Piece Sets')),
    (r'saree|শাড়ি|শাড়ি', ("Women's Fashion", 'Sarees')),
    (r'salwar|kameez|কামিজ', ('Clothing & Fashion', 'Salwar Kameez')),
    (r'panjabi|punjabi|পাঞ্জাবি', ("Men's Fashion", 'Panjabis')),
    (r'fatua|ফতুয়া|ফতুয়া', ("Men's Fashion", 'Fatuas')),
    (r'abaya|আবায়া', ("Women's Fashion", 'Abayas')),
    (r'burqa|বোরকা|বোরখা', ("Women's Fashion", 'Burqas')),
    (r'hijab|হিজাব', ("Women's Fashion", 'Hijabs')),
    (r'couple|কাপল', ('Clothing & Fashion', 'Couple Outfit Sets')),
    (r'nightdress|nighty|নাইটি', ("Women's Fashion", 'Nightdresses')),
    (r'hoodie|হুডি', 'Hoodies'),
    (r'sweatshirt|সুইটশার্ট', 'Sweatshirts'),
    (r'sweater|সোয়েটার', 'Sweaters'),
    (r'jacket|জ্যাকেট', 'Jackets'),
    (r'polo|পিকে|piqué|pique cotton', 'Polo Shirts'),
    (r'drop[ -]?shoulder|t[ -]?shirt|টি[ -]?শার্ট|jersey|calligraphy', 'T-Shirts'),
    (r'formal.{0,12}shirt|office.{0,12}shirt', 'Formal Shirts'),
    (r'\bshirts?\b|শার্ট|dubi cotton', 'Casual Shirts'),
    (r'combo set|matching set|two[ -]?piece', 'Matching Sets'),
    (r'jeans|denim', 'Jeans'),
    (r'trouser|ট্রাউজার|পায়জামা|প্লাজু', 'Trousers'),
    (r'nightwear|underwear|inner', ('Clothing & Fashion', 'Nightwear & Underwear')),
    (r'\bshawl\b|শাল', ("Women's Fashion", 'Scarves')),
)


def clothing_destination(text):
    text = norm(text)
    if JEWELRY.search(text) or SUNGLASSES.search(text):
        return None
    kids = kids_destination(text)
    if kids and len(kids) == 2:
        return kids
    for pattern, destination in CLOTHING_RULES:
        if not re.search(pattern, text):
            continue
        if isinstance(destination, str):
            return _gendered_apparel(text, destination)
        return destination
    return None
