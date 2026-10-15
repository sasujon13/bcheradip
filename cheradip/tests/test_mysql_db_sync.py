from contextlib import nullcontext
from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from django.test import SimpleTestCase

from cheradip.management.commands.mysql_db_sync import _plink_mysql_tunnel
from cheradip.management.commands import mysql_db_sync as sync


class MySQLSyncTunnelTests(SimpleTestCase):
    @patch('cheradip.management.commands.mysql_db_sync.socket.create_connection',
           return_value=nullcontext())
    @patch('cheradip.management.commands.mysql_db_sync.subprocess.Popen')
    @patch('cheradip.management.commands.mysql_db_sync.env')
    def test_plink_tunnel_uses_password_file_without_exposing_secret_in_arguments(
            self, environment, popen, create_connection):
        environment.side_effect = lambda key, default=None: {
            'PLINK_PATH': 'plink.exe', 'SSH_HOST_KEY': None,
        }.get(key, default)
        process = Mock()
        process.poll.return_value = None
        process.wait.return_value = 0
        popen.return_value = process

        with _plink_mysql_tunnel('server.example', 22, 'user', 'top-secret', None,
                                 13306, '127.0.0.1', 3306) as endpoint:
            self.assertEqual(endpoint, ('127.0.0.1', '13306'))

        args = popen.call_args.args[0]
        self.assertIn('-pwfile', args)
        self.assertNotIn('top-secret', args)
        password_path = Path(args[args.index('-pwfile') + 1])
        self.assertFalse(password_path.exists())
        create_connection.assert_called_once_with(('127.0.0.1', 13306), timeout=.4)
        process.terminate.assert_called_once()


class MySQLInsertOnlySyncTests(SimpleTestCase):
    def test_missing_database_prints_shell_quoted_linux_commands_and_does_not_create_it(self):
        import pymysql
        output = StringIO()
        with patch.object(sync, '_open_sync_connection', side_effect=pymysql.OperationalError(1049, 'Unknown database')), redirect_stdout(output):
            with self.assertRaises(sync.MissingRemoteDatabase):
                sync.sync_missing_to_remote(
                    source_host='source', source_port='3306', source_user='root', source_password='',
                    dest_host='remote', dest_port='3306', dest_user='sasha', dest_password='',
                    db='ecommerce', dry=False,
                )
        self.assertIn("sudo mysql -e 'CREATE DATABASE IF NOT EXISTS `ecommerce`", output.getvalue())
        self.assertIn('rerun --l2r', output.getvalue())

    def test_denied_database_is_not_misreported_as_missing(self):
        import pymysql
        with patch.object(sync, '_open_sync_connection', side_effect=pymysql.OperationalError(1044, 'Access denied')):
            with self.assertRaisesRegex(sync.MySQLSyncError, 'access failed') as result:
                sync.sync_missing_to_remote(
                    source_host='source', source_port='3306', source_user='root', source_password='',
                    dest_host='remote', dest_port='3306', dest_user='sasha', dest_password='',
                    db='ecommerce', dry=False,
                )
        self.assertNotIsInstance(result.exception, sync.MissingRemoteDatabase)

    def test_direction_selects_schema_only_for_l2r_and_snapshot_for_r2l(self):
        kwargs = dict(mysqldump='dump', mysql='mysql', local_host='local', local_port='3306',
                      local_user='root', local_password='', remote_host='remote', remote_port='3306',
                      remote_user='sasha', remote_password='', to_sync=['example'], dry=True)
        with patch.object(sync, 'sync_schema_to_remote') as schema_only, patch.object(sync, 'sync_data_to_remote') as with_data, patch.object(sync, 'sync_one_database') as snapshot, redirect_stdout(StringIO()):
            self.assertEqual(sync.run_one_pass(direction='local-to-remote', **kwargs), (1, 0))
            schema_only.assert_called_once()
            with_data.assert_not_called()
            snapshot.assert_not_called()
            schema_only.reset_mock()
            self.assertEqual(sync.run_one_pass(direction='local-to-remote-data', **kwargs), (1, 0))
            with_data.assert_called_once()
            schema_only.assert_not_called()
            with_data.reset_mock()
            self.assertEqual(sync.run_one_pass(direction='remote-to-local', **kwargs), (1, 0))
            schema_only.assert_not_called()
            with_data.assert_not_called()
            snapshot.assert_called_once()

    def test_missing_database_is_not_retried(self):
        with patch.object(sync, 'sync_schema_to_remote', side_effect=sync.MissingRemoteDatabase('create database')) as incremental, redirect_stdout(StringIO()):
            result = sync.run_one_pass(
                direction='local-to-remote', mysqldump='', mysql='mysql', local_host='local',
                local_port='3306', local_user='root', local_password='', remote_host='remote',
                remote_port='3306', remote_user='sasha', remote_password='', to_sync=['example'], dry=False,
            )
        self.assertEqual(result, (0, 1))
        incremental.assert_called_once()


