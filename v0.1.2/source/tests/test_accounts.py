import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from yastreb.accounts import Accounts


class AccountsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.accounts = Accounts(Path(self.tmp.name) / 'users.sqlite')

    def test_password_and_roles(self):
        self.accounts.create_user('head@company.local', 'Начальник', 'branch_head', 'long-password-123')
        self.assertIsNone(self.accounts.authenticate('head@company.local', 'wrong'))
        user = self.accounts.authenticate('HEAD@company.local', 'long-password-123')
        self.assertTrue(self.accounts.can_manage(user['email']))
        self.accounts.create_user('worker@company.local', 'Работник', 'worker', 'long-password-123')
        self.assertFalse(self.accounts.can_manage('worker@company.local'))
        self.assertFalse(self.accounts.can_manage('nobody@company.local'))

    def test_history_survives_and_is_private(self):
        for email in ['a@local.test', 'b@local.test']:
            self.accounts.create_user(email, email, 'worker', 'long-password-123')
        chat = self.accounts.new_chat('a@local.test')
        self.accounts.append('a@local.test', chat, 'user', 'Question')
        self.assertEqual(Accounts(self.accounts.path).messages('a@local.test', chat)[0]['content'], 'Question')
        self.assertEqual(self.accounts.chats('b@local.test'), [])
        with self.assertRaises(PermissionError):
            self.accounts.messages('b@local.test', chat)
        with self.assertRaises(PermissionError):
            self.accounts.append('b@local.test', chat, 'user', 'attack')

    def test_settings_persist(self):
        self.accounts.create_user('a@local.test', 'А', 'worker', 'long-password-123')
        self.accounts.preferences('a@local.test', {'theme': 'dark'})
        self.assertEqual(self.accounts.preferences('a@local.test')['theme'], 'dark')

    def test_delete_chat_removes_messages_only_for_owner(self):
        for email in ['a@local.test', 'b@local.test']:
            self.accounts.create_user(email, email, 'worker', 'long-password-123')
        chat = self.accounts.new_chat('a@local.test')
        keep = self.accounts.new_chat('a@local.test')
        self.accounts.append('a@local.test', chat, 'user', 'Delete me')
        with self.assertRaises(PermissionError):
            self.accounts.delete_chat('b@local.test', chat)
        self.assertEqual(len(self.accounts.messages('a@local.test', chat)), 1)
        self.accounts.delete_chat('a@local.test', chat)
        self.assertEqual([c['id'] for c in Accounts(self.accounts.path).chats('a@local.test')], [keep])
        with self.accounts.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM messages WHERE chat=?', (chat,)).fetchone()[0], 0)
        with self.assertRaises(PermissionError):
            self.accounts.append('a@local.test', chat, 'assistant', 'Late answer')

    def test_user_input_validation(self):
        with self.assertRaises(ValueError):
            self.accounts.create_user('invalid', 'А', 'worker', 'long-password-123')
        with self.assertRaises(ValueError):
            self.accounts.create_user('a@local.test', 'А', 'owner', 'long-password-123')

    def test_concurrent_failures_lock_account(self):
        self.accounts.create_user('a@local.test', 'А', 'worker', 'long-password-123')
        with ThreadPoolExecutor(max_workers=5) as pool:
            attempts = list(pool.map(lambda _: self.accounts.authenticate('a@local.test', 'wrong'), range(5)))
        self.assertEqual(attempts, [None] * 5)
        self.assertIsNone(self.accounts.authenticate('a@local.test', 'long-password-123'))

    def test_initial_admin_only_once(self):
        self.assertTrue(self.accounts.is_empty())
        self.accounts.create_user('admin@local.test', 'Админ', 'admin', 'long-password-123', first_admin=True)
        self.assertFalse(self.accounts.is_empty())
        with self.assertRaises(PermissionError):
            self.accounts.create_user('other@local.test', 'Другой', 'admin', 'long-password-123', first_admin=True)
