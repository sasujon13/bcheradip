"""Shared merchandising taxonomy. Supplier labels remain untouched in source storage."""
import html
import re
from django.utils.text import slugify

VERSION = 1
RESEARCH_SOURCES = [
    'https://support.google.com/merchants/answer/7052112?hl=en',
    'https://support.google.com/merchants/answer/9218260?hl=en',
    'https://schema.org/Product',
    'https://schema.org/additionalProperty',
    'https://www.ikea.com/us/en/p/rundhagtorn-duvet-cover-and-pillowcase-s-white-30600152/',
]
PROPERTY_TEMPLATES = {
    'Clothing': ['Material', 'Size', 'Color', 'Fit', 'Sleeve', 'Pattern', 'Care instructions', 'Package contents'],
    'Shoes & Bags': ['Material', 'Size', 'Color', 'Dimensions', 'Capacity', 'Closure', 'Package contents'],
    'Electronics': ['Brand', 'Model', 'Capacity', 'Connectivity', 'Compatibility', 'Power', 'Voltage', 'Battery', 'Dimensions', 'Warranty'],
    'Home & Living': ['Material', 'Dimensions', 'Size', 'Color', 'Number of pieces', 'Care instructions', 'Package contents'],
    'Kitchen & Appliances': ['Material', 'Capacity', 'Power', 'Voltage', 'Dimensions', 'Warranty', 'Package contents'],
    'Beauty & Personal Care': ['Brand', 'Volume', 'Ingredients', 'Skin type', 'Hair type', 'Directions', 'Expiry date'],
    'Jewelry & Watches': ['Material', 'Size', 'Color', 'Movement', 'Water resistance', 'Warranty'],
    'Kids & Toys': ['Material', 'Size', 'Age range', 'Color', 'Dimensions', 'Safety instructions'],
    'Food & Health': ['Weight', 'Ingredients', 'Storage', 'Expiry date', 'Directions', 'Warnings'],
    'Books & Stationery': ['Author', 'Publisher', 'Language', 'Edition', 'ISBN', 'Pages', 'Material', 'Dimensions'],
    'Sports & Outdoors': ['Material', 'Size', 'Weight', 'Dimensions', 'Package contents'],
    'Tools & Garden': ['Material', 'Power', 'Dimensions', 'Compatibility', 'Package contents'],
    'Automotive': ['Brand', 'Model', 'Compatibility', 'Material', 'Dimensions', 'Warranty'],
    'Pet Supplies': ['Material', 'Size', 'Species', 'Ingredients', 'Directions'],
    'Digital Services': ['Compatibility', 'Duration', 'License', 'Requirements'],
}


def clean(value):
    return ' '.join(html.unescape(str(value or '')).split()).strip()


def category_names(categories):
    return [clean(c.get('name') or c.get('category_name') or c.get('title')) if isinstance(c, dict)
            else clean(c) for c in (categories or [])]


