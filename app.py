"""Run: python -m streamlit run app.py. YASTREB_DEMO=1 enables labelled UI sandbox."""
import os
import secrets
import sqlite3
import time
from pathlib import Path

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'
os.environ['LANGSMITH_TRACING'] = 'false'
os.environ.setdefault('YASTREB_NUM_GPU', '0')

import streamlit as st
from yastreb.accounts import Accounts, ROLES
from yastreb import ui
from yastreb.runtime import get_backend, get_jobs
from yastreb.viewer import clear_document_view, location_label, open_source, show_document

st.set_page_config(page_title='Ястреб · документы', page_icon='🦅', layout='wide', initial_sidebar_state='expanded')
ROOT = Path(__file__).parent
DATA = Path(os.environ.get('YASTREB_DATA_DIR', str(ROOT / 'data')))
DEMO = os.environ.get('YASTREB_DEMO', '0') == '1'
accounts = Accounts(DATA / ('demo' if DEMO else 'accounts') / 'users.sqlite')
ui.apply_theme()

if DEMO:
    demo_role = st.session_state.get('demo_role', 'branch_head')
    email = demo_role + '@demo.local'
    if not accounts.user(email):
        try:
            accounts.create_user(email, 'Алексей Кузнецов', demo_role, secrets.token_urlsafe(24))
        except sqlite3.IntegrityError:
            pass
    st.session_state['email'] = email
else:
    setup_email = os.environ.get('YASTREB_SETUP_EMAIL', '')
    if setup_email and accounts.is_empty() and st.get_option('server.address') == '127.0.0.1':
        st.title('Первый запуск «Ястреб»')
        st.info('Создайте локальную учётную запись администратора: ' + setup_email)
        with st.form('first_admin'):
            setup_name = st.text_input('Ваше имя', value=setup_email.split('@')[0])
            setup_password = st.text_input('Новый пароль (не менее 12 символов)', type='password')
            setup_repeat = st.text_input('Повторите пароль', type='password')
            if st.form_submit_button('Создать администратора', type='primary'):
                if setup_password != setup_repeat:
                    st.error('Пароли не совпадают.')
                else:
                    try:
                        accounts.create_user(setup_email, setup_name, 'admin', setup_password, first_admin=True)
                        st.rerun()
                    except (ValueError, PermissionError) as exc:
                        st.error(str(exc))
        st.caption('Первичная настройка разрешена только при локальном запуске и пустой базе пользователей.')
        st.stop()
    if time.time() - st.session_state.get('last_activity', 0) > 1800:
        st.session_state.pop('email', None)
    if 'email' not in st.session_state:
        with st.container(key='login'):
            ui.brand()
            st.title('Ястреб')
            st.caption('Ваши документы. Проверяемые ответы.')
            with st.form('login'):
                email = st.text_input('Корпоративная почта', placeholder='name@company.local')
                password = st.text_input('Пароль', type='password', placeholder='Введите пароль')
                if st.form_submit_button('Войти', type='primary', width='stretch'):
                    user = accounts.authenticate(email, password)
                    if user:
                        st.session_state['email'] = user['email']
                        st.session_state['last_activity'] = time.time()
                        st.rerun()
                    st.error('Неверные данные или вход временно заблокирован. После 5 ошибок подождите 5 минут.')
            st.caption('Доступ предоставляется администратором вашей организации.')
        st.stop()
    st.session_state['last_activity'] = time.time()

user = accounts.user(st.session_state['email'])
if not user:
    st.session_state.clear()
    st.rerun()
email = user['email']
prefs = accounts.preferences(email)
theme = prefs.get('theme', 'Синяя')
ui.apply_theme(theme, prefs.get('size') == 'Крупный')


def backend():
    return get_backend(*backend_config)


backend_config = (str(DATA.resolve()),
                  os.environ.get('YASTREB_EMBEDDING_PATH', str(ROOT / 'models' / 'bge-m3')),
                  os.environ.get('YASTREB_OLLAMA_URL', 'http://127.0.0.1:11434'),
                  os.environ.get('YASTREB_OLLAMA_MODEL', 'qwen2.5:7b'))
jobs = get_jobs(str(accounts.path.resolve()), *backend_config, DEMO)
active_jobs = jobs.active(email)


def toggle_settings():
    st.session_state['settings_open'] = not st.session_state.get('settings_open', False)


