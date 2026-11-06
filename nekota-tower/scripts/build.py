"""ねこ太と十二月の塔 — 1 ファイル HTML のビルド（標準ライブラリだけ。--subset のときだけ fontTools を使う）。

  python scripts/build.py                  # src/ を連結して index.html を書く（サイズとビルド ID を表示）
  python scripts/build.py --check          # メモリ上で組み立て、コミット済み index.html とバイト一致しなければ exit 1
  python scripts/build.py --dev            # dev.html を書く（src を <link>/<script src> で直接参照。file:// で開ける）
  python scripts/build.py --subset         # tools/fonts/*.ttf から src/fonts/*-sub.woff2 を作り直してから組む
  python scripts/build.py --allow-missing  # 未作成の src ファイルを警告だけで飛ばす（並行開発の初期だけ。既定は厳格）

規約は docs/02_設計.md（構成 / 読み込み順 / ビルド）。要点:
  - 読み込み順は SOURCES の並びが正。後のファイルが前のファイルを使う。
  - {{BUILD}} はソース全体の SHA-256 先頭 8 桁（タイムスタンプは埋め込まない）。
  - 外部参照（src="http, href="http, fetch(, import(, importScripts(）を見つけたら失敗。生成物が 1.5 MB 超なら失敗、1.0 MB 超なら警告。
  - フォントは @font-face の data: URL で同梱し、ライセンス全文を HTML コメントで添える。
"""
from __future__ import annotations

import argparse
import base64
import codecs
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TEMPLATE = SRC / "index.tpl.html"
OUT_HTML = ROOT / "index.html"
DEV_HTML = ROOT / "dev.html"
FONT_DIR = SRC / "fonts"
SUBSET_INFO = FONT_DIR / "subset.json"  # --subset が要求した符号位置の記録。通常ビルドで subset の古さを警告するのに使う
TOOLS_FONTS = ROOT / "tools" / "fonts"
LICENSE_DIR = ROOT / "LICENSES"

# 読み込み順（docs/02_設計.md「構成」と一字一句合わせる）
SOURCES: list[str] = (
    [f"css/{n}.css" for n in "screen crt overlay".split()]
    + [f"data/{n}.js" for n in "text dialogs quests map entities jingles library".split()]
    + [f"svg/{n}.js" for n in "nekota npcs".split()]
    + [
        f"js/{n}.js"
        for n in (
            "00_ns 01_util 02_time 03_storage 04_codec 05_input 06_audio 07_screen 08_fonts 09_text "
            "10_gfx 11_sprites 12_scenes 13_loop 14_state 15_settings 20_dialog 21_menu 22_inputbox "
            "30_scene_boot 31_scene_title 32_scene_name 33_scene_slot 40_tilemap 41_camera 42_player "
            "43_entities 44_scene_map 50_quests 51_quest_q10 52_quest_q9 53_scene_quest 54_quest_impls 55_scene_white 60_scene_save "
            "71_scene_tags 72_excuse 73_scene_bar 74_library "
            "61_scene_card 70_scene_ending 80_interlock 99_main"
        ).split()
    ]
)

# 同梱フォント。family は CSS 側の名前（フォント内部の名前ではない。OFL の Reserved Font Name を避ける意味もある）
FONTS = [
    {
        "family": "PM12",
        "woff2": "PixelMplus12-sub.woff2",
        "ttf": "PixelMplus12-Regular.ttf",
        "license": "PixelMplus-LICENSE_E.txt",
        "label": "PixelMplus12 (M+ FONTS LICENSE)",
    },
    {
        "family": "DG16",
        "woff2": "DotGothic16-sub.woff2",
        "ttf": "DotGothic16-Regular.ttf",
        "license": "DotGothic16-OFL.txt",
        "label": "DotGothic16 (SIL Open Font License 1.1)",
    },
]

FORBIDDEN = ['src="http', 'href="http', "fetch(", "import(", "importScripts("]
SIZE_FAIL = int(1.5 * 1024 * 1024)
SIZE_WARN = 1 * 1024 * 1024
BUILD_MARK = "{{BUILD}}"
MARKERS = ("<!--@fonts-->", "<!--@css-->", "<!--@js-->")

# 開発用 dev.html の CSP。file:// から src/ を <link>/<script src> で読むには file: を許す必要がある
# （Chromium では file:// 文書の 'self' は不透明オリジンなので src/ に一致しない）。配布物の index.html には付けない。
DEV_CSP_EXTRA = {"style-src": " file:", "script-src": " file:"}


def warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


# ---------------------------------------------------------------- 入力の読み込み


def load_sources(allow_missing: bool) -> list[tuple[str, bytes]]:
    """SOURCES の順に (src/ からの相対パス, bytes) を返す。無いファイルは既定で失敗、--allow-missing なら警告して飛ばす。"""
    out: list[tuple[str, bytes]] = []
    missing: list[str] = []
    for name in SOURCES:
        p = SRC / name
        if p.is_file():
            out.append((name, p.read_bytes()))
        else:
            missing.append(name)
    if missing:
        if not allow_missing:
            die("ソースが無い（--allow-missing で飛ばせる）:\n  " + "\n  ".join(f"src/{m}" for m in missing))
        warn(f"未作成のソースを {len(missing)} 件飛ばした: " + " ".join(missing))
    # SOURCES に載っていないのに src/ に置かれたファイルは、黙って抜けるので警告する
    listed = set(SOURCES)
    for sub in ("css", "data", "svg", "js"):
        d = SRC / sub
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.is_file() and f"{sub}/{p.name}" not in listed and not p.name.startswith("."):
                warn(f"SOURCES に無いので index.html に入らない: src/{sub}/{p.name}")
    return out


def load_fonts() -> list[dict]:
    """src/fonts/*-sub.woff2 と LICENSES/ を読む。無ければ --subset の案内を出して失敗する。"""
    fonts = []
    for f in FONTS:
        wp = FONT_DIR / f["woff2"]
        lp = LICENSE_DIR / f["license"]
        if not wp.is_file():
            die(f"{rel(wp)} が無い。tools/fonts/ に {f['ttf']} を置いて `python scripts/build.py --subset` で作る")
        if not lp.is_file():
            die(f"{rel(lp)} が無い")
        # ライセンス本文は原文どおり。行末 CRLF だけ LF に揃える（git の改行変換で index.html が変わらないように）
        text = lp.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        for bad in ("-->", "--!>", "<!--"):
            if bad in text:
                die(f"{rel(lp)} に HTML コメントを壊す文字列 {bad!r} がある")
        fonts.append({**f, "data": wp.read_bytes(), "license_text": text})
    return fonts


def read_template() -> str:
    if not TEMPLATE.is_file():
        die(f"{rel(TEMPLATE)} が無い")
    tpl = TEMPLATE.read_text(encoding="utf-8")
    for m in MARKERS:
        if tpl.count(m) != 1:
            die(f"テンプレートに {m} が {tpl.count(m)} 回ある（1 回だけ必要）")
    if BUILD_MARK not in tpl:
        warn(f"テンプレートに {BUILD_MARK} が無い（<meta name=\"build\"> にビルド ID が入らない）")
    return tpl


# ---------------------------------------------------------------- 検査


def check_forbidden(label: str, text: str) -> None:
    for bad in FORBIDDEN:
        i = text.find(bad)
        if i >= 0:
            line = text.count("\n", 0, i) + 1
            die(f"{label}:{line}: 外部参照を含む文字列 {bad!r}（file:// 配布なので禁止）")


def check_inline_safe(name: str, text: str) -> None:
    """<script>/<style> の中に入れても壊れないか。"""
    low = text.lower()
    if name.endswith(".js") and "</script" in low:
        die(f"src/{name}: '</script' を含むと inline <script> が途中で閉じる")
    if name.endswith(".css") and "</style" in low:
        die(f"src/{name}: '</style' を含むと inline <style> が途中で閉じる")
    if name.endswith(".js") and "<!--" in text:
        warn(f"src/{name}: '<!--' は <script> 内でトークナイザの扱いが変わる。避けたほうがよい")


# ---------------------------------------------------------------- ビルド ID


def build_id(template: bytes, fonts: list[dict], sources: list[tuple[str, bytes]]) -> str:
    """出力に入る全入力の連結の SHA-256 先頭 8 桁。順序: テンプレート → フォント（woff2・ライセンス）→ SOURCES 順。"""
    h = hashlib.sha256()
    h.update(template)
    for f in fonts:
        h.update(f["data"])
        h.update(f["license_text"].encode("utf-8"))
    for _, data in sources:
        h.update(data)
    return h.hexdigest()[:8]


# ---------------------------------------------------------------- 文字列リテラルの走査（フォント subset 用）

