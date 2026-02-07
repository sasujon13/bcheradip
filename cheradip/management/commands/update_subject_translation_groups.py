# -*- coding: utf-8 -*-
"""
Update groups in cheradip_subject_translated for Bengali (language_code='bn').
Format: groups (Bengali, comma-separated) TAB subject_id, one per line.
Stores groups as JSON array of trimmed strings.

Run: python manage.py update_subject_translation_groups
     python manage.py update_subject_translation_groups --dry-run
"""
import json
from django.core.management.base import BaseCommand
from django.db import connection

# groups (Bengali, comma-separated) TAB subject_id
RAW_ROWS = """
বিজ্ঞান, মানবিক, ব্যবসায় শিক্ষা, ইসলাম শিক্ষা, গার্হস্থ্যবিজ্ঞান, সঙ্গীত	BD101
বিজ্ঞান, মানবিক, ব্যবসায় শিক্ষা, ইসলাম শিক্ষা, গার্হস্থ্যবিজ্ঞান, সঙ্গীত	BD102
বিজ্ঞান, মানবিক, ব্যবসায় শিক্ষা, ইসলাম শিক্ষা, গার্হস্থ্যবিজ্ঞান, সঙ্গীত	BD107
বিজ্ঞান, মানবিক, ব্যবসায় শিক্ষা, ইসলাম শিক্ষা, গার্হস্থ্যবিজ্ঞান, সঙ্গীত	BD108
বিজ্ঞান, মানবিক, ব্যবসায় শিক্ষা, ইসলাম শিক্ষা, গার্হস্থ্যবিজ্ঞান, সঙ্গীত	BD275
বিজ্ঞান	BD174
বিজ্ঞান	BD175
বিজ্ঞান	BD176
বিজ্ঞান	BD177
বিজ্ঞান	BD178
বিজ্ঞান	BD179
বিজ্ঞান	BD265
বিজ্ঞান	BD266
বিজ্ঞান	BD180
বিজ্ঞান	BD182
বিজ্ঞান	BD183
বিজ্ঞান	BD222
বিজ্ঞান	BD288
বিজ্ঞান	BD289
বিজ্ঞান, মানবিক, ব্যবসায় শিক্ষা, ইসলাম শিক্ষা	BD239
বিজ্ঞান, মানবিক, ব্যবসায় শিক্ষা, ইসলাম শিক্ষা	BD240
বিজ্ঞান, মানবিক, ব্যবসায় শিক্ষা, ইসলাম শিক্ষা, গার্হস্থ্যবিজ্ঞান	BD125
বিজ্ঞান, মানবিক, ব্যবসায় শিক্ষা, ইসলাম শিক্ষা, গার্হস্থ্যবিজ্ঞান	BD126
বিজ্ঞান, মানবিক, ইসলাম শিক্ষা, গার্হস্থ্যবিজ্ঞান, সঙ্গীত	BD123
বিজ্ঞান, মানবিক, ইসলাম শিক্ষা, গার্হস্থ্যবিজ্ঞান, সঙ্গীত	BD124
বিজ্ঞান, মানবিক, ব্যবসায় শিক্ষা	BD129
বিজ্ঞান, মানবিক, ব্যবসায় শিক্ষা	BD130
মানবিক, সঙ্গীত	BD304
মানবিক, সঙ্গীত	BD305
মানবিক, ইসলাম শিক্ষা	BD267
মানবিক, ইসলাম শিক্ষা	BD268
মানবিক, সঙ্গীত	BD269
মানবিক, সঙ্গীত	BD270
মানবিক, ব্যবসায় শিক্ষা, ইসলাম শিক্ষা, গার্হস্থ্যবিজ্ঞান, সঙ্গীত	BD109
মানবিক, ব্যবসায় শিক্ষা, ইসলাম শিক্ষা, গার্হস্থ্যবিজ্ঞান, সঙ্গীত	BD110
মানবিক, ইসলাম শিক্ষা, গার্হস্থ্যবিজ্ঞান, সঙ্গীত	BD117
মানবিক, ইসলাম শিক্ষা, গার্হস্থ্যবিজ্ঞান, সঙ্গীত	BD118
মানবিক, ইসলাম শিক্ষা, গার্হস্থ্যবিজ্ঞান, সঙ্গীত	BD271
মানবিক, ইসলাম শিক্ষা, গার্হস্থ্যবিজ্ঞান, সঙ্গীত	BD272
মানবিক, ইসলাম শিক্ষা, সঙ্গীত	BD121
মানবিক, ইসলাম শিক্ষা, সঙ্গীত	BD122
মানবিক, ইসলাম শিক্ষা	BD249
মানবিক, ইসলাম শিক্ষা	BD250
মানবিক, ব্যবসায় শিক্ষা, ইসলাম শিক্ষা, সঙ্গীত	BD273
মানবিক, ব্যবসায় শিক্ষা, ইসলাম শিক্ষা, সঙ্গীত	BD274
মানবিক	BD225
মানবিক	BD226
মানবিক	BD227
মানবিক	BD228
মানবিক, ইসলাম শিক্ষা	BD133
মানবিক, ইসলাম শিক্ষা	BD134
মানবিক	BD139
মানবিক	BD140
মানবিক	BD137
মানবিক	BD138
ব্যবসায় শিক্ষা	BD277
ব্যবসায় শিক্ষা	BD278
ব্যবসায় শিক্ষা	BD253
ব্যবসায় শিক্ষা	BD254
ব্যবসায় শিক্ষা	BD292
ব্যবসায় শিক্ষা	BD293
ব্যবসায় শিক্ষা	BD286
ব্যবসায় শিক্ষা	BD287
গার্হস্থ্যবিজ্ঞান	BD298
গার্হস্থ্যবিজ্ঞান	BD299
গার্হস্থ্যবিজ্ঞান	BD279
গার্হস্থ্যবিজ্ঞান	BD280
গার্হস্থ্যবিজ্ঞান	BD282
গার্হস্থ্যবিজ্ঞান	BD283
গার্হস্থ্যবিজ্ঞান	BD284
গার্হস্থ্যবিজ্ঞান	BD285
সঙ্গীত	BD216
সঙ্গীত	BD217
সঙ্গীত	BD218
সঙ্গীত	BD219
""".strip()


def parse_groups(s):
    if not s or not s.strip():
        return []
    return [w.strip() for w in s.split(',') if w.strip()]


class Command(BaseCommand):
    help = "Update groups in cheradip_subject_translated for bn by subject_id (Bengali group names)"

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='No DB writes')
        parser.add_argument('--lang', default='bn', help='Language code to update (default: bn)')

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        lang = (options.get('lang') or 'bn')[:10]
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN – no changes saved'))

        updated = 0
        skipped = 0

        for line in RAW_ROWS.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            groups_str = (parts[0] or '').strip()
            subject_id = (parts[1] or '').strip()[:12]
            if not subject_id:
                skipped += 1
                continue

            groups = parse_groups(groups_str)
            groups_json = json.dumps(groups, ensure_ascii=False)

            if dry_run:
                self.stdout.write(f"  {subject_id} | {len(groups)} groups")
                updated += 1
                continue

            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE cheradip_subject_translated SET `groups` = %s WHERE subject_id = %s AND language_code = %s",
                    [groups_json, subject_id, lang],
                )
                if cur.rowcount:
                    updated += 1
                else:
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(f'Done. Updated {updated}, skipped {skipped}.'))
