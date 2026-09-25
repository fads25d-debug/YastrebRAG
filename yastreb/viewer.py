"""Authenticated in-app document reader. Called only after the login gate."""
from pathlib import Path

import streamlit as st

from yastreb.backend import BackendError
from yastreb.documents import highlighted_text, render_pdf


def location_label(source):
    return ('стр. ' if source.get('format', 'pdf') == 'pdf' else 'абзац ') + str(source['page'])


def clear_document_view():
    for key in ('document', 'section', 'start', 'end'):
        st.query_params.pop(key, None)
    st.session_state.pop('document_section', None)
    st.session_state.pop('document_quote', None)


def open_source(digest, source):
    st.query_params['document'] = digest
    st.query_params['section'] = str(source['page'])
    st.query_params['start'] = str(source.get('start', 0))
    st.query_params['end'] = str(source.get('end', 0))
    st.session_state.pop('document_section', None)
    st.session_state['document_quote'] = source.get('quote', '')


@st.cache_data(show_spinner=False, max_entries=12)
def _page_image(raw, number):
    return render_pdf(raw, number)


def show_document(backend):
    if st.button('← Вернуться к диалогу', key='close_document'):
        clear_document_view()
        st.rerun()
    try:
        document = backend.document(st.query_params['document'])
        numbers = [n for n, _ in document['units']]
        target = int(st.query_params.get('section', '1'))
        start = int(st.query_params.get('start', '0'))
        end = int(st.query_params.get('end', '0'))
        if target not in numbers:
            raise BackendError('Указанный фрагмент отсутствует в документе.')
    except (BackendError, ValueError, KeyError) as exc:
        st.error(str(exc) if isinstance(exc, BackendError) else 'Некорректная ссылка на фрагмент.')
        return
    st.title('Просмотр документа')
    st.text(document['source'])
    kind = document['format']
    st.download_button('Скачать оригинал', document['raw'], file_name=Path(document['source']).name,
                       mime={'pdf': 'application/pdf', 'doc': 'application/msword',
                             'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}[kind])
    label = 'Страница' if kind == 'pdf' else 'Абзац'
    if st.session_state.get('document_section') not in numbers:
        st.session_state['document_section'] = target
    selected = st.selectbox(label, numbers, key='document_section',
                            format_func=lambda n: f'{label} {n} из {len(numbers)}')
    before, after = st.columns(2)
    position = numbers.index(selected)
    def move(offset):
        st.session_state['document_section'] = numbers[position + offset]
    before.button('← Предыдущий', disabled=position == 0, on_click=move, args=(-1,))
    after.button('Следующий →', disabled=position == len(numbers) - 1, on_click=move, args=(1,))
    text = dict(document['units'])[selected]
    quote = st.session_state.get('document_quote', '')
    if selected == target and not (0 <= start < end <= len(text)) and quote and quote in text:
        start = text.index(quote)
        end = start + len(quote)
    st.caption('Извлечённый текст. Найденный фрагмент выделен цветом.'
               if selected == target and 0 <= start < end <= len(text) else 'Извлечённый текст документа.')
    fragment = highlighted_text(text, start if selected == target else 0, end if selected == target else 0)
    st.markdown('<div style="white-space:pre-wrap;line-height:1.8;overflow-wrap:anywhere">' + fragment + '</div>',
                unsafe_allow_html=True)
    if kind == 'pdf':
        st.caption('Оригинальная страница PDF')
        try:
            st.image(_page_image(document['raw'], selected), width='stretch')
        except Exception:
            st.warning('Предпросмотр страницы недоступен. Текст показан выше; оригинал можно скачать.')
    else:
        st.caption('Word показан как текст: нумерация относится к абзацам, включая ячейки таблиц, а не к страницам Word.')
        with st.expander('Соседние абзацы'):
            for number, paragraph in document['units'][max(0, position - 3):position + 4]:
                st.caption(f'Абзац {number}')
                st.text(paragraph)
