"""Local credentials and owner-scoped conversation storage (no external identity service)."""
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ROLES = {'admin': 'Администратор', 'branch_head': 'Начальник отделения', 'worker': 'Работник'}


class Accounts:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, name TEXT NOT NULL,
                    role TEXT NOT NULL, salt TEXT NOT NULL, digest TEXT NOT NULL,
                    prefs TEXT NOT NULL DEFAULT '{}', failures INTEGER NOT NULL DEFAULT 0,
                    locked_until REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                    title TEXT NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, chat TEXT NOT NULL,
                    role TEXT NOT NULL, content TEXT NOT NULL, sources TEXT NOT NULL, mode TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_user(self, email, name, role, password, *, first_admin=False):
        email = email.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or role not in ROLES or not name.strip():
            raise ValueError('Укажите имя, корпоративную почту и допустимую роль.')
        if len(password) < 12:
            raise ValueError('Пароль должен содержать не менее 12 символов.')
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600_000).hex()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if first_admin and (role != 'admin' or db.execute('SELECT 1 FROM users LIMIT 1').fetchone()):
                raise PermissionError('Первичная настройка уже завершена.')
            db.execute('INSERT INTO users(email,name,role,salt,digest) VALUES(?,?,?,?,?)',
                       (email, name.strip(), role, salt, digest))

    def is_empty(self):
        with self.connect() as db:
            return not bool(db.execute('SELECT 1 FROM users LIMIT 1').fetchone())

    def authenticate(self, email, password):
        email = email.strip().lower()
        with self.connect() as db:
            # Serialize read/hash/update so concurrent attempts cannot lose increments.
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
            if row and row['locked_until'] > time.time():
                return None
            salt = bytes.fromhex(row['salt']) if row else bytes(16)
            digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600_000).hex()
            if not row or not hmac.compare_digest(digest, row['digest']):
                if row:
                    failures = row['failures'] + 1
                    db.execute('UPDATE users SET failures=?,locked_until=? WHERE email=?',
                               (failures, time.time() + 300 if failures >= 5 else 0, email))
                return None
            db.execute('UPDATE users SET failures=0,locked_until=0 WHERE email=?', (email,))
            return {key: row[key] for key in ('email', 'name', 'role')}

    def user(self, email):
        with self.connect() as db:
            row = db.execute('SELECT email,name,role FROM users WHERE email=?', (email,)).fetchone()
            return dict(row) if row else None

    def can_manage(self, email):
        user = self.user(email)
        return bool(user and user['role'] in ('admin', 'branch_head'))

    def preferences(self, email, value=None):
        with self.connect() as db:
            if value is not None:
                db.execute('UPDATE users SET prefs=? WHERE email=?', (json.dumps(value), email))
            row = db.execute('SELECT prefs FROM users WHERE email=?', (email,)).fetchone()
            return json.loads(row['prefs']) if row else {}

    def new_chat(self, email):
        if not self.user(email):
            raise PermissionError('Требуется вход.')
        chat = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO chats VALUES(?,?,?,?)', (chat, email, 'Новый диалог', time.time()))
        return chat

    def chats(self, email):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM chats WHERE owner=? ORDER BY updated DESC', (email,))]

    @staticmethod
    def _check_owner(db, email, chat):
        if not db.execute('SELECT 1 FROM chats WHERE id=? AND owner=?', (chat, email)).fetchone():
            raise PermissionError('Диалог недоступен.')

    def messages(self, email, chat):
        with self.connect() as db:
            self._check_owner(db, email, chat)
            return [{**dict(row), 'sources': json.loads(row['sources'])} for row in db.execute(
                'SELECT * FROM messages WHERE chat=? ORDER BY id', (chat,))]

    def delete_chat(self, email, chat):
        """Remove an owned conversation and its messages atomically."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._check_owner(db, email, chat)
            db.execute('DELETE FROM messages WHERE chat=?', (chat,))
            db.execute('DELETE FROM chats WHERE id=? AND owner=?', (chat, email))

    def append(self, email, chat, role, content, sources=(), mode='quick'):
        if role not in ('user', 'assistant'):
            raise ValueError('Недопустимый тип сообщения.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._check_owner(db, email, chat)
            count = db.execute('SELECT count(*) FROM messages WHERE chat=?', (chat,)).fetchone()[0]
            db.execute('INSERT INTO messages(chat,role,content,sources,mode) VALUES(?,?,?,?,?)',
                       (chat, role, content, json.dumps(sources, ensure_ascii=False), mode))
            if count == 0:
                db.execute('UPDATE chats SET title=? WHERE id=?', (content[:70], chat))
            db.execute('UPDATE chats SET updated=? WHERE id=?', (time.time(), chat))
