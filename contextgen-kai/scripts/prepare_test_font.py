"""Windows CI のOCR試験画像用フォントを固定ハッシュで取得する。配布物には含めない。"""
import hashlib
from pathlib import Path
import urllib.request

REVISION = '523d033d6cb47f4a80c58a35753646f5c3608a78'
SHA256 = '68a3fc98800b2a27b371f2fb79991daf3633bd89309d4ffaa6946fd587f375b5'
URL = f'https://raw.githubusercontent.com/notofonts/noto-cjk/{REVISION}/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf'


def prepare():
    target = Path(__file__).resolve().parents[1] / 'build' / 'NotoSansCJKjp-Regular.otf'
    if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != SHA256:
        data = urllib.request.urlopen(URL, timeout=90).read()
        if hashlib.sha256(data).hexdigest() != SHA256:
            raise RuntimeError('OCR test font checksum mismatch')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return target


if __name__ == '__main__':
    print(prepare())
