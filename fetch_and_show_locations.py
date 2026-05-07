"""
Fetch Bangladesh divisions/districts/upazilas from gov API, insert into cheradip_location,
then show the data. Uses pymysql (no Django). DB config matches insert_all_countries.
"""
import json
import ssl
import urllib.request
import pymysql

# Match insert_all_countries / .env defaults
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '',
    'database': 'cheradip_cheradip',
    'charset': 'utf8mb4',
}

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


def main():
    print("Connecting to database...")
    conn = pymysql.connect(**DB_CONFIG)

    # Ensure BD exists in cheradip_country
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM cheradip_country WHERE country_code = 'BD'")
        if not cur.fetchone():
            print("Inserting Bangladesh (BD) into cheradip_country...")
            cur.execute("""
                INSERT INTO cheradip_country
                (country_code, country_code_alpha3, country_code_numeric, country_name, country_name_native,
                 country_name_official, flag_emoji, flag_url, phone_code, phone_code_numeric, phone_format,
                 phone_length_min, phone_length_max, continent, region, capital, currency_code, currency_symbol,
                 timezone, time_display, language_codes, display_order, is_featured, is_active)
                VALUES ('BD','BGD','050','Bangladesh','বাংলাদেশ',"People's Republic of Bangladesh",'🇧🇩',
                 NULL,'+880',880,'+880 1XXX-XXXXXX',10,10,'Asia','Southern Asia','Dhaka','BDT','৳',
                 'Asia/Dhaka','GMT+6','[\"bn\",\"en\"]',1,1,1)
            """)
            conn.commit()
    print("OK. Fetching divisions from API...")

    div_url = f"{API_BASE}?action=getdoptors&el=doptor&elValue=alldiv&target=first_level&layer=&lang=en&currentHostId={HOST_ID}"
    divisions = fetch_json(div_url)
    div_suffixes = (" Division",)
    dist_suffixes = (" District",)
    upa_suffixes = (" Upazila", " Thana")

    rows = []
    for div_obj in divisions:
        div_id = div_obj["id"]
        div_name = strip_suffix(div_obj.get("name", ""), div_suffixes)
        if not div_name:
            continue
        dist_url = f"{API_BASE}?action=getdoptors&el=first_level&elValue={div_id}&target=second_level&layer=alldiv&lang=en&currentHostId={HOST_ID}"
        try:
            districts = fetch_json(dist_url)
        except Exception as e:
            print(f"  Warning: districts for {div_name} failed: {e}")
            continue
        for dist_obj in districts:
            dist_id = dist_obj["id"]
            dist_name = strip_suffix(dist_obj.get("name", ""), dist_suffixes)
            if not dist_name:
                continue
            upa_url = f"{API_BASE}?action=getdoptors&el=second_level&elValue={dist_id}&target=third_level&layer=alldiv&lang=en&currentHostId={HOST_ID}"
            try:
                upazilas = fetch_json(upa_url)
            except Exception as e:
                print(f"  Warning: upazilas for {dist_name} failed: {e}")
                continue
            for upa_obj in upazilas:
                thana_name = strip_suffix(upa_obj.get("name", ""), upa_suffixes)
                if thana_name:
                    rows.append(("BD", div_name, dist_name, thana_name, ""))

    print(f"Fetched {len(rows)} locations. Inserting into cheradip_location...")

    # Ensure table has country_id and local_address
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE table_schema = DATABASE() AND table_name = 'cheradip_location'
        """)
        cols = {r[0] for r in cur.fetchall()}
    use_country_id = "country_id" in cols
    use_local_address = "local_address" in cols

    # Replace all BD locations so we show exactly what the API returned
    with conn.cursor() as cur:
        if use_country_id:
            cur.execute("DELETE FROM cheradip_location WHERE country_id = 'BD'")
        else:
            cur.execute("DELETE FROM cheradip_location WHERE country = 'BD'")
    conn.commit()

    if use_country_id and use_local_address:
        sql = "INSERT INTO cheradip_location (country_id, division, district, thana, local_address) VALUES (%s,%s,%s,%s,%s)"
    elif use_country_id:
        sql = "INSERT INTO cheradip_location (country_id, division, district, thana) VALUES (%s,%s,%s,%s)"
        rows = [(r[0], r[1], r[2], r[3]) for r in rows]
    else:
        sql = "INSERT INTO cheradip_location (country, division, district, thana, local_address) VALUES (%s,%s,%s,%s,%s)" if use_local_address else "INSERT INTO cheradip_location (country, division, district, thana) VALUES (%s,%s,%s,%s)"
        if not use_local_address:
            rows = [(r[0], r[1], r[2], r[3]) for r in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    print(f"Inserted {len(rows)} rows.\n")

    # Show data
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        if use_country_id:
            sel = "SELECT id, country_id, division, district, thana, local_address FROM cheradip_location WHERE country_id = 'BD' ORDER BY division, district, thana" if use_local_address else "SELECT id, country_id, division, district, thana FROM cheradip_location WHERE country_id = 'BD' ORDER BY division, district, thana"
        else:
            sel = "SELECT id, country, division, district, thana, local_address FROM cheradip_location WHERE country = 'BD' ORDER BY division, district, thana" if use_local_address else "SELECT id, country, division, district, thana FROM cheradip_location WHERE country = 'BD' ORDER BY division, district, thana"
        cur.execute(sel)
        all_rows = cur.fetchall()

    print("=" * 100)
    print("LOCATION TABLE (Bangladesh) – sample and summary")
    print("=" * 100)
    print(f"Total rows: {len(all_rows)}\n")
    if not all_rows:
        conn.close()
        return
    # Sample: first 25 rows
    print("First 25 rows:")
    print("-" * 100)
    keys = list(all_rows[0].keys())
    fmt = "  ".join(f"{{:{max(12, len(k)+2)}s}}" for k in keys)
    print(fmt.format(*keys))
    print("-" * 100)
    for r in all_rows[:25]:
        vals = [str(r.get(k, ""))[:20] for k in keys]
        print(fmt.format(*vals))
    print("-" * 100)
    # Summary by division
    from collections import Counter
    by_div = Counter(r["division"] for r in all_rows if r.get("division"))
    print("\nCount by division:")
    for div, cnt in sorted(by_div.items(), key=lambda x: -x[1]):
        print(f"  {div}: {cnt}")
    print("\nDone.")
    conn.close()


if __name__ == "__main__":
    main()
