"""
Apply Location schema change: add local_address, drop post_office, post_code, road_house_no.
Uses pymysql so it runs without Django. Run once; then use migrate for future consistency.
"""
import pymysql

DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '',
    'database': 'cheradip_cheradip',
    'charset': 'utf8mb4',
}

def main():
    conn = pymysql.connect(**DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE table_schema = DATABASE() AND table_name = 'cheradip_location'
        """)
        cols = {r[0] for r in cur.fetchall()}

    with conn.cursor() as cur:
        if 'local_address' not in cols:
            cur.execute("ALTER TABLE cheradip_location ADD COLUMN local_address VARCHAR(500) NULL")
            print("Added column local_address")
        if 'road_house_no' in cols:
            cur.execute("UPDATE cheradip_location SET local_address = TRIM(road_house_no) WHERE road_house_no IS NOT NULL AND TRIM(road_house_no) != ''")
            cur.execute("ALTER TABLE cheradip_location DROP COLUMN road_house_no")
            print("Dropped road_house_no, copied non-empty values to local_address")
        if 'post_code' in cols:
            cur.execute("ALTER TABLE cheradip_location DROP COLUMN post_code")
            print("Dropped post_code")
        if 'post_office' in cols:
            cur.execute("ALTER TABLE cheradip_location DROP COLUMN post_office")
            print("Dropped post_office")
    conn.commit()
    conn.close()
    print("cheradip_location now has local_address; post_office, post_code, road_house_no removed.")

if __name__ == "__main__":
    main()
