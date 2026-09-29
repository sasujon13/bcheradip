from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from cheradip.management.commands.mysql_db_sync import _plink_mysql_tunnel


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
