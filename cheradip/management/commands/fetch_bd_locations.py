"""
Fetch Bangladesh divisions, districts, upazilas (thanas) from gov API, and post office/post code from district pages.

API: https://login.chittagong.gov.bd/api/v1/theme/ajax
- Divisions: el=doptor&elValue=alldiv&target=first_level  -> strip " Division"
- Districts: el=first_level&elValue={div_id}&target=second_level  -> strip " District"
- Upazilas:  el=second_level&elValue={district_id}&target=third_level  -> strip " Upazila"

Post office/post code: parsed from district geo-code pages (e.g. Chittagong).
URL pattern: https://www.{domain}.gov.bd/en/site/page/PwSk-{bengali}-জেলার-জিও-কোড-ও-পোস্ট-কোড

Run: python manage.py fetch_bd_locations
"""
import json
import ssl
import urllib.request
from html.parser import HTMLParser
from urllib.parse import quote
from django.core.management.base import BaseCommand
from cheradip.models import Location, Country


API_BASE = "https://login.chittagong.gov.bd/api/v1/theme/ajax"
HOST_ID = "31649"


def strip_suffix(name, suffixes):
    for s in suffixes:
        if name.endswith(s):
            return name[:-len(s)].strip()
    return name.strip()


def fetch_json(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_html(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


class TableParser(HTMLParser):
    """Extract rows from HTML table; each row is list of cell texts."""
    def __init__(self):
        super().__init__()
        self.rows = []
        self.in_tr = False
        self.in_td = False
        self.current_row = []
        self.current_cell = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_tr = True
            self.current_row = []
        elif tag == "td" and self.in_tr:
            self.in_td = True
            self.current_cell = []

    def handle_endtag(self, tag):
        if tag == "tr":
            self.in_tr = False
            if self.current_row:
                self.rows.append(self.current_row)
        elif tag == "td" and self.in_td:
            self.in_td = False
            self.current_row.append(" ".join(self.current_cell).strip())

    def handle_data(self, data):
        if self.in_td:
            self.current_cell.append(data)


def parse_post_code_table(html, district_name_normalize=None):
    """
    Parse table with columns: District | Thana/Upazila | Post Office | Code.
    Returns list of (district, thana, post_office, code).
    district_name_normalize: callable to normalize district name for matching, or None.
    """
    p = TableParser()
    p.feed(html)
    out = []
    for row in p.rows:
        if len(row) < 4:
            continue
        dist, thana, post_office, code = row[0].strip(), row[1].strip(), row[2].strip(), row[3].strip()
        if not code or not code.isdigit():
            continue
        if district_name_normalize:
            dist = district_name_normalize(dist)
        out.append((dist, thana, post_office, code))
    return out


# (district_name_in_db, [aliases_from_page], url) — match Location by district name or alias.
# URL pattern: https://www.{domain}.gov.bd/en/site/page/PwSk-{bengali}-জেলার-জিও-কোড-ও-পোস্ট-কোড
_SUFFIX = "-\u099c\u09c7\u09b2\u09be\u09b0-\u099c\u09bf\u0993-\u0995\u09cb\u09a1-\u0993-\u09aa\u09cb\u09b8\u09cd\u099f-\u0995\u09cb\u09a1"  # -জেলার-জিও-কোড-ও-পোস্ট-কোড
_POST_CODE_RAW = [
    ("Cumilla", "comilla", "\u0995\u09c1\u09ae\u09bf\u09b2\u09cd\u09b2\u09be", ["Comilla"]),
    ("Feni", "feni", "\u09ab\u09c7\u09a8\u09c0", []),
    ("Brahmanbaria", "brahmanbaria", "\u09ac\u09cd\u09b0\u09b9\u09cd\u09ae\u09a3\u09ac\u09be\u09a1\u09bc\u09bf\u09af\u09bc\u09be", []),
    ("Rangamati", "rangamati", "\u09b0\u09be\u0999\u09cd\u0997\u09be\u09ae\u09be\u09a4\u09bf", []),
    ("Noakhali", "noakhali", "\u09a8\u09cb\u09af\u09bc\u09be\u0996\u09be\u09b2\u09c0", []),
    ("Chandpur", "chandpur", "\u099a\u09be\u0981\u09a6\u09aa\u09c1\u09b0", []),
    ("Lakshmipur", "lakshmipur", "\u09b2\u0995\u09cd\u09b7\u09cd\u09ae\u09c0\u09aa\u09c1\u09b0", []),
    ("Chattogram", "chittagong", "\u099a\u099f\u09cd\u099f\u0997\u09cd\u09b0\u09be\u09ae", ["Chittagong"]),  # চট্টগ্রাম
    ("Cox's Bazar", "coxsbazar", "\u0995\u0995\u09cd\u09b8\u09ac\u09be\u099c\u09be\u09b0", ["Coxs Bazar"]),
    ("Khagrachhari", "khagrachhari", "\u0996\u09be\u0997\u09b0\u09be\u099b\u09b0\u09bf", []),
    ("Bandarban", "bandarban", "\u09ac\u09be\u09a8\u09cd\u09a6\u09b0\u09ac\u09be\u09a8", []),
    ("Sirajganj", "sirajganj", "\u09b8\u09bf\u09b0\u09be\u099c\u09c7\u0999\u09cd\u0997\u09a8\u09cd\u099c", []),
    ("Pabna", "pabna", "\u09aa\u09be\u09ac\u09a8\u09be", []),
    ("Bogra", "bogra", "\u09ac\u0997\u09c1\u09a1\u09bc\u09be", []),
    ("Rajshahi", "rajshahi", "\u09b0\u09be\u099c\u09b6\u09be\u09b9\u09c0", []),
    ("Natore", "natore", "\u09a8\u09be\u09f0\u09cb\u09b0", []),
    ("Joypurhat", "joypurhat", "\u099c\u09af\u09bc\u09aa\u09c1\u09b0\u09b9\u09be\u09f0", []),
    ("Chapainawabganj", "chapainawabganj", "\u099a\u09be\u09aa\u09be\u0987\u09a8\u09ac\u09be\u09ac\u0997\u09a8\u09cd\u099c", []),
    ("Naogaon", "naogaon", "\u09a8\u0993\u0997\u09be\u0981", []),  # নওগাঁ
    ("Jashore", "jashore", "\u09af\u09b6\u09cb\u09b0", ["Jessore"]),
    ("Satkhira", "satkhira", "\u09b8\u09be\u09a4\u0996\u09c0\u09b0\u09be", []),
    ("Meherpur", "meherpur", "\u09ae\u09c7\u09b9\u09c7\u09b0\u09aa\u09c1\u09b0", []),
    ("Narail", "narail", "\u09a8\u09b0\u09be\u0987\u09b2", []),
    ("Chuadanga", "chuadanga", "\u099a\u09c1\u09af\u09bc\u09be\u09a1\u09be\u0999\u09cd\u0997\u09be", []),
    ("Kushtia", "kushtia", "\u0995\u09c1\u09b7\u09f0\u09bf\u09af\u09bc\u09be", []),
    ("Magura", "magura", "\u09ae\u09be\u0997\u09c1\u09b0\u09be", []),
    ("Khulna", "khulna", "\u0996\u09c1\u09b2\u09a8\u09be", []),
    ("Bagerhat", "bagerhat", "\u09ac\u09be\u0997\u09c7\u09b0\u09b9\u09be\u09f0", []),
    ("Jhenaidah", "jhenaidah", "\u099d\u09c7\u09a8\u09be\u0987\u09a6\u09be\u09b9", []),
    ("Jhalakathi", "jhalakathi", "\u099d\u09be\u09b2\u0995\u09be\u09a0\u09bf", []),
    ("Patuakhali", "patuakhali", "\u09aa\u09f0\u09c1\u09af\u09bc\u09be\u0996\u09be\u09b2\u09c0", []),
    ("Pirojpur", "pirojpur", "\u09aa\u09bf\u09b0\u09cb\u099c\u09aa\u09c1\u09b0", []),
    ("Barishal", "barisal", "\u09ac\u09b0\u09bf\u09b6\u09be\u09b2", ["Barisal"]),
    ("Bhola", "bhola", "\u09ad\u09cb\u09b2\u09be", []),
    ("Barguna", "barguna", "\u09ac\u09b0\u09c1\u0997\u09c1\u09a8\u09be", []),
    ("Sylhet", "sylhet", "\u09b8\u09bf\u09b2\u09c7\u09f0", []),
    ("Moulvibazar", "moulvibazar", "\u09ae\u09cc\u09b2\u09ad\u09c0\u09ac\u09be\u099c\u09be\u09b0", []),
    ("Habiganj", "habiganj", "\u09b9\u09ac\u09bf\u0997\u09a8\u09cd\u099c", []),
    ("Sunamganj", "sunamganj", "\u09b8\u09c1\u09a8\u09be\u09ae\u0997\u09a8\u09cd\u099c", []),
    ("Narsingdi", "narsingdi", "\u09a8\u09b0\u09b8\u09bf\u0999\u09cd\u0997\u09a6\u09bf", []),
    ("Gazipur", "gazipur", "\u0997\u09be\u099c\u09c0\u09aa\u09c1\u09b0", []),
    ("Shariatpur", "shariatpur", "\u09b6\u09b0\u09bf\u09af\u09bc\u09be\u09a4\u09aa\u09c1\u09b0", []),
    ("Narayanganj", "narayanganj", "\u09a8\u09be\u09b0\u09be\u09af\u09bc\u09a3\u0997\u09a8\u09cd\u099c", []),
    ("Tangail", "tangail", "\u09f0\u09be\u0999\u09cd\u0997\u09be\u0987\u09b2", []),
    ("Kishoreganj", "kishoreganj", "\u0995\u09bf\u09b6\u09cb\u09b0\u0997\u09a8\u09cd\u099c", []),
    ("Manikganj", "manikganj", "\u09ae\u09be\u09a8\u09bf\u0995\u0997\u09a8\u09cd\u099c", []),
    ("Dhaka", "dhaka", "\u09a2\u09be\u0995\u09be", []),
    ("Munshiganj", "munshiganj", "\u09ae\u09c1\u09a8\u09cd\u09b6\u09bf\u0997\u09a8\u09cd\u099c", []),
    ("Rajbari", "rajbari", "\u09b0\u09be\u099c\u09ac\u09be\u09a1\u09bc\u09bf", []),
    ("Madaripur", "madaripur", "\u09ae\u09be\u09a6\u09be\u09b0\u09c0\u09aa\u09c1\u09b0", []),
    ("Gopalganj", "gopalganj", "\u0997\u09cb\u09aa\u09be\u09b2\u0997\u09a8\u09cd\u099c", []),
    ("Faridpur", "faridpur", "\u09ab\u09b0\u09c0\u09a6\u09aa\u09c1\u09b0", []),
    ("Panchagarh", "panchagarh", "\u09aa\u09be\u0999\u09cd\u099a\u0997\u09b0\u09b9", []),
    ("Dinajpur", "dinajpur", "\u09a6\u09bf\u09a8\u09be\u099c\u09aa\u09c1\u09b0", []),
    ("Lalmonirhat", "lalmonirhat", "\u09b2\u09be\u09b2\u09ae\u09a8\u09bf\u09b0\u09b9\u09be\u09f0", []),
    ("Nilphamari", "nilphamari", "\u09a8\u09c0\u09b2\u09ab\u09be\u09ae\u09be\u09b0\u09bf", []),
    ("Gaibandha", "gaibandha", "\u0997\u09bc\u09be\u0987\u09ac\u09be\u0999\u09cd\u09a7\u09be", []),
    ("Thakurgaon", "thakurgaon", "\u09a0\u09be\u0995\u09c1\u09b0\u0997\u09be\u0981", []),
    ("Rangpur", "rangpur", "\u09b0\u0999\u09cd\u0997\u09aa\u09c1\u09b0", []),
    ("Kurigram", "kurigram", "\u0995\u09c1\u09a1\u09bc\u09bf\u0997\u09b0\u09be\u09ae", []),
    ("Sherpur", "sherpur", "\u09b6\u09c7\u09b0\u09aa\u09c1\u09b0", []),
    ("Mymensingh", "mymensingh", "\u09ae\u09af\u09bc\u09ae\u09a8\u09b8\u09bf\u0999\u09cd\u0997\u09b9", []),
    ("Jamalpur", "jamalpur", "\u099c\u09be\u09ae\u09be\u09b2\u09aa\u09c1\u09b0", []),
    ("Netrokona", "netrokona", "\u09a8\u09c7\u09a4\u09cd\u09b0\u0995\u09cb\u09a3\u09be", []),
]


def _build_post_code_url(domain, bengali_slug):
    slug = bengali_slug + _SUFFIX
    return f"https://www.{domain}.gov.bd/en/site/page/PwSk-{quote(slug, safe='')}"


POST_CODE_PAGES = [
    (db_name, [db_name] + list(extra_aliases), _build_post_code_url(domain, bengali))
    for db_name, domain, bengali, extra_aliases in _POST_CODE_RAW
]

class Command(BaseCommand):
    help = "Fetch Bangladesh divisions/districts/upazilas from gov API and post office/post code from district pages"

    def handle(self, *args, **options):
        bd = Country.objects.filter(country_code="BD").first()
        if not bd:
            self.stdout.write(self.style.WARNING("Country BD not found. Run insert_all_countries first."))
            return

        self.stdout.write("Fetching divisions...")
        div_url = (
            f"{API_BASE}?action=getdoptors&el=doptor&elValue=alldiv&target=first_level"
            f"&layer=&lang=en&currentHostId={HOST_ID}"
        )
        try:
            divisions = fetch_json(div_url)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch divisions: {e}"))
            return

        # Normalize: "Khulna Division" -> "Khulna"
        div_suffixes = (" Division",)
        dist_suffixes = (" District",)
        upa_suffixes = (" Upazila", " Thana")

        total_locs = 0
        for div_obj in divisions:
            div_id = div_obj["id"]
            div_name = strip_suffix(div_obj.get("name", ""), div_suffixes)
            if not div_name:
                continue

            self.stdout.write(f"  Division: {div_name} (id={div_id})")
            dist_url = (
                f"{API_BASE}?action=getdoptors&el=first_level&elValue={div_id}&target=second_level"
                f"&layer=alldiv&lang=en&currentHostId={HOST_ID}"
            )
            try:
                districts = fetch_json(dist_url)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"    Districts fetch failed: {e}"))
                continue

            for dist_obj in districts:
                dist_id = dist_obj["id"]
                dist_name = strip_suffix(dist_obj.get("name", ""), dist_suffixes)
                if not dist_name:
                    continue

                upa_url = (
                    f"{API_BASE}?action=getdoptors&el=second_level&elValue={dist_id}&target=third_level"
                    f"&layer=alldiv&lang=en&currentHostId={HOST_ID}"
                )
                try:
                    upazilas = fetch_json(upa_url)
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"      Upazilas for {dist_name} failed: {e}"))
                    continue

                for upa_obj in upazilas:
                    thana_name = strip_suffix(upa_obj.get("name", ""), upa_suffixes)
                    if not thana_name:
                        continue
                    loc, created = Location.objects.update_or_create(
                        country=bd,
                        division=div_name,
                        district=dist_name,
                        thana=thana_name,
                        defaults={"local_address": ""},
                    )
                    if created:
                        total_locs += 1

        self.stdout.write(self.style.SUCCESS(f"Locations created/updated from API. New: {total_locs}"))

        self.stdout.write(self.style.SUCCESS("Done."))
