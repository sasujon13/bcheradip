# Ensures cheradip_trxmanagement exists in the database when:
# - 0006 was faked/applied without actually creating the table, or
# - an older checkout never ran the CreateModel DDL.
# Safe to apply multiple times on MySQL (CREATE TABLE IF NOT EXISTS).

from django.db import migrations


MYSQL_DDL = """
CREATE TABLE IF NOT EXISTS `cheradip_trxmanagement` (
    `id` int AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `media` varchar(64) NOT NULL,
    `received_amount` decimal(14, 4) NOT NULL,
    `currency` varchar(16) NOT NULL,
    `sender_contact` varchar(32) NOT NULL,
    `trxid` varchar(128) NOT NULL,
    `transaction_date` varchar(32) NOT NULL,
    `transaction_time` varchar(16) NOT NULL,
    `confidence` decimal(7, 5) NOT NULL,
    `status` int NOT NULL DEFAULT 0,
    `token` int NOT NULL DEFAULT 0,
    KEY `cheradip_trxmanagement_trxid_6f8846_idx` (`trxid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS "cheradip_trxmanagement" (
    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "media" varchar(64) NOT NULL,
    "received_amount" decimal NOT NULL,
    "currency" varchar(16) NOT NULL,
    "sender_contact" varchar(32) NOT NULL,
    "trxid" varchar(128) NOT NULL,
    "transaction_date" varchar(32) NOT NULL,
    "transaction_time" varchar(16) NOT NULL,
    "confidence" decimal NOT NULL,
    "status" integer NOT NULL DEFAULT 0,
    "token" integer NOT NULL DEFAULT 0
)
"""


def forwards(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if connection.vendor == "mysql":
            cursor.execute(MYSQL_DDL)
        elif connection.vendor == "sqlite":
            cursor.execute(SQLITE_DDL)
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS cheradip_trxmanagement_trxid_6f8846_idx '
                "ON cheradip_trxmanagement (trxid)"
            )
        elif connection.vendor == "postgresql":
            cursor.execute(
                """
CREATE TABLE IF NOT EXISTS cheradip_trxmanagement (
    id serial NOT NULL PRIMARY KEY,
    media varchar(64) NOT NULL,
    received_amount numeric(14, 4) NOT NULL,
    currency varchar(16) NOT NULL,
    sender_contact varchar(32) NOT NULL,
    trxid varchar(128) NOT NULL,
    transaction_date varchar(32) NOT NULL,
    transaction_time varchar(16) NOT NULL,
    confidence numeric(7, 5) NOT NULL,
    status integer NOT NULL DEFAULT 0,
    token integer NOT NULL DEFAULT 0
)
"""
            )
            cursor.execute(
                """CREATE INDEX IF NOT EXISTS cheradip_trxmanagement_trxid_6f8846_idx
                    ON cheradip_trxmanagement (trxid)"""
            )


class Migration(migrations.Migration):

    dependencies = [
        (
            'cheradip',
            '0007_rename_cqs_customer_counter_idx_cheradip_cr_custome_c6810a_idx_and_more',
        ),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop, elidable=False),
    ]