# Most specific product types precede broad supplier department fallbacks.
RULES = [
    ('Beauty & Personal Care/Grooming', r'\bKemei\s+(?:Kemei\s+)?KM-026\b'),
    ('Electronics/Camera Accessories', r'chest\s+strap\s+mount|action\s+camera\s+accessor'),
    ('Electronics/Tracking Devices', r'\bMiTag\b|bluetooth\s+tracker'),
    ('Electronics/Phone Cases & Accessories', r'phone\s+waterproof\s+box|waterproof\s+phone\s+(?:box|holder)'),
    ('Electronics/Mobile Gaming Accessories', r'(?:magnetic\s+)?phone\s+cooler\s+fan|semiconductor\s+mobile\s+cooler'),
    ('Electronics/Audio & Headphones', r'\bneckband\b'),
    ('Electronics/Power Banks & Chargers', r'চার্জ\s+সেপারেটর'),
    ('Kitchen & Appliances/Kitchen & Dining', r'electric\s+(?:grape\s+)?peeler|grape\s+peeler'),
    ('Food & Health/Health & Wellness', r'\bmassage\s+gun\b'),
    ('Kids & Toys/Children’s Clothing', r'(?:baby|kids?|children|বেবি|বাচ্চাদের).*(?:hoodie|sweatshirt|jacket|হুডি|জ্যাকেট)'),
    ('Clothing/Matching Sets', r't[ -]?shirt\s+(?:and|&)\s+(?:short\s+)?(?:trouser|pant)s?\s+set|\bskirt\s+set\b'),
    ('Electronics/Audio & Headphones', r'bluetooth\s+spea'),
    ('Electronics/Doorbells & Entry', r'calling\s+bell|door\s*bell|ডোরবেল'),
    ('Sports & Outdoors/Outdoor Gear', r'\bumbrella\b|ছাতা'),
    ('Shoes & Bags/Bags & Wallets', r'\bbackpa'),
    ('Books & Stationery/Stationery & Crafts', r'price\s+tag\s+labe'),
    ('Tools & Garden/Tools & Gardening', r'\bDT8(?:30|32)\b|\bmultimeter\b'),
    ('Home & Living/Lighting', r'\b(?:table|desk)\s+lamp\b|smart\s+table\s+lamp'),
    ('Electronics/Audio & Headphones', r'bluetooth\s+speaker|smart\s+light\s+bluetooth\s+speaker'),
    ('Tools & Garden/Tools & Gardening', r'soldering\s+flux|digital\s+multimeter'),
    ('Shoes & Bags/Bags & Wallets', r'\bbackpack\b'),
    ('Books & Stationery/Stationery & Crafts', r'price\s+tag\s+label'),
    ('Home & Living/Cleaning & Laundry', r'\bdry\s+iron\b'),
    ('Home & Living/Clocks', r'\bclocks?\b|দেয়াল.*ঘড়ি'),
    ('Home & Living/Decor & Gifts', r'crystal\s*ball|photo\s*alb[ul]m|polaroid.*all?bum'),
    ('Home & Living/Storage & Organization', r'organiz|storage\s*box|hanger|rack|shelf'),
    ('Home & Living/Cleaning & Laundry', r'car\s*wash|vacuum|broom|duster'),
    ('Home & Living/Soft Furnishings', r'curtain|mosquito\s*net|carpet|rug\b|পর্দা|মশারি'),
    ('Home & Living/Personal Accessories', r'lighter|লাইটার|combination\s*lock'),
    ('Shoes & Bags/Bags & Wallets', r'card\s*holder'),
    ('Shoes & Bags/Shoe Care', r'shoe\s*(?:cleaner|cleaning|polish|brush)|জুতা.*(?:পরিষ্কার|পলিশ)'),
    ('Electronics/Batteries & Power Supplies', r'\bbattery\b|batteries|solar\s*charge|power\s*strip|voltage\s*protector|extension\s*socket|\bups\b'),
    ('Electronics/Audio & Headphones', r'headset|\bairpods?\b'),
    ('Electronics/Cameras & Security', r'gimbal|quadrapod|\bairtag\b'),
    ('Electronics/Computers & Accessories', r'\bhub\b|usb.*adapter|card\s*reader'),
    ('Electronics/Power Banks & Chargers', r'gan.*adapter|pd.*charge|travel\s*adapter'),
    ('Electronics/Smart Rings', r'smart\s*ring'),
    ('Kitchen & Appliances/Cooking Appliances', r'kettle|feather\s*plucker'),
    ('Kitchen & Appliances/Kitchen & Dining', r'egg\s*(box|storage|organizer)'),
    ('Tools & Garden/Tools & Gardening', r'wrench|adhesive\s*tape|sewing\s*machine|fertili[sz]er|screwdriver|self.defense'),
    ('Food & Health/Health & Wellness', r'blood\s*pressure|thermometer|oximeter'),
    ('Books & Stationery/Stationery & Crafts', r'calculator|marker\s*pens?|currency\s*counter'),
    ('Sports & Outdoors/Sports Equipment', r'scooter|punching\s*bag|bicycle|dumbbell'),
    ('Beauty & Personal Care/Oral Care', r'toothbrush|dental|toothpaste'),
    ('Pet Supplies/Pet Care', r'fish\s*medicine|aquarium'),
    ('Home & Living/Bedding', r'comforter|duvet|bed\s*sheet|bedding|blanket|pillow|quilt|কম্ফর্টার|বেডশীট|বেডশিট|ব্লাঙ্কেট|কাথা|কাঁথা|বালিশ'),
    ('Electronics/Storage & Memory', r'micro\s*sd|memory\s*card|flash\s*drive|\bssd\b|\bhdd\b|মেমোরি'),
    ('Home & Living/TV Covers', r'tv\s*cover|television\s*cover'),
    ('Toys & Games/Drawing & Projection Toys', r'drawing\s*projector|drawing.*table|projector\s*torch|torch.*projector'),
    ('Home & Living/Projection Night Lights', r'night\s*(?:light|lamp).*projector|(?:star|galaxy|planet).*projector|projector.*night\s*(?:light|lamp)'),
    ('Electronics/TV Streaming Boxes', r'\btv\s*(?:box|stick)|streamer|টিভি বক্স'),
    ('Electronics/Projectors', r'projector|প্রজেক্টর'),
    ('Electronics/Televisions', r'smart\s*tv|television|টিভি'),
    ('Electronics/Cameras & Security', r'\bcctv\b|security\s*camera|wifi\s*camera|camera|ক্যামেরা|সিসিটিভি'),
    ('Electronics/Networking', r'router|\bonu\b|modem|রাউটার'),
    ('Electronics/Audio & Headphones', r'earbud|earphone|headphone|neckband|speaker|microphone|\btws\b|হেডফোন|মাইক্রোফোন|নেকব্যান্ড|স্পিকার'),
    ('Electronics/Smart Watches', r'smart\s*watch|smartwatch|fitness\s*bracelet|স্মার্ট\s*ওয়া?চ|স্মার্ট\s*ওয়াচ'),
    ('Electronics/Power Banks & Chargers', r'power\s*bank|charger|charging|পাওয়ার\s*ব্যাংক|চার্জার'),
    ('Electronics/Phone Cases & Accessories', r'phone\s*(case|cover|stand)|back\s*cover|screen\s*protector|mobile\s*(case|casing|housing|display|batter)|iphone\s*.*cover|sim\s*tool|selfie|tripod|সেলফি|ট্রাইপড|মোবাইল.*কভার'),
    ('Electronics/Phones & Tablets', r'\b(smartphone|tablet|mobile\s*phone|button\s*mobile)\b|মোবাইল\s*ফোন'),
    ('Electronics/Computers & Accessories', r'laptop|desktop|keyboard|mouse|computer|cable|converter|কীবোর্ড|মাউস|ল্যাপটপ'),
    ('Electronics/Gaming', r'gaming|gamepad|গেমিং'),
    ('Kitchen & Appliances/Fans & Cooling', r'\bfan\b|air\s*cooler|air\s*condition|ফ্যান'),
    ('Kitchen & Appliances/Cooking Appliances', r'rice\s*cooker|blender|juicer|grinder|air\s*fryer|oven|toaster|কুকার|ব্লেন্ডার|জুসার'),
    ('Kitchen & Appliances/Water Filters', r'water\s*(filter|purifier)|ওয়াটার.*ফিল্টার'),
    ('Kitchen & Appliances/Kitchen & Dining', r'kitchen|cookware|cooking|cutlery|dining|lunch\s*box|knife|chopper|bottle|mug|রান্নাঘর|ডাইনিং|বোতল|কিচেন'),
    ('Beauty & Personal Care/Grooming', r'trimmer|shaver|hair\s*clipper|চুল\s*কাটা|ট্রিমার'),
    ('Beauty & Personal Care/Fragrances', r'perfume|fragrance|attar|body\s*spray|পারফিউম|আতর'),
    ('Beauty & Personal Care/Hair Care', r'shampoo|hair\s*(care|treatment|oil|dryer|straightener)|শ্যাম্পু|চুলের'),
    ('Beauty & Personal Care/Skin Care & Cosmetics', r'cosmetic|skin\s*care|serum|cream|lipstick|makeup|soap|সিরাম|ক্রিম|সাবান|কসমেটিক'),
    ('Clothing/Ethnic Wear/Sarees', r'saree|sari\b|শাড়|শাড়|শাড়ি|শাড়ি'),
    ('Clothing/Ethnic Wear/Salwar Kameez', r'salwar|shalwar|kameez|three\s*piece|থ্রি\s*পিস|থ্রী\s*পিস|থ্রিপিস|থ্রীপিস|কামিজ'),
    ('Clothing/Ethnic Wear/Panjabi & Fatua', r'panjabi|punjabi|fatua|পাঞ্জাবি|পাঞ্জাবী|কাতুয়া|ফতুয়া'),
    ('Clothing/Modest Wear', r'abaya|hijab|burqa|niqab|বোরকা|বোরখা|বোর্?কা|হিজাব|নিকাব'),
    ('Clothing/Nightwear & Underwear', r'night\s*wear|nightwear|underwear|inner\s*garment|\bbra\b|\bpanty\b|নাইটি|ইনার'),
    ('Kids & Toys/Children’s Clothing', r'baby.*(dress|shirt|cloth|pant|winter)|kids?.*(dress|shirt|cloth|pant|winter)|কিডস.*প্যান্ট|বেবি.*(কামিজ|শার্ট|বোরখা)|গার্লস.*সেট|বয়েজ.*সেট|পরী\s*ড্রেস'),
    ('Clothing/Tops/Hoodies & Sweatshirts', r'hoodie|sweatshirt|sweetshirt|হুডি|সুইটশার্ট'),
    ('Clothing/Outerwear', r'jacket|sweater|overcoat|blazer|shacket|জ্যাকেট|সুয়েটার|সোয়েটার|ওভারকোট|শ্যাকেট'),
    ('Clothing/Tops/Polo Shirts', r'polo|পলো'),
    ('Clothing/Tops/T-Shirts', r't[ -]?shirt|টিশার্ট|টি.?শার্ট'),
    ('Clothing/Tops/Shirts', r'\bshirt\b|শার্ট'),
    ('Clothing/Bottoms', r'jeans|trouser|\bpants?\b|প্যান্ট|ট্রাউজার'),
    ('Clothing/Dresses', r'dress|gown|kurti|lehenga|স্কার্ট|ড্রেস|গাউন|কুর্তি|লেহেঙ্গা'),
    ('Shoes & Bags/Footwear', r'shoes?|sneaker|sandal|slipper|জুতা|স্যান্ডেল'),
    ('Shoes & Bags/Bags & Wallets', r'bag|wallet|purse|luggage|ব্যাগ|মানিব্যাগ'),
    ('Jewelry & Watches/Watches', r'\bwatch(es)?\b|ঘড়ি|ঘড়ি'),
    ('Jewelry & Watches/Jewelry & Accessories', r'jewel|necklace|pendant|earring|bracelet|sunglass|chain|জুয়েলারি|চেইন|ক্লিপ|ব্যান্ড'),
    ('Home & Living/Clocks', r'\bclocks?\b|দেয়াল.*ঘড়ি'),
    ('Home & Living/Lighting', r'light|lamp|লাইট'),
    ('Home & Living/Furniture', r'furniture|chair|sofa|desk|আসবাব'),
    ('Home & Living/Decor & Gifts', r'decor|showpiece|gift|গৃহ\s*সজ্জা|ঘর\s*সাজানো|সাজ\s*সজ্জা|গিফট'),
    ('Home & Living/Cleaning & Laundry', r'lint\s*remover|laundry|cleaning|mop|পরিষ্কার|হোম\s*কেয়ার'),
    ('Kids & Toys/Toys & Games', r'toys?|খেলনা'),
    ('Food & Health/Food & Drinks', r'food|honey|coffee|tea\b|খাবার|মধু|খেজুর'),
    ('Food & Health/Health & Wellness', r'supplement|medicine|massager|wellness|সাপ্লিমেন্ট|মেডিসিন|ম্যাসেজার|সেক্সচুয়াল'),
    ('Books & Stationery/Books', r'books?|বই'),
    ('Books & Stationery/Stationery & Crafts', r'stationery|craft|notebook|pen\b|খাতা|কলম|প্যাকেজিং'),
    ('Sports & Outdoors/Sports Equipment', r'sports?|football|ফুটবল|ওয়ার্ল্ড\s*কাপ'),
    ('Tools & Garden/Tools & Gardening', r'tools?|garden|seed|বীজ'),
    ('Automotive/Vehicle Accessories', r'automotive|motorcycle|car\s+accessor'),
    ('Pet Supplies/Pet Care', r'pet\s|fish\s*medicine|aquarium'),
    ('Digital Services/Software & Services', r'digital\s*product|online\s*service|software'),
]
COMPILED = [(tuple(path.split('/')), re.compile(pattern, re.I)) for path, pattern in RULES]
GENERIC = re.compile(r'^(all\s*products?|large\s*products?|extra\s*large(?:\s*products?)?|extra\s*items?|supplier\s*collection|random|others?\W*|সব\s*দেখুন|সব\s*পণ্য|accessories|এক্সেসরিজ)$', re.I)
FALLBACKS = [
    ('Clothing', r'fashion|clothing|winter|wear|men|women|শীত'),
    ('Electronics', r'electronic|gadget|গ্যাজেট'),
    ('Home & Living', r'home|household|lifestyle|হোম'),
    ('Beauty & Personal Care', r'beauty|personal\s*care|পার্সোনাল'),
    ('Kids & Baby', r'kids?|baby|বেবি'),
]


