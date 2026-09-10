"""tkinter GUI（restored 版のレイアウト互換 + 改善オプション）.

起動: python -m contextgen.gui
"""
from __future__ import annotations

import queue
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from .config import (
    BASE_DIR_DEFAULT,
    CONTEXT_OUTPUT_DIR_DEFAULT,
    COPYRIGHT_TEXT,
    SEARCH_ROOT_DEFAULT,
    SETTINGS_FILENAME,
    RunConfig,
    load_settings,
    save_settings,
)
from .events import QueueEmitter, now_text
from .textutil import format_size, is_same_or_child
from .widgets import CollapsibleFrame, install_style
from .worker import run_all


def default_settings_path() -> Path:
    if BASE_DIR_DEFAULT.exists():
        return BASE_DIR_DEFAULT / SETTINGS_FILENAME
    return Path.home() / '.contextgen' / SETTINGS_FILENAME


def run_gui(on_ready=None):  # noqa: C901 - GUI 構築はどうしても長い
    """GUI を起動する。

    on_ready: mainloop 直前に呼ばれるフック（画面構成のスモークテスト用）。
        戻り値が False の場合は mainloop に入らず終了する。
    """
    log_queue: queue.Queue = queue.Queue()
    stop_event = threading.Event()
    worker_thread: list[threading.Thread | None] = [None]

    settings_path = default_settings_path()
    settings = load_settings(settings_path)

    root = tk.Tk()
    root.title('Copilot M365用コンテキスト生成 GUI')
    # v3 柱4: 常時展開をやめ、既定で閉じるセクションを設けて画面を小さくする
    root.geometry(settings.get('window_geometry', '900x640'))
    root.minsize(760, 520)
    install_style(root)

    section_state: dict = dict(settings.get('sections_open', {}))

    def remember_section(title: str, opened: bool) -> None:
        section_state[title] = opened

    main = ttk.Frame(root, padding=10)
    main.pack(fill='both', expand=True)

    ttk.Label(
        main,
        text='Copilot M365用コンテキスト生成',
        font=('Meiryo', 18, 'bold'),
    ).pack(anchor='w')

    search_root_var = tk.StringVar(value=settings.get('search_root', str(SEARCH_ROOT_DEFAULT)))
    context_output_dir_var = tk.StringVar(
        value=settings.get('context_output_dir', str(CONTEXT_OUTPUT_DIR_DEFAULT))
    )

    def browse_folder(var, title, fallback):
        current = var.get().strip().strip('"')
        initial_dir = current if current and Path(current).exists() else str(fallback)
        selected = filedialog.askdirectory(title=title, initialdir=initial_dir, mustexist=True)
        if selected:
            var.set(selected)

    def browse_search_root():
        browse_folder(search_root_var, '参照元フォルダを選択', SEARCH_ROOT_DEFAULT)

    def browse_context_output_dir():
        browse_folder(context_output_dir_var, 'コンテキスト出力先フォルダを選択', CONTEXT_OUTPUT_DIR_DEFAULT)

    path_section = CollapsibleFrame(
        main, 'フォルダ設定', opened=section_state.get('フォルダ設定', True),
        on_toggle=remember_section)
    path_section.pack(fill='x', pady=(6, 4))
    path_frame = path_section.body

    def add_folder_row(parent, label_text, variable, button_command):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=2)
        ttk.Label(row, text=label_text, font=('Meiryo', 9), width=18).pack(side='left')
        entry = ttk.Entry(row, textvariable=variable, font=('Meiryo', 9))
        entry.pack(side='left', fill='x', expand=True, padx=(0, 5))
        ttk.Button(row, text='参照', command=button_command).pack(side='left')
        return entry

    add_folder_row(path_frame, '参照元:', search_root_var, browse_search_root)
    add_folder_row(path_frame, 'コンテキスト出力先:', context_output_dir_var, browse_context_output_dir)

    # ---- 改善オプション（既定では閉じておく）----
    option_section = CollapsibleFrame(
        main, 'オプション', opened=section_state.get('オプション', False),
        on_toggle=remember_section)
    option_section.pack(fill='x', pady=(0, 4))
    option_frame = option_section.body

    use_cache_var = tk.BooleanVar(value=bool(settings.get('use_cache', True)))
    full_rescan_var = tk.BooleanVar(value=False)
    token_capacity_var = tk.BooleanVar(value=settings.get('m365_capacity_mode', 'chars') == 'tokens')
    mtime_sort_var = tk.BooleanVar(value=settings.get('sort_mode', 'path') == 'mtime_desc')
    bestfit_var = tk.BooleanVar(value=settings.get('m365_packing', 'sequential') == 'bestfit')
    split_var = tk.BooleanVar(value=bool(settings.get('split_by_subfolder', False)))
    ocr_var = tk.BooleanVar(value=settings.get('ocr_mode', 'off') == 'auto')
    digest_var = tk.BooleanVar(value=bool(settings.get('human_digest', False)))

    options = [
        ('差分キャッシュを使用（変更ファイルのみ再抽出）', use_cache_var),
        ('フルスキャン（今回のみ全ファイル再抽出）', full_rescan_var),
        ('トークン基準で容量管理', token_capacity_var),
        ('更新日の新しい順に収録', mtime_sort_var),
        ('詰め込み最適化（bestfit）', bestfit_var),
        ('サブフォルダ別パッケージ生成', split_var),
        ('OCR実行（テキスト層のないPDF）', ocr_var),
        ('人間向け読解キットも作る', digest_var),
    ]
    for i, (label, var) in enumerate(options):
        ttk.Checkbutton(option_frame, text=label, variable=var).grid(
            row=i // 3, column=i % 3, sticky='w', padx=8, pady=2
        )

    # v2.1: モード選択（機密スキャン / 重複検出 / Boxオンラインオンリー）
    mode_row = ttk.Frame(option_frame)
    mode_row.grid(row=3, column=0, columnspan=3, sticky='w', padx=4, pady=(6, 0))

    sensitive_var = tk.StringVar(value=settings.get('sensitive_scan', 'warn'))
    dedupe_var = tk.StringVar(value=settings.get('dedupe_mode', 'warn'))
    cloud_var = tk.StringVar(value=settings.get('cloud_only_mode', 'download'))

    for label, var, values in [
        ('機密スキャン:', sensitive_var, ['off', 'warn', 'mask', 'block']),
        ('重複検出:', dedupe_var, ['off', 'warn', 'exclude']),
        ('クラウドのみ:', cloud_var, ['download', 'skip', 'warn']),
    ]:
        ttk.Label(mode_row, text=label, font=('Meiryo', 9)).pack(side='left', padx=(4, 2))
        ttk.Combobox(mode_row, textvariable=var, values=values, state='readonly',
                     width=9, font=('Meiryo', 9)).pack(side='left', padx=(0, 10))

    webhook_row = ttk.Frame(option_frame)
    webhook_row.grid(row=4, column=0, columnspan=3, sticky='we', padx=4, pady=(6, 0))
    ttk.Label(webhook_row, text='Teams Webhook:', font=('Meiryo', 9)).pack(side='left', padx=(4, 2))
    teams_webhook_var = tk.StringVar(value=settings.get('teams_webhook_url', ''))
    ttk.Entry(webhook_row, textvariable=teams_webhook_var, font=('Meiryo', 9)).pack(
        side='left', fill='x', expand=True, padx=(0, 4)
    )

    # ---- 動作状況 ----
    progress_frame = ttk.LabelFrame(main, text='動作状況', padding=8)
    progress_frame.pack(fill='x', pady=(6, 4))

    progress_var = tk.IntVar(value=0)
    progress_bar = ttk.Progressbar(
        progress_frame, orient='horizontal', mode='determinate',
        variable=progress_var, maximum=100,
    )
    progress_bar.pack(fill='x')

    percent_label = ttk.Label(progress_frame, text='動作待機中', font=('Meiryo', 13, 'bold'))
    percent_label.pack(anchor='center', pady=3)

    current_dir_var = tk.StringVar(value='現在検索中フォルダ: 待機中')
    ttk.Label(
        progress_frame, textvariable=current_dir_var,
        font=('Meiryo', 9, 'bold'), foreground='blue', wraplength=840,
    ).pack(anchor='w', pady=(5, 0))

    current_file_var = tk.StringVar(value='現在処理中ファイル: 待機中')
    ttk.Label(
        progress_frame, textvariable=current_file_var,
        font=('Meiryo', 9), wraplength=840,
    ).pack(anchor='w', pady=(5, 0))

    counter_frame = ttk.Frame(main)
    counter_frame.pack(fill='x', pady=(2, 2))

    scan_var = tk.StringVar(value='確認: 0')
    target_var = tk.StringVar(value='参照元ファイル: 0')
    error_var = tk.StringVar(value='エラー: 0')
    size_var = tk.StringVar(value='参照元容量: 0 B')

    for i, var in enumerate([scan_var, target_var, error_var, size_var]):
        ttk.Label(counter_frame, textvariable=var, font=('Meiryo', 11, 'bold')).grid(row=0, column=i, padx=8)

    ext_section = CollapsibleFrame(
        main, 'ファイル種別内訳', opened=section_state.get('ファイル種別内訳', False),
        on_toggle=remember_section)
    ext_section.pack(fill='x', pady=(2, 4))
    ext_frame = ext_section.body

    ext_counts: dict[str, int] = {}
    ext_vars = {}
    for i, ext in enumerate(['.doc', '.docx', '.txt', '.pdf', '.xlsx', '.xlsm', '.pptx', '.pptm', '.zip']):
        var = tk.StringVar(value=f"{ext}: 0")
        ext_vars[ext] = var
        ext_counts[ext] = 0
        ttk.Label(ext_frame, textvariable=var, font=('Meiryo', 10)).grid(
            row=i // 5, column=i % 5, padx=10, pady=2
        )

    def refresh_ext_summary() -> None:
        found = [(ext, n) for ext, n in ext_counts.items() if n]
        if not found:
            ext_section.set_summary('まだ検出なし')
            return
        found.sort(key=lambda item: item[1], reverse=True)
        head = ' / '.join(f"{ext} {n}" for ext, n in found[:4])
        if len(found) > 4:
            head += f" ほか{len(found) - 4}種"
        ext_section.set_summary(head)

    refresh_ext_summary()

    button_frame = ttk.Frame(main)
    button_frame.pack(fill='x', pady=(4, 4))

    def build_config(dry_run: bool = False) -> RunConfig:
        return RunConfig(
            search_root=Path(search_root_var.get().strip().strip('"')).expanduser(),
            context_output_dir=Path(context_output_dir_var.get().strip().strip('"')).expanduser(),
            use_cache=use_cache_var.get(),
            full_rescan=full_rescan_var.get(),
            m365_capacity_mode='tokens' if token_capacity_var.get() else 'chars',
            sort_mode='mtime_desc' if mtime_sort_var.get() else 'path',
            m365_packing='bestfit' if bestfit_var.get() else 'sequential',
            split_by_subfolder=split_var.get(),
            dry_run=dry_run,
            ocr_mode='auto' if ocr_var.get() else 'off',
            human_digest=digest_var.get(),
            sensitive_scan=sensitive_var.get(),
            dedupe_mode=dedupe_var.get(),
            cloud_only_mode=cloud_var.get(),
            teams_webhook_url=teams_webhook_var.get().strip(),
        )

    def start_backup(dry_run: bool = False):
        if worker_thread[0] and worker_thread[0].is_alive():
            messagebox.showinfo('実行中', 'すでに処理中です')
            return

        selected_search_text = search_root_var.get().strip().strip('"')
        selected_context_text = context_output_dir_var.get().strip().strip('"')

        if not selected_search_text:
            messagebox.showerror('参照元エラー', '参照元フォルダを指定してください。')
            return
        if not selected_context_text:
            messagebox.showerror('コンテキスト出力先エラー', 'コンテキスト出力先フォルダを指定してください。')
            return

        config = build_config(dry_run=dry_run)

        if not (config.search_root.exists() and config.search_root.is_dir()):
            messagebox.showerror('参照元エラー', f"参照元フォルダが存在しません。\n{config.search_root}")
            return

        try:
            config.context_output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror('出力先エラー', f"コンテキスト出力先を作成できません。\n{e}")
            return

        for blocked_root in (config.context_output_dir, config.base_dir):
            if is_same_or_child(config.search_root, blocked_root):
                messagebox.showerror(
                    '参照元エラー',
                    f"コンテキスト出力先・管理フォルダは参照元に指定できません。\n指定: {config.search_root}"
                    f"\n対象外: {blocked_root}",
                )
                return

        search_root_var.set(str(config.search_root))
        context_output_dir_var.set(str(config.context_output_dir))

        try:
            save_settings(settings_path, {
                'search_root': str(config.search_root),
                'context_output_dir': str(config.context_output_dir),
                'use_cache': config.use_cache,
                'm365_capacity_mode': config.m365_capacity_mode,
                'sort_mode': config.sort_mode,
                'm365_packing': config.m365_packing,
                'split_by_subfolder': config.split_by_subfolder,
                'ocr_mode': config.ocr_mode,
                'human_digest': config.human_digest,
                'sensitive_scan': config.sensitive_scan,
                'dedupe_mode': config.dedupe_mode,
                'cloud_only_mode': config.cloud_only_mode,
                'teams_webhook_url': config.teams_webhook_url,
                'sections_open': section_state,
                'window_geometry': root.winfo_geometry(),
                'saved_at': now_text(),
            })
        except Exception:
            pass

        progress_var.set(0)
        percent_label.config(text='ドライラン中（見積のみ）' if dry_run else '検索・コンテキスト生成中')
        current_dir_var.set('現在検索中フォルダ: 開始準備中...')
        current_file_var.set('現在処理中ファイル: 開始準備中...')
        scan_var.set('確認: 0')
        target_var.set('参照元ファイル: 0')
        error_var.set('エラー: 0')
        size_var.set('参照元容量: 0 B')
        for ext, var in ext_vars.items():
            var.set(f"{ext}: 0")

        start_button.config(state='disabled')
        dry_run_button.config(state='disabled')
        stop_button.config(state='normal')

        stop_event.clear()
        emitter = QueueEmitter(log_queue, log_path=config.log_path)
        worker_thread[0] = threading.Thread(
            target=run_all, args=(config, emitter, stop_event), daemon=True
        )
        worker_thread[0].start()

    def stop_backup():
        stop_event.set()
        current_file_var.set('現在処理中ファイル: 停止要求中... 現在の処理が終わるまで待機')

    start_button = ttk.Button(button_frame, text='開始', command=start_backup)
    start_button.pack(side='left', padx=5)

    dry_run_button = ttk.Button(button_frame, text='ドライラン（見積のみ）',
                                command=lambda: start_backup(dry_run=True))
    dry_run_button.pack(side='left', padx=5)

    def digest_single_file():
        """v3 柱2: 長い資料を1つだけ選んで読み解きキットにする."""
        import threading as _threading

        from .extractors import ExtractorContext, extract as extract_file
        from .outputs.human_digest import write_document_digest
        from .textutil import normalize_text

        target = filedialog.askopenfilename(
            title='読み解きたい資料を選択',
            filetypes=[('対応ファイル', '*.docx *.doc *.xlsx *.xlsm *.pptx *.pptm *.pdf *.txt *.zip'),
                       ('すべて', '*.*')],
        )
        if not target:
            return

        target_path = Path(target)
        output_text = context_output_dir_var.get().strip().strip('"')
        if not output_text:
            messagebox.showerror('出力先エラー', 'コンテキスト出力先フォルダを指定してください。')
            return
        output_dir = Path(output_text).expanduser()

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            config = RunConfig(search_root=target_path.parent,
                               context_output_dir=output_dir, human_digest=True)
            ctx = ExtractorContext(config=config, stop_event=_threading.Event())
            result = extract_file(target_path, ctx)
            text = normalize_text(result.text)
            if not text:
                messagebox.showwarning(
                    '読み解き',
                    f"本文を抽出できませんでした。\n{result.status}: {result.reason}")
                return
            digest_path, digest = write_document_digest(
                output_dir, target_path, target_path.name, text,
                target_path.stat().st_size, result.status, result.coverage,
            )
        except Exception as e:
            messagebox.showerror('読み解きエラー', str(e))
            return

        notes = [f"見出し {len(digest.headings)} 個 / 約{digest.char_count:,}文字"]
        if digest.newest_year:
            notes.append(f"文書内の最新記述: {digest.newest_year} 年")
        if digest.broken_references:
            notes.append(f"参照切れ: {', '.join(digest.broken_references[:3])}")
        if digest.duplicate_paragraphs:
            notes.append(f"重複記述: {len(digest.duplicate_paragraphs)} 箇所")

        messagebox.showinfo(
            '読み解きキットを作成しました',
            f"{digest_path}\n\n" + '\n'.join(notes))

    digest_button = ttk.Button(button_frame, text='1ファイルを読み解く',
                               command=digest_single_file)
    digest_button.pack(side='left', padx=5)

    stop_button = ttk.Button(button_frame, text='停止', command=stop_backup, state='disabled')
    stop_button.pack(side='left', padx=5)

    copyright_label = ttk.Label(main, text=COPYRIGHT_TEXT, font=('Meiryo', 8), foreground='gray')
    copyright_label.pack(side='bottom', anchor='center', fill='x', pady=(2, 0))

    log_frame = ttk.LabelFrame(main, text='ログ', padding=6)
    log_frame.pack(fill='both', expand=True, pady=(4, 2))

    log_text = tk.Text(log_frame, height=8, font=('Consolas', 9), wrap='none')
    log_text.pack(side='left', fill='both', expand=True)

    scrollbar = ttk.Scrollbar(log_frame, orient='vertical', command=log_text.yview)
    scrollbar.pack(side='right', fill='y')
    log_text.configure(yscrollcommand=scrollbar.set)

    def update_gui_from_queue():
        try:
            while True:
                event_type, data = log_queue.get_nowait()

                if event_type == 'log':
                    log_text.insert('end', data + '\n')
                    log_text.see('end')
                elif event_type == 'current':
                    current_file_var.set(f"現在処理中ファイル: {data}")
                elif event_type == 'current_dir':
                    current_dir_var.set(f"現在検索中フォルダ: {data}")
                elif event_type == 'progress':
                    progress_var.set(data['percent'])
                    percent_label.config(text='検索・コンテキスト生成中')
                    scan_var.set(f"確認: {data['scan_checked']}")
                    target_var.set(f"参照元ファイル: {data['target']}")
                    error_var.set(f"エラー: {data['error']}")
                    size_var.set(f"参照元容量: {format_size(data['referenced_bytes'])}")
                    for ext, var in ext_vars.items():
                        count = data['ext'].get(ext, 0)
                        ext_counts[ext] = count
                        var.set(f"{ext}: {count}")
                    refresh_ext_summary()
                elif event_type == 'finish':
                    start_button.config(state='normal')
                    dry_run_button.config(state='normal')
                    stop_button.config(state='disabled')
                    if stop_event.is_set():
                        percent_label.config(text='停止')
                        current_file_var.set('現在処理中ファイル: 停止しました')
                    else:
                        progress_var.set(100)
                        percent_label.config(text='完了')
                        current_file_var.set('現在処理中ファイル: 参照元直接読み取り + AIコンテキスト生成完了')
        except queue.Empty:
            pass

        root.after(200, update_gui_from_queue)

    def on_close():
        if worker_thread[0] and worker_thread[0].is_alive():
            stop_event.set()
            messagebox.showinfo('停止中', '処理中です。停止要求を出しました。数秒後に閉じてください。')
            return
        root.destroy()

    root.protocol('WM_DELETE_WINDOW', on_close)
    update_gui_from_queue()

    if on_ready is not None:
        sections = {'フォルダ設定': path_section, 'オプション': option_section,
                    'ファイル種別内訳': ext_section}
        if on_ready(root, sections) is False:
            root.destroy()
            return

    root.mainloop()


if __name__ == '__main__':  # pragma: no cover
    run_gui()
