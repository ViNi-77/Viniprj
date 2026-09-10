# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 仕様（onedir）。python packaging/build_exe.py から使う。

同梱するもの: backend（コード）、frontend、schema、config（既定）、backend/app/viewer、python-pptx のテンプレート、
jsonschema の仕様データ。
書き込み先（projects/output/logs）は exe の隣に作られる。

Playwright は同梱しない: そのドライバは Node.js 本体（約120MB）を含み、配布物が肥大化するうえ、
展開先パスが深くなりすぎて Windows の MAX_PATH に達したり、社内のウイルス対策/EDR に
実行ファイル同梱の node バイナリを警戒されたりする原因になりやすい。Computed Style
補助機能（見た目優先の微調整）はあくまで任意機能で、Playwright が無い環境では
自動的に静的解析のみへフォールバックする（backend/app/rasterize.py の is_available() 参照）ため、
exe 版では同梱せず、必要な場合はソースから起動する運用とする。
"""
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - SPECPATH は PyInstaller が定義
BACKEND = ROOT / "backend"

datas = [
    (str(ROOT / "frontend"), "frontend"),
    (str(ROOT / "schema"), "schema"),
    (str(ROOT / "config"), "config"),
    (str(BACKEND / "app" / "viewer"), "app/viewer"),
]
binaries = []
hiddenimports = [
    "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto", "uvicorn.lifespan", "uvicorn.lifespan.on",
    "anyio._backends._asyncio", "multipart", "python_multipart",
]
for pkg in ("pptx", "jsonschema", "jsonschema_specifications", "lxml", "bs4", "PIL", "referencing", "rpds"):
    datas += collect_data_files(pkg)
    hiddenimports += collect_submodules(pkg)
# jsonschema/referencing 系は importlib.metadata でパッケージ情報を参照することがあるため、
# .dist-info も明示的に同梱する（collect_data_files だけでは同梱されない）
for _meta_pkg in ("jsonschema", "jsonschema_specifications", "referencing", "attrs", "rpds-py"):
    try:
        datas += copy_metadata(_meta_pkg)
    except Exception:  # noqa: BLE001 - パッケージ名の揺れ（rpds/rpds-py 等）は無視して継続
        pass
# python-pptx の既定テンプレート（default.pptx / *.xml）は明示的に同梱する（collect_data_files が拾わない環境がある）
import pptx as _pptx  # noqa: E402

_tpl = Path(_pptx.__file__).resolve().parent / "templates"
if _tpl.exists():
    datas.append((str(_tpl), "pptx/templates"))
# python-pptx は 'pptx/oxml/../templates/x.xml' という相対経路で開くため、pptx/oxml ディレクトリを実体として置く
_placeholder_dir = Path(workpath).resolve() / "_pptx_oxml_placeholder"  # noqa: F821 - workpath は PyInstaller が定義
_placeholder_dir.mkdir(parents=True, exist_ok=True)
(_placeholder_dir / ".keep").write_text("python-pptx のテンプレート相対経路のためのディレクトリ\n", encoding="utf-8")
datas.append((str(_placeholder_dir / ".keep"), "pptx/oxml"))
a = Analysis(  # noqa: F821
    [str(BACKEND / "launcher.py")],
    pathex=[str(BACKEND)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # TLS は使わないため cryptography/OpenSSL を除外。playwright は同梱しない（上記コメント参照）:
    # ドライバの Node.js 本体を含めると配布物が約120MB膨らみ、パス長/AV 誤検知のリスクが増えるため、
    # ImportError で静的解析のみへ自動フォールバックする既存の作りを活かして exe から完全に外す。
    excludes=["tkinter", "matplotlib", "numpy", "pytest", "IPython", "cryptography", "OpenSSL", "playwright"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="pptx-web-bridge",
    debug=False,
    strip=False,
    upx=False,
    console=True,  # 起動状況とログを窓に出す（依頼: 起動すると窓が開きブラウザが立ち上がる）
    icon=None,
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="pptx-web-bridge",
)
