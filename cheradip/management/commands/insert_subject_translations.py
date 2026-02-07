# -*- coding: utf-8 -*-
"""
Insert Bengali (and other) translations into cheradip_subject_translated.
Format: lang, level, country, subject_code, subject_name, groups (tab-separated).
- subject_name holds the translated name; level and groups are stored exactly as in your data.
- Level/code in Bengali are normalized to English only for subject_id lookup (not for storage).
- subject_id: HSC with code -> BD + digits; SSC/JSC/PSC with blank code -> BD_ + BN_NAME_TO_CODE[name].
Run: python manage.py insert_subject_translations
"""
import json
import re
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

# Bengali level (or Latin) -> English level
LEVEL_BN_TO_EN = {
    'এইসএসসি': 'HSC',
    'এসএসসি,জেএসসি': 'SSC,JSC',
    'এসএসসি,জেএসসি,পিএসসি': 'SSC,JSC,PSC',
    'পিএসসি': 'PSC',
}

# Bengali subject name -> local_code (for rows with empty subject_code); subject_id = country + '_' + code
BN_NAME_TO_CODE = {
    'বাংলা সাহিত্য': 'BLL',
    'বাংলা ব্যাকরণ': 'BLG',
    'ইংরেজি ফর টুডে': 'EFT',
    'ইংরেজি ব্যাকরণ ও রচনা': 'EGC',
    'গণিত': 'MAT',
    'তথ্য ও যোগাযোগ প্রযুক্তি': 'ICT',
    'Science': 'SCI',
    'পদার্থScience': 'PHY',
    'রসায়ন': 'CHM',
    'জীবScience': 'BIO',
    'উচ্চতর গণিত': 'HMT',
    'ভূগোল ও পরিবেশ': 'GEO',
    'অর্থনীতি': 'ECO',
    'কৃষি শিক্ষা': 'AGR',
    'Homo  Science': 'HOS',
    'পৌরনীতি ও নাগরিকতা': 'CIV',
    'হিসাবScience': 'ACC',
    'ফিন্যান্স ও ব্যাংকিং': 'FIB',
    'ব্যবসায় উদ্যোগ': 'BUE',
    'Islamic Studies': 'ISL',
    'হিন্দুধর্ম শিক্ষা': 'HIN',
    'বৌদ্ধধর্ম শিক্ষা': 'BUD',
    'খ্রিষ্টধর্ম শিক্ষা': 'CHR',
    'ক্যারিয়ার শিক্ষা': 'CAE',
    'বাংলাদেশ ও বিশ্বপরিচয়': 'BGS',
    'চারু ও কারুকলা': 'ARC',
    'বাংলাদেশ ও বিশ্বসভ্যতার ইতিহাস': 'HWC',
    'শারীরিক শিক্ষা, স্বাস্থ্যScience ও খেলাধুলা': 'PEH',
    'আরবি': 'ARB',
    'সংস্কৃত': 'SAN',
    'সংষ্কৃত': 'SAN',
    'পালি': 'PAL',
    'Music': 'MUS',
    'বাংলা': 'PBS',
    'ইংরেজি': 'PES',
}

# Bengali numeral digits -> ASCII
BN_DIGITS = '০১২৩৪৫৬৭৮৯'
ASCII_DIGITS = '0123456789'
BN_TO_ASCII = str.maketrans(BN_DIGITS, ASCII_DIGITS)


def normalize_bn_digits(s):
    if not s:
        return ''
    return s.strip().translate(BN_TO_ASCII)


def parse_groups(s):
    if not s or not s.strip():
        return []
    return [w.strip() for w in s.split(',') if w.strip()]


