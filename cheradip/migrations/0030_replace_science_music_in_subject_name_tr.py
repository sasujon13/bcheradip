# Replace "Science" -> "বিজ্ঞান" and "Music" -> "সঙ্গীত" in subject_name_tr (e.g. সমাজScience -> সমাজবিজ্ঞান)

from django.db import migrations


def get_subject_table(conn):
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


def replace_science_music(apps, schema_editor):
    """In subject_name_tr: Science -> বিজ্ঞান, Music -> সঙ্গীত."""
    conn = schema_editor.connection
    vendor = conn.vendor
    subject_table = get_subject_table(conn)
    with conn.cursor() as cur:
        if vendor == 'sqlite':
            cur.execute(
                f'SELECT id, subject_name_tr FROM "{subject_table}" WHERE subject_name_tr LIKE ? OR subject_name_tr LIKE ?',
                ['%Science%', '%Music%'],
            )
        else:
            cur.execute(
                f"SELECT id, subject_name_tr FROM `{subject_table}` WHERE subject_name_tr LIKE %s OR subject_name_tr LIKE %s",
                ['%Science%', '%Music%'],
            )
        rows = cur.fetchall()
    for subject_id, val in rows:
        if not val:
            continue
        new_val = (val.replace('Science', 'বিজ্ঞান').replace('Music', 'সঙ্গীত'))
        if new_val == val:
            continue
        with conn.cursor() as cur:
            if vendor == 'sqlite':
                cur.execute(
                    f'UPDATE "{subject_table}" SET subject_name_tr = ? WHERE id = ?',
                    [new_val, subject_id],
                )
            else:
                cur.execute(
                    f"UPDATE `{subject_table}` SET subject_name_tr = %s WHERE id = %s",
                    [new_val, subject_id],
                )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0029_subject_name_tr_from_translated'),
    ]

    operations = [
        migrations.RunPython(replace_science_music, noop),
    ]
