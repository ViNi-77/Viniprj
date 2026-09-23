"""原本を含まない設定・修正・登録記録のバックアップ。"""
import json
import sqlite3
from pathlib import Path

from .storage import COLLECTION_DEFAULTS, now, validate_identifier, validate_override_bases

MAX_BACKUP_BYTES = 512 * 1024 * 1024


def make_backup(store, scheduler):
    with store.connect() as con:
        con.execute("ATTACH DATABASE ? AS reservations", (str(scheduler.path),))
        con.execute("BEGIN IMMEDIATE")
        collections = []
        for row in con.execute("SELECT c.*,o.settings FROM collections c LEFT JOIN collection_options o ON c.id=o.collection_id"):
            item = dict(row)
            options = json.loads(item.pop("settings") or "{}")
            item["document_ids"] = json.loads(item["document_ids"])
            collections.append({**COLLECTION_DEFAULTS, **item, "library_ids": [item["library_id"]], "selection_mode": "fixed" if item["document_ids"] else "dynamic", **options})
        data = dict(schema_version=2, application="contextgen-kai", created_at=now(),
                    libraries=[dict(r) for r in con.execute("SELECT * FROM libraries")], collections=collections,
                    schedules=[json.loads(r[0]) for r in con.execute("SELECT data FROM reservations.schedules")],
                    documents=[dict(r) for r in con.execute("SELECT id,library_id,relative_path,source_hash,edited_text,edit_base_hash,excluded,revision FROM documents")],
                    edit_history=[dict(r) for r in con.execute("SELECT * FROM edit_history")],
                    handoffs=[dict(r) for r in con.execute("SELECT * FROM handoffs ORDER BY rowid")],
                    note="原本資料・抽出キャッシュ・出力世代は含みません。原本は別に保管してください。復元後は読み取りを実行してください。")
    encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_BACKUP_BYTES:
        raise ValueError("バックアップが512MBを超えています。保存領域のコピーで保管してください")
    return encoded


def restore_backup(store, scheduler, data, collection_model):
    if not isinstance(data, dict) or data.get("application") != "contextgen-kai" or data.get("schema_version") not in (1, 2):
        raise ValueError("対応していないバックアップ形式です")
    roots, collections = {}, {}
    try:
        # 予約DBを同じトランザクションへ参加させ、途中の入力不正で片方だけ復元しない。
        with store.connect() as con:
            con.execute("ATTACH DATABASE ? AS reservations", (str(scheduler.path),))
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT count(*) FROM libraries").fetchone()[0] or con.execute("SELECT count(*) FROM reservations.schedules").fetchone()[0]:
                raise ValueError("復元は登録フォルダのない空の保存領域で実行してください")
            for lib in data.get("libraries", []):
                validate_identifier(lib["id"])
                path = Path(lib["path"]).expanduser().resolve()
                roots[lib["id"]] = path
                con.execute("INSERT INTO libraries VALUES(?,?,?,?,?)", (lib["id"], lib["name"], str(path), lib.get("kind", "folder"), now()))
            doc_libraries = {}
            for doc in data.get("documents", []):
                validate_identifier(doc["id"])
                root = roots[doc["library_id"]]
                path = (root / doc["relative_path"]).resolve()
                if root not in path.parents:
                    raise ValueError("バックアップの資料パスが不正です")
                doc_libraries[doc["id"]] = doc["library_id"]
                con.execute("INSERT INTO documents(id,library_id,relative_path,source_path,size,mtime_ns,source_hash,edited_text,edit_base_hash,effective_text,excluded,status,revision,updated_at) VALUES(?,?,?,?,0,0,?,?,?,?,?,'pending',?,?)",
                            (doc["id"], doc["library_id"], doc["relative_path"], str(path), doc["source_hash"], doc.get("edited_text"), doc.get("edit_base_hash"), doc.get("edited_text") or "", int(doc.get("excluded", False)), int(doc.get("revision", 0)), now()))
            for item in data.get("collections", []):
                validate_identifier(item["id"])
                parsed = collection_model.model_validate(item).model_dump()
                libs = parsed["library_ids"] or [parsed["library_id"]]
                if not libs or any(lib not in roots for lib in libs):
                    raise ValueError("セットの登録元が見つかりません")
                parsed["library_ids"], parsed["library_id"] = libs, libs[0]
                if data["schema_version"] == 1:
                    parsed["cleanup"] = "none"
                    parsed["selection_mode"] = "fixed" if parsed["document_ids"] else "dynamic"
                if parsed["target"] not in ("builder", "studio") or parsed["cleanup"] not in ("none", "standard") or parsed["selection_mode"] not in ("fixed", "dynamic"):
                    raise ValueError("セットの設定が不正です")
                if parsed["selection_mode"] == "fixed" and not parsed["document_ids"]:
                    raise ValueError("固定選択の対象資料がありません")
                if parsed["purpose"] not in ("overview", "compare", "questions", "procedure", "reference") or any(v not in ("include", "exclude") for v in parsed["unit_overrides"].values()):
                    raise ValueError("セットの用途または整理設定が不正です")
                validate_override_bases(parsed)
                if any(not q.get("question", "").strip() or len(q["question"]) > 1000 for q in parsed["evaluation_questions"]):
                    raise ValueError("評価質問は1〜1000文字で入力してください")
                if any(doc_libraries.get(doc) not in libs for doc in parsed["document_ids"] + parsed["excluded_document_ids"]):
                    raise ValueError("セットの対象資料が見つかりません")
                collections[item["id"]] = parsed
                con.execute("INSERT INTO collections VALUES(?,?,?,?,?,?,?,?,?)", (item["id"], parsed["name"], parsed["library_id"], parsed["query"], parsed["folder"], json.dumps(parsed["document_ids"]), parsed["purpose"], parsed["instructions"], now()))
                con.execute("INSERT INTO collection_options VALUES(?,?)", (item["id"], json.dumps({key: parsed[key] for key in COLLECTION_DEFAULTS}, ensure_ascii=False)))
            for item in data.get("edit_history", []):
                validate_identifier(item["id"])
                con.execute("INSERT INTO edit_history VALUES(?,?,?,?,?,?)", (item["id"], item["document_id"], int(item["revision"]), item.get("edited_text"), item["source_hash"], item["created_at"]))
            for item in data.get("handoffs", []):
                validate_identifier(item["id"])
                files = json.loads(item["files"]) if isinstance(item["files"], str) else item["files"]
                if item["target"] not in ("builder", "studio") or not isinstance(files, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in files.items()):
                    raise ValueError("登録記録の形式が不正です")
                con.execute("INSERT INTO handoffs VALUES(?,?,?,?,?,?)", (item["id"], item["collection_id"], item["target"], item["generation_id"], item["recorded_at"], json.dumps(files)))
            for item in data.get("schedules", []):
                clean = scheduler._validate(dict(item, enabled=False))
                if clean["library_id"] not in roots or (clean["collection_id"] and collections.get(clean["collection_id"], {}).get("library_ids") != [clean["library_id"]]):
                    raise ValueError("予約の登録元または資料セットが不正です")
                clean.update(last_run=None, last_result="restored_disabled", last_error="")
                con.execute("INSERT INTO reservations.schedules(id,data) VALUES(?,?)", (clean["id"], json.dumps(clean, ensure_ascii=False)))
    except (KeyError, TypeError, OverflowError, sqlite3.IntegrityError) as exc:
        raise ValueError("バックアップの構造が不正です") from exc
