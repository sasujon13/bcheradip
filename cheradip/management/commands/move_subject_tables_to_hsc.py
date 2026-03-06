"""
Move cheradip_subject and all subject-based tables from default DB (cheradip_cheradip)
to the hsc DB (cheradip_hsc), then remove them from default.

Tables moved:
- cheradip_subject
- cheradip_chapters (subject_code; new ids in hsc)
- cheradip_topics (chapter FK; remap to new chapter ids)
- cheradip_mcq_ict (chapter, topic FKs; remap to new ids)
- All subject question tables (cheradip_* matching pattern, e.g. cheradip_ssc_9_10_physics)

Prerequisites:
- Database cheradip_hsc must already exist.
- Django DATABASES has key 'hsc' pointing to it.

Run:
  python manage.py move_subject_tables_to_hsc
  python manage.py move_subject_tables_to_hsc --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import connections

# Known tables that are NOT subject question tables (from migrations)
NON_QUESTION_TABLES = {
    'cheradip_subject', 'cheradip_groups', 'cheradip_class_levels', 'cheradip_class_group_mappings',
    'cheradip_departments', 'cheradip_chapters', 'cheradip_topics', 'cheradip_country', 'cheradip_location',
    'cheradip_items', 'cheradip_transactions', 'cheradip_orderdetail', 'cheradip_order', 'cheradip_ordered',
    'cheradip_canceled', 'cheradip_customers', 'cheradip_customer_tokens', 'cheradip_notification',
    'cheradip_institute', 'cheradip_institutes', 'cheradip_years', 'cheradip_mcq_institutes', 'cheradip_mcq_years',
    'cheradip_mcq_ict', 'cheradip_tokens', 'cheradip_json_data', 'cheradip_order_orderdetails', 'cheradip_order_transaction',
    'cheradip_ordered_orderdetails', 'cheradip_ordered_transaction', 'cheradip_canceled_orderdetails',
    'cheradip_canceled_transaction', 'cheradip_pending_subject_request',
}


def _get_create_table_sql(conn, table_name):
    """Return CREATE TABLE statement for table (without DB name prefix)."""
    with conn.cursor() as cur:
        cur.execute("SHOW CREATE TABLE `%s`" % table_name.replace('`', '``'))
        row = cur.fetchone()
    if not row:
        return None
    create_sql = row[1]
    # Remove backticked database name if present so it works on hsc
    import re
    create_sql = re.sub(r'CREATE TABLE `[^`]+`\.`', 'CREATE TABLE `', create_sql)
    return create_sql


def _copy_subject(default_conn, hsc_conn, dry_run):
    """Copy cheradip_subject (without id so hsc gets own ids)."""
    with default_conn.cursor() as cur:
        cur.execute("SELECT level, level_tr, groups, class_level, subject_name, subject_translated, subject_code, country_id, language_code, created_at, updated_at FROM cheradip_subject ORDER BY id")
        rows = cur.fetchall()
    if dry_run:
        return len(rows)
    with hsc_conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO cheradip_subject (level, level_tr, groups, class_level, subject_name, subject_translated, subject_code, country_id, language_code, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, rows)
    return len(rows)


def _copy_chapters(default_conn, hsc_conn, dry_run):
    """Copy cheradip_chapters; return dict old_id -> new_id."""
    with default_conn.cursor() as cur:
        cur.execute("SELECT id, subject_code, chapter_no, chapter_name, chapter_name_bn, created_at, updated_at FROM cheradip_chapters ORDER BY id")
        rows = cur.fetchall()
    if dry_run:
        return {}, len(rows)
    id_map = {}
    with hsc_conn.cursor() as cur:
        for r in rows:
            old_id, subject_code, chapter_no, chapter_name, chapter_name_bn, created_at, updated_at = r
            cur.execute("""
                INSERT INTO cheradip_chapters (subject_code, chapter_no, chapter_name, chapter_name_bn, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (subject_code, chapter_no, chapter_name, chapter_name_bn, created_at, updated_at))
            id_map[old_id] = cur.lastrowid
    return id_map, len(rows)


