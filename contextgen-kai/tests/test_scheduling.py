from datetime import datetime, timedelta, timezone
import json
import threading
import xml.etree.ElementTree as ET

import pytest
from contextgen_kai.scheduling import Scheduler, WindowsTasks, next_occurrence, _stamp


def add(scheduler, **kwargs):
    return scheduler.save(dict(name='毎日の更新', library_id='library-a', **kwargs))


def due(scheduler, item, when=None):
    item['next_run'] = _stamp(when or datetime.now(timezone.utc) - timedelta(days=4))
    with scheduler._connect() as conn:
        conn.execute('UPDATE schedules SET data=? WHERE id=?', (json.dumps(item), item['id']))


def test_next_occurrence_weekly_and_interval():
    now = datetime(2026, 9, 23, 10, tzinfo=timezone.utc)  # Wednesday
    assert next_occurrence(dict(frequency='weekly', time='09:00', weekdays=[0, 4]), now).weekday() == 4
    assert next_occurrence(dict(frequency='interval', interval_minutes=15), now) == now + timedelta(minutes=15)


def test_claim_catchup_once_and_completion(tmp_path):
    calls = []
    scheduler = Scheduler(tmp_path, lambda data: calls.append(data) or 'job-1')
    item = add(scheduler)
    due(scheduler, item)
    scheduler.tick()
    other = Scheduler(tmp_path, lambda data: pytest.fail('duplicate callback'))
    assert other.run_reserved(item['id']) == 'job-1'
    assert len(calls) == 1
    scheduler.complete(item['id'], 'job-1', 'held', '確認待ち')
    scheduler.tick()
    row = other.list()[0]
    assert row['last_result'] == 'held' and row['last_error'] == '確認待ち'
    assert row['running_job_id'] is None
    assert len(calls) == 1


