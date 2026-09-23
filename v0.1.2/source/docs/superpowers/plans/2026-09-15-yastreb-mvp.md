# «Ястреб» MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Создать запускаемый локальный Streamlit-MVP RAG-системы «Ястреб» с PDF-индексацией, ChromaDB, Ollama, ролевым доступом и источниками ответов.

**Architecture:** Приложение разделено на конфигурацию/модели, локальную авторизацию, PDF-индексацию, векторное хранилище, retrieval/RAG-сервис и Streamlit UI. Каждый слой имеет тестируемый интерфейс и не обращается к Интернету; UI вызывает сервисы, но не реализует правила доступа или индексации самостоятельно.

**Tech Stack:** Python 3.10+, Streamlit, `langchain-core`, `langchain-community`, `langchain-chroma`, `langchain-ollama`, `chromadb`, `sentence-transformers`, `pypdf`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-15-yastreb-mvp-design.md`

## Global Constraints

- Рабочий режим: 100% Offline; внешние API и Интернет из приложения запрещены.
- PDF чанкинг: размер 1000 символов, overlap 200 символов.
- Retrieval: Top-3 наиболее релевантных чанка.
- Метаданные каждого чанка: имя файла и номер страницы; для цитаты сохраняется исходный текст чанка.
- LLM: Ollama, модель задаётся конфигурацией, по умолчанию `qwen2.5:7b`.
- Embeddings: локальная sentence-transformers модель, по умолчанию `BAAI/bge-m3`.
- Доступ к изменению библиотеки проверяется серверной логикой, а не только UI.
- Production-загрузка файлов требует подтверждающего флажка и роли `admin` или `branch_head`.
- Нельзя активировать частично построенную векторную коллекцию.

---

## File Map

- Create: `pyproject.toml` — зависимости, pytest и команды запуска.
- Create: `.env.example` — только безопасные локальные настройки.
- Create: `.gitignore` — исключения для окружения, данных, Chroma и секретов.
- Create: `README.md` — offline-установка, Ollama, запуск, роли и тестирование.
- Create: `src/yastreb/config.py` — типизированная конфигурация и пути.
- Create: `src/yastreb/models.py` — `Role`, `User`, `ChunkSource`, `Answer`.
- Create: `src/yastreb/auth.py` — получение пользователя и проверка прав.
- Create: `src/yastreb/ingest.py` — PDF, SHA-256, чанкинг и manifest.
- Create: `src/yastreb/store.py` — ChromaDB lifecycle и локальные embeddings.
- Create: `src/yastreb/rag.py` — retriever, prompt, Ollama и форматирование источников.
- Create: `src/yastreb/ui.py` — функции рендеринга Streamlit.
- Create: `app.py` — composition root и session state.
- Create: `config/users.yaml` — пример локальной карты корпоративных пользователей.
- Create: `tests/test_auth.py`, `tests/test_ingest.py`, `tests/test_rag.py`, `tests/test_store.py`, `tests/test_ui_policy.py` — поведенческие тесты.
- Create: `tests/fixtures/sample.pdf` — маленький текстовый PDF для offline-тестов.

### Task 1: Bootstrap and project configuration

**Files:**
- Create: `pyproject.toml`, `.env.example`, `.gitignore`, `config/users.yaml`.
- Test: `tests/test_config.py`.

**Interfaces:** `Settings.from_env() -> Settings`; `Settings.documents_dir`, `Settings.chroma_dir`, `Settings.embedding_model`, `Settings.ollama_model`, `Settings.chunk_size == 1000`, `Settings.chunk_overlap == 200`, `Settings.top_k == 3`.

- [ ] **Step 1: Write the failing test**

```python
def test_default_settings_match_mvp_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("YASTREB_DATA_DIR", str(tmp_path))
    from yastreb.config import Settings
    settings = Settings.from_env()
    assert settings.chunk_size == 1000
    assert settings.chunk_overlap == 200
    assert settings.top_k == 3
    assert settings.chroma_dir == tmp_path / "chroma"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py::test_default_settings_match_mvp_contract -q`

Expected: FAIL because `yastreb.config` and `Settings` do not exist.

- [ ] **Step 3: Write minimal implementation**

Implement `Settings` as a frozen dataclass. Read `YASTREB_DATA_DIR`, `YASTREB_EMBEDDING_MODEL`, `YASTREB_OLLAMA_MODEL`, and `YASTREB_AUTH_MODE`; create no data directories during import.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py::test_default_settings_match_mvp_contract -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example .gitignore config/users.yaml src/yastreb/config.py tests/test_config.py
git commit -m "chore: bootstrap yastreb configuration"
```

### Task 2: Role-aware local authentication

**Files:**
- Create: `src/yastreb/models.py`, `src/yastreb/auth.py`.
- Test: `tests/test_auth.py`.