def _copy_topics(default_conn, hsc_conn, chapter_id_map, dry_run):
    """Copy cheradip_topics with chapter_id remap; return dict old_id -> new_id."""
    with default_conn.cursor() as cur:
        cur.execute("SELECT id, chapter_id, topic_no, topic_name, topic_name_bn, created_at, updated_at FROM cheradip_topics ORDER BY id")
        rows = cur.fetchall()
    if dry_run:
        return {}, len(rows)
    id_map = {}
    with hsc_conn.cursor() as cur:
        for r in rows:
            old_id, chapter_id, topic_no, topic_name, topic_name_bn, created_at, updated_at = r
            new_chapter_id = chapter_id_map.get(chapter_id)
            if new_chapter_id is None:
                continue
            cur.execute("""
                INSERT INTO cheradip_topics (chapter_id, topic_no, topic_name, topic_name_bn, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (new_chapter_id, topic_no, topic_name, topic_name_bn, created_at, updated_at))
            id_map[old_id] = cur.lastrowid
    return id_map, len(rows)


def _copy_mcq_ict(default_conn, hsc_conn, chapter_id_map, topic_id_map, dry_run):
    """Copy cheradip_mcq_ict with chapter_id and topic_id remap. M2M (institute/year) not copied."""
    with default_conn.cursor() as cur:
        cur.execute("""
            SELECT qid, subject_code, chapter_id, topic_id, uddipok, question, option1, option2, option3, option4, answer, explanation,
                   img_uddipok, img_question, img_explanation, difficulty_level, is_active, created_at, updated_at
            FROM cheradip_mcq_ict ORDER BY qid
        """)
        rows = cur.fetchall()
    if dry_run:
        return len(rows)
    count = 0
    with hsc_conn.cursor() as cur:
        for r in rows:
            qid, subject_code, chapter_id, topic_id = r[0], r[1], r[2], r[3]
            new_chapter_id = chapter_id_map.get(chapter_id)
            new_topic_id = topic_id_map.get(topic_id)
            if new_chapter_id is None or new_topic_id is None:
                continue
            cur.execute("""
                INSERT INTO cheradip_mcq_ict (qid, subject_code, chapter_id, topic_id, uddipok, question, option1, option2, option3, option4, answer, explanation,
                    img_uddipok, img_question, img_explanation, difficulty_level, is_active, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (r[0], r[1], new_chapter_id, new_topic_id) + r[4:])
            count += 1
    return count


def _list_subject_question_tables(conn, db_name):
    """Return list of subject question table names in the given schema."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s AND table_name LIKE 'cheradip_%%'",
            [db_name]
        )
        names = [row[0] for row in cur.fetchall() if row[0] not in NON_QUESTION_TABLES]
    return names


def _copy_subject_question_table(default_conn, hsc_conn, default_db, hsc_db, table_name, dry_run):
    """Create table in hsc (from default's DDL) and copy all rows."""
    create_sql = _get_create_table_sql(default_conn, table_name)
    if not create_sql:
        return 0
    # Replace default DB name with hsc DB name in CREATE so table is created in hsc
    if default_db and hsc_db:
        create_sql = create_sql.replace('`' + default_db + '`.', '')
    if dry_run:
        with default_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM `%s`" % table_name.replace('`', '``'))
            return cur.fetchone()[0]
    with hsc_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS `%s`" % table_name.replace('`', '``'))
        cur.execute(create_sql)
    with default_conn.cursor() as cur:
        cur.execute("SELECT * FROM `%s`" % table_name.replace('`', '``'))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    if not rows:
        return 0
    col_list = ', '.join('`%s`' % c.replace('`', '``') for c in cols)
    placeholders = ', '.join(['%s'] * len(cols))
    with hsc_conn.cursor() as cur:
        cur.executemany("INSERT INTO `%s` (%s) VALUES (%s)" % (table_name.replace('`', '``'), col_list, placeholders), rows)
    return len(rows)


def _drop_subject_question_table(conn, table_name):
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS `%s`" % table_name.replace('`', '``'))


class Command(BaseCommand):
    help = 'Move cheradip_subject and all subject-based tables from default DB to cheradip_hsc, then remove from default'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only show what would be done.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN – no changes will be made.'))

        default_conn = connections['default']
        hsc_conn = connections['hsc']
        default_db = connections['default'].settings_dict['NAME']
        hsc_db = connections['hsc'].settings_dict['NAME']

        # 1) Create tables in hsc from default DDL
        for table in ['cheradip_subject', 'cheradip_chapters', 'cheradip_topics', 'cheradip_mcq_ict']:
            create_sql = _get_create_table_sql(default_conn, table)
            if not create_sql:
                self.stdout.write(self.style.ERROR('Table %s not found in default.' % table))
                return
            create_sql = create_sql.replace('`' + default_db + '`.', '') if default_db else create_sql
            if not dry_run:
                with hsc_conn.cursor() as cur:
                    cur.execute("DROP TABLE IF EXISTS `%s`" % table)
                    cur.execute(create_sql)
            self.stdout.write('Created (or replaced) %s in hsc.' % table)

        # 2) Copy data
        n = _copy_subject(default_conn, hsc_conn, dry_run)
        self.stdout.write('Copied %d rows to hsc.cheradip_subject.' % n)

        chapter_id_map, nch = _copy_chapters(default_conn, hsc_conn, dry_run)
        self.stdout.write('Copied %d rows to hsc.cheradip_chapters.' % nch)

        topic_id_map, nt = _copy_topics(default_conn, hsc_conn, chapter_id_map, dry_run)
        self.stdout.write('Copied %d rows to hsc.cheradip_topics.' % nt)

        nmcq = _copy_mcq_ict(default_conn, hsc_conn, chapter_id_map, topic_id_map, dry_run)
        self.stdout.write('Copied %d rows to hsc.cheradip_mcq_ict.' % nmcq)

        # 3) Subject question tables (discover from default DB)
        question_tables = _list_subject_question_tables(default_conn, default_db)
        self.stdout.write('Found %d subject question table(s) in default.' % len(question_tables))
        for tname in question_tables:
            nq = _copy_subject_question_table(default_conn, hsc_conn, default_db, hsc_db, tname, dry_run)
            self.stdout.write('  %s: %d rows' % (tname, nq))

        if dry_run:
            self.stdout.write('Dry run complete. Run without --dry-run to apply and then remove from default.')
            return

        # 4) Remove from default: mcq_ict, topics, chapters, subject; drop subject question tables
        with default_conn.cursor() as cur:
            cur.execute("DELETE FROM cheradip_mcq_ict")
            self.stdout.write('Deleted cheradip_mcq_ict from default.')
            cur.execute("DELETE FROM cheradip_topics")
            self.stdout.write('Deleted cheradip_topics from default.')
            cur.execute("DELETE FROM cheradip_chapters")
            self.stdout.write('Deleted cheradip_chapters from default.')
            cur.execute("DELETE FROM cheradip_subject")
            self.stdout.write('Deleted cheradip_subject from default.')
        for tname in question_tables:
            _drop_subject_question_table(default_conn, tname)
            self.stdout.write('Dropped %s from default.' % tname)

        self.stdout.write(self.style.SUCCESS('Move to cheradip_hsc complete.'))