with st.sidebar:
    ui.brand()
    if st.button('＋ Новый диалог', width='stretch', key='new_dialog'):
        clear_document_view()
        st.session_state['chat_id'] = accounts.new_chat(email)
        st.rerun()
    st.caption('Ваши диалоги')
    chats = accounts.chats(email)
    ids = [c['id'] for c in chats]
    if st.session_state.get('chat_id') not in ids:
        st.session_state['chat_id'] = ids[0] if ids else accounts.new_chat(email)
    with st.container(key='history'):
        for chat in accounts.chats(email):
            title_col, delete_col = st.columns([6, 1], gap='small')
            title = ('⏳ ' if chat['id'] in active_jobs else '') + chat['title']
            if title_col.button(title, key=chat['id'], width='stretch',
                         type='primary' if chat['id'] == st.session_state['chat_id'] else 'secondary'):
                st.session_state['chat_id'] = chat['id']
                clear_document_view()
                st.session_state.pop('delete_chat_id', None)
                st.rerun()
            if delete_col.button('Удалить диалог', icon=':material/delete:', key='delete_' + chat['id'],
                                 help='Удалить диалог', width='stretch'):
                st.session_state['delete_chat_id'] = chat['id']
                st.rerun()
    pending = next((c for c in accounts.chats(email)
                    if c['id'] == st.session_state.get('delete_chat_id')), None)
    if pending:
        with st.container(key='delete_confirmation', border=True):
            st.write('Удалить диалог?')
            st.text(pending['title'])
            st.caption('Все сообщения этого диалога будут удалены без возможности восстановления. Документы останутся в библиотеке.')
            if st.button('Удалить навсегда', key='confirm_delete', width='stretch'):
                try:
                    accounts.delete_chat(email, pending['id'])
                except PermissionError:
                    st.session_state.pop('delete_chat_id', None)
                    st.rerun()
                st.session_state.pop('delete_chat_id', None)
                st.rerun()
            if st.button('Отмена', key='cancel_delete', width='stretch'):
                st.session_state.pop('delete_chat_id', None)
                st.rerun()
    else:
        st.session_state.pop('delete_chat_id', None)
    if st.session_state.get('settings_open'):
        with st.container(key='settings'):
            st.markdown('**Настройки**')
            allowed = accounts.can_manage(email)
            labels = ['Внешний вид'] + (['Внести изменения'] if allowed else []) + ['Профиль']
            tabs = st.tabs(labels)
            with tabs[0]:
                new_theme = st.selectbox('Цветовая тема', ['Синяя', 'Светлая', 'Тёмная'],
                                         index=['Синяя', 'Светлая', 'Тёмная'].index(theme))
                size = st.selectbox('Размер текста', ['Обычный', 'Крупный'], index=1 if prefs.get('size') == 'Крупный' else 0)
                if st.button('Применить', width='stretch'):
                    accounts.preferences(email, {'theme': new_theme, 'size': size})
                    st.rerun()
            if allowed:
                with tabs[1]:
                    st.caption('Добавление документов в общую библиотеку')
                    if not DEMO:
                        try:
                            counts = backend().status()
                            st.caption(f"Документов: {counts['documents']} · фрагментов в индексе: {counts['chunks']}")
                        except Exception as exc:
                            st.error(str(exc))
                    folder_mode = st.checkbox('Выбрать папку целиком', key='folder_mode')
                    files = st.file_uploader('Папка с документами' if folder_mode else 'PDF и Word-документы',
                                             type=['pdf', 'docx', 'doc'],
                                             accept_multiple_files='directory' if folder_mode else True,
                                             key='folder_upload' if folder_mode else 'document_upload')
                    st.caption('Вложенные папки включаются. До 1000 файлов / 500 МиБ за раз; один файл — до 50 МиБ. '
                               'DOCX читается напрямую, для старых DOC нужен LibreOffice на сервере.')
                    confirmed = st.checkbox('Подтверждаю добавление файлов')
                    if st.button('Добавить и проиндексировать', disabled=not (confirmed and files), width='stretch'):
                        if DEMO:
                            st.info('Демонстрация: файлы не сохраняются. Для индексации запустите рабочий режим.')
                        else:
                            try:
                                with st.spinner('Извлекаю текст и строю индекс…'):
                                    if len(files) > 1000 or sum(f.size for f in files) > 500 * 1024 * 1024:
                                        raise ValueError('Превышен лимит: 1000 файлов или 500 МиБ.')
                                    result = backend().ingest_folder([(f.name, f.getvalue()) for f in files],
                                                                     can_manage=accounts.can_manage(email), confirmed=confirmed)
                                    if result['added'] or result['duplicates']:
                                        backend().rebuild(can_manage=accounts.can_manage(email))
                                        st.success('Индексация завершена.')
                                    else:
                                        st.warning('Подходящие документы не добавлены.')
                                st.caption(f"Добавлено: {result['added']} · Дубликатов: {result['duplicates']} · Пропущено: {result['skipped']}")
                                for error in result['errors']:
                                    st.text(error['file'] + ': ' + error['error'])
                            except Exception as exc:
                                st.error(str(exc))
                                st.caption('Если файлы уже сохранены, повторите переиндексацию после устранения ошибки. Прежний индекс остаётся рабочим.')
                    rebuild_confirm = st.checkbox('Подтверждаю перестроение индекса')
                    if st.button('Переиндексировать', disabled=not rebuild_confirm, width='stretch'):
                        if DEMO:
                            st.info('Демонстрация: индекс не изменён.')
                        else:
                            try:
                                with st.spinner('Перестраиваю индекс…'):
                                    backend().rebuild(can_manage=accounts.can_manage(email))
                                st.success('Индекс обновлён.')
                            except Exception as exc:
                                st.error(str(exc))
            with tabs[-1]:
                st.write(user['name'])
                st.caption(email)
                st.write(ROLES[user['role']])
                if DEMO:
                    st.selectbox('Тестовая роль', list(ROLES), format_func=ROLES.get, key='demo_role',
                                 index=list(ROLES).index(user['role']))
                elif st.button('Выйти', width='stretch'):
                    st.session_state.clear()
                    st.rerun()
    with st.container(key='account'):
        name_col, gear_col = st.columns([4, 1])
        with name_col:
            ui.account(user['name'], ROLES[user['role']])
        with gear_col:
            st.button('⚙', help='Настройки', on_click=toggle_settings)