# Format: lang, level, country, subject_code, subject_name, groups (tab-separated)
RAW_ROWS_BN = """
bn	এইসএসসি	BD	১০১	বাংলা ১ম পত্র	Science, Humanities, Business Studies, Islamic Studies, Home Science, Music
bn	এইসএসসি	BD	১০২	বাংলা ২য় পত্র	Science, Humanities, Business Studies, Islamic Studies, Home Science, Music
bn	এইসএসসি	BD	১০৭	ইংরেজি ১ম পত্র	Science, Humanities, Business Studies, Islamic Studies, Home Science, Music
bn	এইসএসসি	BD	১০৮	ইংরেজি ২য় পত্র	Science, Humanities, Business Studies, Islamic Studies, Home Science, Music
bn	এইসএসসি	BD	২৭৫	তথ্য ও যোগাযোগ প্রযুক্তি	Science, Humanities, Business Studies, Islamic Studies, Home Science, Music
bn	এইসএসসি	BD	১৭৪	পদার্থScience ১ম পত্র	Science
bn	এইসএসসি	BD	১৭৫	পদার্থScience ২য় পত্র	Science
bn	এইসএসসি	BD	১৭৬	রসায়ন ১ম পত্র	Science
bn	এইসএসসি	BD	১৭৭	রসায়ন ২য় পত্র	Science
bn	এইসএসসি	BD	১৭৮	জীবScience ১ম পত্র	Science
bn	এইসএসসি	BD	১৭৯	জীবScience ২য় পত্র	Science
bn	এইসএসসি	BD	২৬৫	উচ্চতর গণিত ১ম পত্র	Science
bn	এইসএসসি	BD	২৬৬	উচ্চতর গণিত ২য় পত্র	Science
bn	এইসএসসি	BD	১৮০	প্রকৌশল অঙ্কন ও ওয়ার্কশপ প্র্যাকটিস ১ম পত্র	Science
bn	এইসএসসি	BD	১৮২	প্রকৌশল অঙ্কন ও ওয়ার্কশপ প্র্যাকটিস ২য় পত্র	Science
bn	এইসএসসি	BD	১৮৩	প্রকৌশল অঙ্কন ও ওয়ার্কশপ প্র্যাকটিস ২য় পত্র	Science
bn	এইসএসসি	BD	২২২	প্রকৌশল অঙ্কন ও ওয়ার্কশপ প্র্যাকটিস ২য় পত্র	Science
bn	এইসএসসি	BD	২৮৮	মৃত্তিকাScience ১ম পত্র	Science
bn	এইসএসসি	BD	২৮৯	মৃত্তিকাScience ২য় পত্র	Science
bn	এইসএসসি	BD	২৩৯	কৃষিশিক্ষা ১ম পত্র	Science, Humanities, Business Studies, Islamic Studies
bn	এইসএসসি	BD	২৪০	কৃষিশিক্ষা ২য় পত্র	Science, Humanities, Business Studies, Islamic Studies
bn	এইসএসসি	BD	১২৫	ভূগোল ১ম পত্র	Science, Humanities, Business Studies, Islamic Studies, Home Science
bn	এইসএসসি	BD	১২৬	ভূগোল ২য় পত্র	Science, Humanities, Business Studies, Islamic Studies, Home Science
bn	এইসএসসি	BD	১২৩	মনোScience ১ম পত্র	Science, Humanities, Islamic Studies, Home Science, Music
bn	এইসএসসি	BD	১২৪	মনোScience ২য় পত্র	Science, Humanities, Islamic Studies, Home Science, Music
bn	এইসএসসি	BD	১২৯	পরিসংখ্যান ১ম পত্র	Science, Humanities, Business Studies
bn	এইসএসসি	BD	১৩০	পরিসংখ্যান ২য় পত্র	Science, Humanities, Business Studies
bn	এইসএসসি	BD	৩০৪	ইতিহাস ১ম পত্র	Humanities, Music
bn	এইসএসসি	BD	৩০৫	ইতিহাস ২য় পত্র	Humanities, Music
bn	এইসএসসি	BD	২৬৭	ইসলামের ইতিহাস ও সংস্কৃতি ১ম পত্র	Humanities, Islamic Studies
bn	এইসএসসি	BD	২৬৮	ইসলামের ইতিহাস ও সংস্কৃতি ২য় পত্র	Humanities, Islamic Studies
bn	এইসএসসি	BD	২৬৯	পৌরনীতি ও সুশাসন ১ম পত্র	Humanities, Music
bn	এইসএসসি	BD	২৭০	পৌরনীতি ও সুশাসন ২য় পত্র	Humanities, Music
bn	এইসএসসি	BD	১০৯	অর্থনীতি ১ম পত্র	Humanities, Business Studies, Islamic Studies, Home Science, Music
bn	এইসএসসি	BD	১১০	অর্থনীতি ২য় পত্র	Humanities, Business Studies, Islamic Studies, Home Science, Music
bn	এইসএসসি	BD	১১৭	সমাজScience ১ম পত্র	Humanities, Islamic Studies, Home Science, Music
bn	এইসএসসি	BD	১১৮	সমাজScience ২য় পত্র	Humanities, Islamic Studies, Home Science, Music
bn	এইসএসসি	BD	২৭১	সমাজকর্ম ১ম পত্র	Humanities, Islamic Studies, Home Science, Music
bn	এইসএসসি	BD	২৭২	সমাজকর্ম ২য় পত্র	Humanities, Islamic Studies, Home Science, Music
bn	এইসএসসি	BD	১২১	যুক্তিবিদ্যা ১ম পত্র	Humanities, Islamic Studies, Music
bn	এইসএসসি	BD	১২২	যুক্তিবিদ্যা ২য় পত্র	Humanities, Islamic Studies, Music
bn	এইসএসসি	BD	২৪৯	Islamic Studies ১ম পত্র	Humanities, Islamic Studies
bn	এইসএসসি	BD	২৫০	Islamic Studies ২য় পত্র	Humanities, Islamic Studies
bn	এইসএসসি	BD	২৭৩	Homo  Science ১ম পত্র	Humanities, Business Studies, Islamic Studies, Music
bn	এইসএসসি	BD	২৭৪	Homo  Science ২য় পত্র.	Humanities, Business Studies, Islamic Studies, Music
bn	এইসএসসি	BD	২২৫	চারু ও কারুকলা ১ম পত্র	Humanities
bn	এইসএসসি	BD	২২৬	চারু ও কারুকলা ২য় পত্র	Humanities
bn	এইসএসসি	BD	২২৭	নাট্যকলা ১ম পত্র	Humanities
bn	এইসএসসি	BD	২২৮	নাট্যকলা ২য় পত্র	Humanities
bn	এইসএসসি	BD	১৩৩	আরবি ১ম পত্র	Humanities, Islamic Studies
bn	এইসএসসি	BD	১৩৪	আরবি ২য় পত্র	Humanities, Islamic Studies
bn	এইসএসসি	BD	১৩৯	পালি ১ম পত্র	Humanities
bn	এইসএসসি	BD	১৪০	পালি ২য় পত্র	Humanities
bn	এইসএসসি	BD	১৩৭	সংষ্কৃত ১ম পত্র	Humanities
bn	এইসএসসি	BD	১৩৮	সংষ্কৃত ২য় পত্র	Humanities
bn	এইসএসসি	BD	২৭৭	ব্যবসায় সংগঠন ও ব্যবস্থাপনা ১ম পত্র	Business Studies
bn	এইসএসসি	BD	২৭৮	ব্যবসায় সংগঠন ও ব্যবস্থাপনা ২য় পত্র	Business Studies
bn	এইসএসসি	BD	২৫৩	হিসাবScience ১ম পত্র	Business Studies
bn	এইসএসসি	BD	২৫৪	হিসাবScience ২য় পত্র	Business Studies
bn	এইসএসসি	BD	২৯২	ফিন্যান্স, ব্যাংকিং ও বিমা ১ম পত্র	Business Studies
bn	এইসএসসি	BD	২৯৩	ফিন্যান্স, ব্যাংকিং ও বিমা ২য় পত্র	Business Studies
bn	এইসএসসি	BD	২৮৬	উৎপাদন ব্যবস্থাপনা ও বিপণন ১ম পত্র	Business Studies
bn	এইসএসসি	BD	২৮৭	উৎপাদন ব্যবস্থাপনা ও বিপণন ২য় পত্র	Business Studies
bn	এইসএসসি	BD	২৯৮	শিশুর বিকাশ ১ম পত্র	Home Science
bn	এইসএসসি	BD	২৯৯	শিশুর বিকাশ ২য় পত্র	Home Science
bn	এইসএসসি	BD	২৭৯	খাদ্য ও পুষ্টি ১ম পত্র	Home Science
bn	এইসএসসি	BD	২৮০	খাদ্য ও পুষ্টি ২য় পত্র	Home Science
bn	এইসএসসি	BD	২৮২	গৃহ ব্যবস্থাপনা ও পারিবারিক জীবন ১ম পত্র	Home Science
bn	এইসএসসি	BD	২৮৩	গৃহ ব্যবস্থাপনা ও পারিবারিক জীবন ২য় পত্র	Home Science
bn	এইসএসসি	BD	২৮৪	শিল্পকলা ও বস্ত্র পরিচ্ছদ ১ম পত্র	Home Science
bn	এইসএসসি	BD	২৮৫	শিল্পকলা ও বস্ত্র পরিচ্ছদ ২য় পত্র	Home Science
bn	এইসএসসি	BD	২১৬	লঘু Music ১ম পত্র	Music
bn	এইসএসসি	BD	২১৭	লঘু Music ২য় পত্র	Music
bn	এইসএসসি	BD	২১৮	উচ্চাঙ্গ Music ১ম পত্র	Music
bn	এইসএসসি	BD	২১৯	উচ্চাঙ্গ Music ২য় পত্র	Music
bn	এসএসসি,জেএসসি	BD		বাংলা সাহিত্য	
bn	এসএসসি,জেএসসি	BD		বাংলা ব্যাকরণ	
bn	এসএসসি,জেএসসি	BD		ইংরেজি ফর টুডে	
bn	এসএসসি,জেএসসি	BD		ইংরেজি ব্যাকরণ ও রচনা	
bn	SSC,JSC,PSC	BD		গণিত	
bn	SSC,JSC,PSC	BD		তথ্য ও যোগাযোগ প্রযুক্তি	
bn	SSC,JSC,PSC	BD		Science	
bn	এসএসসি,জেএসসি	BD		পদার্থScience	
bn	এসএসসি,জেএসসি	BD		রসায়ন	
bn	এসএসসি,জেএসসি	BD		জীবScience	
bn	এসএসসি,জেএসসি	BD		উচ্চতর গণিত	
bn	এসএসসি,জেএসসি	BD		ভূগোল ও পরিবেশ	
bn	এসএসসি,জেএসসি	BD		অর্থনীতি	
bn	এসএসসি,জেএসসি	BD		কৃষি শিক্ষা	
bn	এসএসসি,জেএসসি	BD		Homo  Science	
bn	এসএসসি,জেএসসি	BD		পৌরনীতি ও নাগরিকতা	
bn	এসএসসি,জেএসসি	BD		হিসাবScience	
bn	এসএসসি,জেএসসি	BD		ফিন্যান্স ও ব্যাংকিং	
bn	এসএসসি,জেএসসি	BD		ব্যবসায় উদ্যোগ	
bn	এসএসসি,জেএসসি,পিএসসি	BD		Islamic Studies	
bn	এসএসসি,জেএসসি,পিএসসি	BD		হিন্দুধর্ম শিক্ষা	
bn	এসএসসি,জেএসসি,পিএসসি	BD		বৌদ্ধধর্ম শিক্ষা	
bn	এসএসসি,জেএসসি,পিএসসি	BD		খ্রিষ্টধর্ম শিক্ষা	
bn	এসএসসি,জেএসসি	BD		ক্যারিয়ার শিক্ষা	
bn	এসএসসি,জেএসসি	BD		বাংলাদেশ ও বিশ্বপরিচয়	
bn	এসএসসি,জেএসসি,পিএসসি	BD		চারু ও কারুকলা	
bn	এসএসসি,জেএসসি	BD		বাংলাদেশ ও বিশ্বসভ্যতার ইতিহাস	
bn	এসএসসি,জেএসসি,পিএসসি	BD		শারীরিক শিক্ষা, স্বাস্থ্যScience ও খেলাধুলা	
bn	এসএসসি,জেএসসি,পিএসসি	BD		আরবি	
bn	এসএসসি,জেএসসি,পিএসসি	BD		সংস্কৃত	
bn	এসএসসি,জেএসসি,পিএসসি	BD		পালি	
bn	এসএসসি,জেএসসি,পিএসসি	BD		Music	
bn	পিএসসি	BD		বাংলা	
bn	পিএসসি	BD		ইংরেজি	
""".strip()


