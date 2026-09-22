# PyInstaller 6; run from contextgen-kai directory.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH).parent
extra_datas, extra_binaries, hidden = [], [], []
for package in ('pypdfium2', 'pypdfium2_raw'):
    data, binaries, imports = collect_all(package)
    extra_datas += data
    extra_binaries += binaries
    hidden += imports
hidden += collect_submodules('uvicorn')
a = Analysis([str(root / 'launch.py')], pathex=[str(root)],
             binaries=extra_binaries,
             datas=[(str(root / 'contextgen_kai' / 'static'), 'contextgen_kai/static')] + extra_datas,
             hiddenimports=hidden, hookspath=[], runtime_hooks=[], excludes=['pytest', 'playwright'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ContextgenKai',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ContextgenKai')
