"""Process-owned answer queue: workers never access Streamlit session state."""
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import RLock


class AnswerJobs:
    def __init__(self, accounts, answer):
        self.accounts = accounts
        self.answer = answer
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='yastreb-answer')
        self._lock = RLock()
        self._pending = {}

    def _prune(self):
        for key, future in list(self._pending.items()):
            if future.done():
                del self._pending[key]

    def active(self, email):
        with self._lock:
            self._prune()
            return {chat: 'running' if future.running() else 'queued'
                    for (owner, chat), future in self._pending.items() if owner == email}

    def submit(self, email, chat, question, mode):
        if mode not in ('quick', 'detailed') or not isinstance(question, str) or not question.strip():
            raise ValueError('Укажите вопрос и режим поиска.')
        with self._lock:
            self.accounts.messages(email, chat)  # Enforce ownership before revealing job state.
            self._prune()
            key = (email, chat)
            if key in self._pending:
                raise ValueError('В этом диалоге уже готовится ответ.')
            if len(self._pending) >= 32:
                raise ValueError('Очередь заполнена. Повторите запрос позже.')
            self.accounts.append(email, chat, 'user', question, mode=mode)
            future = self._executor.submit(self._run, email, chat, question, mode)
            self._pending[key] = future
            return future

    def _run(self, email, chat, question, mode):
        try:
            self.accounts.messages(email, chat)
        except PermissionError:
            return  # Deleted while queued.
        try:
            result = self.answer(question, mode)
            text, sources = result['text'], result.get('sources', [])
            if result.get('error'):
                text = 'Не удалось обработать вопрос: ' + result['error'] + '. Проверьте локальные модели и повторите запрос.'
                sources = []
        except Exception as exc:
            text, sources = 'Не удалось обработать вопрос: ' + str(exc), []
        try:
            self.accounts.append(email, chat, 'assistant', text, sources, mode)
        except PermissionError:
            pass  # Never recreate a deleted conversation.
        except Exception:
            logging.getLogger(__name__).exception('Could not save background answer')
            raise

    def close(self):
        self._executor.shutdown(wait=True)