class MySQLSchemaOnlySyncTests(SimpleTestCase):
    def test_existing_tables_are_checked_without_copying_rows(self):
        source = MagicMock()
        destination = MagicMock()
        source_cursor = source.cursor.return_value.__enter__.return_value
        remote_cursor = destination.cursor.return_value.__enter__.return_value
        source_cursor.fetchall.return_value = [('questions', 'BASE TABLE')]
        remote_cursor.fetchall.return_value = [('questions', 'BASE TABLE')]
        with patch.object(sync, '_open_sync_connection', side_effect=[source, destination]), redirect_stdout(StringIO()):
            sync.sync_schema_to_remote(
                source_host='local', source_port='3306', source_user='root', source_password='',
                dest_host='remote', dest_port='3306', dest_user='sasha', dest_password='',
                db='cheradip_cheradip', dry=False, mysql='mysql',
            )
        self.assertEqual(source_cursor.execute.call_args.args[0], 'SHOW FULL TABLES')
        self.assertEqual(remote_cursor.execute.call_args.args[0], 'SHOW FULL TABLES')
        destination.commit.assert_not_called()

    def test_missing_database_dry_run_does_not_attempt_create(self):
        import pymysql
        source = MagicMock()
        source_cursor = source.cursor.return_value.__enter__.return_value
        source_cursor.fetchall.return_value = [('questions', 'BASE TABLE')]
        with patch.object(sync, '_open_sync_connection', side_effect=[source, pymysql.OperationalError(1049, 'Unknown database')]), patch.object(sync, 'ensure_destination_database') as create, redirect_stdout(StringIO()):
            sync.sync_schema_to_remote(
                source_host='local', source_port='3306', source_user='root', source_password='',
                dest_host='remote', dest_port='3306', dest_user='sasha', dest_password='',
                db='ecommerce', dry=True, mysql='mysql',
            )
        create.assert_not_called()


@unittest.skipUnless(os.environ.get('MYSQL_SYNC_TEST_INTEGRATION') == '1',
                     'Set MYSQL_SYNC_TEST_INTEGRATION=1 to use isolated local MySQL test databases')