def test_parallel_claim_is_atomic(tmp_path):
    calls = []
    scheduler = Scheduler(tmp_path, lambda data: calls.append(data) or 'job')
    item = add(scheduler)
    due(scheduler, item)
    schedulers = [Scheduler(tmp_path, scheduler.callback) for _ in range(8)]
    threads = [threading.Thread(target=s.tick) for s in schedulers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(calls) == 1


def test_callback_failure_and_immediate_completion(tmp_path):
    def fail(data):
        raise RuntimeError('容量不足')
    scheduler = Scheduler(tmp_path, fail)
    item = add(scheduler)
    with pytest.raises(RuntimeError, match='容量不足'):
        scheduler.run_now(item['id'])
    assert scheduler.list()[0]['last_result'] == 'failed'
    def finish(data):
        scheduler.complete(data['id'], 'fast-job', 'completed')
        return 'fast-job'
    scheduler.callback = finish
    assert scheduler.run_now(item['id']) == 'fast-job'
    assert scheduler.list()[0]['running_job_id'] is None
    assert scheduler.list()[0]['last_result'] == 'completed'


def test_background_registration_is_not_saved_on_failure(tmp_path, monkeypatch):
    scheduler = Scheduler(tmp_path, lambda data: 'job')
    item = add(scheduler)
    def denied(data):
        raise RuntimeError('access denied')
    monkeypatch.setattr(scheduler.windows, 'register', denied)
    with pytest.raises(RuntimeError, match='denied'):
        scheduler.save(dict(item, mode='background'))
    assert scheduler.list()[0]['mode'] == 'app'


def test_mode_switch_unregisters_and_failure_preserves_state(tmp_path, monkeypatch):
    scheduler = Scheduler(tmp_path, lambda data: 'job')
    registrations, deletions = [], []
    monkeypatch.setattr(scheduler.windows, 'register', lambda d: registrations.append(d))
    monkeypatch.setattr(scheduler.windows, 'delete', lambda i: deletions.append(i))
    item = add(scheduler, mode='background')
    assert len(registrations) == 1
    scheduler.save(dict(item, mode='app'))
    assert deletions == [item['id']]
    item = scheduler.save(dict(item, mode='background'))
    def fail(i):
        raise RuntimeError('no permission')
    monkeypatch.setattr(scheduler.windows, 'delete', fail)
    with pytest.raises(RuntimeError):
        scheduler.save(dict(item, enabled=False))
    assert scheduler.list()[0]['enabled'] is True


def test_restore_disabled_never_registers(tmp_path, monkeypatch):
    scheduler = Scheduler(tmp_path, lambda data: 'job')
    monkeypatch.setattr(scheduler.windows, 'register', lambda data: pytest.fail('unexpected OS mutation'))
    restored = scheduler.restore([dict(name='restore', library_id='l', mode='background', enabled=True)])
    assert restored[0]['enabled'] is False
    scheduler.tick()
    assert scheduler.list()[0]['running_job_id'] is None


def test_crashed_claim_can_resume(tmp_path, monkeypatch):
    scheduler = Scheduler(tmp_path, lambda data: 'new-job')
    item = add(scheduler)
    with scheduler._connect() as conn:
        conn.execute('UPDATE schedules SET run_token=?,run_pid=?,run_job=? WHERE id=?', ('old', 9999999, 'lost', item['id']))
    monkeypatch.setattr('contextgen_kai.scheduling._process_alive', lambda pid: False)
    assert scheduler.run_reserved(item['id']) == 'new-job'


def test_xml_is_interactive_limited_and_escapes_paths(tmp_path):
    scheduler = Scheduler(tmp_path / '日本語 & space', lambda data: 'job')
    item = add(scheduler, frequency='weekly', weekdays=[0, 4])
    raw = scheduler.windows.xml(item, username='DOMAIN\\tester')
    root = ET.fromstring(raw)
    ns = {'t': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}
    assert root.find('.//t:LogonType', ns).text == 'InteractiveToken'
    assert root.find('.//t:RunLevel', ns).text == 'LeastPrivilege'
    assert root.find('.//t:WakeToRun', ns).text == 'false'
    assert root.find('.//t:StartWhenAvailable', ns).text == 'true'
    assert root.find('.//t:Monday', ns) is not None
    assert root.find('.//t:Friday', ns) is not None
    assert '日本語 & space' in root.find('.//t:Arguments', ns).text
    assert '--run-schedule' in root.find('.//t:Arguments', ns).text


@pytest.mark.parametrize('changes', [dict(interval_minutes=0), dict(time='25:61'), dict(weekdays=[]), dict(mode='wrong')])
def test_invalid_configuration(tmp_path, changes):
    scheduler = Scheduler(tmp_path, lambda data: 'job')
    with pytest.raises(ValueError):
        add(scheduler, **changes)


def test_delayed_interval_keeps_windows_trigger_alignment(tmp_path):
    scheduler = Scheduler(tmp_path, lambda data: 'job')
    item = add(scheduler, frequency='interval', interval_minutes=60)
    scheduled = datetime(2026, 9, 23, 9, tzinfo=timezone.utc)
    due(scheduler, item, scheduled)
    scheduler.tick(now=scheduled + timedelta(hours=3, seconds=17))
    assert scheduler.list()[0]['next_run'] == _stamp(scheduled + timedelta(hours=4))


def test_manual_run_preserves_future_schedule(tmp_path):
    scheduler = Scheduler(tmp_path, lambda data: 'job')
    item = add(scheduler, frequency='interval', interval_minutes=60)
    scheduler.run_now(item['id'])
    assert scheduler.list()[0]['next_run'] == item['next_run']


def test_stale_completion_does_not_finish_new_pending_job(tmp_path):
    scheduler = Scheduler(tmp_path, lambda data: 'first')
    item = add(scheduler)
    scheduler.run_now(item['id'])
    scheduler.complete(item['id'], 'first', 'completed')
    def second(data):
        scheduler.complete(data['id'], 'first', 'stopped')
        return 'second'
    scheduler.callback = second
    scheduler.run_now(item['id'])
    assert scheduler.list()[0]['running_job_id'] == 'second'
    assert scheduler.list()[0]['last_result'] == 'running'
    scheduler.complete(item['id'], 'second', 'completed')
    assert scheduler.list()[0]['last_result'] == 'completed'


def test_os_task_failure_returns_actionable_error(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import contextgen_kai.scheduling as mod
    tasks = WindowsTasks(tmp_path)
    monkeypatch.setattr(mod.os, 'name', 'nt')
    monkeypatch.setattr(mod.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stderr='Access denied', stdout=''))
    with pytest.raises(ValueError, match='Access denied'):
        tasks._run(['/Query'])


def test_queued_job_cancellation_releases_schedule_claim(tmp_path):
    from contextgen_kai.jobs import JobManager, ProcessLock
    from contextgen_kai.storage import Store
    source = tmp_path / '資料'
    source.mkdir()
    (source / 'memo.txt').write_text('検証用資料', encoding='utf-8')
    store = Store(tmp_path / 'state')
    library = store.add_library('資料', str(source))
    jobs = JobManager(store, use_process=False)
    scheduler = Scheduler(store.root, lambda data: jobs.start(data['library_id'], schedule_id=data['id'])['id'])
    jobs.complete_callback = scheduler.complete
    lock = ProcessLock(store.root)
    assert lock.acquire()
    try:
        item = scheduler.save({'name': '待機中の停止', 'library_id': library['id']})
        job_id = scheduler.run_now(item['id'])
        jobs.stop(job_id)
        assert jobs.wait(job_id, timeout=5)['state'] == 'stopped'
        assert scheduler.list()[0]['running_job_id'] is None
        assert scheduler.list()[0]['last_result'] == 'stopped'
    finally:
        lock.release()
        jobs.close()
