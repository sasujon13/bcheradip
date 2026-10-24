"""Safe photo references retained privately until a verified product import."""
from urllib.parse import urlsplit
from .supplier_service import public_url


def source_image_url_condition():
    """Exact media-reference comparison across old/new MySQL table collations."""
    from django.db import connections
    from django.db.models import Q, F
    from django.db.models.functions import Collate
    original, stored = F('source_media__original_url'), F('source_media__stored_url')
    if connections['ecommerce'].vendor == 'mysql':
        # New staging tables can inherit a newer MariaDB default collation than
        # the older shop image table. Compare explicitly without rewriting either.
        original, stored = Collate(original, 'utf8mb4_bin'), Collate(stored, 'utf8mb4_bin')
    return Q(source_media__stored_url='', url=original) | Q(url=stored)


def safe_images(values):
    if not isinstance(values,list): return []
    result=[]
    for value in values[:20]:
        if not isinstance(value,str) or len(value)>1000: continue
        try:
            parts=urlsplit(value)
            if parts.scheme!='https' or parts.query or parts.fragment or parts.port not in (None,443): continue
            if parts.hostname.endswith(('.local','.lan','.internal','.localhost')): continue
            public_url(value)
        except (ValueError,AttributeError): continue
        if value not in result: result.append(value)
    return result
