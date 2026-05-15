import re

from django import template

register = template.Library()

_DIFF_DEL_RE = re.compile(r"<del\b", re.I)
_CERADIP_HEAD_RE = re.compile(r"^<!--CERADIP_PLAIN:[A-Za-z0-9+/=]+-->", re.I)


@register.filter
def pending_cell_has_diff(value):
    """
    True when a pending-question cell carries diff or legacy edit markup
    (deleted <del>, additions <b> after CERADIP plain prefix, legacy red span).
    """
    if value is None:
        return False
    s = str(value)
    if not s.strip():
        return False
    if _DIFF_DEL_RE.search(s):
        return True
    squish = re.sub(r"\s+", "", s.lower())
    if "color:red" in squish or 'color:"red"' in squish:
        return True
    rest = _CERADIP_HEAD_RE.sub("", s).strip()
    if rest and re.search(r"<b\b", rest, re.I):
        return True
    return False