**Interfaces:** `Role` values `admin`, `branch_head`, `worker`; `User(email, display_name, role)`; `AuthProvider.current_user(headers: Mapping[str, str], demo_user: str | None) -> User`; `can_manage_library(user: User) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
def test_branch_head_can_manage_library():
    from yastreb.auth import can_manage_library
    from yastreb.models import Role, User
    assert can_manage_library(User("head@company.local", "Head", Role.BRANCH_HEAD)) is True

def test_worker_cannot_manage_library():
    from yastreb.auth import can_manage_library
    from yastreb.models import Role, User
    assert can_manage_library(User("worker@company.local", "Worker", Role.WORKER)) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auth.py -q`

Expected: FAIL because the role model and authorization function do not exist.

- [ ] **Step 3: Write minimal implementation**

Load the local YAML map by email. In network mode, accept only `REMOTE_USER` or `X-Forwarded-User` from the configured trusted proxy header. Raise `AuthenticationError` when no mapped user exists. Keep `demo_user` behind `YASTREB_AUTH_MODE=demo`.

- [ ] **Step 4: Add header and demo-mode tests, then run them**

Test that a mapped header returns the configured user and that an unknown email is rejected. Run: `python -m pytest tests/test_auth.py -q`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/yastreb/models.py src/yastreb/auth.py tests/test_auth.py config/users.yaml
git commit -m "feat: add local role-based authorization"
```

### Task 3: PDF ingestion, metadata, deduplication, and chunking

**Files:**
- Create: `src/yastreb/ingest.py`, `tests/fixtures/sample.pdf`.
- Test: `tests/test_ingest.py`.

**Interfaces:** `PdfIndexer.index_file(path: Path) -> list[DocumentChunk]`; `DocumentChunk(text: str, source: str, page: int, file_hash: str)`; `sha256_file(path: Path) -> str`; `Manifest.is_indexed(file_hash: str) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
def test_pdf_chunks_keep_source_and_one_based_page(tmp_path):
    from yastreb.ingest import PdfIndexer
    chunks = PdfIndexer(chunk_size=1000, chunk_overlap=200).index_file(tmp_path / "sample.pdf")
    assert chunks
    assert chunks[0].source == "sample.pdf"
    assert chunks[0].page == 1
    assert chunks[0].text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ingest.py::test_pdf_chunks_keep_source_and_one_based_page -q`

Expected: FAIL because `PdfIndexer` does not exist.

- [ ] **Step 3: Write minimal implementation**

Use `PyPDFLoader`/`pypdf` to extract per-page text, attach one-based page metadata, apply `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)`, and compute SHA-256 before indexing.

- [ ] **Step 4: Add rejection tests and run them**

Cover non-PDF extension, empty/scanned page text, duplicate hash, and preservation of `source`/`page`. Run: `python -m pytest tests/test_ingest.py -q`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/yastreb/ingest.py tests/test_ingest.py tests/fixtures/sample.pdf
git commit -m "feat: index text PDFs with page metadata"
```

### Task 4: ChromaDB storage and safe reindexing

**Files:**
- Create: `src/yastreb/store.py`.
- Test: `tests/test_store.py`.

**Interfaces:** `VectorStore.add(chunks: Sequence[DocumentChunk]) -> int`; `VectorStore.search(query: str, k: int = 3) -> list[DocumentChunk]`; `VectorStore.rebuild(chunks: Sequence[DocumentChunk]) -> int`; `VectorStore.count() -> int`.

- [ ] **Step 1: Write the failing tests**

```python
def test_rebuild_does_not_replace_active_collection_on_failure(tmp_path):
    from yastreb.store import VectorStore
    store = VectorStore(tmp_path, embedding_model="test-hash-embeddings")
    store.add([chunk("old", "old.pdf", 1)])
    try:
        store.rebuild([chunk("new", "new.pdf", 1)], fail_after=0)
    except RuntimeError:
        pass
    assert store.count() == 1
    assert store.search("old", k=3)[0].source == "old.pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_store.py::test_rebuild_does_not_replace_active_collection_on_failure -q`

Expected: FAIL because the store lifecycle does not exist.

- [ ] **Step 3: Write minimal implementation**

Use `langchain_chroma.Chroma` with `persist_directory`. Inject an embeddings implementation so tests use a deterministic local test embedding while production uses `HuggingFaceEmbeddings`. Build under a temporary collection/path and atomically promote only after all chunks are written.

- [ ] **Step 4: Add Top-3 and metadata tests, then run them**

Run: `python -m pytest tests/test_store.py -q`. Expected: PASS and exactly three results when at least three indexed chunks exist.

- [ ] **Step 5: Commit**

```bash
git add src/yastreb/store.py tests/test_store.py
git commit -m "feat: add persistent chroma vector store"
```

### Task 5: RAG prompt, refusal behavior, and source formatting

**Files:**
- Create: `src/yastreb/rag.py`.
- Test: `tests/test_rag.py`.