class Command(BaseCommand):
    help = 'Insert Bengali translations into cheradip_subject_translated; subject_id from code or BN name'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='No DB writes')
        parser.add_argument('--lang', default='bn', help='Language code (default: bn)')

    def resolve_subject_id(self, country, code_raw, subject_name_bn, level_bn):
        """Resolve subject_id for a translated row. country is e.g. 'BD'."""
        code_norm = normalize_bn_digits(code_raw).strip() if code_raw else ''
        if code_norm and re.match(r'^\d+$', code_norm):
            # HSC-style: id = BD101, BD102, ...
            return (country or '') + code_norm
        # SSC/JSC/PSC: no code -> use Bengali name -> local_code -> BD_localcode
        name = (subject_name_bn or '').strip()
        local = BN_NAME_TO_CODE.get(name)
        if local:
            return f"{country}_{local}"
        return None

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        lang = options.get('lang', 'bn')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN – no changes saved'))

        with connection.cursor() as cur:
            cur.execute("SELECT 1 FROM cheradip_country WHERE country_code = %s", ['BD'])
            if not cur.fetchone():
                self.stdout.write(self.style.ERROR('Country BD not found.'))
                return
            cur.execute("""
                SELECT COLUMN_NAME FROM information_schema.COLUMNS
                WHERE table_schema = DATABASE() AND table_name = 'cheradip_subject_translated'
            """)
            cols = {r[0] for r in cur.fetchall()}
        if not cols:
            self.stdout.write(self.style.ERROR('Table cheradip_subject_translated not found.'))
            return

        # subject_name_bn dropped; include created_at/updated_at if present (MySQL needs explicit values)
        want = ['subject_id', 'language_code', 'level', 'country_id', 'subject_name', 'groups', 'created_at', 'updated_at']
        use_cols = [c for c in want if c in cols]
        created = 0
        updated = 0
        skipped = 0

        for line in RAW_ROWS_BN.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            # Format: lang, level, country, subject_code, subject_name, groups
            if len(parts) < 5:
                continue
            row_lang = (parts[0].strip() if len(parts) > 0 else '') or lang
            level_raw = (parts[1].strip() if len(parts) > 1 else '') or ''
            country = (parts[2].strip() if len(parts) > 2 else '')
            code_raw = (parts[3].strip() if len(parts) > 3 else '')
            subject_name = (parts[4].strip() if len(parts) > 4 else '')
            groups_str = (parts[5].strip() if len(parts) > 5 else '') or ''

            if not subject_name or not country:
                continue

            # level_en only for subject_id resolution; stored level = level_raw (as you gave)
            level_en = LEVEL_BN_TO_EN.get(level_raw) or level_raw
            subject_id = self.resolve_subject_id(country, code_raw, subject_name, level_raw)
            if subject_id:
                subject_id = str(subject_id)[:12]  # match Subject.id max_length
            if not subject_id:
                skipped += 1
                if dry_run:
                    self.stdout.write(self.style.WARNING(f"  skip (no subject_id): {subject_name[:40]}"))
                continue

            # Ensure subject exists
            with connection.cursor() as cur:
                cur.execute("SELECT 1 FROM cheradip_subject WHERE id = %s", [subject_id])
                if not cur.fetchone():
                    skipped += 1
                    if dry_run:
                        self.stdout.write(self.style.WARNING(f"  skip (subject missing): {subject_id} {subject_name[:30]}"))
                    continue

            subject_name = (subject_name or '')[:50]
            groups = parse_groups(groups_str)
            use_lang = (row_lang or lang)[:10]

            if dry_run:
                self.stdout.write(f"  {subject_id} | {level_raw or level_en} | {subject_name[:35]} | lang={use_lang}")
                created += 1
                continue

            now = timezone.now()
            subject_id_val = (subject_id or '')[:12]  # fit DB column (matches Subject.id)
            # Store level and groups exactly as in your data (Bengali levels, your group names)
            level_to_store = (level_raw or level_en or '')[:20]
            val_map = {
                'subject_id': subject_id_val,
                'language_code': use_lang,
                'level': level_to_store,
                'country_id': country,
                'subject_name': subject_name,
                'groups': json.dumps(groups) if groups else json.dumps([]),
                'created_at': now,
                'updated_at': now,
            }
            values = [val_map[c] for c in use_cols]
            ph = ', '.join(['%s'] * len(use_cols))
            col_list = ', '.join(f'`{c}`' for c in use_cols)
            # On duplicate, update everything except subject_id, language_code, and created_at
            skip_on_update = {'subject_id', 'language_code', 'created_at'}
            ups = ', '.join(f'`{c}`=VALUES(`{c}`)' for c in use_cols if c not in skip_on_update)

            with connection.cursor() as cur:
                cur.execute(
                    f"INSERT INTO cheradip_subject_translated ({col_list}) VALUES ({ph}) "
                    f"ON DUPLICATE KEY UPDATE {ups}",
                    values,
                )
                rc = cur.rowcount
            if rc == 1:
                created += 1
            elif rc == 2:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f'Done. Created {created}, updated {updated}, skipped {skipped}.'))
