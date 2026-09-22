# 実装境界（0.1.0）

旧2プロジェクトは編集禁止。アプリは `contextgen_kai` パッケージで完結。

## Extractors
`extractors.py`: `extract_document(path: Path, *, ocr=True, max_pages=500, timeout=60) -> Extraction`。
`Extraction`: `text: str`, `status: str` (ok/partial/empty/error/protected/needs_conversion/needs_ocr), `warnings: list[str]`, `units: list[dict]` (locator,text,status), `metadata: dict`。`as_dict()` 提供。副作用は一時領域のみ。OS外部通信なし。OCRは同梱Tesseract/環境指定を利用。

## Scheduling
`scheduling.py`: `Scheduler(state_dir: Path, callback: Callable[[dict], str])`。
`list() -> list[dict]`, `save(data: dict) -> dict`, `delete(id)`, `run_now(id) -> str`, `tick(now=None)`, `start()`, `stop()`。
予約: id,name,library_id,collection_id(optional),enabled,mode(app/background),frequency(daily/weekly/interval),time(HH:MM),weekdays([0..6]),interval_minutes,next_run,last_run,last_result,last_error。
callback receives schedule dict, starts root-owned job and returns job_id. Headless CLI `--run-schedule ID --state-dir PATH` is root owned; provide `run_reserved(id)` for headless runner, claim same occurrence across processes. Scheduler owns separate schedules.sqlite3 under state_dir. callback completion root reports `complete(id, job_id, status, error='')`. UI does not register real tasks except user save. Windows scheduler uses this EXE command; source uses python -m contextgen_kai. No app's other tasks modified. JSON backup `restore(items)` must restore reservations disabled, no OS registration.

## HTTP / UI contract
JSON errors `{detail: string}`. Every mutation requires `X-Contextgen-Token` from GET `/api/status` (`token` field); server checks Origin/Host. Use fetch credentials same-origin. GET status: `{version,token,libraries,collections,counts:{total,ok,attention,excluded},jobs,schedules}`. Lists also separately available.
`POST /api/libraries {name,path}`; `PUT /api/libraries/{id} {name,path}` (実行中の移動不可、移動後に再抽出); `DELETE /api/libraries/{id}` unregisters only (no source deletion).
`POST /api/pick-folder {}` -> `{path}` native picker.
`POST /api/uploads` multipart `files` list, optional `name` -> library.
`POST /api/jobs {library_id,collection_id:null,export_after:false}` -> job.
`POST /api/jobs/{id}/stop`, `/resume`; `GET /api/jobs` -> array.
job: id,library_id,state(queued/scanning/extracting/exporting/completed/held/failed/stopped),stage,processed,total,errors,message,created_at,updated_at,export_id.
`GET /api/documents?library_id=&q=&status=&offset=0&limit=50` -> `{items,total}`.
Document list: id,library_id,relative_path,status,excluded,conflict,updated_at,warning_count.
`GET /api/documents/{id}` adds original_text,effective_text,edited_text,source_hash,warnings,units.
`PUT /api/documents/{id} {excluded?:bool,text?:str|null,expected_hash?:str}`. text null discards edits; text requires expected_hash and acknowledges current original. `POST /api/documents/{id}/open`; `GET /api/documents/{id}/preview` serves registered PDF/image only.
`GET /api/collections` -> array; `POST /api/collections`, `PUT /api/collections/{id}` body `{name,library_id,query:'',folder:'',document_ids:[],purpose:'overview'|'compare'|'questions',instructions:''}`.
`POST /api/exports {collection_id,force:false}` -> job; `GET /api/exports` -> array `{id,collection_id,state,created_at,document_count,chunk_count,reason,is_active}`.
`GET /api/exports/{id}/download`; `POST /api/exports/{id}/activate {}` for explicit held-generation confirmation; `POST /api/exports/{id}/open`; `GET /api/exports/{id}/prompt` -> `{text}`.
`GET /api/schedules` -> array; `POST /api/schedules`, `PUT /api/schedules/{id}` schedule body above; `DELETE /api/schedules/{id}`; `POST /api/schedules/{id}/run` -> `{job_id}`.
`GET /api/backup` -> downloadable JSON; `POST /api/restore` multipart `file`, restore only into empty workspace, schedules disabled.
`POST /api/shutdown {}` requests graceful shutdown; GET `/api/health`, `/api/version` available.

## Runtime / packaging
Entry `python -m contextgen_kai [--state-dir PATH] [--port 8766] [--no-browser] [--run-schedule ID]`. launch.py at project root calls main after freeze_support. Resource lookup from package `static/`, OCR directory relative bundled EXE `ocr/` or CONTEXTGEN_TESSERACT env path. Runtime version contextgen_kai.__version__ = 0.1.0 until actual Windows acceptance. Dependencies root owned pyproject.toml. Build packages onedir, tests excluded, Japanese+English tessdata included, NOTICE files bundled. CI `.github/workflows/contextgen-kai.yml` only new app.
