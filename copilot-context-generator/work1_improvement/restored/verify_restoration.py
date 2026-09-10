"""復元検証スクリプト.

オリジナル exe から抽出された marshal 化 code object と、
復元ソースをコンパイルした code object を再帰的に突合する。

比較項目（code object ごと、関数名でマッチング）:
- co_names / co_varnames / co_cellvars / co_freevars（集合）
- 非 code の co_consts（マルチセット、入れ子 code は名前だけ）
- co_argcount / co_kwonlyargcount / フラグ（generator 等）

使い方:
    python verify_restoration.py <base64ファイル> <復元ソース.py>
"""
import base64
import marshal
import sys
import types
from collections import Counter


def load_original(b64_path):
    with open(b64_path, "r", encoding="utf-8") as f:
        data = f.read()
    blob = base64.b64decode("".join(data.split()))
    return marshal.loads(blob)


def compile_restored(src_path):
    with open(src_path, "r", encoding="utf-8") as f:
        source = f.read()
    return compile(source, "box_copy_gui_direct_context_mode_fixed.pyw", "exec")


def const_key(const):
    if isinstance(const, types.CodeType):
        return f"<code {const.co_name}>"
    return repr(const)


def summarize(code):
    consts = Counter(const_key(c) for c in code.co_consts)
    return {
        "argcount": code.co_argcount,
        "kwonly": code.co_kwonlyargcount,
        "names": sorted(code.co_names),
        "varnames": sorted(code.co_varnames),
        "cellvars": sorted(code.co_cellvars),
        "freevars": sorted(code.co_freevars),
        "consts": consts,
        "is_generator": bool(code.co_flags & 0x20),
    }


def walk(code, prefix=""):
    """(qualified_name, code) を列挙。同名の兄弟には連番を付ける。"""
    yield prefix + code.co_name, code
    seen = Counter()
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            seen[const.co_name] += 1
            suffix = f"#{seen[const.co_name]}" if const.co_name in ("<genexpr>", "<lambda>", "<listcomp>", "<setcomp>") else ""
            yield from walk(const, prefix + code.co_name + "." + ("" if not suffix else ""))


def collect(code):
    result = {}
    order = []

    def rec(c, qual):
        counter = Counter()
        key = qual
        n = 1
        while key in result:
            n += 1
            key = f"{qual}#{n}"
        result[key] = c
        order.append(key)
        for const in c.co_consts:
            if isinstance(const, types.CodeType):
                rec(const, f"{qual}.{const.co_name}")

    rec(code, code.co_name)
    return result, order


def diff_code(name, a, b, problems):
    sa, sb = summarize(a), summarize(b)
    for field in ("argcount", "kwonly", "is_generator"):
        if sa[field] != sb[field]:
            problems.append(f"{name}: {field} 不一致 original={sa[field]} restored={sb[field]}")
    for field in ("names", "varnames", "cellvars", "freevars"):
        if set(sa[field]) != set(sb[field]):
            only_a = set(sa[field]) - set(sb[field])
            only_b = set(sb[field]) - set(sa[field])
            problems.append(f"{name}: {field} 不一致 original側のみ={sorted(only_a)} restored側のみ={sorted(only_b)}")
    if sa["consts"] != sb["consts"]:
        only_a = sa["consts"] - sb["consts"]
        only_b = sb["consts"] - sa["consts"]
        detail = []
        if only_a:
            detail.append(f"original側のみ={dict(only_a)}")
        if only_b:
            detail.append(f"restored側のみ={dict(only_b)}")
        problems.append(f"{name}: consts 不一致 " + " / ".join(detail))


def main():
    b64_path, src_path = sys.argv[1], sys.argv[2]
    original = load_original(b64_path)
    restored = compile_restored(src_path)

    orig_map, orig_order = collect(original)
    rest_map, _ = collect(restored)

    problems = []

    only_orig = set(orig_map) - set(rest_map)
    only_rest = set(rest_map) - set(orig_map)
    if only_orig:
        problems.append(f"original のみに存在する code object: {sorted(only_orig)}")
    if only_rest:
        problems.append(f"restored のみに存在する code object: {sorted(only_rest)}")

    for name in orig_order:
        if name in rest_map:
            diff_code(name, orig_map[name], rest_map[name], problems)

    # オペコード列の完全比較（CACHE を除く）
    import dis

    def ops(code):
        return [
            (i.opname, i.argrepr if not isinstance(i.argval, types.CodeType) else f"<code {i.argval.co_name}>")
            for i in dis.get_instructions(code)
            if i.opname != "CACHE"
        ]

    total_instr = 0
    for name in orig_order:
        if name not in rest_map:
            continue
        a, b = ops(orig_map[name]), ops(rest_map[name])
        total_instr += len(a)
        if a != b:
            first = next((idx, x, y) for idx, (x, y) in enumerate(zip(a, b)) if x != y) if len(a) == len(b) else None
            problems.append(f"{name}: オペコード列不一致 ({len(a)} vs {len(b)} 命令) first_diff={first}")

    print(f"original: {len(orig_map)} code objects / restored: {len(rest_map)} code objects / 総命令数: {total_instr}")
    if problems:
        print(f"\nNG: {len(problems)} 件の差異")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("OK: 全 code object の名前・変数・定数・オペコード列が完全一致")


if __name__ == "__main__":
    main()
