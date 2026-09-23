"""定期更新。予約の保存と実行権取得はプロセス間で共有する SQLite で行う。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable
import uuid
import xml.etree.ElementTree as ET

UTC = timezone.utc
NS = 'http://schemas.microsoft.com/windows/2004/02/mit/task'


def _now():
    return datetime.now().astimezone()


def _parse(value):
    date = datetime.fromisoformat(value)
    return date.astimezone() if date.tzinfo else date.replace(tzinfo=_now().tzinfo)


def _stamp(value):
    return value.astimezone(UTC).isoformat(timespec='seconds')


def next_occurrence(data, now=None):
    """実行漏れをまとめ、現在より後の次回時刻を返す。"""
    now = now or _now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=_now().tzinfo)
    if data['frequency'] == 'interval':
        return now + timedelta(minutes=data['interval_minutes'])
    hour, minute = map(int, data['time'].split(':'))
    for offset in range(8):
        candidate = (now + timedelta(days=offset)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now and (data['frequency'] == 'daily' or candidate.weekday() in data['weekdays']):
            return candidate
    raise ValueError('次回実行日時を計算できません。曜日を確認してください。')


def _process_alive(pid):
    if not pid:
        return False
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # 権限不足なら稼働中として扱う。
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class WindowsTasks:
    """この作業領域の予約だけを登録する。パスワードや管理者権限は要求しない。"""
    def __init__(self, state_dir):
        self.state_dir = Path(state_dir).resolve()
        self.prefix = 'ContextgenKai-' + hashlib.sha256(str(self.state_dir).encode()).hexdigest()[:12] + '-'

    def name(self, schedule_id):
        return self.prefix + schedule_id

    def command(self, schedule_id):
        args = ['--run-schedule', schedule_id, '--state-dir', str(self.state_dir)]
        if getattr(sys, 'frozen', False):
            return str(Path(sys.executable).resolve()), args, str(Path(sys.executable).parent)
        return str(Path(sys.executable).resolve()), ['-m', 'contextgen_kai', *args], str(Path(__file__).resolve().parent.parent)

    def xml(self, data, username=None):
        ET.register_namespace('', NS)
        task = ET.Element(f'{{{NS}}}Task', version='1.2')
        def el(parent, name, value=None, **attrs):
            node = ET.SubElement(parent, name, attrs)
            if value is not None:
                node.text = str(value)
            return node
        registration = el(task, 'RegistrationInfo')
        el(registration, 'Description', 'contextgen 改: ' + data['name'])
        triggers = el(task, 'Triggers')
        trigger = el(triggers, 'TimeTrigger' if data['frequency'] == 'interval' else 'CalendarTrigger')
        if data['frequency'] == 'interval':
            repetition = el(trigger, 'Repetition')
            el(repetition, 'Interval', f"PT{data['interval_minutes']}M")
            el(repetition, 'StopAtDurationEnd', 'false')
        el(trigger, 'StartBoundary', _parse(data['next_run']).isoformat(timespec='seconds'))
        el(trigger, 'Enabled', 'true')
        if data['frequency'] == 'daily':
            el(el(trigger, 'ScheduleByDay'), 'DaysInterval', '1')
        elif data['frequency'] == 'weekly':
            weekly = el(trigger, 'ScheduleByWeek')
            el(weekly, 'WeeksInterval', '1')
            days = el(weekly, 'DaysOfWeek')
            for day in data['weekdays']:
                el(days, ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][day])
        principals = el(task, 'Principals')
        principal = el(principals, 'Principal', id='Author')
        if username is None:
            try:
                username = subprocess.run(['whoami'], capture_output=True, text=True, check=True, timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout.strip()
            except (OSError, subprocess.SubprocessError) as exc:
                raise ValueError('Windows の利用者を確認できません。予約は保存されていません。') from exc
        el(principal, 'UserId', username)
        el(principal, 'LogonType', 'InteractiveToken')
        el(principal, 'RunLevel', 'LeastPrivilege')
        settings = el(task, 'Settings')
        for key, value in [('MultipleInstancesPolicy', 'IgnoreNew'), ('DisallowStartIfOnBatteries', 'false'),
                           ('StopIfGoingOnBatteries', 'false'), ('AllowHardTerminate', 'false'),
                           ('StartWhenAvailable', 'true'), ('RunOnlyIfNetworkAvailable', 'false'),
                           ('AllowStartOnDemand', 'true'), ('Enabled', 'true'), ('Hidden', 'false'),
                           ('RunOnlyIfIdle', 'false'), ('WakeToRun', 'false'), ('ExecutionTimeLimit', 'PT0S'),
                           ('Priority', '7')]:
            el(settings, key, value)
        actions = el(task, 'Actions', Context='Author')
        action = el(actions, 'Exec')
        command, arguments, cwd = self.command(data['id'])
        el(action, 'Command', command)
        el(action, 'Arguments', subprocess.list2cmdline(arguments))
        el(action, 'WorkingDirectory', cwd)
        return ET.tostring(task, encoding='unicode', xml_declaration=False)

    def _run(self, args):
        if os.name != 'nt':
            raise ValueError('アプリ終了後の実行は Windows で設定してください。')
        try:
            result = subprocess.run(['schtasks.exe', *args], capture_output=True, text=True, errors='replace', timeout=45, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError('Windows タスクの操作を完了できませんでした。予約設定を確認してください。') from exc
        if result.returncode:
            raise ValueError('Windows タスク登録の操作に失敗しました: ' + (result.stderr or result.stdout).strip())
        return result

    def register(self, data):
        if os.name != 'nt':
            raise ValueError('アプリ終了後の実行は Windows で設定してください。')
        with tempfile.TemporaryDirectory(prefix='contextgen-task-') as directory:
            path = Path(directory) / 'task.xml'
            path.write_text('<?xml version="1.0" encoding="UTF-16"?>\n' + self.xml(data), encoding='utf-16')
            self._run(['/Create', '/TN', self.name(data['id']), '/XML', str(path), '/F'])

    def delete(self, schedule_id):
        # 他のタスクは変更せず、削除できた場合だけ成功を返す。
        self._run(['/Delete', '/TN', self.name(schedule_id), '/F'])



class Scheduler:
    def __init__(self, state_dir: Path, callback: Callable[[dict], str]):
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.state_dir / 'schedules.sqlite3'
        self.callback = callback
        self.windows = WindowsTasks(self.state_dir)
        self._stop = threading.Event()
        self._thread = None
        self.last_tick_error = ''
        with self._connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS schedules (id TEXT PRIMARY KEY, data TEXT NOT NULL, run_token TEXT, run_pid INTEGER, run_job TEXT)')
            conn.execute('CREATE TABLE IF NOT EXISTS completions (schedule_id TEXT NOT NULL, run_token TEXT NOT NULL, job_id TEXT NOT NULL, status TEXT NOT NULL, error TEXT NOT NULL, PRIMARY KEY(schedule_id,run_token,job_id))')

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        return conn

    def list(self):
        with self._connect() as conn:
            rows = conn.execute('SELECT data,run_job FROM schedules ORDER BY rowid').fetchall()
        return [dict(json.loads(row['data']), running_job_id=row['run_job']) for row in rows]

    def _validate(self, data, old=None):
        result = dict(old or {})
        allowed = ('name', 'library_id', 'collection_id', 'enabled', 'mode', 'frequency', 'time', 'weekdays', 'interval_minutes')
        result.update({key: data[key] for key in allowed if key in data})
        result['id'] = old['id'] if old else uuid.uuid4().hex
        defaults = dict(name='定期更新', collection_id=None, enabled=True, mode='app', frequency='daily', time='09:00',
                        weekdays=[0, 1, 2, 3, 4], interval_minutes=60, last_run=None, last_result=None, last_error='')
        for key, value in defaults.items():
            result.setdefault(key, value)
        if not isinstance(result['name'], str) or not result['name'].strip() or not result.get('library_id'):
            raise ValueError('予約名と資料フォルダを指定してください。')
        if result['mode'] not in ('app', 'background') or result['frequency'] not in ('daily', 'weekly', 'interval'):
            raise ValueError('予約モードまたは実行頻度が不正です。')
        if not isinstance(result['enabled'], bool):
            raise ValueError('有効設定は true / false で指定してください。')
        try:
            datetime.strptime(result['time'], '%H:%M')
            if len(result['time']) != 5:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('時刻は HH:MM で指定してください。') from None
        weekdays = result['weekdays']
        if not isinstance(weekdays, list) or not weekdays or any(type(day) is not int or not 0 <= day <= 6 for day in weekdays):
            raise ValueError('曜日を1つ以上選択してください。')
        result['weekdays'] = sorted(set(weekdays))
        minutes = result['interval_minutes']
        if type(minutes) is not int or not 1 <= minutes <= 44640:
            raise ValueError('実行間隔は 1〜44640 分で指定してください。')
        changed = not old or any(result[key] != old.get(key) for key in ('enabled', 'mode', 'frequency', 'time', 'weekdays', 'interval_minutes'))
        result['next_run'] = _stamp(next_occurrence(result)) if changed else old['next_run']
        return result

    def save(self, data):
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT * FROM schedules WHERE id=?', (data.get('id'),)).fetchone()
            if data.get('id') and not row:
                raise ValueError('予約が見つかりません。')
            old = json.loads(row['data']) if row else None
            result = self._validate(data, old)
            old_bg = bool(old and old['enabled'] and old['mode'] == 'background')
            new_bg = result['enabled'] and result['mode'] == 'background'
            if new_bg:
                self.windows.register(result)  # 成功前に DB を書き換えない。
            elif old_bg:
                self.windows.delete(result['id'])
            try:
                conn.execute('INSERT INTO schedules(id,data) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                             (result['id'], json.dumps(result, ensure_ascii=False)))
                conn.commit()
            except Exception:
                if old_bg:
                    self.windows.register(old)
                elif new_bg:
                    self.windows.delete(result['id'])
                raise
        return result

    def delete(self, schedule_id):
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT * FROM schedules WHERE id=?', (schedule_id,)).fetchone()
            if not row:
                raise ValueError('予約が見つかりません。')
            data = json.loads(row['data'])
            if row['run_token'] and _process_alive(row['run_pid']):
                raise ValueError('実行中の予約は削除できません。先に処理を停止してください。')
            if data['enabled'] and data['mode'] == 'background':
                self.windows.delete(schedule_id)
            try:
                conn.execute('DELETE FROM schedules WHERE id=?', (schedule_id,))
                conn.commit()
            except Exception:
                if data['enabled'] and data['mode'] == 'background':
                    self.windows.register(data)
                raise

    def _run(self, schedule_id, *, manual=False, now=None):
        now = now or _now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=_now().tzinfo)
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT * FROM schedules WHERE id=?', (schedule_id,)).fetchone()
            if not row:
                raise ValueError('予約が見つかりません。')
            data = json.loads(row['data'])
            crashed = bool(row['run_token'] and not _process_alive(row['run_pid']))
            if row['run_token'] and not crashed:
                return row['run_job'] or ''
            if not manual and (not data['enabled'] or (not crashed and _parse(data['next_run']) > now)):
                return ''
            token = uuid.uuid4().hex
            conn.execute('DELETE FROM completions WHERE schedule_id=?', (schedule_id,))
            # Windows 側の繰返し時刻と位相を維持し、数秒の遅れで次回を飛ばさない。
            scheduled = _parse(data['next_run'])
            if manual and scheduled > now:
                following = scheduled
            elif data['frequency'] == 'interval':
                interval = timedelta(minutes=data['interval_minutes'])
                following = scheduled + max(1, (now - scheduled) // interval + 1) * interval
            else:
                following = next_occurrence(data, now)
            data.update(last_run=_stamp(now), last_result='running', last_error='', next_run=_stamp(following))
            conn.execute('UPDATE schedules SET data=?,run_token=?,run_pid=?,run_job=? WHERE id=?',
                         (json.dumps(data, ensure_ascii=False), token, os.getpid(), 'pending', schedule_id))
        try:
            job_id = self.callback(data)
            if not job_id:
                raise RuntimeError('実行ジョブを作成できませんでした。')
            with self._connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                early = conn.execute('SELECT * FROM completions WHERE schedule_id=? AND run_token=? AND job_id=?', (schedule_id, token, str(job_id))).fetchone()
                current = conn.execute('SELECT data FROM schedules WHERE id=? AND run_token=?', (schedule_id, token)).fetchone()
                if early and current:
                    finished = json.loads(current['data'])
                    finished.update(last_result=early['status'], last_error=early['error'])
                    conn.execute('UPDATE schedules SET data=?,run_token=NULL,run_pid=NULL,run_job=NULL WHERE id=? AND run_token=?', (json.dumps(finished, ensure_ascii=False), schedule_id, token))
                else:
                    conn.execute('UPDATE schedules SET run_job=? WHERE id=? AND run_token=?', (str(job_id), schedule_id, token))
                conn.execute('DELETE FROM completions WHERE schedule_id=? AND run_token=?', (schedule_id, token))
            return str(job_id)
        except Exception as exc:
            self.complete(schedule_id, 'pending', 'failed', str(exc))
            raise

    def run_now(self, schedule_id):
        return self._run(schedule_id, manual=True)

    def run_reserved(self, schedule_id):
        return self._run(schedule_id)

    def complete(self, schedule_id, job_id, status, error=''):
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT * FROM schedules WHERE id=?', (schedule_id,)).fetchone()
            if not row or row['run_job'] not in (job_id, 'pending'):
                return
            if row['run_job'] == 'pending' and job_id != 'pending':
                # callback が返るより速い完了通知を記録。古いジョブの遅延通知と混同しない。
                conn.execute('INSERT OR REPLACE INTO completions VALUES(?,?,?,?,?)', (schedule_id, row['run_token'], job_id, status, error))
                return
            data = json.loads(row['data'])
            data.update(last_result=status, last_error=error)
            conn.execute('DELETE FROM completions WHERE schedule_id=?', (schedule_id,))
            conn.execute('UPDATE schedules SET data=?,run_token=NULL,run_pid=NULL,run_job=NULL WHERE id=?',
                         (json.dumps(data, ensure_ascii=False), schedule_id))

    def tick(self, now=None):
        errors = []
        for data in self.list():
            try:
                self._run(data['id'], now=now)
            except Exception as exc:
                errors.append(f"{data['name']}: {exc}")
        self.last_tick_error = '\n'.join(errors)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        def loop():
            while not self._stop.is_set():
                try:
                    self.tick()
                except Exception as exc:
                    self.last_tick_error = str(exc)
                self._stop.wait(15)
        self._thread = threading.Thread(target=loop, name='contextgen-scheduler', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def restore(self, items):
        prepared = []
        for item in items:
            clean = self._validate(dict(item, enabled=False))
            clean.update(last_run=None, last_result='restored_disabled', last_error='')
            prepared.append(clean)
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if conn.execute('SELECT COUNT(*) FROM schedules').fetchone()[0]:
                raise ValueError('予約の復元先は空の作業領域にしてください。')
            conn.executemany('INSERT INTO schedules(id,data) VALUES(?,?)', [(item['id'], json.dumps(item, ensure_ascii=False)) for item in prepared])
        return prepared
