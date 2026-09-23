"""Server resources shared across browser sessions and Streamlit reruns."""
from functools import lru_cache, partial
from pathlib import Path

from yastreb.accounts import Accounts
from yastreb.jobs import AnswerJobs


@lru_cache(maxsize=None)
def get_backend(data, embeddings, url, model):
    from yastreb.backend import Backend
    return Backend(Path(data) / 'library', Path(embeddings), url, model)


def demo_answer(question, mode):
    return {'text': 'Это демонстрационный ответ для проверки интерфейса. В рабочем режиме здесь будет '
            + ('краткий ответ по трём фрагментам.' if mode == 'quick' else
               'подробное объяснение по восьми фрагментам, с разделами и ссылками на источники.'),
            'sources': [{'source': 'Демонстрационный пример.pdf', 'page': 1,
                         'quote': 'Это условный текст для демонстрации раскрывающегося источника, не нормативный документ.'}]}


def _answer(data, embeddings, url, model, question, mode):
    return get_backend(data, embeddings, url, model).answer(question, mode)


# Constructed on the UI thread; executor and callback survive subsequent app reruns.
@lru_cache(maxsize=None)
def get_jobs(database, data, embeddings, url, model, demo):
    answer = demo_answer if demo else partial(_answer, data, embeddings, url, model)
    return AnswerJobs(Accounts(Path(database)), answer)
