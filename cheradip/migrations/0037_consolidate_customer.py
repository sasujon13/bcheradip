# Consolidate cheradip_teacher, cheradip_student, cheradip_jobseeker into Customer.
# Handles DB where cheradip_customers may not exist (create it then copy); or exists (alter then copy).
# 1) State: AddField/AlterField on Customer, DeleteModel for the three.
# 2) Database: create cheradip_customers if missing, else add/alter columns; copy data; drop three tables.

from django.db import migrations, models


def _customer_table_exists(cursor):
    cursor.execute("""
        SELECT 1 FROM information_schema.TABLES
        WHERE table_schema = DATABASE() AND table_name = 'cheradip_customers'
    """)
    return cursor.fetchone() is not None


def _customer_columns(cursor):
    cursor.execute("""
        SELECT COLUMN_NAME FROM information_schema.COLUMNS
        WHERE table_schema = DATABASE() AND table_name = 'cheradip_customers'
    """)
    return {r[0] for r in cursor.fetchall()}


def ensure_customer_table_then_copy_then_drop(apps, schema_editor):
    conn = schema_editor.connection
    with conn.cursor() as cur:
        exists = _customer_table_exists(cur)
        if not exists:
            # Create cheradip_customers with full schema (post-0037)
            cur.execute("""
                CREATE TABLE cheradip_customers (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    last_login DATETIME(6) NULL,
                    is_superuser TINYINT(1) NOT NULL DEFAULT 0,
                    fullName VARCHAR(31) NOT NULL,
                    username VARCHAR(15) NOT NULL,
                    password VARCHAR(128) NOT NULL,
                    acctype VARCHAR(12) NOT NULL DEFAULT 'Student',
                    `group` VARCHAR(30) NOT NULL DEFAULT 'Science',
                    gender VARCHAR(10) NOT NULL DEFAULT 'Male',
                    country_code VARCHAR(2) NULL,
                    date_of_birth DATE NULL,
                    class_name VARCHAR(20) NULL,
                    department VARCHAR(50) NULL,
                    teacher_level VARCHAR(20) NULL,
                    teacher_subject_code VARCHAR(10) NULL,
                    teacher_department_code VARCHAR(20) NULL,
                    teacher_department_name VARCHAR(200) NULL,
                    division VARCHAR(31) NOT NULL DEFAULT '',
                    district VARCHAR(31) NOT NULL DEFAULT '',
                    thana VARCHAR(31) NOT NULL DEFAULT '',
                    `union` VARCHAR(31) NOT NULL DEFAULT '',
                    village VARCHAR(255) NOT NULL DEFAULT '',
                    email VARCHAR(254) NULL,
                    phone_alternate VARCHAR(11) NULL,
                    is_active TINYINT(1) NOT NULL DEFAULT 1,
                    is_staff TINYINT(1) NOT NULL DEFAULT 0,
                    date_joined DATETIME(6) NOT NULL,
                    updated_at DATETIME(6) NOT NULL,
                    UNIQUE KEY username (username),
                    KEY cheradip_customers_username_idx (username)
                )
            """)
        else:
            cols = _customer_columns(cur)
            # Add new columns if missing
            if 'country_code' not in cols:
                cur.execute("ALTER TABLE cheradip_customers ADD COLUMN country_code VARCHAR(2) NULL")
            if 'date_of_birth' not in cols:
                cur.execute("ALTER TABLE cheradip_customers ADD COLUMN date_of_birth DATE NULL")
            if 'class_name' not in cols:
                cur.execute("ALTER TABLE cheradip_customers ADD COLUMN class_name VARCHAR(20) NULL")
            if 'department' not in cols:
                cur.execute("ALTER TABLE cheradip_customers ADD COLUMN department VARCHAR(50) NULL")
            if 'teacher_department_name' not in cols:
                cur.execute("ALTER TABLE cheradip_customers ADD COLUMN teacher_department_name VARCHAR(200) NULL")
            if 'teacher_level' not in cols:
                cur.execute("ALTER TABLE cheradip_customers ADD COLUMN teacher_level VARCHAR(20) NULL")
            if 'teacher_subject_code' not in cols:
                cur.execute("ALTER TABLE cheradip_customers ADD COLUMN teacher_subject_code VARCHAR(10) NULL")
            if 'teacher_department_code' not in cols:
                cur.execute("ALTER TABLE cheradip_customers ADD COLUMN teacher_department_code VARCHAR(20) NULL")
            # Widen/modify columns (MySQL: MODIFY; skip if would fail)
            try:
                cur.execute("ALTER TABLE cheradip_customers MODIFY COLUMN username VARCHAR(15) NOT NULL")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE cheradip_customers MODIFY COLUMN `group` VARCHAR(30) NOT NULL DEFAULT 'Science'")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE cheradip_customers MODIFY COLUMN gender VARCHAR(10) NOT NULL DEFAULT 'Male'")
            except Exception:
                pass
            for col, spec in [
                ('division', "VARCHAR(31) NOT NULL DEFAULT ''"),
                ('district', "VARCHAR(31) NOT NULL DEFAULT ''"),
                ('thana', "VARCHAR(31) NOT NULL DEFAULT ''"),
                ('union', "VARCHAR(31) NOT NULL DEFAULT ''"),
                ('village', "VARCHAR(255) NOT NULL DEFAULT ''"),
            ]:
                try:
                    cur.execute("ALTER TABLE cheradip_customers MODIFY COLUMN `%s` %s" % (col, spec))
                except Exception:
                    pass

    # Copy from cheradip_student, cheradip_jobseeker, cheradip_teacher using raw SQL
    with conn.cursor() as cur:
        for table, acctype_val in [
            ('cheradip_student', 'Student'),
            ('cheradip_jobseeker', 'JobSeeker'),
            ('cheradip_teacher', 'Teacher'),
        ]:
            try:
                cur.execute("""
                    SELECT 1 FROM information_schema.TABLES
                    WHERE table_schema = DATABASE() AND table_name = %s
                """, [table])
                if not cur.fetchone():
                    continue
            except Exception:
                continue

            if table == 'cheradip_student':
                cur.execute("""
                    INSERT INTO cheradip_customers
                    (password, fullName, username, acctype, `group`, gender, country_code, date_of_birth,
                     class_name, department, email, division, district, thana, `union`, village,
                     teacher_level, teacher_subject_code, teacher_department_code, teacher_department_name,
                     is_superuser, is_active, is_staff, date_joined, updated_at)
                    SELECT password, fullName, username, COALESCE(acctype, 'Student'), COALESCE(`group`, 'Science'),
                           COALESCE(gender, 'Male'), country_code, date_of_birth, class_name, department, email,
                           '', '', '', '', '',
                           NULL, NULL, NULL, NULL,
                           0, 1, 0, COALESCE(date_joined, NOW()), COALESCE(updated_at, NOW())
                    FROM cheradip_student
                    ON DUPLICATE KEY UPDATE
                    password = VALUES(password), fullName = VALUES(fullName), acctype = VALUES(acctype),
                    `group` = VALUES(`group`), gender = VALUES(gender), country_code = VALUES(country_code),
                    date_of_birth = VALUES(date_of_birth), class_name = VALUES(class_name),
                    department = VALUES(department), email = VALUES(email)
                """)
            elif table == 'cheradip_jobseeker':
                cur.execute("""
                    INSERT INTO cheradip_customers
                    (password, fullName, username, acctype, `group`, gender, country_code, date_of_birth,
                     class_name, department, email, division, district, thana, `union`, village,
                     teacher_level, teacher_subject_code, teacher_department_code, teacher_department_name,
                     is_superuser, is_active, is_staff, date_joined, updated_at)
                    SELECT password, fullName, username, 'JobSeeker', COALESCE(`group`, 'Science'),
                           COALESCE(gender, 'Male'), country_code, date_of_birth, class_name, department, email,
                           '', '', '', '', '',
                           NULL, NULL, NULL, NULL,
                           0, 1, 0, COALESCE(date_joined, NOW()), COALESCE(updated_at, NOW())
                    FROM cheradip_jobseeker
                    ON DUPLICATE KEY UPDATE
                    password = VALUES(password), fullName = VALUES(fullName), acctype = 'JobSeeker',
                    `group` = VALUES(`group`), gender = VALUES(gender), country_code = VALUES(country_code),
                    date_of_birth = VALUES(date_of_birth), class_name = VALUES(class_name),
                    department = VALUES(department), email = VALUES(email)
                """)
            else:
                cur.execute("""
                    INSERT INTO cheradip_customers
                    (password, fullName, username, acctype, `group`, gender, country_code, date_of_birth,
                     class_name, department, email, division, district, thana, `union`, village,
                     teacher_level, teacher_subject_code, teacher_department_code, teacher_department_name,
                     is_superuser, is_active, is_staff, date_joined, updated_at)
                    SELECT password, fullName, username, 'Teacher', 'Science', COALESCE(gender, 'Male'),
                           country_code, date_of_birth, NULL, NULL, email,
                           '', '', '', '', '',
                           teacher_level, teacher_subject_code, teacher_department_code, teacher_department_name,
                           0, 1, 0, COALESCE(date_joined, NOW()), COALESCE(updated_at, NOW())
                    FROM cheradip_teacher
                    ON DUPLICATE KEY UPDATE
                    password = VALUES(password), fullName = VALUES(fullName), acctype = 'Teacher',
                    gender = VALUES(gender), country_code = VALUES(country_code), date_of_birth = VALUES(date_of_birth),
                    teacher_level = VALUES(teacher_level), teacher_subject_code = VALUES(teacher_subject_code),
                    teacher_department_code = VALUES(teacher_department_code),
                    teacher_department_name = VALUES(teacher_department_name), email = VALUES(email)
                """)

    # Drop the three tables
    for table in ('cheradip_student', 'cheradip_jobseeker', 'cheradip_teacher'):
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    SELECT 1 FROM information_schema.TABLES
                    WHERE table_schema = DATABASE() AND table_name = %s
                """, [table])
                if cur.fetchone():
                    cur.execute("DROP TABLE `%s`" % table)
            except Exception:
                pass


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0036_rename_cheradip_user_to_student'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='customer',
                    name='country_code',
                    field=models.CharField(blank=True, db_index=True, max_length=2, null=True),
                ),
                migrations.AddField(
                    model_name='customer',
                    name='date_of_birth',
                    field=models.DateField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name='customer',
                    name='class_name',
                    field=models.CharField(blank=True, max_length=20, null=True),
                ),
                migrations.AddField(
                    model_name='customer',
                    name='department',
                    field=models.CharField(blank=True, max_length=50, null=True),
                ),
                migrations.AddField(
                    model_name='customer',
                    name='teacher_department_name',
                    field=models.CharField(blank=True, max_length=200, null=True),
                ),
                migrations.AlterField(
                    model_name='customer',
                    name='username',
                    field=models.CharField(db_index=True, max_length=15, unique=True),
                ),
                migrations.AlterField(
                    model_name='customer',
                    name='group',
                    field=models.CharField(blank=True, default='Science', max_length=30),
                ),
                migrations.AlterField(
                    model_name='customer',
                    name='gender',
                    field=models.CharField(choices=[('Male', 'Male'), ('Female', 'Female'), ('Common', 'Common')], default='Male', max_length=10),
                ),
                migrations.AlterField(
                    model_name='customer',
                    name='division',
                    field=models.CharField(blank=True, default='', max_length=31),
                ),
                migrations.AlterField(
                    model_name='customer',
                    name='district',
                    field=models.CharField(blank=True, default='', max_length=31),
                ),
                migrations.AlterField(
                    model_name='customer',
                    name='thana',
                    field=models.CharField(blank=True, default='', max_length=31),
                ),
                migrations.AlterField(
                    model_name='customer',
                    name='union',
                    field=models.CharField(blank=True, default='', max_length=31),
                ),
                migrations.AlterField(
                    model_name='customer',
                    name='village',
                    field=models.CharField(blank=True, default='', max_length=255),
                ),
                migrations.DeleteModel(name='CheradipStudent'),
                migrations.DeleteModel(name='CheradipTeacher'),
                migrations.DeleteModel(name='CheradipJobseeker'),
            ],
            database_operations=[
                migrations.RunPython(ensure_customer_table_then_copy_then_drop, noop),
            ],
        ),
    ]
