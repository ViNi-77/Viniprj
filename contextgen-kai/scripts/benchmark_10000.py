#!/usr/bin/env python3
"""独立した一時資料1万件で、実プロセス抽出・差分・検索を測定する。

利用: python scripts/benchmark_10000.py [--count 10000] [--output artifacts/benchmark-10000.json]
原本/保存先とも一時フォルダに作り、実際のJobManager経由で試験する。
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import multiprocessing
from pathlib import Path
import platform
import signal
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contextgen_kai import __version__
from contextgen_kai.jobs import ExtractionWorker, JobManager
from contextgen_kai.storage import Store


def peak_rss_bytes(children=False):
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_CHILDREN if children else resource.RUSAGE_SELF)
        return int(usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024))
    except ImportError:
        return None


def measure(count=10000):
    report = {
        "application_version": __version__,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "environment": {"os": platform.platform(), "python": platform.python_version(), "machine": platform.machine()},
        "document_count": count,
        "method": "Temporary unique UTF-8 text documents; actual JobManager and spawned extraction worker; no existing user sources touched.",
        "baseline_peak_rss_bytes": peak_rss_bytes(),
        "scenarios": [],
    }
    with tempfile.TemporaryDirectory(prefix="contextgen-kai-10000-") as temp:
        root = Path(temp)
        sources = root / "日本語 資料"
        sources.mkdir()
        generation_start = time.perf_counter()
        source_bytes = 0
        for number in range(count):
            # 100ファイルずつ分け、大量の単一ディレクトリも全本文読込も不要にする。
            folder = sources / f"group-{number // 100:03d}"
            folder.mkdir(exist_ok=True)
            path = folder / f"資料 {number:05d}.txt"
            payload = f"資料番号 {number:05d}\nunique-token-{number:05d}\n" + "設備の点検記録。工程、原因、対策、確認結果を記録します。\n" * 8
            source_bytes += path.write_bytes(payload.encode("utf-8"))
        report["input_generation_seconds"] = round(time.perf_counter() - generation_start, 3)
        report["source_bytes"] = source_bytes
        store = Store(root / "state")
        library = store.add_library("1万件受入試験", str(sources))
        manager = JobManager(store, use_process=True)
        interrupted = False

        def request_stop(signum, frame):
            # Thread.join中に例外を投げるとPythonの状態が不整合になるため協調停止する。
            nonlocal interrupted
            interrupted = True
            for event in list(manager.stops.values()):
                event.set()

        previous_sigint = signal.signal(signal.SIGINT, request_stop)
        original_extract = ExtractionWorker.extract
        extraction_calls = 0

        def counted_extract(worker, path, *args, **kwargs):
            nonlocal extraction_calls
            extraction_calls += 1
            return original_extract(worker, path, *args, **kwargs)

        ExtractionWorker.extract = counted_extract

        def run_scenario(name, expected_extractions):
            nonlocal extraction_calls
            extraction_calls = 0
            start = time.perf_counter()
            job = manager.start(library["id"])
            last_update = start
            while True:
                final = manager.wait(job["id"], timeout=1)
                current = time.perf_counter()
                if final["state"] not in {"queued", "scanning", "extracting", "exporting"}:
                    break
                if current - start > 900:
                    manager.stop(job["id"])
                    raise RuntimeError(f"{name}: exceeded 900-second limit")
                if current - last_update >= 20:
                    print(f"{name}: {final['processed']:,}/{final['total']:,} ({current-start:.1f}s)", flush=True)
                    last_update = current
            elapsed = time.perf_counter() - start
            if interrupted:
                raise KeyboardInterrupt("Benchmark stopped after worker shutdown")
            assert final["state"] == "completed", final
            assert final["processed"] == final["total"] == count, final
            assert final["errors"] == 0, final
            assert extraction_calls == expected_extractions, (name, extraction_calls, expected_extractions)
            scenario = {
                "name": name, "elapsed_seconds": round(elapsed, 3),
                "processed": final["processed"], "total": final["total"], "errors": final["errors"],
                "extractor_calls": extraction_calls, "expected_extractor_calls": expected_extractions,
                "throughput_files_per_second": round(count / elapsed, 1),
                "parent_peak_rss_bytes": peak_rss_bytes(), "completed_worker_peak_rss_bytes": peak_rss_bytes(children=True),
            }
            report["scenarios"].append(scenario)
            print(json.dumps(scenario, ensure_ascii=False), flush=True)

        try:
            run_scenario("initial_scan", count)
            assert store.counts()["total"] == count
            # ハッシュのみを収集する。全資料の本文をPythonリストへ読み込まない。
            before = {r["relative_path"]: r["source_hash"] for r in store.all("SELECT relative_path,source_hash FROM documents WHERE active=1")}
            run_scenario("unchanged_scan", 0)
            change_count = min(20, count)
            for number in range(change_count):
                path = sources / f"group-{number // 100:03d}" / f"資料 {number:05d}.txt"
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(f"\n変更確認 {number}: 最新の点検結果を追記しました。\n")
            run_scenario("twenty_changed_files", change_count)
            after = {r["relative_path"]: r["source_hash"] for r in store.all("SELECT relative_path,source_hash FROM documents WHERE active=1")}
            changed = [name for name, value in before.items() if after[name] != value]
            assert len(changed) == change_count, len(changed)
            report["changed_source_hash_count"] = len(changed)
            timings = []
            for index in range(40):
                number = (index * 251) % count
                start = time.perf_counter()
                result = store.list_documents(library["id"], query=f"unique-token-{number:05d}", offset=0, limit=50)
                timings.append(time.perf_counter() - start)
                assert result["total"] == 1 and len(result["items"]) == 1
                assert "original_text" not in result["items"][0]
            page_timings = []
            for offset in [0, count // 2, max(0, count - 50)]:
                start = time.perf_counter()
                page = store.list_documents(library["id"], offset=offset, limit=50)
                page_timings.append(time.perf_counter() - start)
                assert page["total"] == count and len(page["items"]) <= 50
            report["search"] = {
                "queries": len(timings), "median_seconds": round(statistics.median(timings), 6),
                "p95_seconds": round(sorted(timings)[int(len(timings) * .95) - 1], 6),
                "max_seconds": round(max(timings), 6),
                "paged_listing_max_seconds": round(max(page_timings), 6),
                "all_queries_found_exactly_one": True, "list_response_omits_document_body": True,
            }
            report["sqlite_file_bytes"] = store.db_path.stat().st_size
            report["parent_peak_rss_bytes"] = peak_rss_bytes()
            report["completed_worker_peak_rss_bytes"] = peak_rss_bytes(children=True)
            report["passed"] = True
            report["limits"] = [
                "Generated text corpus; does not measure OCR-heavy or large Office/PDF corpora.",
                "Peak RSS is the process high-water mark, not a claim of constant memory for every document type.",
                "macOS/Linux resource API gives parent and completed-child peaks separately; they must not be added as simultaneous usage.",
                "No Windows target-device acceptance is implied by this benchmark.",
            ]
        finally:
            ExtractionWorker.extract = original_extract
            manager.close()
            signal.signal(signal.SIGINT, previous_sigint)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10000)
    parser.add_argument("--output", type=Path, default=Path("artifacts/benchmark-10000.json"))
    args = parser.parse_args()
    if args.count < 20:
        parser.error("count must be at least 20")
    try:
        result = measure(args.count)
    except KeyboardInterrupt:
        print("Benchmark stopped; previous report was not replaced.", file=sys.stderr)
        raise SystemExit(130)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {args.output.resolve()}", flush=True)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
