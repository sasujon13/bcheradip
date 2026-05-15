"""One-off: verify admin changelist HTML includes filter enhancement script."""
import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
u = User.objects.filter(is_staff=True, is_superuser=True).first()
print("user", u)
c = Client()
if not u:
    sys.exit(0)
c.force_login(u)
r = c.get("/admin/cheradip/customer/", HTTP_HOST="localhost")
print("status", r.status_code)
t = r.content.decode("utf-8", errors="replace")
if r.status_code != 200:
    print("body_head", repr(t[:800]))
print("has_js", "admin/js/admin_changelist_filters.js" in t)
j = t.find("admin/js/admin_changelist_filters.js")
print("js_snippet", repr(t[j - 20 : j + 120]) if j >= 0 else "NONE")
print("extrabody_near_end", repr(t[-1200:]))
