"""
Insert data directly into cheradip_subject.
Format: level, country, subject_code, subject_name, groups (tab-separated).
- Creates unique subject code when column is "BD" or blank (from subject_name).
- id = country + "_" + local_code so (country, subject_code) is unique at 100k+ scale.
- No new tables; groups stored as JSON list of strings exactly as in data.
Run: python manage.py insert_subjects
"""
import json
import re
from django.core.management.base import BaseCommand
from django.db import connection

RAW_ROWS = """
HSC	BD	BD101	Bangla 1st Paper	Science, Humanities, Business Studies, Islamic Studies, Home Science, Music
HSC	BD	BD102	Bangla 2nd Paper	Science, Humanities, Business Studies, Islamic Studies, Home Science, Music
HSC	BD	BD107	English 1st Paper	Science, Humanities, Business Studies, Islamic Studies, Home Science, Music
HSC	BD	BD108	English 2nd Paper	Science, Humanities, Business Studies, Islamic Studies, Home Science, Music
HSC	BD	BD275	Information and Communication Technology	Science, Humanities, Business Studies, Islamic Studies, Home Science, Music
HSC	BD	BD174	Physics 1st Paper	Science
HSC	BD	BD175	Physics 2nd Paper	Science
HSC	BD	BD176	Chemistry 1st Paper	Science
HSC	BD	BD177	Chemistry 2nd Paper	Science
HSC	BD	BD178	Biology 1st Paper	Science
HSC	BD	BD179	Biology 2nd Paper	Science
HSC	BD	BD265	Higher Mathematics 1st Paper	Science
HSC	BD	BD266	Higher Mathematics 2nd Paper	Science
HSC	BD	BD180	Engineering Drawing and Workshop Practice 1st Paper	Science
HSC	BD	BD182	Engineering Drawing and Workshop Practice 2nd Paper	Science
HSC	BD	BD183	Engineering Drawing and Workshop Practice 2nd Paper	Science
HSC	BD	BD222	Engineering Drawing and Workshop Practice 2nd Paper	Science
HSC	BD	BD288	Soil Science 1st Paper	Science
HSC	BD	BD289	Soil Science 2nd Paper	Science
HSC	BD	BD239	Agricultural Studies 1st Paper	Science, Humanities, Business Studies, Islamic Studies
HSC	BD	BD240	Agricultural Studies 2nd Paper	Science, Humanities, Business Studies, Islamic Studies
HSC	BD	BD125	Geography 1st Paper	Science, Humanities, Business Studies, Islamic Studies, Home Science
HSC	BD	BD126	Geography 2nd Paper	Science, Humanities, Business Studies, Islamic Studies, Home Science
HSC	BD	BD123	Psychology 1st Paper	Science, Humanities, Islamic Studies, Home Science, Music
HSC	BD	BD124	Psychology 2nd Paper	Science, Humanities, Islamic Studies, Home Science, Music
HSC	BD	BD129	Statistics 1st Paper	Science, Humanities, Business Studies
HSC	BD	BD130	Statistics 2nd Paper	Science, Humanities, Business Studies
HSC	BD	BD304	History 1st Paper	Humanities, Music
HSC	BD	BD305	History 2nd Paper	Humanities, Music
HSC	BD	BD267	History and Culture of Islam 1st Paper	Humanities, Islamic Studies
HSC	BD	BD268	History and Culture of Islam 2nd Paper	Humanities, Islamic Studies
HSC	BD	BD269	Civics and Good Governance 1st Paper	Humanities, Music
HSC	BD	BD270	Civics and Good Governance 2nd Paper	Humanities, Music
HSC	BD	BD109	Economics 1st Paper	Humanities, Business Studies, Islamic Studies, Home Science, Music
HSC	BD	BD110	Economics 2nd Paper	Humanities, Business Studies, Islamic Studies, Home Science, Music
HSC	BD	BD117	Sociology 1st Paper	Humanities, Islamic Studies, Home Science, Music
HSC	BD	BD118	Sociology 2nd Paper	Humanities, Islamic Studies, Home Science, Music
HSC	BD	BD271	Social Work 1st Paper	Humanities, Islamic Studies, Home Science, Music
HSC	BD	BD272	Social Work 2nd Paper	Humanities, Islamic Studies, Home Science, Music
HSC	BD	BD121	Logic 1st Paper	Humanities, Islamic Studies, Music
HSC	BD	BD122	Logic 2nd Paper	Humanities, Islamic Studies, Music
HSC	BD	BD249	Islamic Studies 1st Paper	Humanities, Islamic Studies
HSC	BD	BD250	Islamic Studies 2nd Paper	Humanities, Islamic Studies
HSC	BD	BD273	Home Science 1st Paper	Humanities, Business Studies, Islamic Studies, Music
HSC	BD	BD274	Home Science 2nd Paper	Humanities, Business Studies, Islamic Studies, Music
HSC	BD	BD225	Arts and Crafts 1st Paper	Humanities
HSC	BD	BD226	Arts and Crafts 2nd Paper	Humanities
HSC	BD	BD227	Drama 1st Paper	Humanities
HSC	BD	BD228	Drama 2nd Paper	Humanities
HSC	BD	BD133	Arabic 1st Paper	Humanities, Islamic Studies
HSC	BD	BD134	Arabic 2nd Paper	Humanities, Islamic Studies
HSC	BD	BD139	Pali 1st Paper	Humanities
HSC	BD	BD140	Pali 2nd Paper	Humanities
HSC	BD	BD137	Sanskrit 1st Paper	Humanities
HSC	BD	BD138	Sanskrit 2nd Paper	Humanities
HSC	BD	BD277	Business Organization and Management 1st Paper	Business Studies
HSC	BD	BD278	Business Organization and Management 2nd Paper	Business Studies
HSC	BD	BD253	Accounting 1st Paper	Business Studies
HSC	BD	BD254	Accounting 2nd Paper	Business Studies
HSC	BD	BD292	Finance, Banking and Insurance 1st Paper	Business Studies
HSC	BD	BD293	Finance, Banking and Insurance 2nd Paper	Business Studies
HSC	BD	BD286	Production Management and Marketing 1st Paper	Business Studies
HSC	BD	BD287	Production Management and Marketing 2nd Paper	Business Studies
HSC	BD	BD298	Child Development 1st Paper	Home Science
HSC	BD	BD299	Child Development 2nd Paper	Home Science
HSC	BD	BD279	Food and Nutrition 1st Paper	Home Science
HSC	BD	BD280	Food and Nutrition 2nd Paper	Home Science
HSC	BD	BD282	Home Management and Family Life 1st Paper	Home Science
HSC	BD	BD283	Home Management and Family Life 2nd Paper	Home Science
HSC	BD	BD284	Art and Textile Apparel 1st Paper	Home Science
HSC	BD	BD285	Art and Textile Apparel 2nd Paper	Home Science
HSC	BD	BD216	Light Music 1st Paper	Music
HSC	BD	BD217	Light Music 2nd Paper	Music
HSC	BD	BD218	Classical Music 1st Paper	Music
HSC	BD	BD219	Classical Music 2nd Paper	Music
SSC,JSC	BD	BD	Bengali Literature	
SSC,JSC	BD	BD	Bengali Grammer	
SSC,JSC	BD	BD	English For Today	
SSC,JSC	BD	BD	English Grammar and Composition	
SSC,JSC,PSC	BD	BD	Mathematics	
SSC,JSC,PSC	BD	BD	Information And Communication Technology	
SSC,JSC,PSC	BD	BD	Science	
SSC,JSC	BD	BD	Physics	
SSC,JSC	BD	BD	Chemistry	
SSC,JSC	BD	BD	Biology	
SSC,JSC	BD	BD	Higher Mathematics	
SSC,JSC	BD	BD	Geography and Environment	
SSC,JSC	BD	BD	Economics	
SSC,JSC	BD	BD	Agriculture Studies	
SSC,JSC	BD	BD	Home Science	
SSC,JSC	BD	BD	Civics and Citizenship	
SSC,JSC	BD	BD	Accounting	
SSC,JSC	BD	BD	Finance and Banking	
SSC,JSC	BD	BD	Business Entrepreneurship	
SSC,JSC,PSC	BD	BD	Islamic Studies	
SSC,JSC,PSC	BD	BD	Hindu Religion Studies	
SSC,JSC,PSC	BD	BD	Buddhist Religion Studies	
SSC,JSC,PSC	BD	BD	Christian Religion Studies	
SSC,JSC	BD	BD	Career Education	
SSC,JSC	BD	BD	Bangladesh And Global Studies	
SSC,JSC,PSC	BD	BD	Arts and Crafts	
SSC,JSC	BD	BD	History of Bangladesh and World Civilization	
SSC,JSC,PSC	BD	BD	Physical Education, Health Science and Sports	
SSC,JSC,PSC	BD	BD	Arabic	
SSC,JSC,PSC	BD	BD	Sanskrit	
SSC,JSC,PSC	BD	BD	Pali	
SSC,JSC,PSC	BD	BD	Music	
PSC	BD	BD	Bangla	
PSC	BD	BD	English	
""".strip()

