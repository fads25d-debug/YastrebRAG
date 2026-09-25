from streamlit.testing.v1 import AppTest
from pathlib import Path
from threading import Event

from yastreb import runtime

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


def finish_demo(app, tmp_path):
    manager = runtime.get_jobs(str((tmp_path / 'demo/users.sqlite').resolve()),
                               str(tmp_path.resolve()), str(Path(APP).parent / 'models/bge-m3'),
                               'http://127.0.0.1:11434', 'qwen2.5:7b', True)
    # Wait for accepted work, not an arbitrary delay; the renderer runs independently.
    with manager._lock:
        futures = list(manager._pending.values())
    for future in futures:
        future.result(timeout=10)
    app.run()


def test_switching_chat_during_answer_keeps_background_work(tmp_path, monkeypatch):
    monkeypatch.setenv('YASTREB_DEMO', '1')
    monkeypatch.setenv('YASTREB_DATA_DIR', str(tmp_path))
    started, release = Event(), Event()

    def slow_answer(question, mode):
        started.set()
        assert release.wait(15)
        return {'text': 'Ответ на исходный вопрос', 'sources': []}

    monkeypatch.setattr(runtime, 'demo_answer', slow_answer)
    app = AppTest.from_file(APP, default_timeout=5).run()
    original = app.session_state['chat_id']
    try:
        app.chat_input[0].set_value('Исходный вопрос').run()
        assert started.wait(5)
        assert app.chat_input[0].disabled
        app.button(key='new_dialog').click().run()
        other = app.session_state['chat_id']
        assert other != original
        assert not app.chat_input[0].disabled
        assert len(app.chat_message) == 0
        app.button(key=original).click().run()
        assert app.chat_input[0].disabled
        assert len(app.chat_message) == 1
        app.button(key=other).click().run()
        release.set()
        finish_demo(app, tmp_path)
        assert len(app.chat_message) == 0
        app.button(key=original).click().run()
        assert not app.exception
        assert len(app.chat_message) == 2
        assert app.chat_message[1].markdown[0].value == 'Ответ на исходный вопрос'
        assert not app.chat_input[0].disabled
    finally:
        release.set()
        finish_demo(app, tmp_path)


def test_delete_dialog_confirmation_and_last_chat(tmp_path, monkeypatch):
    monkeypatch.setenv('YASTREB_DEMO', '1')
    monkeypatch.setenv('YASTREB_DATA_DIR', str(tmp_path))
    app = AppTest.from_file(APP, default_timeout=20).run()
    app.chat_input[0].set_value('Диалог для удаления').run()
    finish_demo(app, tmp_path)
    original = app.session_state['chat_id']
    app.button(key='delete_' + original).click().run()
    assert len(app.chat_message) == 2
    app.button(key='cancel_delete').click().run()
    assert len(app.chat_message) == 2
    app.button(key='delete_' + original).click().run()
    app.button(key='confirm_delete').click().run()
    assert not app.exception
    assert len(app.chat_message) == 0
    assert app.session_state['chat_id'] != original
    assert not any(b.key == original for b in app.button)
    app.run()
    assert not any(b.key == original for b in app.button)


def test_demo_modes_settings_and_history(tmp_path, monkeypatch):
    monkeypatch.setenv('YASTREB_DEMO', '1')
    monkeypatch.setenv('YASTREB_DATA_DIR', str(tmp_path))
    app = AppTest.from_file(APP, default_timeout=20).run()
    assert not app.exception
    assert app.radio[0].options == ['Быстрый', 'Подробный']
    app.radio[0].set_value('Подробный').run()
    app.chat_input[0].set_value('Как оформить отчёт?').run()
    finish_demo(app, tmp_path)
    assert not app.exception
    assert len(app.chat_message) == 2
    assert 'восьми' in app.chat_message[1].markdown[0].value
    next(b for b in app.button if b.label == '⚙').click().run()
    assert 'Внести изменения' in [t.label for t in app.tabs]
    next(s for s in app.selectbox if s.label == 'Цветовая тема').select('Тёмная').run()
    next(b for b in app.button if b.label == 'Применить').click().run()
    assert not app.exception
    next(s for s in app.selectbox if s.label == 'Тестовая роль').select('worker').run()
    # Widget value applies to identity at next script evaluation.
    app.run()
    assert 'Внести изменения' not in [t.label for t in app.tabs]
    assert len(app.chat_message) == 0


