"""Presentation/checkout formatting only; never change authentication usernames."""
import re

def local_contact(value,country='BD'):
    original=str(value or '').strip()
    number=re.sub(r'[\s().-]','',original)
    country=str(country or '').strip().upper()
    if country not in ('BD','BANGLADESH','+880','880'):return original
    if re.fullmatch(r'1[3-9]\d{8}',number):return '0'+number
    # An explicitly displayed country prefix is already unambiguous.
    return original
