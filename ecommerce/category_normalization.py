"""Canonical names shared by imports and the category consolidation command."""
import re


DEPARTMENTS = {
    'Clothing': 'Clothing & Fashion',
    'Jewelry & Watches': 'Watches & Jewelry',
    'Watches & Accessories': 'Watches & Jewelry',
    'Tools & Garden': 'Tools & Home Improvement',
    'Computer & Accessories': 'Electronics',
    'Office & Stationery': 'Electronics',
    'Office & Stationary': 'Electronics',
    'Automotive': 'Tools & Home Improvement',
    'Pet Supplies': 'Home & Living',
    'Kids & Toys': 'Kids & Baby',
    'Toys & Games': 'Kids & Baby',
    'Mobile & Accessories': 'Electronics',
}
PATHS = {
    ('Electronics', 'Smart Watches'): ('Electronics', 'Smartwatches'),
    ('Electronics', 'Smart Watch'): ('Electronics', 'Smartwatches'),
    ('Electronics', 'TV Streaming boxes'): ('Electronics', 'TV Streaming Boxes'),
    ('Electronics', 'Storage & Memory'): ('Electronics', 'USB Flash Drives'),
    ('Electronics', 'Networking'): ('Electronics', 'Networking Equipment'),
    ('Electronics', 'Tracking Devices'): ('Electronics', 'Bluetooth Trackers'),
    ('Electronics', 'Doorbells & Entry'): ('Electronics', 'Doorbells'),
    ('Kitchen & Appliances', 'Water Filters'): ('Kitchen & Dining', 'Water Filters'),
    ('Kitchen & Appliances', 'Fans & Cooling'): ('Home & Living', 'Fans & Cooling'),
    ('Kitchen & Appliances', 'Cooking Appliances'): ('Kitchen & Dining', 'Cooking Appliances'),
    ('Kitchen & Appliances', 'Kitchen & Dining'): ('Kitchen & Dining', 'Kitchen Utensils'),
    ('Shoes & Bags', 'Footwear'): ('Shoes & Footwear', 'Footwear'),
    ('Shoes & Bags', 'Bags & Wallets'): ('Bags & Luggage', 'Bags & Wallets'),
    ('Shoes & Bags', 'Shoe Care'): ('Shoes & Footwear', 'Shoe Care'),
    ('Jewelry & Watches', 'Watches'): ('Watches & Jewelry', 'Wrist Watches'),
    ('Watches & Accessories', 'Wristwatches'): ('Watches & Jewelry', 'Wrist Watches'),
    ('Watches & Jewelry', 'Wristwatches'): ('Watches & Jewelry', 'Wrist Watches'),
    ('Pet Supplies', 'Pet Care'): ('Home & Living', 'Aquarium Supplies'),
    ('Kids & Toys', 'Children’s Clothing'): ('Kids & Baby', "Children's Clothing"),
    ('Kids & Toys', 'Toys & Games'): ('Kids & Baby', 'Toys'),
    ('Toys & Games', 'Drawing & Projection Toys'): ('Kids & Baby', 'Drawing & Projection Toys'),
    ('Toys & Games', 'Toys'): ('Kids & Baby', 'Toys'),
    ('Mobile & Accessories', 'Phone Cases'): ('Electronics', 'Phone Cases & Accessories'),
    ('Electronics', 'Phone Cases'): ('Electronics', 'Phone Cases & Accessories'),
    ('Digital Services', 'Software & Services'): ('Digital Services',),
    ('Clothing', 'Sarees'): ("Women's Fashion", 'Sarees'),
    ('Food & Health', 'Health & Wellness'): ('Health & Wellness', 'Wellness Products'),
    ('Food & Health', 'Food & Drinks'): ('Food & Groceries',),
    ('Food & Groceries', 'Food & Drinks'): ('Food & Groceries',),
}


def canonical_path(path):
    path = tuple(path)
    if len(path) > 2:
        path = (path[0], path[-1])
    if path in PATHS:
        path = PATHS[path]
    if path:
        path = (DEPARTMENTS.get(path[0], path[0]), *path[1:])
    if path in PATHS:
        path = PATHS[path]
    # Merge spelling/spacing synonyms, never different product types.
    if len(path) == 2 and path[0] == 'Electronics' and re.sub(r'\s+', '', path[1]).casefold() in ('smartwatch', 'smartwatches'):
        return ('Electronics', 'Smartwatches')
    return path


def specialized_path(path, title, description=''):
    """Split mixed legacy buckets using explicit product-type evidence."""
    from .taxonomy_proposal import normalized_classification
    path = tuple(path)
    text = str(title).casefold()
    if path[-1:] == ('TV & Streaming',):
        if re.search(r'tv cover|television cover', text):
            return ('Home & Living', 'TV Covers')
        if re.search(r'drawing projector|drawing.*table|projector torch|torch.*projector', text):
            return ('Kids & Baby', 'Drawing & Projection Toys')
        if re.search(r'night light|night lamp|star.*projector|galaxy.*projector|planet.*projector|projector.*(?:light|lamp)|projection lamp', text):
            return ('Home & Living', 'Projection Night Lights')
        if re.search(r'projector|প্রজেক্টর', text):
            return ('Electronics', 'Projectors')
        if re.search(r'television|smart tv|android.*tv|টিভি', text) and not re.search(r'box|streamer|stick', text):
            return ('Electronics', 'Televisions')
        if re.search(r'tv.?box|streamer|tv stick', text):
            return ('Electronics', 'TV Streaming Boxes')
        # A marketing slogan without product evidence cannot establish a type.
        return ('Electronics',)
    if path[-1:] in (('Smart Watches',), ('Smartwatches',)):
        if re.search(r'smart ring', text):
            return ('Electronics', 'Smart Rings')
        if re.search(r'fuel.*pump', text):
            return ('Automotive', 'Fuel Transfer Pumps')
    # Only inspect broad legacy buckets; curated specific types stay stable.
    legacy = {'Hoodies & Sweatshirts', 'Outerwear', 'Dresses', 'Bottoms',
        'Audio & Headphones', 'Power Banks & Chargers', 'Cameras & Security',
        'Bedding', 'Watches', 'Fragrances', 'Storage & Memory', 'Water Filters',
        'Cooking Appliances', 'Bags & Wallets', 'Footwear', 'Kitchen & Dining',
        'Grooming', 'Hair Care', 'Nightwear & Underwear', 'Modest Wear', 'Panjabi & Fatua'}
    if path[-1:] and path[-1] in legacy:
        plan = normalized_classification(title, description=description)
        if plan['path']:
            return canonical_path(plan['path'])
    return canonical_path(path)
