"""Git版の実行中はコード・依存環境を更新しない。複数の読取り実行は許可する。"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sys


class InstallationBusy(RuntimeError):
    pass


@contextmanager
def installation_lock(root: Path | None = None, *, shared: bool = True):
    """アプリ/予約は共有、セットアップ/Git更新は排他。プロセス終了時にOSが解除する。"""
    if root is None and getattr(sys, "frozen", False):
        # 配布EXEはGitの更新対象ではない。読取り専用の配布先でも起動できる。
        yield
        return
    folder = Path(root or Path(__file__).resolve().parents[1]) / ".runtime"
    folder.mkdir(exist_ok=True)
    path = folder / "installation.lock"
    message = "アプリまたは定期更新が動作中です。画面の「終了」で本体を終了し、定期更新の完了後に再実行してください。"
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                           wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        create.restype = wintypes.HANDLE
        close = kernel.CloseHandle
        close.argtypes = (wintypes.HANDLE,)
        close.restype = wintypes.BOOL
        # OPEN_ALWAYS。sharedのときも書込み権限は要求しないため複数アプリが共存できる。
        handle = create(str(path), 0x80000000 if shared else 0xC0000000,
                        1 if shared else 0, None, 4, 0x80, None)
        if handle == wintypes.HANDLE(-1).value:
            error = ctypes.get_last_error()
            if error in (32, 33):
                raise InstallationBusy(message)
            raise OSError(error, "起動・更新の排他確認に失敗しました", str(path))
        try:
            yield
        finally:
            close(handle)
    else:
        import fcntl

        with path.open("a+b") as stream:
            try:
                fcntl.flock(stream, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
            except BlockingIOError:
                raise InstallationBusy(message) from None
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)
