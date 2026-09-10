"""v3 柱4: GUI をコンパクトにするための折りたたみセクション.

tkinter には折りたたみウィジェットが無いので自作する。
ヘッダをクリックすると本体を出し入れし、閉じているときは
ヘッダに要約（例:「オプション（3件設定中）」）を表示して
中身を開かなくても状況が分かるようにする。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class CollapsibleFrame(ttk.Frame):
    """クリックで開閉できるセクション。

    使い方::

        section = CollapsibleFrame(parent, 'オプション', opened=False)
        section.pack(fill='x')
        ttk.Checkbutton(section.body, ...).pack()
        section.set_summary('3件設定中')
    """

    def __init__(self, parent, title: str, opened: bool = True,
                 on_toggle=None, body_padding=(14, 4, 6, 8)):
        super().__init__(parent)
        self._title = title
        self._opened = bool(opened)
        self._summary = ''
        self._on_toggle = on_toggle

        self._header = ttk.Button(self, command=self.toggle, style='Collapsible.TButton')
        self._header.pack(fill='x')

        self.body = ttk.Frame(self, padding=body_padding)
        if self._opened:
            self.body.pack(fill='x')

        self._refresh_header()

    # ---- 状態 ----

    @property
    def opened(self) -> bool:
        return self._opened

    def toggle(self) -> None:
        self.set_opened(not self._opened)

    def set_opened(self, opened: bool) -> None:
        opened = bool(opened)
        if opened == self._opened:
            return
        self._opened = opened
        if opened:
            self.body.pack(fill='x')
        else:
            self.body.pack_forget()
        self._refresh_header()
        if self._on_toggle is not None:
            self._on_toggle(self._title, opened)

    def set_summary(self, summary: str) -> None:
        """閉じているときにヘッダへ出す補足。開いているときは表示しない."""
        self._summary = summary or ''
        self._refresh_header()

    # ---- 内部 ----

    def _refresh_header(self) -> None:
        arrow = '▼' if self._opened else '▶'
        text = f"{arrow}  {self._title}"
        if not self._opened and self._summary:
            text += f"　（{self._summary}）"
        self._header.config(text=text)


def install_style(root: tk.Misc) -> None:
    """折りたたみヘッダを「押せる見出し」らしく見せる."""
    style = ttk.Style(root)
    try:
        style.configure(
            'Collapsible.TButton',
            anchor='w',
            padding=(8, 5),
            font=('Meiryo', 10, 'bold'),
        )
    except Exception:
        pass
