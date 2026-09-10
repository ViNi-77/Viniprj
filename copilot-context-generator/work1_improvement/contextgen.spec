# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Windows で以下を実行:
#   .venv\Scripts\pyinstaller contextgen.spec
# onedir 構成（起動が速く AV 誤検知も減る）。単一 exe が必要なら
# EXE(...) の exclude_binaries を False にし COLLECT を外すこと。

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
        # 依存の掃除（原本exeはPIL同梱で27MBに肥大していた。
        # python-pptx は画像を挿入しない限り Pillow 不要）
        'matplotlib', 'numpy', 'scipy', 'IPython',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name='CopilotM365ContextGenerator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='CopilotM365ContextGenerator',
)