def classify(title, categories=(), description=''):
    def assignment(path, reason):
        if path[-1:] == ('Dresses',):
            from .taxonomy_proposal import normalized_classification
            specific = normalized_classification(title, description=description)
            if specific['status'] == 'assigned' and len(specific['path']) == 2:
                return {**specific, 'reason': reason + ':specific_dress_type'}
            return {'path': [], 'status': 'needs_review',
                    'reason': 'Specific dress type needs review', 'version': VERSION}
        return {'path': list(path), 'status': 'assigned', 'reason': reason, 'version': VERSION}
    labels = [c for c in category_names(categories) if c and not GENERIC.fullmatch(c)]
    for origin, text in [('title', clean(title)), ('supplier_category', ' | '.join(labels))]:
        for path, pattern in COMPILED:
            if pattern.search(text):
                return assignment(path, origin)
    if description:
        from lxml import html as markup
        try:
            doc=markup.fragment_fromstring(description,create_parent='div')
            for n in doc.xpath('.//script|.//style'): n.drop_tree()
            paragraphs=doc.xpath('.//h1|.//h2|.//p')
            intro=clean(' '.join(n.text_content() for n in paragraphs[:2]) if paragraphs else doc.text_content())[:450]
        except (ValueError,TypeError): intro=''
        matches={path for path,pattern in COMPILED if pattern.search(intro)}
        if len(matches)==1:
            return assignment(matches.pop(), 'supplier_description')
    for root, pattern in FALLBACKS:
        if any(re.search(pattern, label, re.I) for label in labels):
            return {'path': [root], 'status': 'assigned', 'reason': 'supplier_department', 'version': VERSION}
    return {'path': [], 'status': 'needs_review', 'reason': 'Product type is not established by the supplied information.', 'version': VERSION}


def category_slug(path):
    from .category_normalization import canonical_path
    path = canonical_path(path)
    return slugify(' '.join(path))[:180]


def ensure_category(path):
    from .models import Category
    from .category_normalization import canonical_path
    path = canonical_path(path)
    # Compatibility for old importers: never recreate an intermediate third
    # level. The reviewed normalizer replaces legacy broad labels separately.
    if len(path) > 2:
        path = (path[0], path[-1])
    parent = None
    for i, name in enumerate(path):
        parent, _ = Category.objects.using('ecommerce').update_or_create(slug=category_slug(path[:i+1]), defaults={
            'name': name, 'parent': parent, 'is_active': True,
            'description': 'Product properties: ' + ', '.join(PROPERTY_TEMPLATES.get(path[0], [])),
        })
    return parent