_HEX = set("0123456789abcdefABCDEF")
_REGEX_PREV_CHARS = set("(,=:[!&|?{};+-*%<>~^") | {""}
_REGEX_PREV_WORDS = {"return", "typeof", "case", "in", "of", "delete", "void", "throw", "new", "do", "else", "instanceof", "yield", "await"}
_SIMPLE_ESC = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


def string_chars(src: str) -> set[str]:
    """JS ソースの文字列リテラル（' " `）に現れる文字を集める。

    コメントと正規表現リテラルは飛ばす（コメントの日本語まで subset に入れないため）。
    \\uXXXX / \\u{...} / \\xNN / 単純エスケープは復号する。テンプレートの ${...} の中の式は再帰的に走査する。
    正規表現かどうかは直前のトークンで判定する（ヒューリスティック。外れても集まる文字が少し増減するだけ）。"""
    chars: set[str] = set()
    n = len(src)

    def esc(i: int) -> tuple[str, int]:
        c = src[i + 1] if i + 1 < n else ""
        if c == "u":
            if i + 2 < n and src[i + 2] == "{":
                j = src.find("}", i + 3)
                if j > 0 and all(ch in _HEX for ch in src[i + 3 : j]) and j > i + 3:
                    try:
                        return chr(int(src[i + 3 : j], 16)), j + 1
                    except (ValueError, OverflowError):
                        pass
            h = src[i + 2 : i + 6]
            if len(h) == 4 and all(ch in _HEX for ch in h):
                return chr(int(h, 16)), i + 6
        if c == "x":
            h = src[i + 2 : i + 4]
            if len(h) == 2 and all(ch in _HEX for ch in h):
                return chr(int(h, 16)), i + 4
        if c in "\r\n":
            return "", i + 2  # 行継続
        return _SIMPLE_ESC.get(c, c), i + 2

    def quoted(i: int, q: str) -> int:
        while i < n:
            c = src[i]
            if c == "\\":
                t, i = esc(i)
                chars.update(t)
            elif c == q:
                return i + 1
            elif c == "\n":
                return i  # 閉じていない
            else:
                chars.add(c)
                i += 1
        return n

    def template(i: int) -> int:
        while i < n:
            c = src[i]
            if c == "\\":
                t, i = esc(i)
                chars.update(t)
            elif c == "`":
                return i + 1
            elif src.startswith("${", i):
                i = walk(i + 2, True)
            else:
                chars.add(c)
                i += 1
        return n

    def regex(i: int) -> int:
        in_class = False
        while i < n:
            c = src[i]
            if c == "\\":
                i += 2
            elif c == "[":
                in_class = True
                i += 1
            elif c == "]":
                in_class = False
                i += 1
            elif c == "/" and not in_class:
                i += 1
                while i < n and (src[i].isalpha()):
                    i += 1
                return i
            elif c == "\n":
                return i
            else:
                i += 1
        return n

    def walk(i: int, in_template_expr: bool) -> int:
        depth = 0
        prev = ""  # 直前の意味のある文字
        prev_word = ""
        while i < n:
            c = src[i]
            if c in " \t\r\n":
                i += 1
                continue
            if src.startswith("//", i):
                j = src.find("\n", i)
                i = n if j < 0 else j + 1
                continue
            if src.startswith("/*", i):
                j = src.find("*/", i + 2)
                i = n if j < 0 else j + 2
                continue
            if c in "'\"":
                i = quoted(i + 1, c)
                prev, prev_word = '"', ""
                continue
            if c == "`":
                i = template(i + 1)
                prev, prev_word = '"', ""
                continue
            if c == "/":
                if prev in _REGEX_PREV_CHARS or prev_word in _REGEX_PREV_WORDS:
                    i = regex(i + 1)
                    prev, prev_word = ")", ""
                    continue
            if c.isalnum() or c in "_$":
                j = i
                while j < n and (src[j].isalnum() or src[j] in "_$"):
                    j += 1
                prev_word = src[i:j]
                prev = "a"
                i = j
                continue
            if in_template_expr:
                if c == "{":
                    depth += 1
                elif c == "}":
                    if depth == 0:
                        return i + 1
                    depth -= 1
            prev, prev_word = c, ""
            i += 1
        return n

    walk(0, False)
    # 制御文字と書式文字（BOM U+FEFF、ゼロ幅など。グリフを持たない）は除く
    return {c for c in chars if ord(c) >= 0x20 and ord(c) != 0x7F and unicodedata.category(c) != "Cf"}


