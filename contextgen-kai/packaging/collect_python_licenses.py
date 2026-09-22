"""配布物に Python 依存関係の権利表示と正確なバージョン一覧を保存する。"""
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
packages = []
for dist in sorted(metadata.distributions(), key=lambda d: d.metadata['Name'].lower()):
    name = dist.metadata['Name']
    if name.lower() == 'contextgen-kai':
        continue  # アプリ自体に新しいライセンスを付与しない。
    target = out / name
    target.mkdir(exist_ok=True)
    copied = []
    for file in dist.files or []:
        if any(part.lower().startswith(('license', 'licence', 'copying', 'notice')) for part in file.parts):
            source = Path(dist.locate_file(file))
            if source.is_file():
                relative = Path(*[part for part in file.parts if part not in ('..', '.')])
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                copied.append(str(relative))
    info = {'name': name, 'version': dist.version, 'license_expression': dist.metadata.get('License-Expression'),
            'license': dist.metadata.get('License'), 'home_page': dist.metadata.get('Home-page'),
            'project_urls': dist.metadata.get_all('Project-URL') or [], 'license_files': copied}
    (target / 'metadata.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    packages.append(info)
(out / 'DEPENDENCIES.json').write_text(json.dumps(packages, ensure_ascii=False, indent=2), encoding='utf-8')

python_notices = [Path(sys.base_prefix) / 'LICENSE.txt', Path(sys.base_prefix) / 'LICENSE']
for notice in python_notices:
    if notice.is_file():
        shutil.copy2(notice, out / 'Python-LICENSE.txt')
        break
else:
    if sys.platform == 'win32':
        raise RuntimeError('Python runtime license could not be located')
(out / 'Python-VERSION.txt').write_text(sys.version, encoding='utf-8')
