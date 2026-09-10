"""v3 柱4: GUI のコンパクト化に関するテスト.

「PCで表示すると画面が大きすぎる」というフィードバックへの対応。
折りたたみで既定の高さが縮むこと、開閉状態が保存されることを保証する。
"""
from __future__ import annotations

import pytest

tk = pytest.importorskip('tkinter', reason='tkinter が無い環境ではGUIテストを行わない')


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as e:  # pragma: no cover - ヘッドレス環境
        pytest.skip(f'ディスプレイが使えません: {e}')
    r.withdraw()
    yield r
    r.destroy()


def test_collapsible_hides_and_shows_body(root):
    from contextgen.widgets import CollapsibleFrame

    section = CollapsibleFrame(root, 'テスト', opened=True)
    section.pack(fill='x')
    tk.Label(section.body, text='中身' * 20).pack()
    root.update_idletasks()

    opened_height = section.winfo_reqheight()

    section.toggle()
    root.update_idletasks()
    closed_height = section.winfo_reqheight()

    assert not section.opened
    assert closed_height < opened_height, '閉じても高さが縮んでいない'

    section.toggle()
    root.update_idletasks()
    assert section.opened
    assert section.winfo_reqheight() == opened_height


def test_collapsible_summary_only_when_closed(root):
    from contextgen.widgets import CollapsibleFrame

    section = CollapsibleFrame(root, 'オプション', opened=False)
    section.pack(fill='x')
    section.set_summary('3件設定中')
    root.update_idletasks()

    assert '3件設定中' in section._header.cget('text')
    assert '▶' in section._header.cget('text')

    section.toggle()
    root.update_idletasks()
    # 開いているときは中身が見えるので要約は出さない
    assert '3件設定中' not in section._header.cget('text')
    assert '▼' in section._header.cget('text')


def test_toggle_notifies_state(root):
    from contextgen.widgets import CollapsibleFrame

    seen = {}
    section = CollapsibleFrame(root, 'オプション', opened=False,
                               on_toggle=lambda title, opened: seen.__setitem__(title, opened))
    section.pack(fill='x')

    section.toggle()
    assert seen == {'オプション': True}
    section.toggle()
    assert seen == {'オプション': False}


def test_gui_builds_and_is_compact(tmp_path, monkeypatch):
    """GUI 全体が構築でき、既定の必要高さが従来より小さいこと."""
    from contextgen import gui

    monkeypatch.setattr(gui, 'default_settings_path', lambda: tmp_path / 'settings.json')

    measured = {}

    def on_ready(root, sections):
        root.update_idletasks()
        measured['height'] = root.winfo_reqheight()
        measured['sections'] = {name: sec.opened for name, sec in sections.items()}
        return False

    try:
        gui.run_gui(on_ready=on_ready)
    except tk.TclError as e:  # pragma: no cover - ヘッドレス環境
        pytest.skip(f'ディスプレイが使えません: {e}')

    # 既定でオプションとファイル種別内訳は閉じている
    assert measured['sections']['オプション'] is False
    assert measured['sections']['ファイル種別内訳'] is False
    assert measured['sections']['フォルダ設定'] is True

    # 旧レイアウトは 920px 固定だった。既定状態はそれより明確に小さいこと
    assert measured['height'] < 800, f"画面がまだ大きい: {measured['height']}px"


def test_section_state_is_restored_from_settings(tmp_path, monkeypatch):
    """開閉状態が設定から復元されること."""
    import json

    from contextgen import gui

    settings_path = tmp_path / 'settings.json'
    settings_path.write_text(json.dumps({'sections_open': {'オプション': True}}),
                             encoding='utf-8')
    monkeypatch.setattr(gui, 'default_settings_path', lambda: settings_path)

    seen = {}

    def on_ready(root, sections):
        seen.update({name: sec.opened for name, sec in sections.items()})
        return False

    try:
        gui.run_gui(on_ready=on_ready)
    except tk.TclError as e:  # pragma: no cover
        pytest.skip(f'ディスプレイが使えません: {e}')

    assert seen['オプション'] is True, '保存した開閉状態が復元されていない'