# Unique local code when subject_code is "BD" or blank (max 10 chars for subject_code)
NAME_TO_CODE = {
    'Bengali Literature': 'BLL',
    'Bengali Grammer': 'BLG',
    'English For Today': 'EFT',
    'English Grammar and Composition': 'EGC',
    'Mathematics': 'MAT',
    'Information And Communication Technology': 'ICT',
    'Science': 'SCI',
    'Physics': 'PHY',
    'Chemistry': 'CHM',
    'Biology': 'BIO',
    'Higher Mathematics': 'HMT',
    'Geography and Environment': 'GEO',
    'Economics': 'ECO',
    'Agriculture Studies': 'AGR',
    'Home Science': 'HOS',
    'Civics and Citizenship': 'CIV',
    'Accounting': 'ACC',
    'Finance and Banking': 'FIB',
    'Business Entrepreneurship': 'BUE',
    'Islamic Studies': 'ISL',
    'Hindu Religion Studies': 'HIN',
    'Buddhist Religion Studies': 'BUD',
    'Christian Religion Studies': 'CHR',
    'Career Education': 'CAE',
    'Bangladesh And Global Studies': 'BGS',
    'Arts and Crafts': 'ARC',
    'History of Bangladesh and World Civilization': 'HWC',
    'Physical Education, Health Science and Sports': 'PEH',
    'Arabic': 'ARB',
    'Sanskrit': 'SAN',
    'Pali': 'PAL',
    'Music': 'MUS',
    'Bangla': 'PBS',
    'English': 'PES',
}


