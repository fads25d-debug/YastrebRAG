from threading import Event

import pytest

from yastreb.accounts import Accounts
from yastreb.jobs import AnswerJobs


def test_background_answer_stays_with_owner_and_chat(tmp_path):
    accounts = Accounts(tmp_path / 'users.sqlite')
    for email in ('a@local.test', 'b@local.test'):
        accounts.create_user(email, email, 'worker', 'long-password-123')
    chat = accounts.new_chat('a@local.test')
    other = accounts.new_chat('a@local.test')
    started, release = Event(), Event()

    def answer(question, mode):
        started.set()
        assert release.wait(10)
        return {'text': question + ' answered', 'sources': [{'source': 'a.pdf', 'page': 2, 'quote': 'original'}]}

    jobs = AnswerJobs(accounts, answer)
    try:
        future = jobs.submit('a@local.test', chat, 'Question', 'detailed')
        assert started.wait(5)
        assert jobs.active('a@local.test') == {chat: 'running'}
        assert jobs.active('b@local.test') == {}
        with pytest.raises(PermissionError):
            jobs.submit('b@local.test', chat, 'Attack', 'quick')
        with pytest.raises(ValueError):
            jobs.submit('a@local.test', chat, 'Duplicate', 'quick')
        assert accounts.messages('a@local.test', other) == []
        release.set()
        future.result(timeout=10)
        saved = Accounts(accounts.path).messages('a@local.test', chat)
        assert [m['role'] for m in saved] == ['user', 'assistant']
        assert saved[-1]['content'] == 'Question answered'
        assert saved[-1]['mode'] == 'detailed'
        assert saved[-1]['sources'][0]['page'] == 2
        assert jobs.active('a@local.test') == {}
        assert accounts.messages('a@local.test', other) == []
    finally:
        release.set()
        jobs.close()


def test_deleted_chat_is_not_recreated_by_late_answer(tmp_path):
    accounts = Accounts(tmp_path / 'users.sqlite')
    email = 'a@local.test'
    accounts.create_user(email, email, 'worker', 'long-password-123')
    chat = accounts.new_chat(email)
    started, release = Event(), Event()

    def answer(question, mode):
        started.set()
        assert release.wait(10)
        return {'text': 'Late', 'sources': []}

    jobs = AnswerJobs(accounts, answer)
    try:
        future = jobs.submit(email, chat, 'Question', 'quick')
        assert started.wait(5)
        accounts.delete_chat(email, chat)
        release.set()
        future.result(timeout=10)
        assert accounts.chats(email) == []
        with accounts.connect() as db:
            assert db.execute('SELECT count(*) FROM messages').fetchone()[0] == 0
    finally:
        release.set()
        jobs.close()


def test_error_is_saved_and_next_question_can_run(tmp_path):
    accounts = Accounts(tmp_path / 'users.sqlite')
    email = 'a@local.test'
    accounts.create_user(email, email, 'worker', 'long-password-123')
    chat = accounts.new_chat(email)

    def answer(question, mode):
        raise RuntimeError('Model unavailable')

    jobs = AnswerJobs(accounts, answer)
    try:
        jobs.submit(email, chat, 'One', 'quick').result(timeout=5)
        assert 'Model unavailable' in accounts.messages(email, chat)[-1]['content']
        jobs.submit(email, chat, 'Two', 'quick').result(timeout=5)
        assert len(accounts.messages(email, chat)) == 4
    finally:
        jobs.close()
