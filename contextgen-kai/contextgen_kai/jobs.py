"""差分走査と抽出ジョブ。処理済み一覧を保存し、停止・再開を可能にする。"""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import threading
import time
from pathlib import Path

from .storage import Store, identifier, now

ACTIVE = ("queued", "scanning", "extracting", "exporting")


class ProcessLock:
    """UIとWindows予約プロセスが同時に原本・出力を処理しないためのOSロック。"""
    def __init__(self, root: Path):
        self.path = root / "processing.lock"
        self.file = None

    def acquire(self) -> bool:
        self.file = self.path.open("a+b")
        try:
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt
                if self.path.stat().st_size == 0:
                    self.file.write(b"0")
                    self.file.flush()
                    self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            self.file.close()
            self.file = None
            return False

    def release(self):
        if self.file:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            self.file.close()
            self.file = None


def _extract_loop(connection):
    """解析は別プロセス。壊れたライブラリの停止にも画面が巻き込まれない。"""
    from .extractors import extract_document
    try:
        while True:
            message = connection.recv()
            if message is None:
                return
            try:
                result = extract_document(Path(message), ocr=True, max_pages=500, timeout=60)
                connection.send(result.as_dict())
            except Exception as exc:
                connection.send(dict(text="", status="error", warnings=[f"解析に失敗しました: {type(exc).__name__}"], units=[], metadata={}))
    except (EOFError, BrokenPipeError):
        return
    finally:
        connection.close()