def slug_code(name):
    """Fallback: first letters of words, max 6 chars."""
    words = re.sub(r'[^a-zA-Z0-9\s]', '', (name or '')).split()
    s = ''.join(w[0].upper() for w in words[:6] if w)[:6]
    return s or 'X'


def parse_groups(s):
    """Groups as in data: JSON list of strings (e.g. ["Science", "Humanities", ...])."""
    if not s or not s.strip():
        return []
    return [w.strip() for w in s.split(',') if w.strip()]


class Command(BaseCommand):
    help = 'Insert subjects into cheradip_subject; unique id = country + "_" + local_code'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='No DB writes')

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN – no changes saved'))

        with connection.cursor() as cur:
            cur.execute("SELECT 1 FROM cheradip_country WHERE country_code = %s", ['BD'])
            if not cur.fetchone():
                self.stdout.write(self.style.ERROR('Country BD not found.'))
                return
            cur.execute("""
                SELECT COLUMN_NAME FROM information_schema.COLUMNS
                WHERE table_schema = DATABASE() AND table_name = 'cheradip_subject'
            """)
            subject_columns = {r[0] for r in cur.fetchall()}

        if not subject_columns:
            self.stdout.write(self.style.ERROR('Table cheradip_subject not found.'))
            return

        pk_col = 'id' if 'id' in subject_columns else 'subject_code'
        want = ['id', 'country_id', 'subject_code', 'level', 'subject_name', 'subject_name_bn', 'groups']
        cols = [c for c in want if c in subject_columns]
        if pk_col == 'subject_code' and 'id' in cols:
            cols = [c for c in cols if c != 'id']

        created = 0
        updated = 0
        seen_id = set()

        for line in RAW_ROWS.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) < 4:
                continue
            level = (parts[0].strip() if len(parts) > 0 else '') or None
            country = (parts[1].strip() if len(parts) > 1 else '')
            raw_code = (parts[2].strip() if len(parts) > 2 else '')
            subject_name = (parts[3].strip() if len(parts) > 3 else '')
            groups_str = (parts[4].strip() if len(parts) > 4 else '') or ''

            if not subject_name or not country:
                continue

            # Unique code: use BD101 as-is when provided; "BD" or blank -> generate from name
            if raw_code and raw_code != country and len(raw_code) > len(country):
                # e.g. BD101 -> id=BD101, local_code=101
                rest = raw_code[len(country):].lstrip('_') if raw_code.upper().startswith(country.upper()) else raw_code
                local_code = (rest or raw_code)[:10]
                subject_id = (raw_code[:12] if pk_col == 'id' else local_code)
            else:
                local_code = NAME_TO_CODE.get(subject_name) or slug_code(subject_name)
                base, n = local_code, 0
                while (country, local_code) in seen_id:
                    n += 1
                    local_code = f"{base}{n}"[:10]
                seen_id.add((country, local_code))
                subject_id = f"{country}_{local_code}" if pk_col == 'id' else local_code

            subject_id = str(subject_id or '')[:12]
            local_code = (local_code or '')[:10]
            subject_name = (subject_name or '')[:50]
            groups = parse_groups(groups_str)

            if dry_run:
                self.stdout.write(f"  {subject_id} | {local_code} | {level} | {subject_name[:30]} | {len(groups)} groups")
                created += 1
                continue

            val_map = {
                'id': subject_id,
                'country_id': country,
                'subject_code': local_code,
                'level': level,
                'subject_name': subject_name,
                'subject_name_bn': None,
                'groups': json.dumps(groups) if groups else json.dumps([]),
            }
            values = [val_map[c] for c in cols]
            ph = ', '.join(['%s'] * len(cols))
            col_list = ', '.join(f'`{c}`' for c in cols)
            ups = ', '.join(f'`{c}`=VALUES(`{c}`)' for c in cols if c != pk_col)

            with connection.cursor() as cur:
                cur.execute(
                    f"INSERT INTO cheradip_subject ({col_list}) VALUES ({ph}) "
                    f"ON DUPLICATE KEY UPDATE {ups}",
                    values,
                )
                rc = cur.rowcount
            if rc == 1:
                created += 1
            elif rc == 2:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f'Done. Created {created}, updated {updated}.'))
