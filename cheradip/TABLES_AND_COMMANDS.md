# Tables and management commands

## What happens when you run makemigrations and migrate?

- **makemigrations**: Creates new migration files if you changed any model (added/removed fields or models). If you don't change models, it does nothing.
- **migrate**: Applies all existing migrations to each database. That creates tables for **every** model that has a migration, according to the DB routers:
  - **default (cheradip_cheradip)**: All cheradip models that are **not** routed to job/hsc/honours (Country, Location, Item, Transaction, OrderDetail, Order, Ordered, Canceled, Customer, CustomerToken, Group, ClassLevel, Department, ClassGroupMapping, Chapter, Topic, Institute, Year, Mcq_ict, Notification, JsonData, PendingSubjectRequest) plus Django tables (auth, contenttypes, sessions, admin, migrations).
  - **job (cheradip_job)**: Banbeis, Institutes, Token, Merit (→ merit7), Merit5, Merit6, Vacancy (→ vacancy7), Vacancy5, Vacancy6, Recommend (→ recommend7), Recommend5, Recommend6.
  - **hsc (cheradip_hsc)**: Subject, PendingSubjectRequestHsc.
  - **honours (cheradip_honours)**: PendingSubjectRequestHonours.

So **migrate creates more tables than the ones your commands "ensure"** — it creates everything defined in migrations.

---

## Tables targeted by each command

| Command | Database | Tables it ensures / expects |
|--------|----------|----------------------------|
| **ensure_cheradip** | default | cheradip_country, cheradip_location, cheradip_customers, cheradip_items, cheradip_transactions, cheradip_order*, cheradip_ordered*, cheradip_canceled*, cheradip_customer_tokens, django_*, auth_* |
| **ensure_job** | job | cheradip_banbeis, cheradip_institutes, cheradip_merit5/6/7, cheradip_recommend5/6/7, cheradip_tokens, cheradip_vacancy5/6/7 |
| **ensure_hsc** | hsc | cheradip_pending_question_request, cheradip_pending_subject_request (renamed from _hsc), cheradip_subject (+ dynamic subject question tables via SQL; schema: **qid** PK, **topic_no**) |
| **ensure_honours** | honours | cheradip_pending_question_request, cheradip_pending_subject_request (renamed from _honours), cheradip_subject (+ dynamic book question tables via SQL; same schema: **qid** PK, **topic_no**) |
| **ensure_insertion** | hsc | Reads SQL file (default: cheradip/sql/cheradip_higher_secon_11_12_information_and_communication_techno.sql), adds topic_no and qid (empty in file), replaces Bengali chapter_no with English, then inserts into the table with auto-generated qid and topic_no. |
| **drop_cheradip_tables_except_…** | default | Keeps only: cheradip_location, cheradip_customers, cheradip_country |

**topic_no and qid** are never inserted by the user from the frontend; they are set automatically on insert (e.g. by ensure_insertion or approve flow), or via database/CSV/MySQL.

So:
- **ensure_cheradip** targets country, location, customer **and** order/payment tables (default DB only).
- **ensure_job** creates NTRCA/job tables on cheradip_job.
- **ensure_hsc** creates cheradip_pending_question_request, cheradip_pending_subject_request (renaming from cheradip_pending_subject_request_hsc if present), cheradip_subject, then one subject question table per (class_level, subject_tr) with **qid** PK and **topic_no** (subject_question_tables.py).
- **ensure_honours** creates cheradip_pending_question_request, cheradip_pending_subject_request (renaming from cheradip_pending_subject_request_honours if present), cheradip_subject, then one book question table per book_tr with the same **qid** + **topic_no** schema (ensure_honours.py).
- **ensure_insertion** updates the SQL file (add topic_no, qid with empty values; replace Bengali digits in chapter_no with English), then inserts into the given HSC subject question table with auto-generated **qid** and **topic_no** (same logic as migrate_question_tables_qid).
- **drop_*** keeps only country, location, customer on default.

### Required tables on cheradip_cheradip (default)

These tables are **required** on the default database and must be kept:
- **Country**, **Location**, **Customer**
- **Item**, **Transaction**, **Order**, **OrderDetail**, **Ordered**, **Canceled**
- **CustomerToken**
- **Notification**, **JsonData**

So the targeted set for default DB is: country, location, customer, items, transactions, order/orderdetail/ordered/canceled, customer_tokens, notification, json_data (+ Django tables). No changes are needed to remove these; they stay.

---

## Model → table mapping (for reference)

- **Default DB:** Country→cheradip_country, Location→cheradip_location, Customer→cheradip_customers, Item→cheradip_items, Transaction→cheradip_transactions, OrderDetail→cheradip_orderdetail, Order→cheradip_order, Ordered→cheradip_ordered, Canceled→cheradip_canceled, CustomerToken→cheradip_customer_tokens, Group→cheradip_groups, ClassLevel→cheradip_class_levels, Department→cheradip_departments, ClassGroupMapping→cheradip_class_group_mappings, Chapter→cheradip_chapters, Topic→cheradip_topics, Institute→cheradip_institute, Year→cheradip_years, Mcq_ict→cheradip_mcq_ict, Notification→cheradip_notification, JsonData→cheradip_json_data, PendingSubjectRequest→cheradip_pending_subject_request (default DB).
- **Job DB:** Banbeis→cheradip_banbeis, Institutes→cheradip_institutes, Token→cheradip_tokens, Merit→cheradip_merit7, Merit5→cheradip_merit5, Merit6→cheradip_merit6, Vacancy→cheradip_vacancy7, Vacancy5→cheradip_vacancy5, Vacancy6→cheradip_vacancy6, Recommend→cheradip_recommend7, Recommend5→cheradip_recommend5, Recommend6→cheradip_recommend6.
- **HSC:** Subject→cheradip_subject, PendingSubjectRequestHsc→cheradip_pending_subject_request (ensure_hsc creates/renames to this). Pending questions: cheradip_pending_question_request (ensure_hsc creates it).
- **Honours:** PendingSubjectRequestHonours→cheradip_pending_subject_request (ensure_honours creates/renames to this). Pending questions: cheradip_pending_question_request (ensure_honours creates it).
- **SubjectQuestionBase** is abstract (no table).

---

## Optional: trimming other default-DB tables

If you later want the default DB to have **only** the required set above (no Group, ClassLevel, Department, ClassGroupMapping, Chapter, Topic, Institute, Year, Mcq_ict, PendingSubjectRequest), we would remove those models and their use in admin/views/serializers and align **drop_cheradip_tables_except_…** and **ensure_cheradip** with the full required list (country, location, customer, item, transaction, order*, ordered*, canceled*, customer_tokens, notification, json_data). Until then, **ensure_cheradip** and migrate keep the current behaviour; the required set is documented above.

---

## Repeatable reset (drop tables → delete migration → makemigrations → migrate)

To avoid "table already exists" and regenerate from scratch on **cheradip_cheradip** (default):

1. **Drop all tables** in the default database `cheradip_cheradip` (and clear `django_migrations` if you drop that table too).
2. **Delete** `cheradip/migrations/0001_initial.py` (and any other app migrations if you want a full reset).
3. **Makemigrations:** `python manage.py makemigrations cheradip`
4. **Migrate:** `python manage.py migrate`

On **default** DB, PendingSubjectRequest→cheradip_pending_subject_request. On **hsc** and **honours**, ensure_hsc / ensure_honours create the table **cheradip_pending_subject_request** (and rename from _hsc / _honours if those old tables exist). You must drop all tables on the default DB before migrating if it already has that table.