**Interfaces:** `RagService.answer(question: str) -> Answer`; `Answer.text`, `Answer.sources`; `format_sources(documents) -> tuple[ChunkSource, ...]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_missing_context_returns_explicit_refusal():
    service = service_with_retriever([])
    answer = service.answer("Вопрос вне документов")
    assert answer.text == "В предоставленных документах ответ не найден"
    assert answer.sources == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rag.py::test_missing_context_returns_explicit_refusal -q`

Expected: FAIL because `RagService` does not exist.

- [ ] **Step 3: Write minimal implementation**

Retrieve Top-3, reject empty/under-threshold context, and call Ollama through an injected chat model. The prompt must contain: `Используй только предоставленный контекст. Если ответа в контексте нет, прямо скажи об этом и не выдумывай факты.` Format each source with filename, one-based page and exact chunk quote.

- [ ] **Step 4: Add prompt/source tests and run them**

Test that context is passed to the model, sources preserve page and quote, and Ollama errors become a user-safe local error. Run: `python -m pytest tests/test_rag.py -q`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/yastreb/rag.py tests/test_rag.py
git commit -m "feat: add grounded rag answers with citations"
```

### Task 6: Streamlit UI and role-gated settings

**Files:**
- Create: `src/yastreb/ui.py`, `app.py`.
- Test: `tests/test_ui_policy.py`.

**Interfaces:** `render_sidebar(user, history, settings)`, `render_settings(user, settings)`, `render_chat(messages)`, and `handle_upload(user, confirmed, files)`; `handle_upload` must raise `PermissionError` for unauthorized roles before touching a file.

- [ ] **Step 1: Write the failing policy tests**

```python
def test_worker_upload_is_rejected_before_file_write(tmp_path):
    from yastreb.auth import can_manage_library
    from yastreb.models import Role, User
    assert can_manage_library(User("w@company.local", "Worker", Role.WORKER)) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_policy.py -q`

Expected: FAIL until the UI policy module and upload handler exist.

- [ ] **Step 3: Write minimal implementation**

Render history on the left, current user and gear at the bottom, and settings as a panel expanding upward inside the sidebar. Put `Внешний вид`, `Внести изменения`, and `Профиль` in the settings panel. Render upload/reindex controls only for `admin` and `branch_head`, while still enforcing the same check in `handle_upload`.

- [ ] **Step 4: Add Streamlit smoke test and run tests**

Use `streamlit.testing.v1.AppTest` to assert the app renders a chat and worker does not receive an upload control. Run: `python -m pytest tests/test_ui_policy.py -q`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/yastreb/ui.py app.py tests/test_ui_policy.py
git commit -m "feat: add streamlit chat and role-gated settings"
```

### Task 7: Offline startup, documentation, and acceptance tests

**Files:**
- Modify: `README.md`, `.env.example`, `pyproject.toml`.
- Create: `tests/test_acceptance.py`, `scripts/run_offline_check.ps1`.

**Interfaces:** `python -m pytest`; `streamlit run app.py`; `scripts/run_offline_check.ps1` exits non-zero when Ollama or the local data paths are unusable.

- [ ] **Step 1: Write the failing acceptance checks**

```python
def test_empty_store_has_safe_refusal(tmp_path):
    from yastreb.rag import RagService
    assert RagService.empty().answer("любой вопрос").text == "В предоставленных документах ответ не найден"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_acceptance.py -q`

Expected: FAIL until composition and empty-store behavior are wired.

- [ ] **Step 3: Write minimal implementation and docs**

Document preloading wheels/models for air-gapped machines, `ollama pull qwen2.5:7b` before disconnection, startup commands, role configuration, upload confirmation, backup of `data/`, and the limitation that scanned PDFs require OCR outside MVP.

- [ ] **Step 4: Run the complete verification set**

Run:

```powershell
python -m pytest -q
python -m compileall src app.py
streamlit run app.py --server.headless true
```

Expected: all tests pass, compilation succeeds, and Streamlit starts without an external network request.

- [ ] **Step 5: Commit**

```bash
git add README.md .env.example pyproject.toml scripts/run_offline_check.ps1 tests/test_acceptance.py
git commit -m "docs: add offline setup and acceptance checks"
```

## Verification Checklist

- [ ] `worker` cannot upload or reindex even if the upload endpoint is called directly.
- [ ] Upload requires the UI confirmation checkbox.
- [ ] Duplicate files are detected by SHA-256.
- [ ] Every source includes file name, one-based page and exact quote.
- [ ] Retrieval returns at most Top-3 chunks.
- [ ] Empty/insufficient context yields the exact refusal text.
- [ ] Failed rebuild leaves the previous active Chroma collection intact.
- [ ] No application code performs HTTP requests to Internet services.
- [ ] Offline setup works with preinstalled wheels and local model caches.
