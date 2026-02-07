# Add subject_name_tr to Subject and backfill from cheradip_subject_translated.subject_name

from django.db import migrations, models


def get_subject_table(conn):
    """Return subject table name."""
    if conn.vendor == 'sqlite':
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND (name='cheradip_subject' OR name='cheradip_subjects')"
            )
            row = cur.fetchone()
            return row[0] if row else 'cheradip_subject'
    with conn.cursor() as cur:
        for name in ('cheradip_subject', 'cheradip_subjects'):
            cur.execute(
                "SELECT 1 FROM information_schema.TABLES WHERE table_schema = DATABASE() AND table_name = %s",
                [name],
            )
            if cur.fetchone():
                return name
    return 'cheradip_subject'


def backfill_subject_name_tr(apps, schema_editor):
    """Copy subject_name from cheradip_subject_translated into cheradip_subject.subject_name_tr (per subject_id; prefer bn)."""
    conn = schema_editor.connection
    vendor = conn.vendor
    with conn.cursor() as cur:
        if vendor == 'sqlite':
            cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cheradip_subject_translated'"
            )
        else:
            cur.execute(
                "SELECT 1 FROM information_schema.TABLES WHERE table_schema = DATABASE() AND table_name = 'cheradip_subject_translated'"
            )
        if not cur.fetchone():
            return
        subject_table = get_subject_table(conn)
        # Add column if not exists (in case user added it manually, we still ensure it exists)
        if vendor == 'sqlite':
            cur.execute(f"PRAGMA table_info({subject_table})")
            cols = [r[1] for r in cur.fetchall()]
        else:
            cur.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE table_schema = DATABASE() AND table_name = %s",
                [subject_table],
            )
            cols = [r[0] for r in cur.fetchall()]
        if 'subject_name_tr' not in cols:
            if vendor == 'sqlite':
                cur.execute(f'ALTER TABLE "{subject_table}" ADD COLUMN subject_name_tr VARCHAR(50) NULL')
            else:
                cur.execute(f"ALTER TABLE `{subject_table}` ADD COLUMN subject_name_tr VARCHAR(50) NULL")
        # Copy: for each subject_id, take subject_name (prefer language_code='bn', else first)
        cur.execute(
            """
            SELECT subject_id, language_code, subject_name
            FROM cheradip_subject_translated
            ORDER BY subject_id, (CASE WHEN language_code = 'bn' THEN 0 ELSE 1 END), language_code
            """
        )
        rows = cur.fetchall()
        # Keep first row per subject_id (so bn first if present)
        seen = set()
        updates = []
        for row in rows:
            sid, lang, name = row[0], row[1], (row[2] or '').strip()[:50]
            if sid in seen or not name:
                continue
            seen.add(sid)
            updates.append((name, sid))
        for name, subject_id in updates:
            if vendor == 'sqlite':
                cur.execute(
                    f'UPDATE "{subject_table}" SET subject_name_tr = ? WHERE id = ?',
                    [name, subject_id],
                )
            else:
                cur.execute(
                    f"UPDATE `{subject_table}` SET subject_name_tr = %s WHERE id = %s",
                    [name, subject_id],
                )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0028_remove_cheradipuser_year_of_birth'),
    ]

    operations = [
        # Add column (in DB only if missing) and backfill; state always gets the field
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='subject',
                    name='subject_name_tr',
                    field=models.CharField(blank=True, max_length=50, null=True),
                ),
            ],
            database_operations=[
                migrations.RunPython(backfill_subject_name_tr, noop),
            ],
        ),
    ]