class ExtractionWorker:
    def __init__(self, stop_event: threading.Event, check_stop=None):
        self.stop_event = stop_event
        self.check_stop = check_stop
        self.process = None
        self.connection = None

    def extract(self, path: Path, timeout=180):
        if self.process is None:
            ctx = multiprocessing.get_context("spawn")
            self.connection, child = ctx.Pipe()
            self.process = ctx.Process(target=_extract_loop, args=(child,), daemon=True)
            self.process.start()
            child.close()
        self.connection.send(str(path))
        start = time.monotonic()
        last_check = start
        while not self.connection.poll(0.15):
            if self.check_stop and time.monotonic() - last_check >= 1:
                self.check_stop()
                last_check = time.monotonic()
            if self.stop_event.is_set():
                self.close()
                raise InterruptedError("利用者が停止しました")
            if time.monotonic() - start > timeout or not self.process.is_alive():
                self.close()
                return dict(text="", status="error", warnings=["解析が制限時間内に完了しませんでした。資料を分割して再実行してください"], units=[], metadata={})
        try:
            return self.connection.recv()
        except EOFError:
            self.close()
            return dict(text="", status="error", warnings=["解析プロセスが終了しました"], units=[], metadata={})

    def close(self):
        if self.process:
            if self.process.is_alive():
                try:
                    self.connection.send(None)
                except (BrokenPipeError, OSError):
                    pass
                self.process.join(timeout=0.3)
                if self.process.is_alive():
                    self.process.terminate()
                    self.process.join(timeout=2)
            self.connection.close()
            self.process = self.connection = None


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class JobManager:
    def __init__(self, store: Store, use_process=True):
        self.store = store
        self.use_process = use_process
        self.stops: dict[str, threading.Event] = {}
        self.threads: dict[str, threading.Thread] = {}
        self.thread_lock = threading.Lock()
        self.complete_callback = None
        lock = ProcessLock(store.root)
        if lock.acquire():
            try:
                from .scheduling import _process_alive
                for previous in store.all("SELECT id,state,owner_pid FROM jobs WHERE state IN ('queued','scanning','extracting','exporting')"):
                    if previous["state"] != "queued" or not _process_alive(previous["owner_pid"]):
                        store.update_job(previous["id"], state="stopped", message="前回の実行が中断しました。再開できます")
            finally:
                lock.release()

    def list(self):
        return self.store.all("SELECT id,library_id,kind,state,stage,processed,total,errors,message,created_at,updated_at,export_id FROM jobs ORDER BY created_at DESC,rowid DESC LIMIT 100")

    def start(self, library_id: str, *, collection_id=None, export_after=False, kind="scan", force=False, schedule_id=None, refresh_sources=False, document_id=None, force_extract=False):
        if not self.store.one("SELECT id FROM libraries WHERE id=?", (library_id,)):
            raise ValueError("登録フォルダが見つかりません")
        payload = dict(collection_id=collection_id, export_after=export_after, force=force, schedule_id=schedule_id, refresh_sources=refresh_sources, document_id=document_id, force_extract=force_extract)
        job_id = identifier()
        self.store.execute("INSERT INTO jobs(id,library_id,kind,created_at,updated_at,payload,owner_pid) VALUES (?,?,?,?,?,?,?)", (job_id, library_id, kind, now(), now(), json.dumps(payload), os.getpid()))
        self._launch(job_id)
        return self.store.one("SELECT * FROM jobs WHERE id=?", (job_id,))

    def _launch(self, job_id):
        with self.thread_lock:
            if job_id in self.threads and self.threads[job_id].is_alive():
                return
            event = threading.Event()
            self.stops[job_id] = event
            thread = threading.Thread(target=self._run, args=(job_id, event), daemon=True)
            self.threads[job_id] = thread
            thread.start()

    def stop(self, job_id):
        if job_id in self.stops:
            self.stops[job_id].set()
        # 別プロセスのジョブにも停止要求が届くよう永続化する。
        self.store.execute("UPDATE jobs SET message='停止要求',updated_at=? WHERE id=? AND state IN ('queued','scanning','extracting','exporting')", (now(), job_id))

    def resume(self, job_id):
        job = self.store.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not job or job["state"] not in ("stopped", "failed"):
            raise ValueError("停止または失敗した実行だけ再開できます")
        with self.thread_lock:
            if job_id in self.threads and self.threads[job_id].is_alive():
                raise ValueError("停止処理が終わるまでお待ちください")
        self.store.update_job(job_id, state="queued", message="再開待ち")
        self._launch(job_id)
        return self.store.one("SELECT * FROM jobs WHERE id=?", (job_id,))

    def wait(self, job_id, timeout=120):
        thread = self.threads.get(job_id)
        if thread:
            thread.join(timeout)
        return self.store.one("SELECT * FROM jobs WHERE id=?", (job_id,))

    def close(self):
        for event in list(self.stops.values()):
            event.set()
        for thread in list(self.threads.values()):
            thread.join(timeout=3)

    def _check_stop(self, job_id, event):
        if event.is_set():
            raise InterruptedError("利用者が停止しました")
        job = self.store.one("SELECT message FROM jobs WHERE id=?", (job_id,))
        if job and job["message"] == "停止要求":
            event.set()
            raise InterruptedError("利用者が停止しました")

    def _run(self, job_id, event):
        lock = ProcessLock(self.store.root)
        payload = {}
        try:
            job = self.store.one("SELECT * FROM jobs WHERE id=?", (job_id,))
            payload = json.loads(job["payload"])
            while not lock.acquire():
                self._check_stop(job_id, event)
                event.wait(0.3)
            self._check_stop(job_id, event)
            job = self.store.one("SELECT * FROM jobs WHERE id=?", (job_id,))
            self.store.update_job(job_id, owner_pid=os.getpid())
            if job["kind"] == "scan":
                self._scan(job, event, verify_hash=bool(payload.get("export_after")))
            elif job["kind"] == "export" and payload.get("refresh_sources"):
                collection = self.store.collection(payload["collection_id"])
                for lib_id in collection["library_ids"]:
                    self._check_stop(job_id, event)
                    # 再開時も全登録元を再走査するが、完了した抽出は内容hashで再利用する。
                    self.store.update_job(job_id, scan_complete=0, errors=0, processed=0, total=0)
                    self._scan({**job, "library_id": lib_id, "scan_complete": 0}, event, verify_hash=True)
            if job["kind"] == "export" or payload.get("export_after"):
                from .exporting import build_export
                self._check_stop(job_id, event)
                self.store.update_job(job_id, state="exporting", stage="用途別ファイルを生成")
                result = build_export(self.store, payload["collection_id"], force=payload.get("force", False),
                                      verify_sources=True,
                                      cancelled=lambda: self._check_stop(job_id, event))
                self.store.update_job(job_id, state="held" if result["state"] == "held" else "completed", stage="出力完了", export_id=result["id"], message=result["reason"] or "Copilot用ファイルを生成しました")
            else:
                self.store.update_job(job_id, state="completed", stage="読み取り完了", message="資料の確認画面で結果を確認できます")
        except InterruptedError:
            self.store.update_job(job_id, state="stopped", message="停止しました。処理済みの資料を保持しています")
        except Exception as exc:
            self.store.update_job(job_id, state="failed", message=f"{type(exc).__name__}: {str(exc)[:400]}")
        finally:
            lock.release()
            if payload.get("schedule_id") and self.complete_callback:
                job = self.store.one("SELECT * FROM jobs WHERE id=?", (job_id,))
                self.complete_callback(payload["schedule_id"], job_id, job["state"], job["message"] if job["state"] in ("failed", "held") else "")

    def _scan(self, job, event, verify_hash=False):
        from . import extractors
        from .extractors import SUPPORTED_EXTENSIONS, extract_document
        version = getattr(extractors, "EXTRACTOR_VERSION", "2")
        ocr = extractors.tesseract_path()
        engine = str(ocr or "unavailable") + ":" + os.environ.get("CONTEXTGEN_OCR_LANG", "jpn+eng") + ":" + os.environ.get("TESSDATA_PREFIX", "")
        if ocr:
            data_root = Path(os.environ.get("TESSDATA_PREFIX") or Path(ocr).parent / "tessdata")
            for component in [Path(ocr), *(data_root / (lang + ".traineddata") for lang in os.environ.get("CONTEXTGEN_OCR_LANG", "jpn+eng").split("+"))]:
                try:
                    st = component.stat()
                    engine += f":{st.st_size}:{st.st_mtime_ns}"
                except OSError:
                    engine += ":missing"
        signature = str(version) + ":" + engine
        payload = json.loads(job["payload"])
        library = self.store.one("SELECT * FROM libraries WHERE id=?", (job["library_id"],))
        root = Path(library["path"]).resolve()
        if not root.is_dir():
            raise ValueError("参照元フォルダが見つかりません。前回データを保持しています")
        if not job["scan_complete"] and payload.get("document_id"):
            doc = self.store.document(payload["document_id"])
            if not doc or doc["library_id"] != library["id"]:
                raise ValueError("再読み取りする資料が見つかりません")
            self.store.execute("DELETE FROM job_files WHERE job_id=?", (job["id"],))
            self.store.execute("INSERT INTO job_files(job_id,relative_path,source_path,size,mtime_ns) VALUES(?,?,?,?,?)", (job["id"], doc["relative_path"], str(root / doc["relative_path"]), doc["size"], doc["mtime_ns"]))
            self.store.update_job(job["id"], scan_complete=1, total=1)
        elif not job["scan_complete"]:
            self.store.update_job(job["id"], state="scanning", stage=f"資料を探しています: {library['name']}", processed=0, total=0)
            # 途中の走査結果は作り直すが、文書抽出キャッシュは保持する。
            self.store.execute("DELETE FROM job_files WHERE job_id=?", (job["id"],))
            stack = [root]
            visited = set()
            found = 0
            while stack:
                self._check_stop(job["id"], event)
                folder = stack.pop()
                resolved = folder.resolve()
                if resolved in visited or not resolved.is_relative_to(root):
                    continue
                visited.add(resolved)
                rows = []
                with os.scandir(folder) as entries:
                    for entry in entries:
                        if entry.name.startswith(("~$", ".~")) or entry.is_symlink():
                            continue
                        path = Path(entry.path)
                        if entry.is_dir(follow_symlinks=False):
                            if path.name not in (".git", ".venv", "__pycache__") and path.resolve() != self.store.root and not path.is_junction():
                                stack.append(path)
                        elif entry.is_file(follow_symlinks=False) and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                            st = entry.stat(follow_symlinks=False)
                            cloud = bool(getattr(st, "st_file_attributes", 0) & (0x1000 | 0x40000 | 0x400000))
                            rows.append((job["id"], path.relative_to(root).as_posix(), str(path), st.st_size, st.st_mtime_ns, int(cloud)))
                with self.store.connect() as con:
                    con.executemany("INSERT INTO job_files(job_id,relative_path,source_path,size,mtime_ns,cloud_only) VALUES(?,?,?,?,?,?)", rows)
                found += len(rows)
                self.store.update_job(job["id"], total=found, message=f"{found:,}件見つかりました（走査中）")
            self.store.update_job(job["id"], scan_complete=1)
            # フォルダ全体の走査成功後だけ消えた資料を無効化する。
            self.store.execute("UPDATE documents SET active=0 WHERE library_id=? AND relative_path NOT IN (SELECT relative_path FROM job_files WHERE job_id=?)", (library["id"], job["id"]))
        self.store.update_job(job["id"], state="extracting", stage=f"本文と出典を読み取り: {library['name']}")
        worker = ExtractionWorker(event, lambda: self._check_stop(job["id"], event)) if self.use_process else None
        done = self.store.one("SELECT count(*) n FROM job_files WHERE job_id=? AND processed=1", (job["id"],))["n"]
        errors = self.store.one("SELECT errors FROM jobs WHERE id=?", (job["id"],))["errors"]
        pending = []

        def flush_progress():
            if not pending:
                return
            with self.store.connect() as con:
                con.executemany("UPDATE documents SET active=1,source_path=? WHERE library_id=? AND relative_path=?", [(str(p["source_path"]), library["id"], p["relative_path"]) for p in pending])
                con.executemany("UPDATE job_files SET processed=1 WHERE job_id=? AND relative_path=?", [(job["id"], p["relative_path"]) for p in pending])
                con.execute("UPDATE jobs SET processed=?,errors=?,message=?,updated_at=? WHERE id=?", (done, errors, pending[-1]["relative_path"], now(), job["id"]))
            pending.clear()

        try:
            while True:
                self._check_stop(job["id"], event)
                rows = self.store.all("SELECT f.*,d.id old_id,d.size old_size,d.mtime_ns old_mtime_ns,d.source_hash old_hash,d.status old_status,d.metadata old_metadata FROM job_files f LEFT JOIN documents d ON d.library_id=? AND d.relative_path=f.relative_path WHERE f.job_id=? AND f.processed=0 ORDER BY f.relative_path LIMIT 50", (library["id"], job["id"]))
                if not rows:
                    break
                for item in rows:
                    if event.is_set():
                        raise InterruptedError("利用者が停止しました")
                    path = Path(item["source_path"])
                    old = dict(size=item["old_size"], mtime_ns=item["old_mtime_ns"], source_hash=item["old_hash"], status=item["old_status"], metadata=item["old_metadata"]) if item["old_id"] else None
                    extracted = {}
                    try:
                        if path.is_symlink() or not path.resolve().is_relative_to(root):
                            raise ValueError("原本の場所が登録フォルダ外へ変わりました")
                        stat = path.stat()
                        cloud = bool(getattr(stat, "st_file_attributes", 0) & (0x1000 | 0x40000 | 0x400000))
                        if cloud:
                            extracted = dict(text="", status="needs_download", warnings=["クラウド上のみの資料です。端末に取得してから再実行してください"], units=[], metadata={})
                            sha = old["source_hash"] if old else ""
                        elif (not verify_hash and not payload.get("force_extract") and old and old["size"] == stat.st_size and old["mtime_ns"] == stat.st_mtime_ns and old["status"] in ("ok", "empty", "partial") and not json.loads(old["metadata"]).get("retryable") and json.loads(old["metadata"]).get("extractor_signature") == signature):
                            extracted = None
                        else:
                            self._check_stop(job["id"], event)
                            sha = file_hash(path)
                            if (not payload.get("force_extract") and old and old["source_hash"] == sha and old["status"] in ("ok", "empty", "partial") and not json.loads(old["metadata"]).get("retryable") and json.loads(old["metadata"]).get("extractor_signature") == signature):
                                extracted = None
                                self.store.execute("UPDATE documents SET size=?,mtime_ns=? WHERE id=?", (stat.st_size, stat.st_mtime_ns, item["old_id"]))
                            else:
                                extracted = worker.extract(path) if worker else extract_document(path, ocr=True, max_pages=500, timeout=60).as_dict()
                            after = path.stat()
                            if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                                extracted = dict(text="", status="error", warnings=["読み取り中に原本が変わりました。再実行してください"], units=[], metadata={})
                        if extracted is not None:
                            extracted.setdefault("metadata", {}).update(extractor_version=version, extractor_signature=signature)
                            self.store.upsert_extraction(library["id"], item["relative_path"], path, stat.st_size, stat.st_mtime_ns, sha, extracted)
                            errors += int(extracted["status"] not in ("ok", "empty"))
                    except InterruptedError:
                        raise
                    except Exception as exc:
                        errors += 1
                        self.store.upsert_extraction(library["id"], item["relative_path"], path, item["size"], item["mtime_ns"], old["source_hash"] if old else "", dict(text="", status="error", warnings=[f"読み取り不能: {type(exc).__name__}"], units=[]))
                    done += 1
                    pending.append(item)
                    # 抽出した資料は即保存し、キャッシュ利用分だけ最大50件をまとめる。
                    if extracted is not None:
                        flush_progress()
                flush_progress()
        finally:
            flush_progress()
            if worker:
                worker.close()