def used_chars() -> set[str]:
    """src/data, src/svg, src/js の全 .js の文字列リテラルに現れる文字（UI 文言は data/text.js だが、他にも出る）。"""
    out: set[str] = set()
    for sub in ("data", "svg", "js"):
        d = SRC / sub
        if d.is_dir():
            for p in sorted(d.glob("*.js")):
                out |= string_chars(p.read_text(encoding="utf-8"))
    return out


# ---------------------------------------------------------------- フォント subset


def _ranges(*pairs: tuple[int, int]) -> set[int]:
    s: set[int] = set()
    for a, b in pairs:
        s.update(range(a, b + 1))
    return s


def jis1_kanji() -> set[int]:
    """JIS 第一水準漢字 = cp932 の 16〜47 区（0x889F〜0x9872）。2 バイト符号を 1 つずつ cp932 で復号する。"""
    out: set[int] = set()
    for lead in range(0x88, 0x99):
        for trail in list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)):
            code = (lead << 8) | trail
            if code < 0x889F or code > 0x9872:
                continue
            try:
                ch = codecs.decode(bytes([lead, trail]), "cp932")
            except UnicodeDecodeError:
                continue
            out.add(ord(ch))
    return out


# 欠けていると画面に影響する記号（game 側でフォールバックするために、無いものを名指しで報告する）
WATCH_CHARS = [chr(c) for c in range(0x2776, 0x2780)] + ["★", "☆", "▶", "▼"]


def pm12_unicodes(used: set[str]) -> set[int]:
    """本文フォント。利用者が打つ名前も出すので広めに（JIS 第一水準まで）。"""
    s = _ranges(
        (0x0020, 0x007E), (0x00A1, 0x00FF), (0x2010, 0x2312), (0x2460, 0x24FF), (0x2500, 0x25FF),
        (0x2600, 0x266F), (0x2700, 0x27BF), (0x3000, 0x303F), (0x3041, 0x309F), (0x30A0, 0x30FF),
        (0xFF01, 0xFF9F),
    )
    s |= jis1_kanji()
    s |= {ord(c) for c in used}
    return s


def dg16_unicodes(used: set[str]) -> set[int]:
    """見出しフォント。小さく保つ（ASCII・かな・記号・ソースの文言だけ）。"""
    s = _ranges((0x0020, 0x007E), (0x3000, 0x303F), (0x3041, 0x309F), (0x30A0, 0x30FF), (0xFF01, 0xFF65), (0x2776, 0x277F))
    s |= {0x2605, 0x2606}
    s |= {ord(c) for c in used}
    return s


UNICODE_SETS = {"PM12": pm12_unicodes, "DG16": dg16_unicodes}


def unicode_arg(cps: set[int]) -> str:
    """ソート済み符号位置を 0020-007E,00A1 の形に畳む（pyftsubset の --unicodes= 形式）。"""
    parts: list[str] = []
    seq = sorted(cps)
    i = 0
    while i < len(seq):
        j = i
        while j + 1 < len(seq) and seq[j + 1] == seq[j] + 1:
            j += 1
        parts.append(f"{seq[i]:04X}" if i == j else f"{seq[i]:04X}-{seq[j]:04X}")
        i = j + 1
    return ",".join(parts)


def parse_unicode_arg(text: str) -> set[int]:
    out: set[int] = set()
    for part in text.split(","):
        if not part:
            continue
        a, _, b = part.partition("-")
        out.update(range(int(a, 16), int(b or a, 16) + 1))
    return out


def check_subset_fresh(used: set[str]) -> None:
    """ソースの文字列に、前回 --subset が要求しなかった字が増えていたら警告する（fontTools なしで判定できる範囲）。"""
    if not SUBSET_INFO.is_file():
        warn(f"{rel(SUBSET_INFO)} が無い。`python scripts/build.py --subset` を一度実行する")
        return
    info = json.loads(SUBSET_INFO.read_text(encoding="utf-8"))
    for f in FONTS:
        fam = f["family"]
        recorded = parse_unicode_arg(info.get("fonts", {}).get(fam, {}).get("requested", ""))
        new = sorted(c for c in UNICODE_SETS[fam](used) if c not in recorded)
        if new:
            shown = " ".join(f"{chr(c)}(U+{c:04X})" for c in new[:20]) + (" …" if len(new) > 20 else "")
            warn(f"{fam} の subset が古い（ソースの文字列に新しい字が {len(new)} 字）: {shown} → `python scripts/build.py --subset`")


