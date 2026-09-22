"""
Report unwanted special characters in a subject question table — read-only.

    python manage.py scan_question_junk cheradip_hsc_..._physics --db hsc --limit 500

Shows the code points that cannot belong to a Bangla/English question (control / zero-width /
invisible characters, U+FFFD, private-use or unassigned code points, emoji, letters pasted
from another script, stranded or doubled Bangla signs, unbalanced math delimiters). Math,
HTML markup, Bangla/English text, the normal punctuation of a sentence and the usual symbols
are whitelisted — see ``cheradip.text_hygiene``.

Nothing is written and no AI is called: the admin "Update" button (Home AI) queues the removed
characters as a pending request that a reviewer approves, and "AI Update" (Cloud AI) queues the
corrected words/sentences the same way.
"""
from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from cheradip import text_hygiene
from cheradip.question_updater import _HYGIENE_FIELDS

_SEVERITY_RANK = {'low': 0, 'medium': 1, 'high': 2}


def _context(text, index, width=32):
    """``…text[<char>]text…`` window around a finding offset."""
    text = str(text or '')
    start = max(0, index - width)
    end = min(len(text), index + width)
    return (text[start:index] + '[' + text[index] + ']' + text[index + 1:end]).replace('\n', '\\n')


class Command(BaseCommand):
    help = ('Scan a subject question table for unwanted special characters (control, zero-width, '
            'emoji, foreign-script look-alikes, doubled/stranded Bangla signs, unbalanced math $). '
            'Read-only: nothing is changed and no AI call is made.')

    def add_arguments(self, parser):
        parser.add_argument('table', help='subject question table, e.g. cheradip_hsc_..._physics')
        parser.add_argument('--db', default='default', help='database alias (default: default)')
        parser.add_argument('--limit', type=int, default=500, help='rows to scan (default: 500)')
        parser.add_argument('--samples', type=int, default=5, help='sample findings to print')
        parser.add_argument('--min-severity', choices=('low', 'medium', 'high'), default='low',
                            help='hide findings below this severity (default: low)')

    def handle(self, *args, **options):
        alias = options['db']
        if alias not in connections:
            raise CommandError('Unknown database alias: %s' % alias)
        table = (options['table'] or '').strip().lower().replace('`', '')
        if not table:
            raise CommandError('No table given.')
        limit = max(1, int(options['limit']))
        min_rank = _SEVERITY_RANK[options['min_severity']]
        conn = connections[alias]

        with conn.cursor() as cur:
            cur.execute(
                "SELECT GROUP_CONCAT(COLUMN_NAME) FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = %s", [table])
            columns = set(((cur.fetchone() or [None])[0] or '').split(','))
            if not columns:
                raise CommandError('Table not found on %s: %s' % (alias, table))
            if 'question' not in columns:
                raise CommandError("'%s' is not a question table (it has no question column)."
                                   % table)
            fields = [f for f in _HYGIENE_FIELDS if f in columns]
            qid = '`qid`' if 'qid' in columns else 'NULL'
            select = ', '.join([qid + ' AS qid'] + ['`%s`' % f for f in fields])
            cur.execute('SELECT %s FROM `%s` LIMIT %d'
                        % (select, table.replace('`', '``'), limit))
            names = [d[0] for d in cur.description]
            rows = [dict(zip(names, r)) for r in cur.fetchall()]

        kinds = Counter()
        severities = Counter()
        fields_hit = Counter()
        dirty = 0
        strippable = 0
        samples = []
        for row in rows:
            found = text_hygiene.scan_row(row, fields)
            if not found:
                continue
            dirty += 1
            if any(text_hygiene.strip_junk(str(row.get(f) or ''))[1] for f in fields):
                strippable += 1
            for field, items in found.items():
                fields_hit[field] += 1
                for item in items:
                    kinds[item.kind] += 1
                    severities[item.severity] += 1
                    if len(samples) < int(options['samples']) \
                            and _SEVERITY_RANK[item.severity] >= min_rank:
                        samples.append((row.get('qid'), field, item, row.get(field)))

        self.stdout.write('Scanned %d row(s) of `%s` on `%s` (fields: %s)'
                          % (len(rows), table, alias, ', '.join(fields)))
        if not dirty:
            self.stdout.write(self.style.SUCCESS('No unwanted special characters found.'))
            return
        self.stdout.write(self.style.WARNING(
            '%d row(s) contain findings in %d field(s); %d row(s) hold code points that can be '
            'removed automatically.' % (dirty, sum(fields_hit.values()), strippable)))
        for kind, count in kinds.most_common():
            example = next((it for _q, _f, it, _t in samples if it.kind == kind), None)
            self.stdout.write('   %-18s %3d%s' % (kind, count,
                                                  '' if example is None else
                                                  '  e.g. %s %r' % (example.code_label,
                                                                    example.char)))
        self.stdout.write('   severity: %s' % ', '.join('%s=%d' % kv
                                                       for kv in sorted(severities.items())))
        self.stdout.write('   fields:   %s' % ', '.join('%s=%d' % kv
                                                       for kv in fields_hit.most_common()))
        if samples:
            self.stdout.write('Samples:')
            for row_qid, field, item, value in samples:
                self.stdout.write('   qid %-14s %-12s %-17s %-9s %s'
                                  % (row_qid, field, item.kind, item.code_label, item.message))
                self.stdout.write('        %s' % _context(value, item.index))
        self.stdout.write('Approve or deny the fixes in the admin: the "Update" button queues the '
                          'removed characters (Home AI) and "AI Update" the corrected words '
                          '(Cloud AI) as pending requests — this scan changes nothing.')
