# -*- mode: python ; coding: utf-8 -*-
# 単一 exe（onefile）ビルド用 spec — 原本 exe と同じ配布形態。
# Windows で:
#   .venv\Scripts\pyinstaller contextgen_onefile.spec
# 生成物: dist\CopilotM365ContextGenerator.exe（1ファイル）
#
# onefile は起動時に一時フォルダへ自己展開するため、
# onedir（contextgen.spec）より起動が数秒遅く、AV誤検知もやや増える。
# 配布の手軽さを優先する場合にこちらを使う。

a = Analysis(
    ['launcher_gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'charset_normalizer',
        'docx',
        'openpyxl',
        'pptx',
        'pypdf',
        # v2.1 OCR（インストールされている場合のみ同梱される）
        'pypdfium2',
        'winsdk.windows.media.ocr',
        'winsdk.windows.graphics.imaging',
        'winsdk.windows.storage.streams',
        'winsdk.windows.globalization',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'scipy', 'IPython',
        'PIL.ImageQt', 'PyQt5', 'PySide6',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,      # onefile: バイナリ・データを exe に内包する
    a.datas,
    [],
    name='CopilotM365ContextGenerator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,       # UPX圧縮はAV誤検知が増えるため使わない
    # console=False（windowed）: ダブルクリック起動で黒いコンソール窓を
    # 出さない。launcher_gui.py が起動直後に sys.stdout/stderr/stdin の
    # None フォールバックを行うため、CLIモード（--source 等）でも
    # print() で落ちない。CLI実行結果は画面には出ないが、
    # 管理フォルダのログファイルと --teams-webhook で確認できる
    # （events.Emitter.log は print() と独立にファイル書き込みするため
    # 影響を受けない）。ターミナルでの対話利用を重視する場合は
    # console=True に変更するか onedir 版（contextgen.spec）を使う。
    console=False,
    disable_windowed_traceback=False,
    runtime_tmpdir=None,
)