class MySQLInsertOnlyIntegrationTests(SimpleTestCase):
    """Real-driver regression tests. Never connect to configured project/remote databases."""

    def setUp(self):
        import pymysql
        self.options = dict(
            host=os.environ.get('MYSQL_SYNC_TEST_HOST', '127.0.0.1'),
            port=int(os.environ.get('MYSQL_SYNC_TEST_PORT', '3306')),
            user=os.environ.get('MYSQL_SYNC_TEST_USER', 'root'),
            password=os.environ.get('MYSQL_SYNC_TEST_PASSWORD', ''),
            charset='utf8mb4', autocommit=True,
        )
        self.admin = pymysql.connect(**self.options)
        suffix = uuid4().hex
        self.source_db = 'codex_sync_test_source_' + suffix
        self.destination_db = 'codex_sync_test_dest_' + suffix
        self.addCleanup(self.admin.close)
        for name in (self.source_db, self.destination_db):
            with self.admin.cursor() as cursor:
                cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
            self.addCleanup(self._drop_test_database, name)

    def _drop_test_database(self, name):
        # Exact generated name, with no environment-derived deletion target.
        self.assertRegex(name, r'^codex_sync_test_(source|dest)_[0-9a-f]{32}$')
        with self.admin.cursor() as cursor:
            cursor.execute(f'DROP DATABASE `{name}`')

    def sql(self, name, query, args=None):
        import pymysql
        with pymysql.connect(database=name, **self.options) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, args)
                return cursor.fetchall()

    def run_insert_only(self, dry=False):
        import pymysql
        def connect(host, port, user, password, db):
            options = {**self.options, 'autocommit': False}
            return pymysql.connect(database=self.source_db if host == 'test-source' else self.destination_db, **options)
        output = StringIO()
        with patch.object(sync, '_open_sync_connection', side_effect=connect), redirect_stdout(output):
            sync.sync_missing_to_remote(
                source_host='test-source', source_port='3306', source_user='root', source_password='',
                dest_host='test-destination', dest_port='3306', dest_user='root', dest_password='',
                db=self.source_db, dry=dry,
            )
        return output.getvalue()

    def test_schema_only_creates_table_without_copying_rows(self):
        import pymysql
        self.sql(self.source_db, 'CREATE TABLE products (id INT PRIMARY KEY, name VARCHAR(80))')
        self.sql(self.source_db, "INSERT INTO products VALUES (1,'Local product')")

        def connect(host, port, user, password, db):
            options = {**self.options, 'autocommit': False}
            database = self.source_db if host == 'test-source' else self.destination_db
            return pymysql.connect(database=database, **options)

        with patch.object(sync, '_open_sync_connection', side_effect=connect), redirect_stdout(StringIO()):
            sync.sync_schema_to_remote(
                source_host='test-source', source_port='3306', source_user='root', source_password='',
                dest_host='test-destination', dest_port='3306', dest_user='root', dest_password='',
                db=self.source_db, dry=False, mysql='mysql',
            )
        self.assertEqual(self.sql(self.destination_db, 'SELECT COUNT(*) FROM products'), ((0,),))

    def test_l2rd_updates_matching_rows_inserts_new_and_keeps_remote_only(self):
        import pymysql
        ddl = 'CREATE TABLE accounts (id INT PRIMARY KEY, note VARCHAR(80))'
        for name in (self.source_db, self.destination_db):
            self.sql(name, ddl)
        self.sql(self.source_db, "INSERT INTO accounts VALUES (1,'Local edit'),(2,'New local')")
        self.sql(self.destination_db, "INSERT INTO accounts VALUES (1,'Remote edit'),(99,'Remote only')")

        def connect(host, port, user, password, db):
            options = {**self.options, 'autocommit': False}
            database = self.source_db if host == 'test-source' else self.destination_db
            return pymysql.connect(database=database, **options)

        def run(dry):
            with patch.object(sync, '_open_sync_connection', side_effect=connect), redirect_stdout(StringIO()):
                sync.sync_data_to_remote(
                    source_host='test-source', source_port='3306', source_user='root', source_password='',
                    dest_host='test-destination', dest_port='3306', dest_user='root', dest_password='',
                    db=self.source_db, dry=dry, mysql='mysql',
                )

        run(True)
        self.assertEqual(self.sql(self.destination_db, 'SELECT note FROM accounts WHERE id=1'),
                         (('Remote edit',),))
        run(False)
        self.assertEqual(self.sql(self.destination_db, 'SELECT id,note FROM accounts ORDER BY id'),
                         ((1, 'Local edit'), (2, 'New local'), (99, 'Remote only')))
        run(False)
        self.assertEqual(self.sql(self.destination_db, 'SELECT COUNT(*) FROM accounts'), ((3,),))

    def test_l2rd_preserves_duplicate_keyless_rows(self):
        import pymysql
        for name in (self.source_db, self.destination_db):
            self.sql(name, 'CREATE TABLE unkeyed (value VARCHAR(20))')
        self.sql(self.source_db, "INSERT INTO unkeyed VALUES ('same'),('same'),('new')")
        self.sql(self.destination_db, "INSERT INTO unkeyed VALUES ('same')")

        def connect(host, port, user, password, db):
            options = {**self.options, 'autocommit': False}
            database = self.source_db if host == 'test-source' else self.destination_db
            return pymysql.connect(database=database, **options)

        with patch.object(sync, '_open_sync_connection', side_effect=connect), redirect_stdout(StringIO()):
            sync.sync_data_to_remote(
                source_host='test-source', source_port='3306', source_user='root', source_password='',
                dest_host='test-destination', dest_port='3306', dest_user='root', dest_password='',
                db=self.source_db, dry=False, mysql='mysql',
            )
        self.assertEqual(self.sql(self.destination_db, 'SELECT value, COUNT(*) FROM unkeyed GROUP BY value ORDER BY value'),
                         (('new', 1), ('same', 2)))

    def test_remote_edits_and_remote_only_rows_survive_repeated_passes(self):
        ddl = 'CREATE TABLE accounts (id INT PRIMARY KEY, email VARCHAR(80) UNIQUE, note TEXT)'
        for name in (self.source_db, self.destination_db):
            self.sql(name, ddl)
        self.sql(self.source_db, "INSERT INTO accounts VALUES (1,'one@example.com','local'),(2,'two@example.com','new'),(3,'shared@example.com','conflict')")
        self.sql(self.destination_db, "INSERT INTO accounts VALUES (1,'one@example.com','REMOTE EDIT'),(99,'shared@example.com','REMOTE ONLY')")
        first = self.run_insert_only()
        second = self.run_insert_only()
        self.assertEqual(self.sql(self.destination_db, 'SELECT id,note FROM accounts ORDER BY id'),
                         ((1, 'REMOTE EDIT'), (2, 'new'), (99, 'REMOTE ONLY')))
        self.assertIn('inserted=1', first)
        self.assertIn('duplicate-key conflicts skipped=1', first)
        self.assertIn('inserted=0', second)

    def test_no_key_unicode_binary_null_and_decimal_rows_are_idempotent(self):
        ddl = 'CREATE TABLE unkeyed (label TEXT, value DECIMAL(12,2), payload BLOB, optional INT NULL)'
        for name in (self.source_db, self.destination_db):
            self.sql(name, ddl)
        rows = [('বাংলা\nline', '12.34', b'\x00\xff', None), ('Other', '0.00', b'', 5)]
        for row in rows + [rows[0]]:
            self.sql(self.source_db, 'INSERT INTO unkeyed VALUES (%s,%s,%s,%s)', row)
        self.sql(self.destination_db, 'INSERT INTO unkeyed VALUES (%s,%s,%s,%s)', rows[0])
        self.run_insert_only()
        self.run_insert_only()
        self.assertEqual(self.sql(self.destination_db, 'SELECT COUNT(*) FROM unkeyed'), ((2,),))

    def test_missing_tables_with_foreign_keys_created_and_populated(self):
        self.sql(self.source_db, 'CREATE TABLE z_parent (id INT PRIMARY KEY, label VARCHAR(50))')
        self.sql(self.source_db, 'CREATE TABLE a_child (id INT PRIMARY KEY, parent_id INT, FOREIGN KEY (parent_id) REFERENCES z_parent(id))')
        self.sql(self.source_db, "INSERT INTO z_parent VALUES (1,'Parent')")
        self.sql(self.source_db, 'INSERT INTO a_child VALUES (1,1)')
        self.run_insert_only()
        self.assertEqual(self.sql(self.destination_db, 'SELECT * FROM a_child'), ((1, 1),))
        self.run_insert_only()
        self.assertEqual(self.sql(self.destination_db, 'SELECT COUNT(*) FROM z_parent'), ((1,),))

    def test_dry_run_compares_without_creating_tables_or_inserting(self):
        for name in (self.source_db, self.destination_db):
            self.sql(name, 'CREATE TABLE existing (id INT PRIMARY KEY)')
        self.sql(self.source_db, 'INSERT INTO existing VALUES (1)')
        self.sql(self.source_db, 'CREATE TABLE missing (id INT PRIMARY KEY)')
        self.sql(self.source_db, 'INSERT INTO missing VALUES (1)')
        output = self.run_insert_only(dry=True)
        self.assertEqual(self.sql(self.destination_db, 'SHOW TABLES'), (('existing',),))
        self.assertEqual(self.sql(self.destination_db, 'SELECT COUNT(*) FROM existing'), ((0,),))
        self.assertEqual(output.count('would insert=1'), 2)

    def test_schema_mismatch_is_reported_while_other_tables_are_imported(self):
        self.sql(self.source_db, 'CREATE TABLE bad (id INT PRIMARY KEY, extra TEXT)')
        self.sql(self.destination_db, 'CREATE TABLE bad (id INT PRIMARY KEY)')
        self.sql(self.source_db, 'CREATE TABLE good (id INT PRIMARY KEY)')
        self.sql(self.source_db, 'INSERT INTO good VALUES (10)')
        with self.assertRaisesRegex(sync.MySQLSyncError, 'incomplete.*bad'):
            self.run_insert_only()
        self.assertEqual(self.sql(self.destination_db, 'SELECT * FROM good'), ((10,),))
        self.assertEqual(len(self.sql(self.destination_db, 'SHOW COLUMNS FROM bad')), 1)

    def test_nullable_unique_keys_compare_full_rows_when_null(self):
        ddl = 'CREATE TABLE nullable_key (code VARCHAR(20) UNIQUE NULL, label TEXT)'
        for name in (self.source_db, self.destination_db):
            self.sql(name, ddl)
        self.sql(self.source_db, "INSERT INTO nullable_key VALUES (NULL,'one'),(NULL,'two'),('x','new')")
        self.sql(self.destination_db, "INSERT INTO nullable_key VALUES (NULL,'one'),('x','remote')")
        self.run_insert_only()
        self.run_insert_only()
        self.assertEqual(self.sql(self.destination_db, 'SELECT COUNT(*) FROM nullable_key'), ((3,),))
        self.assertEqual(self.sql(self.destination_db, "SELECT label FROM nullable_key WHERE code='x'"), (('remote',),))

    def test_collation_conflict_skips_only_duplicate_and_inserts_other_candidates(self):
        ddl = 'CREATE TABLE words (word VARCHAR(40) PRIMARY KEY, note TEXT)'
        for name in (self.source_db, self.destination_db):
            self.sql(name, ddl)
        self.sql(self.source_db, "INSERT INTO words VALUES ('hello','local'),('new','missing')")
        self.sql(self.destination_db, "INSERT INTO words VALUES ('HELLO','remote')")
        output = self.run_insert_only()
        self.assertEqual(self.sql(self.destination_db, 'SELECT word,note FROM words ORDER BY word'),
                         (('HELLO', 'remote'), ('new', 'missing')))
        self.assertIn('duplicate-key conflicts skipped=1', output)

    def test_foreign_key_errors_are_reported_instead_of_ignored(self):
        self.sql(self.source_db, 'CREATE TABLE z_parent (id INT PRIMARY KEY)')
        self.sql(self.source_db, 'CREATE TABLE a_child (id INT PRIMARY KEY, parent_id INT, FOREIGN KEY (parent_id) REFERENCES z_parent(id))')
        # Insert an orphan in one source session to model a corrupted legacy table.
        import pymysql
        with pymysql.connect(database=self.source_db, **self.options) as connection:
            with connection.cursor() as cursor:
                cursor.execute('SET FOREIGN_KEY_CHECKS=0')
                cursor.execute('INSERT INTO a_child VALUES (1,99)')
        with self.assertRaisesRegex(sync.MySQLSyncError, 'incomplete.*a_child'):
            self.run_insert_only()
        self.assertEqual(self.sql(self.destination_db, 'SELECT COUNT(*) FROM a_child'), ((0,),))

    def test_remote_view_is_never_replaced_by_a_table(self):
        self.sql(self.source_db, 'CREATE TABLE protected (id INT PRIMARY KEY)')
        self.sql(self.destination_db, 'CREATE VIEW protected AS SELECT 7 AS id')
        with self.assertRaisesRegex(sync.MySQLSyncError, 'incomplete.*protected'):
            self.run_insert_only()
        self.assertEqual(self.sql(self.destination_db, 'SELECT * FROM protected'), ((7,),))

    def test_zero_auto_increment_identity_is_preserved(self):
        import pymysql
        ddl = 'CREATE TABLE zero_id (id INT PRIMARY KEY AUTO_INCREMENT, note TEXT)'
        for name in (self.source_db, self.destination_db):
            self.sql(name, ddl)
        with pymysql.connect(database=self.source_db, **self.options) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION sql_mode='NO_AUTO_VALUE_ON_ZERO'")
                cursor.execute("INSERT INTO zero_id VALUES (0,'original')")
        self.run_insert_only()
        self.run_insert_only()
        self.assertEqual(self.sql(self.destination_db, 'SELECT * FROM zero_id'), ((0, 'original'),))
