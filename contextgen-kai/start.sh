#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python ]; then
  printf '%s\n' '先に Python 3.12 で仮想環境を作成し、python -m pip install -e . を実行してください。' >&2
  exit 1
fi
exec .venv/bin/python -m contextgen_kai "$@"
