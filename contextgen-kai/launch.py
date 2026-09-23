"""PyInstaller 用起動点。Windows の子プロセス再帰起動を防止する。"""
import multiprocessing
import os
import sys

if __name__ == '__main__':
    multiprocessing.freeze_support()
    # --windowed EXE でも標準ログ出力先が必ず存在するようにする。
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w', encoding='utf-8')
    from contextgen_kai.__main__ import main
    raise SystemExit(main())
