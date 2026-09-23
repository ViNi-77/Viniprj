"""資料選定・原本確認・利用者による登録記録。外部サービスへ接続しない。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .storage import identifier, now


def validate_generation_sources(store, export, manifest, *, cancelled=lambda: None):
    """生成後の設定・本文修正・原本変更を検知し、古い世代への切替を止める。"""
    from .extractors import SUPPORTED_EXTENSIONS
    from .jobs import file_hash
    collection = store.collection(export["collection_id"])
    if not manifest.get("source_snapshot") or manifest.get("collection_settings") != collection:
        raise ValueError("資料セットの設定が更新されています。再生成してください")
    where, args = store.collection_filters(collection, include_excluded=True)
    current = {row["id"]: row for row in store.all("SELECT id,revision,source_hash,active FROM documents d WHERE " + where, args)}
    snapshots = manifest["source_snapshot"]
    if current.keys() != {row["id"] for row in snapshots}:
        raise ValueError("収録対象が更新されています。再生成してください")
    for item in snapshots:
        cancelled()
        doc = current[item["id"]]
        if doc["revision"] != item["revision"] or doc["source_hash"] != item["source_hash"] or doc["active"] != item.get("active", 1):
            raise ValueError("資料の読み取り結果または修正が更新されています。再生成してください")
        if not item.get("active", 1) or item["status"] not in ("ok", "partial", "empty") or item["excluded"] or item["conflict"]:
            continue
        path = Path(item["source_path"])
        try:
            root = Path(store.one("SELECT path FROM libraries WHERE id=?", (item["library_id"],))["path"]).resolve()
            st = path.stat()
            if path.is_symlink() or not path.resolve().is_relative_to(root) or getattr(st, "st_file_attributes", 0) & (0x1000 | 0x40000 | 0x400000) or file_hash(path) != item["source_hash"]:
                raise ValueError("原本が更新されています。再生成してください")
        except OSError as exc:
            raise ValueError("原本を確認できません。再生成してください") from exc
    # まだ索引にない追加資料も検知する。固定選択では追加資料は対象外。
    if collection["selection_mode"] == "dynamic":
        for lib_id in collection["library_ids"]:
            root = Path(store.one("SELECT path FROM libraries WHERE id=?", (lib_id,))["path"])
            known = {d["relative_path"] for d in store.all("SELECT relative_path FROM documents WHERE library_id=? AND active=1", (lib_id,))}
            stack = [root]
            while stack:
                cancelled()
                folder = stack.pop()
                try:
                    with os.scandir(folder) as entries:
                        for entry in entries:
                            path = Path(entry.path)
                            if entry.is_symlink() or entry.name.startswith(("~$", ".~")):
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                if entry.name not in (".git", ".venv", "__pycache__") and path.resolve() != store.root and not path.is_junction():
                                    stack.append(path)
                            elif entry.is_file(follow_symlinks=False) and path.suffix.lower() in SUPPORTED_EXTENSIONS and path.relative_to(root).as_posix() not in known:
                                raise ValueError("新しい資料が追加されています。再生成してください")
                except OSError as exc:
                    raise ValueError("登録フォルダを確認できません。再生成してください") from exc


def preview_collection(store, collection, offset=0, limit=100):
    where, args = store.collection_filters(collection, include_excluded=True)
    excluded = set(collection.get("excluded_document_ids", []))
    with store.connect() as con:
        totals = con.execute("SELECT count(*) total,coalesce(sum(excluded OR id IN (SELECT value FROM json_each(?))),0) excluded,coalesce(sum(conflict OR active=0 OR status NOT IN ('ok','empty')),0) warning_count,coalesce(sum(active=1 AND excluded=0 AND conflict=0 AND id NOT IN (SELECT value FROM json_each(?))),0) included,coalesce(sum(active=0),0) missing FROM documents d WHERE " + where, (json.dumps(list(excluded)), json.dumps(list(excluded)), *args)).fetchone()
        rows = con.execute("SELECT id,library_id,relative_path,status,active,excluded,conflict,updated_at,json_array_length(warnings) warning_count,substr(effective_text,1,220) snippet FROM documents d WHERE " + where + " ORDER BY relative_path,id LIMIT ? OFFSET ?", (*args, limit, offset))
        items = []
        for row in rows:
            item = dict(row)
            item["set_excluded"] = item["id"] in excluded
            item["missing"] = not bool(item["active"])
            item["included"] = not (item["excluded"] or item["set_excluded"] or item["conflict"] or item["missing"])
            item["reason"] = "資料全体で除外" if item["excluded"] else "このセットで除外" if item["set_excluded"] else "固定選択の原本が削除済み（再読み取りまたは選択の見直しが必要）" if item["missing"] else "修正の確認待ち" if item["conflict"] else "固定選択" if collection["selection_mode"] == "fixed" else "検索条件に一致"
            if item["missing"]:
                item["extraction_status"], item["status"] = item["status"], "deleted"
            items.append(item)
    result = dict(totals)
    result.update(items=items, offset=offset, limit=limit)
    return result


def preflight_collection(store, collection):
    # この画面は属性照合。生成ジョブでは原本ハッシュまで照合してから再抽出する。
    where, args = store.collection_filters(collection)
    stale = issues = included = total = 0
    files = []
    roots = {lib: Path(store.one("SELECT path FROM libraries WHERE id=?", (lib,))["path"]).resolve() for lib in collection["library_ids"]}
    with store.connect() as con:
        for row in con.execute("SELECT id,library_id,relative_path,source_path,size,mtime_ns,status,active,excluded,conflict FROM documents d WHERE " + where, args):
            total += 1
            state = "確認済み"
            path = Path(row["source_path"])
            try:
                st = path.stat()
                if not path.resolve().is_relative_to(roots[row["library_id"]]) or path.is_symlink():
                    state = "参照元の再確認が必要"
                elif getattr(st, "st_file_attributes", 0) & (0x1000 | 0x40000 | 0x400000):
                    state = "端末への取得が必要"
                elif (st.st_size, st.st_mtime_ns) != (row["size"], row["mtime_ns"]):
                    state = "原本更新あり"
            except OSError:
                state = "原本が見つかりません"
            if not row["active"]:
                state = "固定選択の原本が削除済み、または再読み取り待ちです"
            stale += state != "確認済み"
            issue = not row["active"] or row["conflict"] or row["status"] not in ("ok", "empty")
            issues += bool(issue)
            included += bool(row["active"]) and not (row["excluded"] or row["conflict"])
            if len(files) < 200 and (state != "確認済み" or issue):
                files.append(dict(document_id=row["id"], name=row["relative_path"], status=state, extraction_status=row["status"], conflict=bool(row["conflict"])))
    return dict(total=total, included=included, stale=stale, issues=issues, files=files,
                note="この表示は登録済み原本の属性確認です。生成時に追加・削除・内容ハッシュを確認します。警告一覧は先頭200件です。")


def handoff_status(store, export):
    manifest = json.loads(export["manifest"])
    current = manifest.get("knowledge_files")
    if current is None:
        current = {name: digest for name, digest in manifest.get("files", {}).items() if name.startswith("M365/")}
    target = manifest.get("target", "builder")
    baseline = store.handoff(export["collection_id"], target)
    old = baseline["files"] if baseline else {}
    return dict(target=target, knowledge_files=[dict(path=path, sha256=digest) for path, digest in current.items()],
                baseline_generation_id=baseline["generation_id"] if baseline else None,
                recorded_at=baseline["recorded_at"] if baseline else None,
                changed=[name for name, digest in current.items() if old.get(name) != digest],
                removed=[name for name in old if name not in current],
                note="登録状態は利用者の記録です。Copilot側の状態を自動確認したものではありません。")


def record_handoff(store, export, data):
    info = handoff_status(store, export)
    if export["state"] not in ("published",):
        raise ValueError("確認待ちの出力は先に確認して使用する操作を行ってください")
    selected, removed = data.get("files", []), data.get("removed", [])
    current = {entry["path"]: entry["sha256"] for entry in info["knowledge_files"]}
    if not isinstance(selected, list) or not isinstance(removed, list) or any(not isinstance(p, str) for p in selected + removed):
        raise ValueError("登録したファイルを選択してください")
    if not set(selected) <= current.keys() or not set(removed) <= set(info["removed"]):
        raise ValueError("登録・削除対象のファイルを確認してください")
    if not selected and not removed:
        raise ValueError("登録または削除したファイルを1件以上選択してください")
    baseline = store.handoff(export["collection_id"], info["target"])
    files = dict(baseline["files"]) if baseline else {}
    files.update({path: current[path] for path in selected})
    for path in removed:
        files.pop(path, None)
    store.execute("INSERT INTO handoffs VALUES(?,?,?,?,?,?)", (identifier(), export["collection_id"], info["target"], export["id"], now(), json.dumps(files)))
    return handoff_status(store, export)