def subset_fonts(used: set[str]) -> None:
    """tools/fonts/*.ttf → src/fonts/*-sub.woff2。fontTools（brotli 付き）が要る。"""
    try:
        from fontTools import subset  # 遅延 import。--subset 以外では fontTools が無くても動く
        from fontTools.ttLib import TTFont
    except ImportError as e:  # noqa: PERF203
        die(f"--subset には fontTools と brotli が要る（pip install fonttools brotli）: {e}")

    FONT_DIR.mkdir(parents=True, exist_ok=True)
    info: dict = {"_note": "scripts/build.py --subset が書く。手で編集しない。requested は要求した符号位置（元フォントに無い字も含む）", "fonts": {}}
    for f in FONTS:
        src = TOOLS_FONTS / f["ttf"]
        dst = FONT_DIR / f["woff2"]
        if not src.is_file():
            die(f"{rel(src)} が無い。配布元から TTF を取得して tools/fonts/ に置く（.gitignore 済み。src/fonts/README.md 参照）")
        want = UNICODE_SETS[f["family"]](used)
        cmap = TTFont(str(src)).getBestCmap()
        have = {c for c in want if c in cmap}
        missing_used = sorted(c for c in used if ord(c) in want and ord(c) not in cmap)
        missing_watch = [c for c in WATCH_CHARS if ord(c) not in cmap]
        args = [
            str(src),
            f"--output-file={dst}",
            f"--unicodes={unicode_arg(want)}",
            "--flavor=woff2",
            "--no-hinting",
            "--desubroutinize",
            "--layout-features=",  # シェルの --layout-features='' と同じ（空）
            "--drop-tables+=DSIG,FFTM",  # 署名と FontForge の時刻表は不要
            "--no-recalc-timestamp",  # head.modified を触らない → 同じ入力なら同じバイト列
            "--name-IDs+=13,14",  # ライセンス記述・URL の name レコードを残す
        ]
        subset.main(args)
        size = dst.stat().st_size
        print(
            f"{f['family']}: {rel(dst)} {size / 1024:.1f} KB (base64 {len(base64.b64encode(dst.read_bytes())) / 1024:.1f} KB)"
            f"  要求 {len(want)} 字 / 収録 {len(have)} 字 / 元に無い {len(want) - len(have)} 字"
        )
        if missing_watch:
            print(f"  {f['family']} に無い記号（game 側でフォールバックすること）: " + " ".join(f"{c}(U+{ord(c):04X})" for c in missing_watch))
        if missing_used:
            print(f"  ソースの文字列にあるが {f['family']} に無い字: " + " ".join(f"{c}(U+{ord(c):04X})" for c in missing_used))
        info["fonts"][f["family"]] = {
            "source": f["ttf"],
            "requested": unicode_arg(want),
            "requested_count": len(want),
            "in_font": len(have),
            "woff2_bytes": size,
            "missing_watch": "".join(missing_watch),
        }
    SUBSET_INFO.write_text(json.dumps(info, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- HTML 組み立て


def font_style(fonts: list[dict]) -> str:
    rules = []
    for f in fonts:
        b64 = base64.b64encode(f["data"]).decode("ascii")
        rules.append(
            f'@font-face{{font-family:"{f["family"]}";src:url(data:font/woff2;base64,{b64}) format("woff2");font-display:block}}'
        )
    lic = ["<!--", "同梱フォントのライセンス（subset 化は両ライセンスが許す改変の範囲。CSS の family 名は独自で、元のフォント名は名乗らない）"]
    for f in fonts:
        lic += ["", "=" * 72, f"{f['label']} — src/fonts/{f['woff2']} — LICENSES/{f['license']}", "=" * 72, f["license_text"].rstrip("\n")]
    lic.append("-->")
    return "<style>\n" + "\n".join(rules) + "\n</style>\n" + "\n".join(lic)


def css_block(sources: list[tuple[str, bytes]]) -> str:
    parts = ["<style>"]
    for name, data in sources:
        if name.endswith(".css"):
            parts.append(f"/* src/{name} */")
            parts.append(data.decode("utf-8").rstrip("\n"))
    parts.append("</style>")
    return "\n".join(parts)


def js_block(sources: list[tuple[str, bytes]]) -> str:
    parts = []
    for name, data in sources:
        if name.endswith(".js"):
            parts.append(f"<script>\n//# sourceURL=src/{name}\n{data.decode('utf-8').rstrip(chr(10))}\n</script>")
    return "\n".join(parts)


def dev_css_block(sources: list[tuple[str, bytes]]) -> str:
    return "\n".join(f'<link rel="stylesheet" href="src/{n}">' for n, _ in sources if n.endswith(".css"))


def dev_js_block(sources: list[tuple[str, bytes]], bid: str) -> str:
    parts = []
    for name, _ in sources:
        if name.endswith(".js"):
            parts.append(f'<script src="src/{name}"></script>')
            if name == "js/00_ns.js":
                # 00_ns.js の {{BUILD}} は置換されないので、直後にビルド ID を入れる
                parts.append(f"<script>if(window.NT)NT.BUILD='dev-{bid}';</script>")
    return "\n".join(parts)


def dev_csp(tpl: str) -> str:
    """dev.html では CSP の style-src / script-src に file: を足す。"""
    for directive, extra in DEV_CSP_EXTRA.items():
        key = directive + " "
        i = tpl.find(key)
        if i < 0:
            continue
        j = tpl.find(";", i)
        if j < 0:
            continue
        tpl = tpl[:j] + extra + tpl[j:]
    return tpl


def render(tpl: str, sources: list[tuple[str, bytes]], fonts: list[dict], bid: str, dev: bool) -> bytes:
    for name, data in sources:
        text = data.decode("utf-8")
        check_forbidden(f"src/{name}", text)
        check_inline_safe(name, text)
    check_forbidden(rel(TEMPLATE), tpl)
    if dev:
        html = dev_csp(tpl)
        html = html.replace("<!--@fonts-->", font_style(fonts))
        html = html.replace("<!--@css-->", dev_css_block(sources))
        html = html.replace("<!--@js-->", dev_js_block(sources, bid))
        html = html.replace(BUILD_MARK, f"dev-{bid}")
    else:
        html = tpl.replace("<!--@fonts-->", font_style(fonts))
        html = html.replace("<!--@css-->", css_block(sources))
        html = html.replace("<!--@js-->", js_block(sources))
        html = html.replace(BUILD_MARK, bid)
    check_forbidden("生成物", html)
    out = html.encode("utf-8")
    if len(out) > SIZE_FAIL:
        die(f"生成物が {len(out) / 1024:.1f} KB で上限 {SIZE_FAIL / 1024:.0f} KB を超えた")
    if len(out) > SIZE_WARN:
        warn(f"生成物が {len(out) / 1024:.1f} KB（{SIZE_WARN / 1024:.0f} KB 超）")
    return out


# ---------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--check", action="store_true", help="index.html と一致するか確かめるだけ（不一致は exit 1）")
    ap.add_argument("--dev", action="store_true", help="dev.html（src を直接参照）を書く")
    ap.add_argument("--subset", action="store_true", help="フォント subset を作り直してから組む（fontTools）")
    ap.add_argument("--allow-missing", action="store_true", help="未作成の src ファイルを警告だけで飛ばす")
    a = ap.parse_args(argv)

    used = used_chars()
    if a.subset:
        subset_fonts(used)
    else:
        check_subset_fresh(used)

    tpl = read_template()
    sources = load_sources(a.allow_missing)
    fonts = load_fonts()
    bid = build_id(TEMPLATE.read_bytes(), fonts, sources)

    font_bytes = sum(len(f["data"]) for f in fonts)
    out = render(tpl, sources, fonts, bid, dev=False)

    if a.check:
        if not OUT_HTML.is_file():
            die(f"{rel(OUT_HTML)} が無い。`python scripts/build.py` で生成してコミットする")
        if OUT_HTML.read_bytes() != out:
            die(f"{rel(OUT_HTML)} がソースと一致しない（build {bid}）。`python scripts/build.py` で作り直してコミットする")
        print(f"ok: {rel(OUT_HTML)} はソースと一致（{len(out) / 1024:.1f} KB, build {bid}）")
        return 0

    if a.dev:
        dev = render(tpl, sources, fonts, bid, dev=True)
        DEV_HTML.write_bytes(dev)
        print(f"{rel(DEV_HTML)}: {len(dev) / 1024:.1f} KB (build dev-{bid}) — file:// で開く。src/ の変更は再ビルドなしで反映")
        return 0

    OUT_HTML.write_bytes(out)
    n_css = sum(1 for n, _ in sources if n.endswith(".css"))
    n_js = sum(1 for n, _ in sources if n.endswith(".js"))
    print(
        f"{rel(OUT_HTML)}: {len(out) / 1024:.1f} KB (build {bid})"
        f"  [fonts {font_bytes / 1024:.1f} KB raw / {font_bytes * 4 / 3 / 1024:.1f} KB base64, css {n_css} files, js {n_js} files]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
