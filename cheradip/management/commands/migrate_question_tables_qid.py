"""
Add qid and topic_no to existing subject/book question tables and switch primary key to qid.

- Adds columns: topic_no VARCHAR(50) NULL, qid VARCHAR(64) NULL
- Backfills topic_no: 1, 2, 3... per distinct (chapter_no, topic) within each chapter
- Backfills qid: chapter_no_topic_no_0001, 0002, ... (auto sequence per chapter_no + topic_no)
- Drops old primary key (id), adds primary key (qid)
- Keeps id column as non-PK for backward compatibility

Run for HSC:  python manage.py migrate_question_tables_qid --database=hsc
Run for Honours: python manage.py migrate_question_tables_qid --database=honours
Dry run:  python manage.py migrate_question_tables_qid --database=hsc --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import connections
from collections import defaultdict

from cheradip.subject_question_tables import subject_question_table_name
from cheradip.management.commands.ensure_honours import book_question_table_name


def _table_has_column(cursor, table_name, column_name, db_name=None):
    if db_name:
        cursor.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = %s AND table_name = %s AND COLUMN_NAME = %s",
            [db_name, table_name, column_name],
        )
    else:
        cursor.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = %s AND COLUMN_NAME = %s",
            [table_name, column_name],
        )
    return cursor.fetchone() is not None


def _table_has_pk_on(cursor, table_name, column_name, db_name=None):
    if db_name:
        cursor.execute(
            """SELECT 1 FROM information_schema.key_column_usage k
             JOIN information_schema.table_constraints t ON k.constraint_name = t.constraint_name AND k.table_schema = t.table_schema
             WHERE k.table_schema = %s AND k.table_name = %s AND k.column_name = %s AND t.constraint_type = 'PRIMARY KEY'""",
            [db_name, table_name, column_name],
        )
    else:
        cursor.execute(
            """SELECT 1 FROM information_schema.key_column_usage k
             JOIN information_schema.table_constraints t ON k.constraint_name = t.constraint_name AND k.table_schema = t.table_schema
             WHERE k.table_schema = DATABASE() AND k.table_name = %s AND k.column_name = %s AND t.constraint_type = 'PRIMARY KEY'""",
            [table_name, column_name],
        )
    return cursor.fetchone() is not None


def _migrate_table_to_qid(cursor, table_name, db_name, dry_run, verbose):
    """Add topic_no and qid, backfill, then set qid as PK. Table must have id as PK and columns chapter_no, chapter, topic."""
    safe_name = table_name.replace("`", "``")
    has_id = _table_has_column(cursor, table_name, "id", db_name)
    has_qid = _table_has_column(cursor, table_name, "qid", db_name)
    has_topic_no = _table_has_column(cursor, table_name, "topic_no", db_name)
    pk_on_id = _table_has_pk_on(cursor, table_name, "id", db_name) if has_id else False

    pk_on_qid = _table_has_pk_on(cursor, table_name, "qid", db_name) if has_qid else False
    if has_qid and pk_on_qid:
        if verbose:
            print(f"  Skip {table_name}: already uses qid as primary key")
        return False
    if not has_id or not pk_on_id:
        if verbose:
            print(f"  Skip {table_name}: no id PK (unexpected schema)")
        return False
    if dry_run:
        print(f"  Would migrate {table_name}: add topic_no, qid, backfill, set qid as PK")
        return True

    # 1) Add columns if missing
    if not has_topic_no:
        cursor.execute(f"ALTER TABLE `{safe_name}` ADD COLUMN topic_no VARCHAR(50) NULL")
    if not has_qid:
        cursor.execute(f"ALTER TABLE `{safe_name}` ADD COLUMN qid VARCHAR(64) NULL")

    # If both columns already existed, only switch primary key (do not backfill)
    if has_qid and has_topic_no:
        # Remove AUTO_INCREMENT from id first (MySQL: auto column must be a key)
        cursor.execute(f"ALTER TABLE `{safe_name}` MODIFY COLUMN id INT NOT NULL")
        cursor.execute(f"ALTER TABLE `{safe_name}` DROP PRIMARY KEY")
        cursor.execute(f"ALTER TABLE `{safe_name}` ADD PRIMARY KEY (qid)")
        return True

    # 2) Fetch all rows (id, chapter_no, chapter, topic)
    cursor.execute(
        f"SELECT id, COALESCE(chapter_no, ''), COALESCE(chapter, ''), COALESCE(topic, '') FROM `{safe_name}` ORDER BY id"
    )
    rows = cursor.fetchall()

    if not rows:
        cursor.execute(f"ALTER TABLE `{safe_name}` MODIFY COLUMN qid VARCHAR(64) NOT NULL DEFAULT ''")
        cursor.execute(f"ALTER TABLE `{safe_name}` MODIFY COLUMN id INT NOT NULL")
        cursor.execute(f"ALTER TABLE `{safe_name}` DROP PRIMARY KEY")
        cursor.execute(f"ALTER TABLE `{safe_name}` ADD PRIMARY KEY (qid)")
        return True

    # 3) Assign topic_no per (chapter_no, topic): 1, 2, 3... per distinct topic within each chapter_no
    key_to_topic_no = {}
    per_chapter = defaultdict(list)
    for id_, ch_no, ch, topic in rows:
        ch_no = (ch_no or "").strip()
        topic = (topic or "").strip()
        per_chapter[ch_no].append(topic)

    for ch_no in sorted(per_chapter.keys()):
        for seq, topic in enumerate(sorted(set(per_chapter[ch_no])), start=1):
            key_to_topic_no[(ch_no, topic)] = str(seq)

    # 4) Assign qid: (chapter_no, topic_no) -> sequence 0001, 0002, ...
    prefix_to_seq = defaultdict(int)
    row_data = []
    for id_, ch_no, ch, topic in rows:
        ch_no = (ch_no or "").strip()
        topic = (topic or "").strip()
        topic_no = key_to_topic_no.get((ch_no, topic), "1")
        prefix = f"{ch_no or '0'}_{topic_no}_"
        prefix_to_seq[prefix] += 1
        seq = prefix_to_seq[prefix]
        qid = f"{prefix}{seq:04d}"
        row_data.append((id_, topic_no, qid))

    # 5) Update each row
    for id_val, topic_no_val, qid_val in row_data:
        cursor.execute(
            f"UPDATE `{safe_name}` SET topic_no = %s, qid = %s WHERE id = %s",
            [topic_no_val, qid_val, id_val],
        )

    # 6) Make qid NOT NULL; remove AUTO_INCREMENT from id, then drop old PK and add new PK
    cursor.execute(f"ALTER TABLE `{safe_name}` MODIFY COLUMN qid VARCHAR(64) NOT NULL")
    cursor.execute(f"ALTER TABLE `{safe_name}` MODIFY COLUMN id INT NOT NULL")
    cursor.execute(f"ALTER TABLE `{safe_name}` DROP PRIMARY KEY")
    cursor.execute(f"ALTER TABLE `{safe_name}` ADD PRIMARY KEY (qid)")

    return True


def migrate_hsc(cursor, db_name, dry_run, verbose):
    cursor.execute("SELECT level_tr, class_level, subject_tr FROM cheradip_subject ORDER BY id")
    seen = set()
    tables_migrated = 0
    for row in cursor.fetchall():
        level_tr = (row[0] or "").strip()
        class_level = (row[1] or "").strip()
        subject_tr = (row[2] or "").strip()
        key = (class_level, subject_tr)
        if key in seen:
            continue
        seen.add(key)
        table_name = subject_question_table_name(level_tr, class_level, subject_tr)
        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
            [db_name, table_name],
        )
        if not cursor.fetchone():
            continue
        if _migrate_table_to_qid(cursor, table_name, db_name, dry_run, verbose):
            tables_migrated += 1
    return tables_migrated


def migrate_honours(cursor, db_name, dry_run, verbose):
    cursor.execute(
        "SELECT DISTINCT book_tr FROM cheradip_subject WHERE book_tr IS NOT NULL AND TRIM(COALESCE(book_tr, '')) != '' ORDER BY book_tr"
    )
    tables_migrated = 0
    for row in cursor.fetchall():
        book_tr = (row[0] or "").strip()
        table_name = book_question_table_name(book_tr)
        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
            [db_name, table_name],
        )
        if not cursor.fetchone():
            continue
        if _migrate_table_to_qid(cursor, table_name, db_name, dry_run, verbose):
            tables_migrated += 1
    return tables_migrated


class Command(BaseCommand):
    help = "Add qid and topic_no to existing question tables, backfill, and set qid as primary key (HSC and/or Honours)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            type=str,
            default="hsc",
            help="Database to migrate: hsc, honours, or both (default: hsc)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only print what would be done.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        db_arg = (options.get("database") or "hsc").strip().lower()

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN – no changes will be written."))

        total = 0
        if db_arg in ("hsc", "both"):
            if "hsc" not in connections:
                self.stdout.write(self.style.ERROR("Database 'hsc' is not configured."))
            else:
                conn = connections["hsc"]
                db_name = conn.settings_dict.get("NAME", "")
                self.stdout.write(f"Migrating HSC tables in {db_name}...")
                with conn.cursor() as cur:
                    n = migrate_hsc(cur, db_name, dry_run, True)
                    total += n
                self.stdout.write(self.style.SUCCESS(f"  HSC: {n} table(s) migrated."))

        if db_arg in ("honours", "both"):
            if "honours" not in connections:
                self.stdout.write(self.style.ERROR("Database 'honours' is not configured."))
            else:
                conn = connections["honours"]
                db_name = conn.settings_dict.get("NAME", "")
                self.stdout.write(f"Migrating Honours tables in {db_name}...")
                with conn.cursor() as cur:
                    n = migrate_honours(cur, db_name, dry_run, True)
                    total += n
                self.stdout.write(self.style.SUCCESS(f"  Honours: {n} table(s) migrated."))

        if total > 0 and not dry_run:
            self.stdout.write(self.style.SUCCESS(f"Done. {total} table(s) now use qid as primary key."))
        elif dry_run:
            self.stdout.write("Dry run complete.")