if st.query_params.get('document'):
    if DEMO:
        st.info('В деморежиме оригиналы документов недоступны.')
        if st.button('Вернуться к демонстрации'):
            st.query_params.clear()
            st.rerun()
    else:
        show_document(backend())
    st.stop()

st.markdown('<div class="workspace-bar"><span class="workspace-label">Библиотека знаний</span>'
            '<span class="local-badge"><i></i>Локальная обработка</span></div>', unsafe_allow_html=True)
st.title('Разобраться в документах.')
st.markdown('<p class="intro-copy">Найдите требование, уточните порядок действий или сравните положения — '
            'с опорой на первоисточник.</p>', unsafe_allow_html=True)
if DEMO:
    st.warning('Демонстрационный режим · ответы условные · реальные модели не используются')
else:
    st.caption('Ответы формируются по вашей библиотеке. Сверяйте важные выводы с источниками.')
with st.container(key='mode'):
    mode_label = st.radio('Режим поиска', ['Быстрый', 'Подробный'], horizontal=True, label_visibility='collapsed',
                          help='Быстрый: до 3 фрагментов. Подробный: до 8 фрагментов и развёрнутое объяснение.')
mode = 'quick' if mode_label == 'Быстрый' else 'detailed'
st.caption('Краткий ответ · до 3 источников' if mode == 'quick' else 'Развёрнутое объяснение · до 8 источников')
chat_id = st.session_state['chat_id']
messages = accounts.messages(email, chat_id)
if not messages:
    st.markdown('''<section class="empty-state"><h2>С чего начнём?</h2>
<p>Напишите вопрос и укажите предмет поиска. Ястреб найдёт подходящие фрагменты и приложит источники к ответу.</p>
<div class="question-examples">
<div class="question-example"><strong>Найти требование</strong><p>Какой срок подачи отчёта указан в регламенте?</p></div>
<div class="question-example"><strong>Понять порядок</strong><p>Как проходит согласование документа?</p></div>
<div class="question-example"><strong>Уточнить условия</strong><p>Кто может участвовать в мероприятии?</p></div>
</div></section>''', unsafe_allow_html=True)
for message in messages:
    with st.chat_message(message['role'], avatar=':material/person:' if message['role'] == 'user' else ':material/auto_stories:'):
        st.caption('Вы' if message['role'] == 'user' else 'Ястреб')
        if message['role'] == 'user':
            st.text(message['content'])
        else:
            # Prevent Markdown image embeds from contacting external hosts.
            st.markdown(message['content'].replace('!', r'\!'))
        if message['role'] == 'assistant':
            st.caption('Быстрый поиск' if message['mode'] == 'quick' else 'Подробный поиск')
        if message['sources']:
            st.caption('Источники ответа')
        for i, source in enumerate(message['sources'], 1):
            with st.expander(f"[{i}] {source['source']} · {location_label(source)}"):
                st.text(source['quote'])
                if not DEMO:
                    digest = backend().resolve_source(source)
                    if digest:
                        st.button('Открыть найденный фрагмент ↗', type='tertiary',
                                  key=f"open_source_{message['id']}_{i}",
                                  on_click=open_source, args=(digest, source))
                    else:
                        st.caption('Оригинал не найден или имя неоднозначно. Повторите поиск после переиндексации.')

if chat_id in active_jobs:
    st.info('Ищу в документах и готовлю ответ… Можно перейти в другой диалог.'
            if active_jobs[chat_id] == 'running' else
            'Запрос в очереди. Можно перейти в другой диалог — ответ сохранится здесь.')

if question := st.chat_input('Введите вопрос по документам…', max_chars=4000,
                             disabled=chat_id in active_jobs):
    try:
        jobs.submit(email, chat_id, question, mode)
    except (ValueError, PermissionError) as exc:
        st.error(str(exc))
    else:
        st.rerun()


# Numeric seconds avoid importing NumPy/pandas while the answer worker loads models.
@st.fragment(run_every=1.0 if active_jobs else None)
def refresh_answers():
    # Compare with the snapshot used to draw this page, including completion races.
    if jobs.active(email) != active_jobs:
        st.rerun()


refresh_answers()