def test_production_requires_login(tmp_path, monkeypatch):
    monkeypatch.setenv('YASTREB_DEMO', '0')
    monkeypatch.setenv('YASTREB_DATA_DIR', str(tmp_path))
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert len(app.chat_input) == 0
    assert [t.label for t in app.text_input] == ['Корпоративная почта', 'Пароль']


def test_worker_opens_word_source_and_returns_to_chat(tmp_path, monkeypatch):
    import hashlib
    from yastreb.accounts import Accounts
    from yastreb.backend import Backend
    from test_documents import docx
    monkeypatch.setenv('YASTREB_DEMO', '0')
    monkeypatch.setenv('YASTREB_DATA_DIR', str(tmp_path))
    accounts = Accounts(tmp_path / 'accounts/users.sqlite')
    email = 'reader@local.test'
    accounts.create_user(email, 'Читатель', 'worker', 'long-password-123')
    raw = docx('Порядок', 'Подать отчёт до 12 мая.')
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    backend.ingest([('order.docx', raw)], can_manage=True, confirmed=True)
    chat = accounts.new_chat(email)
    accounts.append(email, chat, 'assistant', 'Срок: 12 мая. [1]', [{
        'document_id': hashlib.sha256(raw).hexdigest(), 'source': 'order.docx',
        'format': 'docx', 'page': 2, 'quote': '12 мая', 'start': 15, 'end': 21}])
    app = AppTest.from_file(APP).run()
    app.text_input[0].set_value(email)
    app.text_input[1].set_value('long-password-123')
    app.button[0].click().run()
    next(b for b in app.button if b.label == 'Открыть найденный фрагмент ↗').click().run()
    assert not app.exception
    assert app.title[0].value == 'Просмотр документа'
    assert app.selectbox[0].value == 2
    assert any('Подать отчёт' in m.value for m in app.markdown)
    assert app.get('download_button')
    next(b for b in app.button if b.label == '← Предыдущий').click().run()
    assert app.selectbox[0].value == 1
    app.button(key='close_document').click().run()
    assert len(app.chat_message) == 1
    assert app.session_state['chat_id'] == chat


def test_document_deep_link_requires_login(tmp_path, monkeypatch):
    monkeypatch.setenv('YASTREB_DEMO', '0')
    monkeypatch.setenv('YASTREB_DATA_DIR', str(tmp_path))
    app = AppTest.from_file(APP)
    app.query_params['document'] = 'a' * 64
    app.run()
    assert app.title[0].value == 'Ястреб'
    assert not app.get('download_button')


def test_folder_picker_available_only_to_managers(tmp_path, monkeypatch):
    monkeypatch.setenv('YASTREB_DEMO', '1')
    monkeypatch.setenv('YASTREB_DATA_DIR', str(tmp_path))
    app = AppTest.from_file(APP).run()
    next(b for b in app.button if b.label == '⚙').click().run()
    app.checkbox(key='folder_mode').check().run()
    assert app.get('file_uploader')[0].proto.accept_directory
    next(s for s in app.selectbox if s.label == 'Тестовая роль').select('worker').run()
    app.run()
    assert not app.get('file_uploader')


def test_first_admin_setup_then_login(tmp_path, monkeypatch):
    monkeypatch.setenv('YASTREB_DEMO', '0')
    monkeypatch.setenv('YASTREB_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('YASTREB_SETUP_EMAIL', 'admin@local.test')
    app = AppTest.from_file(APP).run()
    assert app.title[0].value == 'Первый запуск «Ястреб»'
    app.text_input[1].set_value('long-password-123')
    app.text_input[2].set_value('long-password-123')
    app.button[0].click().run()
    assert not app.exception
    assert app.title[0].value == 'Ястреб'
    app.text_input[0].set_value('admin@local.test')
    app.text_input[1].set_value('long-password-123')
    app.button[0].click().run()
    assert len(app.chat_input) == 1
